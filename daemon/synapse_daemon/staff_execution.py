"""Truthful work-cycle read model for persistent AI Staff.

A status column saying "working" does not prove an active runtime. An observed
running work item without a recent linked agent heartbeat is stale, not healthy.
This module does not launch, resume, kill or mutate workers.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any

from .staff import get_staff
from .time_utils import utc_now

HEARTBEAT_STALE_SECONDS = 300


def _parse_datetime(value: str | datetime | None) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    elif value:
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if parsed.tzinfo is None:
        # The database uses ISO UTC; naive timestamps must never prove liveness.
        return None
    return parsed.astimezone(timezone.utc)


def _item_state(
    row: sqlite3.Row, *, observed_at: datetime, heartbeat_stale_seconds: int,
) -> dict[str, Any]:
    status = row["work_status"]
    hb = _parse_datetime(row["last_heartbeat_at"])
    session_status = row["session_status"]
    age = max(0.0, (observed_at - hb).total_seconds()) if hb else None
    # An ancient or future heartbeat cannot establish current proof.
    live = (
        status == "running"
        and session_status == "active"
        and age is not None
        and hb <= observed_at + timedelta(seconds=15)
        and age <= heartbeat_stale_seconds
        and row["ended_at"] is None
    )
    if status == "running":
        observed = "running_confirmed" if live else "stale_or_disconnected"
    elif status == "completed":
        observed = "completed_with_handoff" if (row["summary_md"] or "").strip() else "completed_without_handoff"
    elif status in ("handoff", "blocked", "queued"):
        observed = status
    else:
        observed = "unknown"
    return {
        "work_item_id": row["work_item_id"],
        "squad_id": row["squad_id"],
        "project_id": row["project_id"],
        "title": row["title"],
        "stored_status": status,
        "observed_state": observed,
        "runtime": row["preferred_runtime"],
        "session_id": row["session_id"],
        "session_status": session_status,
        "last_heartbeat_at": row["last_heartbeat_at"],
        "heartbeat_age_seconds": round(age, 1) if age is not None else None,
        "updated_at": row["updated_at"],
        "completed_at": row["completed_at"],
        "summary_md": row["summary_md"],
        "blockers_md": row["blockers_md"],
        "is_live": bool(live),
        "requires_reconciliation": observed in {"stale_or_disconnected", "completed_without_handoff"},
    }


def staff_execution_snapshot(
    conn: sqlite3.Connection,
    staff_id: str,
    *,
    now: datetime | None = None,
    limit: int = 20,
    heartbeat_stale_seconds: int = HEARTBEAT_STALE_SECONDS,
) -> dict[str, Any]:
    """Classify actual staff-linked assignments against durable worker receipts."""
    member = get_staff(conn, staff_id)
    observed_at = (now or utc_now()).astimezone(timezone.utc)
    limit = max(1, min(100, int(limit)))
    rows = conn.execute(
        """SELECT w.id AS work_item_id, w.squad_id, sq.project_id,
                  w.title, w.status AS work_status, w.preferred_runtime,
                  w.summary_md, w.blockers_md, w.updated_at, w.completed_at,
                  ses.id AS session_id, ses.status AS session_status,
                  ses.last_heartbeat_at, ses.ended_at
           FROM staff_work_items sw
           JOIN agent_work_items w ON w.id = sw.work_item_id
           JOIN agent_squads sq ON sq.id = w.squad_id
           LEFT JOIN agent_sessions ses ON ses.id = (
               SELECT newest.id FROM agent_sessions newest
               WHERE newest.coder_thread_id = w.pty_session_id
               ORDER BY newest.registered_at DESC, newest.id DESC LIMIT 1
           )
           WHERE sw.staff_member_id=?
           ORDER BY sw.created_at DESC, w.id DESC
           LIMIT ?""",
        (member.id, limit),
    ).fetchall()
    items = [
        _item_state(row, observed_at=observed_at, heartbeat_stale_seconds=heartbeat_stale_seconds)
        for row in rows
    ]
    counts = {name: sum(x["observed_state"] == name for x in items) for name in (
        "queued", "running_confirmed", "stale_or_disconnected",
        "blocked", "handoff", "completed_with_handoff", "completed_without_handoff", "unknown"
    )}
    if counts["stale_or_disconnected"]:
        state = "reconciliation_needed"
        next_action = "Inspect stale sessions and their last durable handoff before any retry. Never silently launch duplicates."
    elif counts["running_confirmed"]:
        state = "working_verified"
        next_action = "Review heartbeat and eventual verified handoff; do not equate running with success."
    elif counts["blocked"]:
        state = "blocked"
        next_action = "Read the recorded blocker and resolve it with an approved bounded action."
    elif counts["queued"]:
        state = "queued"
        next_action = "Check current runtime readiness and project boundaries before launching the queued work item."
    elif counts["completed_without_handoff"]:
        state = "proof_missing"
        next_action = "Get an evidence-backed handoff before recognizing completed work."
    elif counts["handoff"]:
        state = "handoff"
        next_action = "Review handoff evidence and decide whether to continue or close the assignment."
    elif counts["completed_with_handoff"]:
        state = "completed"
        next_action = "Evaluate real outcome metrics before considering a new assignment."
    else:
        state = "not_started"
        next_action = "Give this staff member one bounded assignment with a measurable pass/fail result."
    return {
        "staff_id": member.id,
        "stored_profile_status": member.status.value,
        "observed_state": state,
        "observed_at": observed_at.isoformat(),
        "heartbeat_stale_seconds": heartbeat_stale_seconds,
        "counts": counts,
        "work_items": items,
        "next_safe_action": next_action,
        "limit_applied": limit,
        "note": "This snapshot reads durable staff work-item and agent-session records. A connected/green runtime label alone is not proof of a live task.",
    }
