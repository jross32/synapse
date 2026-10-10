"""Maya's review must be honest, non-destructive and repeatable."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from synapse_daemon import agent_squads, personalities
from synapse_daemon.maya_growth import build_growth_review, record_growth_review
from synapse_daemon.projects import Project, create as create_project
from synapse_daemon.staff import seed_staff_foundation
from synapse_daemon.staff_operations import seed_staff_operations
from synapse_daemon.storage import Storage


@pytest.fixture()
def db(tmp_path: Path):
    storage = Storage(tmp_path / "data")
    storage.open()
    storage.migrate()
    with storage.transaction() as conn:
        agent_squads.seed_default_role_templates(conn)
        personalities.seed_default_personalities(conn)
        seed_staff_foundation(conn)
        seed_staff_operations(conn)
        for ident in ("reselltogether", "nabsignal", "pageassert", "synapse", "unrelated"):
            create_project(conn, Project(
                id=ident, name=ident.title(),
                path=str(tmp_path / ident), launch_cmd="echo test"
            ))
        conn.execute(
            "UPDATE projects SET status='launched',current_health='healthy',"
            "last_health_at='2026-10-09T10:00:00+00:00' WHERE id='reselltogether'"
        )
        conn.execute(
            "UPDATE projects SET status='stopped',current_health='unhealthy' "
            "WHERE id='pageassert'"
        )
    yield storage
    storage.close()


def test_preview_is_read_only_and_uses_real_sources(db):
    before = db.conn.execute("SELECT COUNT(*) FROM staff_events").fetchone()[0]
    result = build_growth_review(db.conn)
    assert result["recommended_project_id"] == "reselltogether"
    assert result["projects_examined"] == 5
    assert result["commercial_candidates"] == 3
    assert db.conn.execute("SELECT COUNT(*) FROM staff_events").fetchone()[0] == before
    assert "unrelated" not in [x["project_id"] for x in result["candidates"]]
    assert "synapse" not in [x["project_id"] for x in result["candidates"]]


def test_no_invented_revenue_or_experiment_result(db):
    result = build_growth_review(db.conn)
    assert result["selection_basis"].endswith("NOT estimated market size or ROI")
    for item in result["candidates"]:
        assert item["customers"] is None
        assert item["revenue"] is None
        assert item["conversion_rate"] is None
        assert item["experiment_status"] == "proposed_not_executed"
        assert "attempt" in item["success_measure"] or "pass/fail" in item["success_measure"]


def test_unhealthy_product_not_marked_customer_ready(db):
    rows = {x["project_id"]: x for x in build_growth_review(db.conn)["candidates"]}
    assert rows["pageassert"]["readiness"] == "runtime_blocked"
    assert rows["pageassert"]["readiness_rank"] == 1
    assert rows["nabsignal"]["readiness"] == "unverified"


def test_receipt_is_idempotent_and_does_not_modify_kpis(db):
    with db.transaction() as conn:
        before_kpis = [tuple(row) for row in conn.execute(
            "SELECT id,status,current_value FROM staff_kpis ORDER BY id"
        )]
        first = record_growth_review(conn)
        again = record_growth_review(conn)
        after_kpis = [tuple(row) for row in conn.execute(
            "SELECT id,status,current_value FROM staff_kpis ORDER BY id"
        )]
    assert first["created"] is True
    assert again["created"] is False
    assert first["event_id"] == again["event_id"]
    assert before_kpis == after_kpis
    assert db.conn.execute("SELECT COUNT(*) FROM staff_events").fetchone()[0] == 1
    assert db.conn.execute("SELECT COUNT(*) FROM staff_work_items").fetchone()[0] == 0


def test_new_actual_health_snapshot_creates_new_receipt(db):
    with db.transaction() as conn:
        a = record_growth_review(conn)
        conn.execute(
            "UPDATE projects SET current_health='unhealthy',"
            "last_health_at='2026-10-09T12:00:00+00:00' WHERE id='reselltogether'"
        )
        b = record_growth_review(conn)
    assert a["event_id"] != b["event_id"]
    assert b["brief"]["recommended_project_id"] == "nabsignal"
    assert db.conn.execute("SELECT COUNT(*) FROM staff_events").fetchone()[0] == 2


def test_no_candidates_fails_closed_without_fake_experiment(db):
    with db.transaction() as conn:
        conn.execute(
            "UPDATE projects SET deleted_at='2026-10-09T00:00:00+00:00' "
            "WHERE id IN ('reselltogether','nabsignal','pageassert')"
        )
        review = build_growth_review(conn)
        receipt = record_growth_review(conn)
    assert review["recommended_project_id"] is None
    assert review["candidates"] == []
    assert "No commercial candidates" in review["recommendation"]
    assert receipt["created"] is True


def test_preview_limit_bounded(db):
    assert len(build_growth_review(db.conn, limit=1)["candidates"]) == 1
    assert len(build_growth_review(db.conn, limit=999)["candidates"]) <= 12


def test_maya_chat_uses_verified_registry_evidence_only(db):
    from synapse_daemon import staff_chat
    from synapse_daemon.staff import get_staff
    prompt = staff_chat._persona_prompt(db.conn, get_staff(db.conn, "maya"))
    assert "Synapse registry evidence snapshot" in prompt
    assert "status=launched" in prompt
    assert "health=healthy" in prompt
    assert "revenue" in prompt.lower() and "UNKNOWN" in prompt
    assert "never claim" in prompt.lower()
    other = staff_chat._persona_prompt(db.conn, get_staff(db.conn, "adrian"))
    assert "Synapse registry evidence snapshot" not in other


def test_maya_router_preview_then_idempotent_receipt(db):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from synapse_daemon.routes_staff import build_staff_router
    app = FastAPI()
    app.include_router(build_staff_router(db))
    with TestClient(app) as client:
        preview = client.get("/staff/maya/growth-review")
        assert preview.status_code == 200
        assert preview.json()["recommended_project_id"] == "reselltogether"
        created = client.post("/staff/maya/growth-review")
        assert created.status_code == 200 and created.json()["created"] is True
        duplicate = client.post("/staff/maya/growth-review")
        assert duplicate.status_code == 200 and duplicate.json()["created"] is False


def test_health_probe_clock_refresh_does_not_spam_receipts(db):
    with db.transaction() as conn:
        first = record_growth_review(conn)
        conn.execute(
            "UPDATE projects SET last_health_at='2026-10-09T11:00:00+00:00',"
            "updated_at='2026-10-09T11:00:00+00:00' WHERE id='reselltogether'"
        )
        second = record_growth_review(conn)
    assert first["event_id"] == second["event_id"]
    assert second["created"] is False
