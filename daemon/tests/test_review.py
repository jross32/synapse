"""Tests for the Needs-Review / approval inbox (ADR-0016 Phase R)."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from synapse_daemon import agent_squads as squads
from synapse_daemon.agent_squads import (
    AgentSquadCreate,
    AgentWorkItemCreate,
    AgentWorkItemHandoffRequest,
    AgentWorkItemStatus,
)
from synapse_daemon.app import build_app
from synapse_daemon.projects import Project, create
from synapse_daemon.storage import Storage
from synapse_daemon.ws import EventBus


def _harness(tmp_path: Path) -> tuple[TestClient, dict]:
    storage = Storage(tmp_path / "data")
    storage.open()
    storage.migrate()
    ids: dict = {}
    with storage.transaction() as conn:
        create(conn, Project(id="proj-1", name="Demo Project", path=str(tmp_path), launch_cmd="echo hi"))
        squad = squads.create_squad(conn, AgentSquadCreate(project_id="proj-1", name="Build Crew", lead_role_id=None))
        ids["squad"] = squad.id
        # A handoff item (ready for review)...
        handoff = squads.create_work_item(conn, squad.id, AgentWorkItemCreate(title="Add login form"))
        squads.handoff_work_item(
            conn,
            handoff.id,
            AgentWorkItemHandoffRequest(summary_md="Form built, needs your sign-off", files_touched=["login.tsx"]),
        )
        ids["handoff"] = handoff.id
        # ...a blocked item (AI is stuck)...
        blocked = squads.create_work_item(conn, squad.id, AgentWorkItemCreate(title="Wire payments"))
        squads.update_work_item_status(conn, blocked.id, AgentWorkItemStatus.BLOCKED)
        ids["blocked"] = blocked.id
        # ...and a queued item that should NOT appear.
        queued = squads.create_work_item(conn, squad.id, AgentWorkItemCreate(title="Later task"))
        ids["queued"] = queued.id
    app = build_app(storage, EventBus())
    return TestClient(app, headers={"X-Synapse-Token": app.state.auth.local_token}), ids


def test_inbox_aggregates_handoff_and_blocked(tmp_path: Path) -> None:
    client, ids = _harness(tmp_path)
    res = client.get("/api/v1/review/inbox")
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["count"] == 2
    by_id = {i["id"]: i for i in data["items"]}
    assert ids["queued"] not in by_id  # queued items aren't "needs review"
    assert by_id[ids["handoff"]]["kind"] == "handoff"
    assert by_id[ids["handoff"]]["project_name"] == "Demo Project"
    assert by_id[ids["handoff"]]["squad_name"] == "Build Crew"
    assert by_id[ids["handoff"]]["files_touched"] == ["login.tsx"]
    assert by_id[ids["blocked"]]["kind"] == "blocked"


def test_approve_clears_item(tmp_path: Path) -> None:
    client, ids = _harness(tmp_path)
    res = client.post(f"/api/v1/review/items/{ids['handoff']}/approve")
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "completed"
    remaining = {i["id"] for i in client.get("/api/v1/review/inbox").json()["items"]}
    assert ids["handoff"] not in remaining
    assert ids["blocked"] in remaining  # the other one stays


def test_revise_requeues_with_feedback(tmp_path: Path) -> None:
    client, ids = _harness(tmp_path)
    res = client.post(f"/api/v1/review/items/{ids['handoff']}/revise", json={"note": "Use OAuth, not a password form."})
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "queued"
    assert "Use OAuth" in res.json()["instructions_md"]  # feedback reaches the AI
    # No longer in the review queue.
    assert ids["handoff"] not in {i["id"] for i in client.get("/api/v1/review/inbox").json()["items"]}


def test_reject_blocks_with_reason(tmp_path: Path) -> None:
    client, ids = _harness(tmp_path)
    res = client.post(f"/api/v1/review/items/{ids['handoff']}/reject", json={"note": "Out of scope for now."})
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "blocked"
    assert "Out of scope" in res.json()["blockers_md"]


def test_unknown_item_is_404(tmp_path: Path) -> None:
    client, _ = _harness(tmp_path)
    assert client.post("/api/v1/review/items/nope/approve").status_code == 404


def test_empty_inbox(tmp_path: Path) -> None:
    storage = Storage(tmp_path / "empty")
    storage.open()
    storage.migrate()
    app = build_app(storage, EventBus())
    client = TestClient(app, headers={"X-Synapse-Token": app.state.auth.local_token})
    res = client.get("/api/v1/review/inbox")
    assert res.status_code == 200
    assert res.json() == {"items": [], "count": 0}
