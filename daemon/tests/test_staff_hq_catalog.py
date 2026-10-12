"""Staff HQ expansion seeds and permission/continuity regression tests."""
from __future__ import annotations

from synapse_daemon.storage import Storage
from synapse_daemon.agent_squads import seed_default_role_templates
from synapse_daemon.personalities import seed_default_personalities
from synapse_daemon.staff import seed_staff_foundation, list_staff, update_staff, StaffMemberUpdate
from synapse_daemon.staff_hq_catalog import CREW, SENSITIVE_CAPABILITIES, seed_creator_revenue_staff
from synapse_daemon.staff_operations import seed_staff_operations, list_triggers, list_permissions, list_kpis


def test_creator_revenue_staff_is_seeded_and_idempotent(tmp_path):
    s = Storage(tmp_path / "state")
    s.open()
    s.migrate()
    with s.transaction() as conn:
        seed_default_role_templates(conn)
        seed_default_personalities(conn)
        seed_staff_foundation(conn)
        seed_staff_operations(conn)
        seed_creator_revenue_staff(conn)
        people = list_staff(conn)
        assert len(people) == 14
        assert len({p.handle for p in people}) == 14
        assert {b.handle for b in CREW} <= {p.handle for p in people}
        assert {"maya", "adrian", "sofia", "marcus", "jordan", "riley"} <= {p.handle for p in people}
        assert {p.handle for p in people if p.builtin} == {p.handle for p in people}
        eli = next(p for p in people if p.handle == "eli")
        assert eli.role_template_id == "staff-hq-eli"
        assert eli.authority_policy == "prepare_for_approval"
        for person in people:
            if person.handle not in {b.handle for b in CREW}:
                continue
            assert all(t.enabled is False for t in list_triggers(conn, person.id))
            assert all(k.current_value is None and k.status == "unknown" for k in list_kpis(conn, person.id))
            grants = [p for p in list_permissions(conn, person.id) if p.scope_type == "external_action"]
            assert {p.capability for p in grants} >= set(SENSITIVE_CAPABILITIES)
            assert all(p.decision == "ask" for p in grants)
        update_staff(conn, "eli", StaffMemberUpdate(status_line="Custom owner status"))
        original_triggers = {p.handle: len(list_triggers(conn, p.id)) for p in people}
        seed_creator_revenue_staff(conn)
        again = list_staff(conn)
        assert len(again) == 14
        assert next(p for p in again if p.handle == "eli").status_line == "Custom owner status"
        assert {p.handle: len(list_triggers(conn, p.id)) for p in again} == original_triggers
    s.close()



def test_hq_staff_router_assigns_streaming_money_and_creator_tasks(tmp_path):
    from synapse_daemon.staff_operations import route_task
    s = Storage(tmp_path / "route")
    s.open()
    s.migrate()
    with s.transaction() as conn:
        seed_default_role_templates(conn)
        seed_default_personalities(conn)
        seed_staff_foundation(conn)
        seed_staff_operations(conn)
        seed_creator_revenue_staff(conn)
        samples = {
            "Can you help me stream with OBS and a webcam?": "eli",
            "Plan my personal budget and my bills": "lena",
            "Please edit my video Shorts clips": "nova",
            "Schedule a TikTok social media post": "zoe",
            "Design a YouTube thumbnail and banner": "iris",
            "Find sponsors and affiliate partnerships": "felix",
            "Organize my day and coordinate team priorities": "tess",
            "Handle customer support tickets": "sam",
        }
        for text, expected in samples.items():
            result = route_task(conn, text)
            assert result.selected.handle == expected, (text, result.selected.handle)
        assert route_task(conn, "@eli please check the mic").explicit
    s.close()
