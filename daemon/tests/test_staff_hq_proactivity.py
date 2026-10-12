"""Opt-in staff reminders: no spontaneous sends, bounded duplicate-proof ticks."""
from datetime import timedelta

import pytest

from synapse_daemon.storage import Storage
from synapse_daemon.agent_squads import seed_default_role_templates
from synapse_daemon.personalities import seed_default_personalities
from synapse_daemon.staff import seed_staff_foundation
from synapse_daemon.staff_hq_catalog import seed_creator_revenue_staff
from synapse_daemon.staff_hq_proactivity import (
    emit_due_staff_reminders, set_staff_trigger_enabled,
)
from synapse_daemon.staff_operations import list_triggers, list_events
from synapse_daemon.time_utils import utc_now


@pytest.fixture
def data(tmp_path):
    db = Storage(tmp_path / "state")
    db.open()
    db.migrate()
    with db.transaction() as conn:
        seed_default_role_templates(conn)
        seed_default_personalities(conn)
        seed_staff_foundation(conn)
        seed_creator_revenue_staff(conn)
    yield db
    db.close()


def test_reminders_are_disabled_by_default(data):
    with data.transaction() as conn:
        assert len(list_triggers(conn, "eli")) == 1
        assert all(not t.enabled for t in list_triggers(conn, "eli"))
        assert emit_due_staff_reminders(conn) == []
        assert list_events(conn, "eli") == []


def test_opt_in_emits_once_and_can_be_paused(data):
    with data.transaction() as conn:
        trigger = list_triggers(conn, "eli")[0]
        enabled = set_staff_trigger_enabled(conn, "eli", trigger.id, True)
        assert enabled["enabled"] is True
        start = utc_now() + timedelta(seconds=5)
        assert emit_due_staff_reminders(conn, now=start) == [trigger.id]
        assert emit_due_staff_reminders(conn, now=start + timedelta(seconds=10)) == []
        events = list_events(conn, "eli")
        assert len(events) == 1
        assert events[0].event_type == "proactive_review_due"
        assert events[0].metadata["execution_type"] == "reminder_only"
        assert events[0].action_required is True
        paused = set_staff_trigger_enabled(conn, "eli", trigger.id, False)
        assert paused["enabled"] is False
        assert emit_due_staff_reminders(conn, now=start + timedelta(days=3)) == []
        assert len(list_events(conn, "eli")) == 1


def test_invalid_staff_or_trigger_cannot_be_enabled(data):
    with data.transaction() as conn:
        trigger = list_triggers(conn, "eli")[0]
        with pytest.raises(Exception):
            set_staff_trigger_enabled(conn, "unknown", trigger.id, True)
        with pytest.raises(Exception):
            set_staff_trigger_enabled(conn, "lena", trigger.id, True)
