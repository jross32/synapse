"""Tests for the Capture inbox (ADR-0016 Phase R)."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from synapse_daemon.ai_context_memory import ai_context_path
from synapse_daemon.app import build_app
from synapse_daemon.projects import Project, create
from synapse_daemon.storage import Storage
from synapse_daemon.ws import EventBus


def _harness(tmp_path: Path) -> tuple[TestClient, Storage]:
    storage = Storage(tmp_path / "data")
    storage.open()
    storage.migrate()
    with storage.transaction() as conn:
        create(conn, Project(id="proj-1", name="Demo Project", path=str(tmp_path), launch_cmd="echo hi"))
    app = build_app(storage, EventBus())
    return TestClient(app, headers={"X-Synapse-Token": app.state.auth.local_token}), storage


def test_capture_to_backlog(tmp_path: Path) -> None:
    client, _ = _harness(tmp_path)
    res = client.post(
        "/api/v1/capture",
        json={"content": "Add a dark-mode toggle to settings", "destination": "backlog", "project_id": "proj-1"},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["destination"] == "backlog"
    assert "Demo Project" in body["message"]
    assert body["ref_id"]
    # It really landed in the project backlog.
    records = client.get("/api/v1/projects/proj-1/records").json()
    titles = [b["title"] for b in records["backlog"]]
    assert "Add a dark-mode toggle to settings" in titles


def test_capture_title_defaults_to_first_line(tmp_path: Path) -> None:
    client, _ = _harness(tmp_path)
    res = client.post(
        "/api/v1/capture",
        json={"content": "Fix the login bug\nIt 500s when the email has a +", "project_id": "proj-1"},
    )
    assert res.status_code == 200
    records = client.get("/api/v1/projects/proj-1/records").json()
    item = next(b for b in records["backlog"] if b["title"] == "Fix the login bug")
    assert "500s" in item["body_md"]  # full note kept in the body


def test_capture_to_ai_context_writes_file(tmp_path: Path) -> None:
    client, storage = _harness(tmp_path)
    res = client.post(
        "/api/v1/capture",
        json={"content": "Remember: the prod DB is read-only on weekends.", "destination": "ai_context", "project_id": "proj-1"},
    )
    assert res.status_code == 200, res.text
    assert res.json()["destination"] == "ai_context"
    path = ai_context_path(storage.data_dir, "proj-1")
    assert path.exists()
    assert "read-only on weekends" in path.read_text(encoding="utf-8")


def test_capture_empty_is_422(tmp_path: Path) -> None:
    client, _ = _harness(tmp_path)
    res = client.post("/api/v1/capture", json={"content": "   ", "project_id": "proj-1"})
    assert res.status_code == 422


def test_capture_unknown_project_is_404(tmp_path: Path) -> None:
    client, _ = _harness(tmp_path)
    res = client.post("/api/v1/capture", json={"content": "hi", "project_id": "ghost"})
    assert res.status_code == 404
