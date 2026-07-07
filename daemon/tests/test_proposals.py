"""Improvement proposals inbox (Plan 3 Phase 3f, ADR-0025)."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from synapse_daemon.app import build_app
from synapse_daemon.storage import Storage
from synapse_daemon.ws import EventBus


def _client(tmp_path: Path):
    s = Storage(tmp_path / "data")
    s.open()
    s.migrate()
    app = build_app(s, EventBus())
    return TestClient(app, headers={"X-Synapse-Token": app.state.auth.local_token})


def test_file_proposal_shows_in_inbox_then_approve(tmp_path: Path) -> None:
    client = _client(tmp_path)
    with client as c:
        filed = c.post(
            "/api/v1/review/proposals",
            json={
                "title": "Add a dark-mode toggle",
                "rationale_md": "Several users asked for it.",
                "source_runtime": "claude",
                "est_effort": "S",
                "est_token_cost": 20000,
            },
        )
        assert filed.status_code == 200, filed.text
        pid = filed.json()["id"]
        assert filed.json()["status"] == "open"

        inbox = c.get("/api/v1/review/inbox").json()
        assert any(p["id"] == pid for p in inbox["proposals"])

        approved = c.post(f"/api/v1/review/proposals/{pid}/approve", json={"note": "yes, do it"})
        assert approved.status_code == 200, approved.text
        assert approved.json()["status"] == "approved"

        # Resolved -> no longer in the open inbox.
        inbox2 = c.get("/api/v1/review/inbox").json()
        assert not any(p["id"] == pid for p in inbox2["proposals"])


def test_reject_proposal(tmp_path: Path) -> None:
    client = _client(tmp_path)
    with client as c:
        pid = c.post("/api/v1/review/proposals", json={"title": "Rewrite everything in Rust"}).json()["id"]
        rejected = c.post(f"/api/v1/review/proposals/{pid}/reject", json={"note": "not now"})
        assert rejected.status_code == 200, rejected.text
        assert rejected.json()["status"] == "rejected"


def test_proposal_needs_title(tmp_path: Path) -> None:
    client = _client(tmp_path)
    with client as c:
        assert c.post("/api/v1/review/proposals", json={"title": "   "}).status_code == 422


def test_approve_unknown_proposal_404(tmp_path: Path) -> None:
    client = _client(tmp_path)
    with client as c:
        assert c.post("/api/v1/review/proposals/nope/approve").status_code == 404
