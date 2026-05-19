"""Tests for snapshot / restore (Contract #28 · v0.1.10.5)."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from synapse_daemon.app import build_app
from synapse_daemon.projects import Project, create, get, list_projects
from synapse_daemon.secrets import EnvVar
from synapse_daemon.snapshot import SNAPSHOT_FORMAT_VERSION
from synapse_daemon.storage import Storage
from synapse_daemon.ws import EventBus


def _harness(tmp_path: Path, *, sub: str = "data"):
    storage = Storage(tmp_path / sub)
    storage.open()
    storage.migrate()
    app = build_app(storage, EventBus())
    client = TestClient(app, headers={"X-Synapse-Token": app.state.auth.local_token})
    return client, storage


def _seed(storage: Storage, project: Project) -> None:
    with storage.transaction() as conn:
        create(conn, project)


def test_export_returns_registered_projects(tmp_path: Path) -> None:
    client, storage = _harness(tmp_path)
    _seed(storage, Project(id="alpha", name="Alpha", path="C:/a", launch_cmd="run a"))
    _seed(storage, Project(id="beta", name="Beta", path="C:/b", launch_cmd="run b"))
    with client as c:
        res = c.get("/api/v1/snapshot")
        assert res.status_code == 200
        body = res.json()
        assert body["format_version"] == SNAPSHOT_FORMAT_VERSION
        assert {p["id"] for p in body["projects"]} == {"alpha", "beta"}


def test_restore_round_trip_into_fresh_registry(tmp_path: Path) -> None:
    # Source daemon with two projects.
    src_client, src = _harness(tmp_path, sub="src")
    _seed(src, Project(id="alpha", name="Alpha", path="C:/a", launch_cmd="run a"))
    _seed(src, Project(id="beta", name="Beta", path="C:/b", launch_cmd="run b"))
    with src_client as c:
        snapshot = c.get("/api/v1/snapshot").json()

    # Fresh daemon — empty registry — restores the snapshot.
    dst_client, dst = _harness(tmp_path, sub="dst")
    with dst_client as c:
        res = c.post("/api/v1/restore", json=snapshot)
        assert res.status_code == 200
        report = res.json()
        assert report["projects_created"] == 2
        assert report["projects_updated"] == 0

    assert {p.id for p in list_projects(dst.conn)} == {"alpha", "beta"}


def test_restore_is_idempotent_merge(tmp_path: Path) -> None:
    client, storage = _harness(tmp_path)
    _seed(storage, Project(id="alpha", name="Alpha", path="C:/a", launch_cmd="run a"))
    with client as c:
        snapshot = c.get("/api/v1/snapshot").json()
        # Restoring its own snapshot updates in place — never duplicates.
        report = c.post("/api/v1/restore", json=snapshot).json()
        assert report["projects_created"] == 0
        assert report["projects_updated"] == 1

    assert len(list_projects(storage.conn)) == 1


def test_restore_rejects_incompatible_format(tmp_path: Path) -> None:
    client, _ = _harness(tmp_path)
    bad = {
        "synapse_version": "0.1.10.5",
        "format_version": SNAPSHOT_FORMAT_VERSION + 99,
        "schema_migration": 1,
        "projects": [],
    }
    with client as c:
        res = c.post("/api/v1/restore", json=bad)
        assert res.status_code == 422
        assert res.json()["code"] == "snapshot.invalid"


def test_restore_blanks_secret_values_and_reports_them(tmp_path: Path) -> None:
    src_client, src = _harness(tmp_path, sub="src")
    _seed(
        src,
        Project(
            id="vault",
            name="Vault",
            path="C:/v",
            launch_cmd="run",
            env=[EnvVar(key="API_KEY", value="super-secret", secret=True)],
        ),
    )
    with src_client as c:
        snapshot = c.get("/api/v1/snapshot").json()

    dst_client, dst = _harness(tmp_path, sub="dst")
    with dst_client as c:
        report = c.post("/api/v1/restore", json=snapshot).json()

    # The secret key is flagged for re-entry...
    assert {"project_id": "vault", "key": "API_KEY"} in report["secrets_needing_reentry"]
    # ...and the restored project never received the real value.
    restored = get(dst.conn, "vault")
    api_key = next(e for e in restored.env if e.key == "API_KEY")
    assert api_key.value != "super-secret"


def test_restored_project_status_is_reset_to_idle(tmp_path: Path) -> None:
    """A project exported while 'launched' restores as idle — nothing runs yet."""

    src_client, src = _harness(tmp_path, sub="src")
    from synapse_daemon.models import EntityStatus
    from synapse_daemon.projects import set_status

    _seed(src, Project(id="srv", name="Server", path="C:/s", launch_cmd="run"))
    with src.transaction() as conn:
        set_status(conn, "srv", status=EntityStatus.LAUNCHED)
    with src_client as c:
        snapshot = c.get("/api/v1/snapshot").json()

    dst_client, dst = _harness(tmp_path, sub="dst")
    with dst_client as c:
        c.post("/api/v1/restore", json=snapshot)

    assert get(dst.conn, "srv").status == EntityStatus.IDLE
