"""Staff HQ REST smoke against a disposable database, not the live daemon."""
from fastapi import FastAPI
from fastapi.testclient import TestClient

from synapse_daemon.agent_squads import seed_default_role_templates
from synapse_daemon.personalities import seed_default_personalities
from synapse_daemon.staff import seed_staff_foundation
from synapse_daemon.staff_hq_catalog import seed_creator_revenue_staff
from synapse_daemon.staff_hq_proactivity import emit_due_staff_reminders
from synapse_daemon.staff_operations import seed_staff_operations
from synapse_daemon.routes_staff import build_staff_router
from synapse_daemon.storage import Storage
from synapse_daemon.time_utils import utc_now
from datetime import timedelta


def test_rest_roster_profile_and_opt_in_reminder(tmp_path):
    storage = Storage(tmp_path / "state")
    storage.open()
    storage.migrate()
    with storage.transaction() as conn:
        seed_default_role_templates(conn)
        seed_default_personalities(conn)
        seed_staff_foundation(conn)
        seed_staff_operations(conn)
        seed_creator_revenue_staff(conn)
    app = FastAPI()
    app.include_router(build_staff_router(storage), prefix="/api/v1")
    client = TestClient(app)

    people = client.get("/api/v1/staff")
    assert people.status_code == 200, people.text
    roster = people.json()["staff"]
    assert len(roster) == 14
    assert any(p["handle"] == "eli" for p in roster)
    profile = client.get("/api/v1/staff/eli")
    assert profile.status_code == 200, profile.text
    dash = client.get("/api/v1/staff/eli/dashboard")
    assert dash.status_code == 200, dash.text
    trigger = dash.json()["triggers"][0]
    assert trigger["enabled"] is False
    enabled = client.patch(f"/api/v1/staff/eli/triggers/{trigger['id']}", json={"enabled": True})
    assert enabled.status_code == 200, enabled.text
    assert enabled.json()["enabled"] is True
    with storage.transaction() as conn:
        assert emit_due_staff_reminders(conn, now=utc_now() + timedelta(seconds=5)) == [trigger["id"]]
    next_dash = client.get("/api/v1/staff/eli/dashboard").json()
    assert len([e for e in next_dash["events"] if e["event_type"] == "proactive_review_due"]) == 1
    brief = client.get("/api/v1/staff/briefing").json()
    assert any(a["staff_id"] == "staff-hq-eli" for a in brief["attention"])
    paused = client.patch(f"/api/v1/staff/eli/triggers/{trigger['id']}", json={"enabled": False})
    assert paused.status_code == 200
    assert paused.json()["enabled"] is False
    storage.close()
