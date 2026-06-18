"""Contracts #1, #2, #7 — REST endpoints for the project registry."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from synapse_daemon.app import build_app
from synapse_daemon.process_manager import ProcessManager
from synapse_daemon.projects import Project, create
from synapse_daemon.storage import Storage
from synapse_daemon.ws import EventBus

LONG_RUNNING_CMD = f'{sys.executable} -c "import time; time.sleep(60)"'


def _harness(tmp_path: Path):
    storage = Storage(tmp_path / "data")
    storage.open()
    storage.migrate()
    bus = EventBus()
    pm = ProcessManager(storage, bus)
    app = build_app(storage, bus, process_manager=pm)
    client = TestClient(app, headers={"X-Synapse-Token": app.state.auth.local_token})
    return client, storage, bus, pm


def _seed_probe(storage: Storage, tmp_path: Path) -> str:
    project_path = tmp_path / "probe-project"
    project_path.mkdir()
    with storage.transaction() as conn:
        create(conn, Project(
            id="probe",
            name="Probe",
            path=str(project_path),
            launch_cmd=LONG_RUNNING_CMD,
        ))
    return str(project_path)


def test_list_returns_empty_array(tmp_path: Path) -> None:
    client, storage, *_ = _harness(tmp_path)
    try:
        with client as c:
            res = c.get("/api/v1/projects")
            assert res.status_code == 200
            assert res.json() == {"projects": []}
    finally:
        storage.close()


def test_list_returns_seeded_project(tmp_path: Path) -> None:
    client, storage, *_ = _harness(tmp_path)
    try:
        _seed_probe(storage, tmp_path)
        with client as c:
            res = c.get("/api/v1/projects")
            body = res.json()
            assert len(body["projects"]) == 1
            assert body["projects"][0]["id"] == "probe"
            assert body["projects"][0]["status"] == "idle"
    finally:
        storage.close()


def test_get_one_returns_404_on_missing(tmp_path: Path) -> None:
    client, storage, *_ = _harness(tmp_path)
    try:
        with client as c:
            res = c.get("/api/v1/projects/missing")
            assert res.status_code == 404
            assert res.json()["code"] == "project.not_found"
    finally:
        storage.close()


def test_patch_renames_project(tmp_path: Path) -> None:
    client, storage, *_ = _harness(tmp_path)
    try:
        _seed_probe(storage, tmp_path)
        with client as c:
            res = c.patch("/api/v1/projects/probe", json={"name": "Probe v2"})
            assert res.status_code == 200
            assert res.json()["name"] == "Probe v2"
    finally:
        storage.close()


def test_patch_empty_body_returns_invalid(tmp_path: Path) -> None:
    client, storage, *_ = _harness(tmp_path)
    try:
        _seed_probe(storage, tmp_path)
        with client as c:
            res = c.patch("/api/v1/projects/probe", json={})
            assert res.status_code == 422
            assert res.json()["code"] == "project.invalid"
    finally:
        storage.close()


def test_launch_then_stop_full_round_trip(tmp_path: Path) -> None:
    client, storage, bus, pm = _harness(tmp_path)
    try:
        _seed_probe(storage, tmp_path)
        with client as c:
            launch_res = c.post("/api/v1/projects/probe/launch", json={"source": "desktop"})
            assert launch_res.status_code == 200
            assert launch_res.json()["status"] == "launched"

            stop_res = c.post("/api/v1/projects/probe/stop", json={"source": "desktop"})
            assert stop_res.status_code == 200
            assert stop_res.json()["status"] == "stopped"
    finally:
        pm.shutdown()
        storage.close()


def test_create_via_post_returns_201(tmp_path: Path) -> None:
    client, storage, *_ = _harness(tmp_path)
    try:
        project_path = tmp_path / "new-app"
        project_path.mkdir()
        payload = {
            "id": "new-app",
            "name": "New App",
            "path": str(project_path),
            "launch_cmd": "python -V",
        }
        with client as c:
            res = c.post("/api/v1/projects", json=payload)
            assert res.status_code == 201
            assert res.json()["id"] == "new-app"
    finally:
        storage.close()


def test_create_duplicate_returns_conflict(tmp_path: Path) -> None:
    client, storage, *_ = _harness(tmp_path)
    try:
        _seed_probe(storage, tmp_path)
        with client as c:
            payload = {
                "id": "probe",
                "name": "Duplicate",
                "path": str(tmp_path),
                "launch_cmd": "x",
            }
            res = c.post("/api/v1/projects", json=payload)
            assert res.status_code == 409
            assert res.json()["code"] == "project.conflict"
    finally:
        storage.close()


def test_delete_returns_204(tmp_path: Path) -> None:
    client, storage, *_ = _harness(tmp_path)
    try:
        _seed_probe(storage, tmp_path)
        with client as c:
            res = c.delete("/api/v1/projects/probe")
            assert res.status_code == 204
            # And the project is gone.
            get_res = c.get("/api/v1/projects/probe")
            assert get_res.status_code == 404
    finally:
        storage.close()


# ── v0.1.36 A5: GET /projects/{id}/disk-usage ──────────────────────


def test_disk_usage_returns_byte_count(tmp_path: Path) -> None:
    """The route walks the project's path and returns total bytes."""

    from synapse_daemon.routes_projects import _disk_cache

    _disk_cache.clear()
    client, storage, *_ = _harness(tmp_path)
    try:
        # _seed_probe always uses tmp_path/probe-project as the project's
        # path; populate THAT directory with known contents.
        _seed_probe(storage, tmp_path)
        project_dir = tmp_path / "probe-project"
        (project_dir / "a.txt").write_bytes(b"x" * 100)
        (project_dir / "b.txt").write_bytes(b"y" * 200)
        nested = project_dir / "nested"
        nested.mkdir()
        (nested / "c.txt").write_bytes(b"z" * 300)
        with client as c:
            res = c.get("/api/v1/projects/probe/disk-usage")
            assert res.status_code == 200, res.text
            body = res.json()
            assert body["bytes"] == 600
            assert body["file_count"] == 3
            assert body["truncated"] is False
            assert body["cached"] is False
    finally:
        storage.close()


def test_disk_usage_is_cached(tmp_path: Path) -> None:
    """A second call within the TTL is served from cache."""

    from synapse_daemon.routes_projects import _disk_cache

    _disk_cache.clear()
    client, storage, *_ = _harness(tmp_path)
    try:
        _seed_probe(storage, tmp_path)
        (tmp_path / "probe-project" / "a.txt").write_bytes(b"x" * 42)
        with client as c:
            first = c.get("/api/v1/projects/probe/disk-usage").json()
            second = c.get("/api/v1/projects/probe/disk-usage").json()
            assert first["bytes"] == 42
            assert second["bytes"] == 42
            assert first["cached"] is False
            assert second["cached"] is True
    finally:
        storage.close()


def test_disk_usage_unknown_project_404(tmp_path: Path) -> None:
    client, storage, *_ = _harness(tmp_path)
    try:
        with client as c:
            res = c.get("/api/v1/projects/never-heard-of/disk-usage")
            assert res.status_code == 404
    finally:
        storage.close()
