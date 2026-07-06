"""Squad concurrency cap (Plan 3 Phase 3, ADR-0025)."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from synapse_daemon import agent_squads as squads
from synapse_daemon.app import build_app
from synapse_daemon.projects import Project, create as create_project
from synapse_daemon.storage import Storage
from synapse_daemon.ws import EventBus


def _setup(tmp_path: Path, max_concurrent: int):
    s = Storage(tmp_path / "data")
    s.open()
    s.migrate()
    with s.transaction() as conn:
        squads.seed_default_role_templates(conn)
        create_project(conn, Project(id="p1", name="P1", path=str(tmp_path), launch_cmd="echo"))
        squad = squads.create_squad(
            conn,
            squads.AgentSquadCreate(project_id="p1", name="Sq", lead_role_id="planner", max_concurrent=max_concurrent),
        )
        i1 = squads.create_work_item(conn, squad.id, squads.AgentWorkItemCreate(title="a", assigned_role_id="tester"))
        i2 = squads.create_work_item(conn, squad.id, squads.AgentWorkItemCreate(title="b", assigned_role_id="reviewer"))
    return s, squad, i1, i2


def test_max_concurrent_roundtrip(tmp_path: Path) -> None:
    s, squad, _i1, _i2 = _setup(tmp_path, 3)
    assert squads.get_squad(s.conn, squad.id).max_concurrent == 3
    with s.transaction() as conn:
        squads.update_squad(conn, squad.id, squads.AgentSquadUpdate(max_concurrent=5))
    assert squads.get_squad(s.conn, squad.id).max_concurrent == 5


def test_count_running_work_items(tmp_path: Path) -> None:
    s, squad, i1, _i2 = _setup(tmp_path, 0)
    assert squads.count_running_work_items(s.conn, squad.id) == 0
    with s.transaction() as conn:
        conn.execute("UPDATE agent_work_items SET status = 'running' WHERE id = ?", (i1.id,))
    assert squads.count_running_work_items(s.conn, squad.id) == 1


def test_launch_blocked_when_cap_reached(tmp_path: Path) -> None:
    # cap = 1, one worker already running -> launching a second must 409 (no spawn).
    s, squad, i1, i2 = _setup(tmp_path, 1)
    with s.transaction() as conn:
        conn.execute("UPDATE agent_work_items SET status = 'running' WHERE id = ?", (i1.id,))
    app = build_app(s, EventBus())
    client = TestClient(app, headers={"X-Synapse-Token": app.state.auth.local_token})
    with client as c:
        blocked = c.post(f"/api/v1/agent-work-items/{i2.id}/launch")
        assert blocked.status_code == 409, blocked.text
        assert "cap reached" in blocked.text.lower()
