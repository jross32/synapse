"""Measured staff activity must never trust a stale stored status."""
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from synapse_daemon import agent_squads, personalities
from synapse_daemon.projects import Project, create as create_project
from synapse_daemon.staff import link_work_item, seed_staff_foundation
from synapse_daemon.staff_execution import staff_execution_snapshot
from synapse_daemon.staff_operations import seed_staff_operations
from synapse_daemon.storage import Storage

NOW = datetime(2026, 10, 9, 17, 0, 0, tzinfo=timezone.utc)


@pytest.fixture()
def storage(tmp_path: Path):
    s = Storage(tmp_path / "data")
    s.open()
    s.migrate()
    with s.transaction() as c:
        agent_squads.seed_default_role_templates(c)
        personalities.seed_default_personalities(c)
        seed_staff_foundation(c)
        seed_staff_operations(c)
        create_project(c, Project(
            id="reselltogether", name="ResellTogether",
            path=str(tmp_path / "reselltogether"), launch_cmd="echo test",
        ))
    yield s
    s.close()


def assign(s: Storage, *, staff_id: str = "maya-growth") -> str:
    with s.transaction() as c:
        squad = agent_squads.create_squad(c, agent_squads.AgentSquadCreate(
            project_id="reselltogether", name="Maya execution test",
            lead_role_id="growth-director", max_concurrent=1,
        ))
        item = agent_squads.create_work_item(c, squad.id, agent_squads.AgentWorkItemCreate(
            title="Verify first user value", assigned_role_id="growth-director",
        ))
        link_work_item(c, staff_id, item.id)
    return item.id


def add_session(s: Storage, item_id: str, *,
                heartbeat: datetime | None, status: str = "active", ended: str | None = None):
    session_key = "pty-" + item_id
    with s.transaction() as c:
        agent_squads.set_work_item_session(
            c, item_id, status=agent_squads.AgentWorkItemStatus.RUNNING,
            pty_session_id=session_key, chosen_runtime="chatgpt_web", opened_in_tab=False,
        )
        c.execute(
            """INSERT INTO agent_sessions
               (id, project_id, runtime_id, agent_label, coder_thread_id, task, status,
                registered_at, last_heartbeat_at, ended_at, metadata_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            ("session-" + item_id, "reselltogether", "chatgpt_web", "Maya",
             session_key, "Verify first user value", status,
             (NOW - timedelta(minutes=10)).isoformat(),
             heartbeat.isoformat() if heartbeat else None, ended, "{}"),
        )


def test_no_items_does_not_fake_activity(storage):
    result = staff_execution_snapshot(storage.conn, "maya", now=NOW)
    assert result["observed_state"] == "not_started"
    assert result["counts"]["running_confirmed"] == 0
    assert result["work_items"] == []


def test_queued_assignment_is_not_running(storage):
    assign(storage)
    result = staff_execution_snapshot(storage.conn, "maya", now=NOW)
    assert result["observed_state"] == "queued"
    assert result["counts"]["queued"] == 1
    assert not result["work_items"][0]["is_live"]


def test_recent_confirmed_heartbeat_is_running(storage):
    item_id = assign(storage)
    add_session(storage, item_id, heartbeat=NOW - timedelta(seconds=45))
    result = staff_execution_snapshot(storage.conn, "maya", now=NOW)
    assert result["observed_state"] == "working_verified"
    assert result["work_items"][0]["session_status"] == "active"
    assert result["work_items"][0]["is_live"]


def test_stale_green_active_session_is_not_live(storage):
    item_id = assign(storage)
    add_session(storage, item_id, heartbeat=NOW - timedelta(hours=3))
    result = staff_execution_snapshot(storage.conn, "maya", now=NOW)
    assert result["observed_state"] == "reconciliation_needed"
    assert result["work_items"][0]["observed_state"] == "stale_or_disconnected"
    assert not result["work_items"][0]["is_live"]


def test_gone_session_is_not_running_even_with_fresh_heartbeat(storage):
    item_id = assign(storage)
    add_session(storage, item_id, heartbeat=NOW - timedelta(seconds=5),
                status="gone", ended=NOW.isoformat())
    result = staff_execution_snapshot(storage.conn, "maya", now=NOW)
    assert result["observed_state"] == "reconciliation_needed"


def test_running_without_session_is_stale(storage):
    item_id = assign(storage)
    with storage.transaction() as c:
        agent_squads.update_work_item_status(
            c, item_id, agent_squads.AgentWorkItemStatus.RUNNING
        )
    result = staff_execution_snapshot(storage.conn, "maya", now=NOW)
    assert result["observed_state"] == "reconciliation_needed"


def test_completion_requires_handoff_summary(storage):
    item_id = assign(storage)
    with storage.transaction() as c:
        agent_squads.update_work_item_status(
            c, item_id, agent_squads.AgentWorkItemStatus.COMPLETED
        )
    result = staff_execution_snapshot(storage.conn, "maya", now=NOW)
    assert result["observed_state"] == "proof_missing"
    with storage.transaction() as c:
        agent_squads.handoff_work_item(
            c, item_id, agent_squads.AgentWorkItemHandoffRequest(
                status=agent_squads.AgentWorkItemStatus.COMPLETED,
                summary_md="Verified 4/4 test account flow steps; evidence attached separately.",
            ),
        )
    result = staff_execution_snapshot(storage.conn, "maya", now=NOW)
    assert result["observed_state"] == "completed"
    assert result["counts"]["completed_with_handoff"] == 1


def test_staff_identity_isolation(storage):
    assign(storage)
    assert staff_execution_snapshot(storage.conn, "adrian", now=NOW)["observed_state"] == "not_started"
    assert staff_execution_snapshot(storage.conn, "maya", now=NOW)["counts"]["queued"] == 1


def test_future_heartbeat_and_limit_not_proof_of_liveness(storage):
    item_id = assign(storage)
    add_session(storage, item_id, heartbeat=NOW + timedelta(minutes=10))
    result = staff_execution_snapshot(storage.conn, "maya", now=NOW, limit=500)
    assert result["limit_applied"] == 100
    assert result["observed_state"] == "reconciliation_needed"


def test_execution_endpoint_is_truthful_and_read_only(storage):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from synapse_daemon.routes_staff import build_staff_router
    item = assign(storage)
    add_session(storage, item, heartbeat=NOW - timedelta(days=1))
    before = storage.conn.execute("SELECT COUNT(*) FROM staff_events").fetchone()[0]
    app = FastAPI()
    app.include_router(build_staff_router(storage))
    with TestClient(app) as client:
        result = client.get("/staff/maya/execution")
        assert result.status_code == 200
        body = result.json()
        assert body["observed_state"] == "reconciliation_needed"
        assert body["work_items"][0]["is_live"] is False
    assert storage.conn.execute("SELECT COUNT(*) FROM staff_events").fetchone()[0] == before


def test_blocked_session_surfaces_exact_reason(storage):
    item_id = assign(storage)
    with storage.transaction() as c:
        agent_squads.handoff_work_item(
            c, item_id, agent_squads.AgentWorkItemHandoffRequest(
                status=agent_squads.AgentWorkItemStatus.BLOCKED,
                summary_md="",
                blockers_md="Dedicated ChatGPT profile is not signed in.",
            ),
        )
    result = staff_execution_snapshot(storage.conn, "maya", now=NOW)
    assert result["observed_state"] == "blocked"
    assert result["work_items"][0]["blockers_md"] == "Dedicated ChatGPT profile is not signed in."
    assert not result["work_items"][0]["is_live"]
