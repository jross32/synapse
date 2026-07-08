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


def test_list_and_get_proposals_with_status_filter(tmp_path: Path) -> None:
    client = _client(tmp_path)
    with client as c:
        p_open = c.post("/api/v1/review/proposals", json={"title": "Keep this open"}).json()["id"]
        p_rej = c.post("/api/v1/review/proposals", json={"title": "Reject this"}).json()["id"]
        c.post(f"/api/v1/review/proposals/{p_rej}/reject", json={"note": "no"})

        assert {p["id"] for p in c.get("/api/v1/review/proposals").json()} == {p_open, p_rej}
        rejected = c.get("/api/v1/review/proposals?status=rejected").json()
        assert [p["id"] for p in rejected] == [p_rej]

        one = c.get(f"/api/v1/review/proposals/{p_open}").json()
        assert one["id"] == p_open and one["status"] == "open"
        assert c.get("/api/v1/review/proposals/nope").status_code == 404


def test_promote_project_proposal_creates_backlog_item(tmp_path: Path) -> None:
    from synapse_daemon import project_records
    from synapse_daemon.projects import Project, create as create_project

    s = Storage(tmp_path / "data")
    s.open()
    s.migrate()
    with s.transaction() as conn:
        create_project(conn, Project(id="proj1", name="Proj", path="/tmp", launch_cmd="echo hi"))
    app = build_app(s, EventBus())
    with TestClient(app, headers={"X-Synapse-Token": app.state.auth.local_token}) as c:
        pid = c.post(
            "/api/v1/review/proposals",
            json={"title": "Add dark mode", "rationale_md": "Users want it", "project_id": "proj1"},
        ).json()["id"]

        promoted = c.post(f"/api/v1/review/proposals/{pid}/promote")
        assert promoted.status_code == 200, promoted.text
        body = promoted.json()
        assert body["proposal"]["status"] == "approved"
        assert body["backlog_item"]["title"] == "Add dark mode"
        assert body["backlog_item"]["project_id"] == "proj1"
        assert "proposal" in body["backlog_item"]["body_md"].lower()

    # The backlog item is persisted in the project's backlog.
    items = project_records.list_backlog(s.conn, "proj1")
    assert any(i.title == "Add dark mode" for i in items)


def test_promote_synapse_wide_proposal_is_rejected(tmp_path: Path) -> None:
    client = _client(tmp_path)
    with client as c:
        # No project_id -> Synapse-wide proposal -> cannot promote to a project backlog.
        pid = c.post("/api/v1/review/proposals", json={"title": "Global idea"}).json()["id"]
        assert c.post(f"/api/v1/review/proposals/{pid}/promote").status_code >= 400
