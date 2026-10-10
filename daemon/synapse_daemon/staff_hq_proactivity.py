"""Lightweight opt-in staff reminder dispatcher.

Does not run AI models, inspect user devices or perform external actions.
A due enabled schedule trigger creates an auditable in-app staff event only.
A future worker dispatcher must separately check permissions and model readiness.
"""
from __future__ import annotations

import asyncio
import logging
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any

from .errors import invalid, not_found
from .staff import get_staff
from .staff_operations import _trigger, record_event
from .storage import Storage
from .time_utils import to_iso, utc_now

log = logging.getLogger(__name__)
POLL_SECONDS = 900  # cheap background check, never more than every 15 minutes
MIN_INTERVAL_HOURS = 24


def set_staff_trigger_enabled(
    conn: sqlite3.Connection, staff_id: str, trigger_id: str, enabled: bool
) -> dict[str, Any]:
    member = get_staff(conn, staff_id)
    row = conn.execute("SELECT * FROM staff_triggers WHERE id=? AND staff_member_id=?",
                       (trigger_id, member.id)).fetchone()
    if row is None:
        raise not_found("staff_trigger", trigger_id)
    if row["trigger_type"] != "schedule":
        raise invalid("staff_trigger", "Only scheduled review reminders are supported by this dispatcher.")
    if enabled:
        import json
        cfg = json.loads(row["config_json"] or "{}")
        if cfg.get("cadence") != "daily":
            raise invalid("staff_trigger", "Only daily opt-in reminders are supported right now.")
    # Newly enabled triggers start at next check. This is a reminder, NOT permission
    # for remote/model execution, a broadcast, or an external send.
    next_at = to_iso(utc_now()) if enabled else None
    conn.execute(
        "UPDATE staff_triggers SET enabled=?, next_run_at=?, updated_at=? "
        "WHERE id=? AND staff_member_id=?",
        (int(enabled), next_at, to_iso(utc_now()), trigger_id, member.id),
    )
    return _trigger(conn.execute("SELECT * FROM staff_triggers WHERE id=?", (trigger_id,)).fetchone()).model_dump(mode="json")


def emit_due_staff_reminders(
    conn: sqlite3.Connection, *, now: datetime | None = None
) -> list[str]:
    """Atomically write due receipts with next-run checkpoints.

    The caller must hold a SQLite transaction; this protects against duplicate
    emission in overlapping scheduler ticks.
    """
    current = (now or utc_now()).astimezone(timezone.utc)
    rows = conn.execute(
        "SELECT id, staff_member_id, name, prompt_md, last_run_at, next_run_at "
        "FROM staff_triggers WHERE enabled=1 AND trigger_type='schedule' "
        "AND next_run_at IS NOT NULL ORDER BY next_run_at, id"
    ).fetchall()
    emitted = []
    for row in rows:
        try:
            due = datetime.fromisoformat(row["next_run_at"].replace("Z", "+00:00"))
            if due.tzinfo is None:
                continue
            if due > current:
                continue
            if row["last_run_at"]:
                last = datetime.fromisoformat(row["last_run_at"].replace("Z", "+00:00"))
                if last.tzinfo is None or current - last < timedelta(hours=MIN_INTERVAL_HOURS):
                    continue
        except (ValueError, TypeError):
            log.warning("Invalid staff trigger schedule; skipping id=%s", row["id"])
            continue
        next_at = current + timedelta(hours=MIN_INTERVAL_HOURS)
        conn.execute(
            "UPDATE staff_triggers SET last_run_at=?, next_run_at=?, updated_at=? WHERE id=?",
            (to_iso(current), to_iso(next_at), to_iso(current), row["id"]),
        )
        record_event(
            conn, row["staff_member_id"],
            event_type="proactive_review_due",
            title=f"Staff review ready: {row['name']}",
            body_md=(
                "An opt-in scheduled review is due. Ask this employee to evaluate current verified "
                "information and propose next actions. No background AI task or external action ran.\n\n"
                + (row["prompt_md"] or "")
            ),
            severity="info", action_required=True,
            source="staff-proactivity",
            metadata={"trigger_id": row["id"], "execution_type": "reminder_only"},
        )
        emitted.append(row["id"])
    return emitted


class StaffProactivityService:
    def __init__(self, storage: Storage) -> None:
        self.storage = storage
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        if self._task and not self._task.done():
            return
        self._task = asyncio.create_task(self._run(), name="staff-review-reminders")

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _run(self) -> None:
        # Startup waits for normal API initialization and avoids a tight poll.
        while True:
            try:
                with self.storage.transaction() as conn:
                    emitted = emit_due_staff_reminders(conn)
                if emitted:
                    log.info("Staff reminder events emitted count=%d", len(emitted))
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("Staff reminder tick failed (will retry later)")
            await asyncio.sleep(POLL_SECONDS)
