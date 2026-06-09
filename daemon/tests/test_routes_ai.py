"""Tests for the AI-facing context endpoint (v0.1.29 · ADR-0002 Phase B)."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from synapse_daemon.app import build_app
from synapse_daemon.projects import Project, create
from synapse_daemon.storage import Storage
from synapse_daemon.ws import EventBus


def _harness(tmp_path: Path):
    storage = Storage(tmp_path / "data")
    storage.open()
    storage.migrate()
    with storage.transaction() as conn:
        create(
            conn,
            Project(
                id="demo",
                name="Demo",
                path=str(tmp_path),
                launch_cmd="echo hi",
            ),
        )
    app = build_app(storage, EventBus())
    client = TestClient(app, headers={"X-Synapse-Token": app.state.auth.local_token})
    return client


def test_ai_context_returns_versioned_digest(tmp_path: Path) -> None:
    client = _harness(tmp_path)
    with client as c:
        res = c.get("/api/v1/ai/context")
        assert res.status_code == 200
        body = res.json()
        assert body["schema"] == "synapse.ai.context/v1"
        # The demo project is in there.
        ids = [p["id"] for p in body["projects"]]
        assert "demo" in ids
        # Endpoints list is non-empty -- this is the "how do I do X" pointer
        # for AI sessions.
        assert any(e["path"] == "/api/v1/projects" for e in body["endpoints_for_ai"])


def test_ai_context_requires_auth(tmp_path: Path) -> None:
    storage = Storage(tmp_path / "data")
    storage.open()
    storage.migrate()
    app = build_app(storage, EventBus())
    unauthed = TestClient(app)
    assert unauthed.get("/api/v1/ai/context").status_code == 401
