"""Tests for the discovery REST endpoints (v0.1.8.5)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from synapse_daemon.app import build_app
from synapse_daemon.process_manager import ProcessManager
from synapse_daemon.projects import Project, create
from synapse_daemon.storage import Storage
from synapse_daemon.ws import EventBus


def _harness(tmp_path: Path):
    storage = Storage(tmp_path / "data")
    storage.open()
    storage.migrate()
    bus = EventBus()
    pm = ProcessManager(storage, bus)
    app = build_app(storage, bus, process_manager=pm)
    return TestClient(app), storage


def _mk_project_dir(root: Path, name: str, files: dict[str, str]) -> Path:
    d = root / name
    d.mkdir(parents=True)
    for rel, content in files.items():
        (d / rel).write_text(content, encoding="utf-8")
    return d


def test_scan_finds_projects(tmp_path: Path) -> None:
    client, storage = _harness(tmp_path)
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    _mk_project_dir(workspace, "node-app", {"package.json": json.dumps({"scripts": {"dev": "vite"}})})
    _mk_project_dir(workspace, "py-app", {"main.py": "pass"})
    try:
        with client as c:
            res = c.get(f"/api/v1/discovery/scan?root={workspace}&depth=1")
            assert res.status_code == 200
            body = res.json()
            assert body["count"] == 2
            stacks = {p["stack"] for p in body["projects"]}
            assert {"node", "python"} == stacks
    finally:
        storage.close()


def test_scan_flags_already_registered(tmp_path: Path) -> None:
    client, storage = _harness(tmp_path)
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    node_dir = _mk_project_dir(workspace, "node-app", {"package.json": json.dumps({"scripts": {"dev": "x"}})})
    # Register it first.
    with storage.transaction() as conn:
        create(conn, Project(id="node-app", name="Node App", path=str(node_dir), launch_cmd="npm run dev"))
    try:
        with client as c:
            body = c.get(f"/api/v1/discovery/scan?root={workspace}&depth=1").json()
            hit = next(p for p in body["projects"] if p["stack"] == "node")
            assert hit["already_registered"] is True
    finally:
        storage.close()


def test_scan_bad_root_returns_invalid(tmp_path: Path) -> None:
    client, storage = _harness(tmp_path)
    try:
        with client as c:
            res = c.get("/api/v1/discovery/scan?root=Z:/definitely/not/here")
            assert res.status_code == 422
            assert res.json()["code"] == "discovery.invalid"
    finally:
        storage.close()


def test_import_creates_discovered_projects(tmp_path: Path) -> None:
    client, storage = _harness(tmp_path)
    try:
        with client as c:
            payload = {
                "projects": [
                    {"id": "imported-one", "name": "Imported One", "path": "C:/x/one",
                     "launch_cmd": "npm run dev", "tags": ["scanned"]},
                    {"id": "imported-two", "name": "Imported Two", "path": "C:/x/two",
                     "launch_cmd": "cargo run"},
                ]
            }
            res = c.post("/api/v1/discovery/import", json=payload)
            assert res.status_code == 200
            report = res.json()
            assert set(report["imported"]) == {"imported-one", "imported-two"}

            # Both now appear in the project list, flagged discovered.
            projects = c.get("/api/v1/projects").json()["projects"]
            by_id = {p["id"]: p for p in projects}
            assert by_id["imported-one"]["discovered"] is True
            assert by_id["imported-one"]["tags"] == ["scanned"]
    finally:
        storage.close()


def test_import_resolves_id_collision(tmp_path: Path) -> None:
    client, storage = _harness(tmp_path)
    with storage.transaction() as conn:
        create(conn, Project(id="dup", name="Existing", path="C:/x", launch_cmd="x"))
    try:
        with client as c:
            res = c.post("/api/v1/discovery/import", json={
                "projects": [{"id": "dup", "name": "New Dup", "path": "C:/y", "launch_cmd": "y"}]
            })
            report = res.json()
            # The collision is resolved by suffixing, not skipped.
            assert report["imported"] == ["dup-2"]
    finally:
        storage.close()
