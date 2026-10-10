"""Maya's measurable growth experiment drafts require evidence and never run actions."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from synapse_daemon import agent_squads, personalities
from synapse_daemon.maya_experiments import build_experiment_plan, record_experiment_plan
from synapse_daemon.projects import Project, create as create_project
from synapse_daemon.staff import seed_staff_foundation
from synapse_daemon.staff_operations import seed_staff_operations
from synapse_daemon.storage import Storage


@pytest.fixture(scope="module")
def seeded_storage(tmp_path_factory):
    tmp_path = tmp_path_factory.mktemp("maya-experiment")
    db = Storage(tmp_path / "data")
    db.open()
    db.migrate()
    with db.transaction() as conn:
        agent_squads.seed_default_role_templates(conn)
        personalities.seed_default_personalities(conn)
        seed_staff_foundation(conn)
        seed_staff_operations(conn)
        for ident in ("reselltogether", "nabsignal", "synapse"):
            create_project(conn, Project(id=ident, name=ident.title(),
                                         path=str(tmp_path / ident), launch_cmd="echo test"))
        conn.execute(
            "UPDATE projects SET status='launched', current_health='healthy', last_health_at=?"
            " WHERE id='reselltogether'",
            (datetime.now(timezone.utc).isoformat(),),
        )
    yield db
    db.close()


@pytest.fixture()
def storage(seeded_storage):
    # Reuse one migrated DB: a full Synapse migration is expensive on low-RAM hosts.
    with seeded_storage.transaction() as conn:
        conn.execute("DELETE FROM staff_events WHERE staff_member_id=(SELECT id FROM staff_members WHERE handle='maya')")
        conn.execute(
            "UPDATE projects SET status='idle', current_health=NULL, last_health_at=NULL,"
            " deleted_at=NULL WHERE id IN ('reselltogether','nabsignal','synapse')"
        )
        conn.execute(
            "UPDATE projects SET status='launched',current_health='healthy',last_health_at=?"
            " WHERE id='reselltogether'",
            (datetime.now(timezone.utc).isoformat(),),
        )
    yield seeded_storage


def test_plan_uses_actual_registry_and_does_not_write(storage):
    before = storage.conn.execute("SELECT COUNT(*) FROM staff_events").fetchone()[0]
    plan = build_experiment_plan(storage.conn)
    assert plan["project_id"] == "reselltogether"
    assert plan["status"] == "draft_unexecuted"
    assert plan["readiness_gate"] == "internal_test_candidate"
    assert plan["health_freshness"] == "fresh"
    assert storage.conn.execute("SELECT COUNT(*) FROM staff_events").fetchone()[0] == before


def test_numerators_and_baseline_must_remain_unknown(storage):
    plan = build_experiment_plan(storage.conn)
    assert plan["baseline"] is None and plan["attempts"] is None
    assert plan["completions"] is None and not plan["executed"]
    assert plan["metric"]["unit"] == "completed / attempted"


def test_specific_resell_funnel_without_publishing(storage):
    plan = build_experiment_plan(storage.conn)
    assert len(plan["funnel_steps"]) == 4
    assert "private closet item" in " ".join(plan["funnel_steps"]).lower()
    assert "publish" not in " ".join(plan["funnel_steps"]).lower()
    assert any("account" in s.lower() for s in plan["guardrails"])


def test_stale_health_requires_new_probe(storage):
    with storage.transaction() as conn:
        conn.execute("UPDATE projects SET last_health_at=? WHERE id='reselltogether'",
                     ((datetime.now(timezone.utc) - timedelta(days=3)).isoformat(),))
    plan = build_experiment_plan(storage.conn)
    assert plan["readiness_gate"] == "runtime_preflight_required"
    assert plan["health_freshness"] == "stale"
    assert "Recheck" in plan["next_action"]


def test_no_health_timestamp_is_not_fresh(storage):
    with storage.transaction() as conn:
        conn.execute("UPDATE projects SET last_health_at=NULL WHERE id='reselltogether'")
    assert build_experiment_plan(storage.conn)["health_freshness"] == "unknown"


def test_future_clock_skew_not_mistaken_for_fresh(storage):
    with storage.transaction() as conn:
        conn.execute("UPDATE projects SET last_health_at=? WHERE id='reselltogether'",
                     ((datetime.now(timezone.utc) + timedelta(days=2)).isoformat(),))
    plan = build_experiment_plan(storage.conn)
    assert plan["health_freshness"] == "future_clock_skew"
    assert plan["readiness_gate"] == "runtime_preflight_required"


def test_stopped_product_not_allowed_to_run_funnel(storage):
    with storage.transaction() as conn:
        conn.execute("UPDATE projects SET status='stopped' WHERE id='reselltogether'")
    assert build_experiment_plan(storage.conn)["readiness_gate"] == "runtime_preflight_required"


def test_receipt_is_idempotent_and_safe(storage):
    with storage.transaction() as conn:
        before = conn.execute("SELECT COUNT(*) FROM staff_work_items").fetchone()[0]
        a = record_experiment_plan(conn)
        b = record_experiment_plan(conn)
    assert a["created"] is True and b["created"] is False
    assert a["event_id"] == b["event_id"]
    assert storage.conn.execute("SELECT COUNT(*) FROM staff_work_items").fetchone()[0] == before
    event = storage.conn.execute(
        "SELECT event_type,metadata_json FROM staff_events WHERE id=?", (a["event_id"],)
    ).fetchone()
    assert event["event_type"] == "growth_experiment_plan"
    assert '"execution_status": "not_executed"' in event["metadata_json"]


def test_change_of_project_creates_new_draft_not_duplicate(storage):
    with storage.transaction() as conn:
        a = record_experiment_plan(conn)
        conn.execute("UPDATE projects SET status='stopped',current_health='unhealthy'"
                     " WHERE id='reselltogether'")
        b = record_experiment_plan(conn)
    assert b["created"] and b["event_id"] != a["event_id"]
    assert b["plan"]["project_id"] == "nabsignal"
    assert "actual" in b["plan"]["funnel_steps"][0].lower()


def test_no_candidate_has_no_event(storage):
    with storage.transaction() as conn:
        conn.execute("UPDATE projects SET deleted_at=? WHERE id IN ('reselltogether','nabsignal')",
                     (datetime.now(timezone.utc).isoformat(),))
        a = record_experiment_plan(conn)
    assert not a["created"] and a["event_id"] is None
    assert a["plan"]["status"] == "no_candidate"
    assert storage.conn.execute("SELECT COUNT(*) FROM staff_events").fetchone()[0] == 0


def test_router_preview_and_receipt(storage):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from synapse_daemon.routes_staff import build_staff_router
    app = FastAPI()
    app.include_router(build_staff_router(storage))
    with TestClient(app) as client:
        preview = client.get("/staff/maya/experiment-plan")
        assert preview.status_code == 200
        assert preview.json()["executed"] is False
        first = client.post("/staff/maya/experiment-plan")
        second = client.post("/staff/maya/experiment-plan")
        assert first.status_code == 200 and first.json()["created"] is True
        assert second.status_code == 200 and second.json()["created"] is False
