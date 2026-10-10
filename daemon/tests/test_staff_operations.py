from __future__ import annotations

from pathlib import Path

import pytest

from synapse_daemon import agent_squads, personalities
from synapse_daemon.errors import SynapseError
from synapse_daemon.projects import Project, create as create_project
from synapse_daemon.staff import seed_staff_foundation, get_staff, link_work_item
from synapse_daemon.staff_operations import (
    StaffKpiUpdate,
    StaffPermissionCreate,
    assert_project_work_allowed,
    enforce_launch_authority,
    list_channels,
    list_kpis,
    list_responsibilities,
    list_triggers,
    route_task,
    seed_staff_operations,
    team_briefing,
    update_kpi,
    upsert_permission,
)
from synapse_daemon.storage import Storage


def _storage(tmp_path: Path) -> Storage:
    storage = Storage(tmp_path / "data")
    storage.open()
    storage.migrate()
    with storage.transaction() as conn:
        agent_squads.seed_default_role_templates(conn)
        personalities.seed_default_personalities(conn)
        seed_staff_foundation(conn)
        seed_staff_operations(conn)
        create_project(
            conn,
            Project(
                id="demo-project",
                name="Demo",
                path=str(tmp_path / "demo"),
                launch_cmd="echo hi",
            ),
        )
    return storage


def test_advanced_seed_is_truthful_and_complete(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    try:
        for handle in ("maya", "adrian", "sofia", "marcus", "jordan", "riley"):
            member = get_staff(storage.conn, handle)
            assert list_responsibilities(storage.conn, member.id)
            kpis = list_kpis(storage.conn, member.id)
            assert kpis
            assert all(kpi.status == "unknown" for kpi in kpis)
            assert all(kpi.current_value is None for kpi in kpis)
            assert all(kpi.source == "not connected" for kpi in kpis)
            triggers = list_triggers(storage.conn, member.id)
            assert triggers
            assert all(trigger.enabled is False for trigger in triggers)
            channels = {item.channel: item.status for item in list_channels(storage.conn, member.id)}
            assert channels["synapse"] == "connected"
            assert channels["whatsapp"] == "disconnected"
            assert channels["email"] == "disconnected"
    finally:
        storage.close()


@pytest.mark.parametrize(
    ("task", "expected"),
    [
        ("How do we make more money with pricing and conversion?", "maya"),
        ("Review cash, expenses, margin, and bookkeeping", "adrian"),
        ("Build a launch campaign and content plan", "sofia"),
        ("Fix this app onboarding bug and verify the UX", "marcus"),
        ("Prepare a client proposal and follow-up", "jordan"),
        ("Research competitors and compare the market", "riley"),
    ],
)
def test_intent_router_selects_domain_owner(
    tmp_path: Path, task: str, expected: str
) -> None:
    storage = _storage(tmp_path)
    try:
        result = route_task(storage.conn, task)
        assert result.selected.handle == expected
        assert result.selected.score > 0
    finally:
        storage.close()


def test_explicit_handle_beats_automatic_routing(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    try:
        result = route_task(
            storage.conn,
            "@riley, research pricing and then compare competitors for me",
        )
        assert result.explicit is True
        assert result.selected.handle == "riley"
        assert result.selected.score == 1000
    finally:
        storage.close()


def test_project_permission_can_fail_closed(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    try:
        with storage.transaction() as conn:
            maya = get_staff(conn, "maya")
            upsert_permission(
                conn,
                maya.id,
                StaffPermissionCreate(
                    scope_type="project",
                    scope_id="demo-project",
                    capability="work",
                    decision="deny",
                    reason="Regression fixture.",
                ),
            )
            with pytest.raises(SynapseError):
                assert_project_work_allowed(conn, maya, "demo-project")
    finally:
        storage.close()


def _linked_work_item(storage: Storage, handle: str) -> str:
    with storage.transaction() as conn:
        member = get_staff(conn, handle)
        squad = agent_squads.create_squad(
            conn,
            agent_squads.AgentSquadCreate(
                project_id="demo-project",
                name=f"{handle} test",
                lead_role_id=member.role_template_id,
            ),
        )
        item = agent_squads.create_work_item(
            conn,
            squad.id,
            agent_squads.AgentWorkItemCreate(
                title="Authority fixture",
                assigned_role_id=member.role_template_id,
                personality_id=member.personality_id,
            ),
        )
        link_work_item(conn, member.id, item.id)
        return item.id


def test_advice_only_staff_cannot_escalate_to_workspace(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    try:
        item_id = _linked_work_item(storage, "adrian")
        with storage.transaction() as conn:
            member = enforce_launch_authority(
                conn, item_id, agent_squads.AgentExecutionAuthority.OBSERVE
            )
            assert member is not None and member.handle == "adrian"
            with pytest.raises(SynapseError):
                enforce_launch_authority(
                    conn, item_id, agent_squads.AgentExecutionAuthority.WORKSPACE
                )
    finally:
        storage.close()


def test_no_staff_assignment_can_receive_full_machine_authority(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    try:
        item_id = _linked_work_item(storage, "marcus")
        with storage.transaction() as conn:
            assert enforce_launch_authority(
                conn, item_id, agent_squads.AgentExecutionAuthority.WORKSPACE
            )
            with pytest.raises(SynapseError):
                enforce_launch_authority(
                    conn, item_id, agent_squads.AgentExecutionAuthority.FULL
                )
    finally:
        storage.close()


def test_off_track_kpi_surfaces_in_team_briefing(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    try:
        maya = get_staff(storage.conn, "maya")
        kpi = list_kpis(storage.conn, maya.id)[0]
        with storage.transaction() as conn:
            update_kpi(
                conn,
                maya.id,
                kpi.id,
                StaffKpiUpdate(status="off_track", current_value=0),
            )
        briefing = team_briefing(storage.conn)
        assert briefing["counts"]["attention_items"] >= 1
        assert any(
            item["staff_id"] == maya.id and item["severity"] == "critical"
            for item in briefing["attention"]
        )
    finally:
        storage.close()
