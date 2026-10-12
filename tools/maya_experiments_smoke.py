"""Fast, stdlib-only Maya experiment logic checks against a minimal registry fixture.

This is not a replacement for the full migrated Synapse route integration tests.
"""
from __future__ import annotations
import sys
from pathlib import Path
from datetime import datetime, timedelta, timezone
import sqlite3

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "daemon"))
from synapse_daemon.maya_experiments import build_experiment_plan

db = sqlite3.connect(":memory:")
db.row_factory = sqlite3.Row
db.executescript("""
CREATE TABLE projects(
 id TEXT PRIMARY KEY, name TEXT, status TEXT, current_health TEXT, last_health_at TEXT,
 updated_at TEXT, group_name TEXT, tags_json TEXT, kind TEXT, pinned INTEGER,
 deleted_at TEXT);
CREATE TABLE project_backlog(project_id TEXT, status TEXT, priority TEXT);
""")
now = datetime.now(timezone.utc)
db.execute(
 "INSERT INTO projects VALUES(?,?,?,?,?,?,?,?,?,?,?)",
 ("reselltogether","ResellTogether","launched","healthy",now.isoformat(),
  now.isoformat(), "","[]","ui",0,None))
db.execute(
 "INSERT INTO projects VALUES(?,?,?,?,?,?,?,?,?,?,?)",
 ("nabsignal","NabSignal","idle",None,None,now.isoformat(),"","[]","app",0,None))
def check(ok, name):
    assert ok, name
    print("PASS",name,flush=True)
p = build_experiment_plan(db)
check(p["project_id"] == "reselltogether", "grounded project selection")
check(p["readiness_gate"] == "internal_test_candidate", "fresh health gate")
check(p["baseline"] is None and p["completions"] is None and not p["executed"], "metrics unknown, no execution")
check(len(p["funnel_steps"]) == 4, "specific first-value steps")
check("publish" not in " ".join(p["funnel_steps"]).lower(), "no live publication")
check(any("privacy" in s.lower() for s in p["guardrails"]), "privacy stop condition")
db.execute("UPDATE projects SET last_health_at=? WHERE id='reselltogether'",
           ((now-timedelta(days=3)).isoformat(),))
p=build_experiment_plan(db)
check(p["health_freshness"]=="stale" and p["readiness_gate"]=="runtime_preflight_required", "stale health downgrades")
db.execute("UPDATE projects SET last_health_at=? WHERE id='reselltogether'",
           ((now+timedelta(days=2)).isoformat(),))
p=build_experiment_plan(db)
check(p["health_freshness"]=="future_clock_skew", "future clock skew blocked")
db.execute("UPDATE projects SET current_health='unhealthy',status='error' WHERE id='reselltogether'")
p=build_experiment_plan(db)
check(p["project_id"]=="nabsignal" and p["readiness_gate"]=="runtime_preflight_required", "switches to viable candidate")
db.execute("UPDATE projects SET deleted_at=? WHERE id IN ('reselltogether','nabsignal')",(now.isoformat(),))
p=build_experiment_plan(db)
check(p["status"]=="no_candidate" and p["project_id"] is None, "no fabricated candidates")


# Receipt exercise against isolated in-memory staff tables; no live DB writes.
from synapse_daemon.maya_experiments import record_experiment_plan
db.executescript("""
CREATE TABLE staff_members(
 id TEXT, handle TEXT, display_name TEXT, title TEXT,
 role_template_id TEXT, personality_id TEXT, avatar_asset_id TEXT, bio TEXT,
 about_md TEXT, status TEXT, status_line TEXT, specialties_json TEXT,
 goals_json TEXT, assigned_project_ids_json TEXT, authority_policy TEXT,
 notification_policy_json TEXT, contact_channels_json TEXT, builtin INTEGER,
 sort_order INTEGER, created_at TEXT, updated_at TEXT);
CREATE TABLE staff_events(
 id TEXT, staff_member_id TEXT, event_type TEXT, title TEXT,
 body_md TEXT, severity TEXT, action_required INTEGER, source TEXT,
 metadata_json TEXT, created_at TEXT);
""")
db.execute(
 "INSERT INTO staff_members VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
 ("maya-growth","maya","Maya","Growth Director","growth-director",None,None,
  "","","available","","[]","[]","[]","prepare_for_approval","{}","[]",1,0,
  now.isoformat(),now.isoformat()))
db.execute(
 "UPDATE projects SET deleted_at=NULL,status='launched',current_health='healthy',"
 "last_health_at=? WHERE id='reselltogether'", (now.isoformat(),))
first=record_experiment_plan(db)
second=record_experiment_plan(db)
check(first["created"] and first["event_id"]==second["event_id"] and not second["created"],
      "draft receipt persists once without duplication")
event=db.execute("SELECT event_type,metadata_json FROM staff_events").fetchone()
check(event["event_type"]=="growth_experiment_plan"
      and '"execution_status": "not_executed"' in event["metadata_json"],
      "receipt explicitly records not executed")
db.execute(
 "UPDATE projects SET last_health_at=? WHERE id='reselltogether'",
 ((now-timedelta(days=3)).isoformat(),))
third=record_experiment_plan(db)
check(third["created"] and third["event_id"]!=first["event_id"],
      "meaningful readiness downgrade creates a new auditable version")
check(db.execute("SELECT COUNT(*) FROM staff_events").fetchone()[0]==2,
      "receipt events contain only two distinct proposals")
print("MAYA_FAST_CHECKS: 14 passed",flush=True)
