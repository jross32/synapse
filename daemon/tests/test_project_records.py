"""Tests for per-project decision records, backlog, and versions (ADR-0011)."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from synapse_daemon.app import build_app
from synapse_daemon.projects import Project, create
from synapse_daemon.storage import Storage
from synapse_daemon.ws import EventBus


def _harness(tmp_path: Path) -> TestClient:
    storage = Storage(tmp_path / "data")
    storage.open()
    storage.migrate()
    with storage.transaction() as conn:
        create(
            conn,
            Project(
                id="demo-project",
                name="Demo Project",
                path=str(tmp_path),
                launch_cmd="echo hi",
            ),
        )
    app = build_app(storage, EventBus())
    return TestClient(app, headers={"X-Synapse-Token": app.state.auth.local_token})


# ── ADRs ─────────────────────────────────────────────────────────────────────


def test_quick_idea_then_promote_assigns_per_project_number(tmp_path: Path) -> None:
    client = _harness(tmp_path)

    # Quick idea: title alone is enough; defaults to status=idea, no number.
    res = client.post("/api/v1/projects/demo-project/adrs", json={"title": "Switch to X"})
    assert res.status_code == 201, res.text
    adr = res.json()
    assert adr["status"] == "idea"
    assert adr["number"] is None

    # Promote -> accepted, number 1, decided_at stamped.
    res = client.post(f"/api/v1/project-adrs/{adr['id']}/promote")
    assert res.status_code == 200, res.text
    promoted = res.json()
    assert promoted["status"] == "accepted"
    assert promoted["number"] == 1
    assert promoted["decided_at"] is not None

    # A second idea promoted gets the next per-project number.
    second = client.post("/api/v1/projects/demo-project/adrs", json={"title": "Adopt Y"}).json()
    promoted2 = client.post(f"/api/v1/project-adrs/{second['id']}/promote").json()
    assert promoted2["number"] == 2


def test_promote_is_idempotent_for_settled_adr(tmp_path: Path) -> None:
    client = _harness(tmp_path)
    adr = client.post("/api/v1/projects/demo-project/adrs", json={"title": "Decide"}).json()
    first = client.post(f"/api/v1/project-adrs/{adr['id']}/promote").json()
    again = client.post(f"/api/v1/project-adrs/{adr['id']}/promote").json()
    assert first["number"] == again["number"]
    assert again["status"] == "accepted"


def test_supersede_marks_old_adr_superseded(tmp_path: Path) -> None:
    client = _harness(tmp_path)
    old = client.post("/api/v1/projects/demo-project/adrs", json={"title": "Use SQLite"}).json()
    client.post(f"/api/v1/project-adrs/{old['id']}/promote")

    new = client.post(
        "/api/v1/projects/demo-project/adrs",
        json={"title": "Use Postgres", "supersedes_id": old["id"]},
    ).json()
    client.post(f"/api/v1/project-adrs/{new['id']}/promote")

    refreshed = client.get(f"/api/v1/project-adrs/{old['id']}").json()
    assert refreshed["status"] == "superseded"


def test_update_and_delete_adr(tmp_path: Path) -> None:
    client = _harness(tmp_path)
    adr = client.post("/api/v1/projects/demo-project/adrs", json={"title": "Draft"}).json()

    patched = client.patch(
        f"/api/v1/project-adrs/{adr['id']}",
        json={"status": "draft", "body_md": "Because reasons.", "tags": ["infra"]},
    ).json()
    assert patched["status"] == "draft"
    assert patched["body_md"] == "Because reasons."
    assert patched["tags"] == ["infra"]

    assert client.delete(f"/api/v1/project-adrs/{adr['id']}").status_code == 204
    assert client.get(f"/api/v1/project-adrs/{adr['id']}").status_code == 404


# ── Backlog ──────────────────────────────────────────────────────────────────


def test_backlog_done_sets_completed_at(tmp_path: Path) -> None:
    client = _harness(tmp_path)
    item = client.post(
        "/api/v1/projects/demo-project/backlog",
        json={"title": "Add dark mode", "priority": "high"},
    ).json()
    assert item["status"] == "todo"
    assert item["priority"] == "high"
    assert item["completed_at"] is None

    done = client.patch(
        f"/api/v1/project-backlog/{item['id']}", json={"status": "done"}
    ).json()
    assert done["completed_at"] is not None

    # Reopening clears completed_at.
    reopened = client.patch(
        f"/api/v1/project-backlog/{item['id']}", json={"status": "todo"}
    ).json()
    assert reopened["completed_at"] is None

    assert client.delete(f"/api/v1/project-backlog/{item['id']}").status_code == 204


# ── Versions ─────────────────────────────────────────────────────────────────


def test_version_history_crud(tmp_path: Path) -> None:
    client = _harness(tmp_path)
    res = client.post(
        "/api/v1/projects/demo-project/versions",
        json={"version": "0.1.0", "changes_md": "Initial release."},
    )
    assert res.status_code == 201, res.text
    version = res.json()
    assert version["version"] == "0.1.0"

    patched = client.patch(
        f"/api/v1/project-versions/{version['id']}", json={"changes_md": "Initial + fixes."}
    ).json()
    assert patched["changes_md"] == "Initial + fixes."

    assert client.delete(f"/api/v1/project-versions/{version['id']}").status_code == 204


# ── Bundle + validation + empty/malformed ────────────────────────────────────


def test_records_bundle_returns_all_three_planes(tmp_path: Path) -> None:
    client = _harness(tmp_path)
    client.post("/api/v1/projects/demo-project/adrs", json={"title": "An idea"})
    client.post("/api/v1/projects/demo-project/backlog", json={"title": "A task"})
    client.post("/api/v1/projects/demo-project/versions", json={"version": "0.1.0"})

    bundle = client.get("/api/v1/projects/demo-project/records").json()
    assert bundle["project_id"] == "demo-project"
    assert len(bundle["adrs"]) == 1
    assert len(bundle["backlog"]) == 1
    assert len(bundle["versions"]) == 1


def test_empty_project_records(tmp_path: Path) -> None:
    client = _harness(tmp_path)
    bundle = client.get("/api/v1/projects/demo-project/records").json()
    assert bundle["adrs"] == []
    assert bundle["backlog"] == []
    assert bundle["versions"] == []


def test_unknown_project_is_404(tmp_path: Path) -> None:
    client = _harness(tmp_path)
    assert client.get("/api/v1/projects/nope/records").status_code == 404
    assert (
        client.post("/api/v1/projects/nope/adrs", json={"title": "x"}).status_code == 404
    )


def test_malformed_adr_body_is_422(tmp_path: Path) -> None:
    client = _harness(tmp_path)
    # Missing required 'title'.
    assert client.post("/api/v1/projects/demo-project/adrs", json={}).status_code == 422
    # Invalid status enum.
    assert (
        client.post(
            "/api/v1/projects/demo-project/adrs",
            json={"title": "x", "status": "bogus"},
        ).status_code
        == 422
    )
