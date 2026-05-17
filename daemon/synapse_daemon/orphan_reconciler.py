"""Orphan process reconciliation (Contract #6).

On daemon startup — **before** accepting any client connections — scan the
``managed_processes`` table for rows that were active when the daemon last
exited. For each:

  • Alive and ``cmdline`` matches what we recorded → re-attach (resume
    monitoring without re-spawning).
  • Alive but ``cmdline`` differs → the OS recycled the PID; mark stopped
    with reason ``pid-recycled``.
  • Dead → the child process exited while we were down; mark stopped with
    reason ``daemon-restart``.

This is what makes the "processes persist past UI death" promise survive a
daemon restart too. Without it, a daemon crash would lose all references to
running children even though the OS still has them.
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timezone
from enum import Enum
from typing import NamedTuple

import psutil
from pydantic import BaseModel, Field

log = logging.getLogger(__name__)


class ReconcileOutcome(str, Enum):
    """What the reconciler decided about one row."""

    RE_ATTACHED = "re-attached"
    PID_RECYCLED = "pid-recycled"
    DAEMON_RESTART = "daemon-restart"


class ReconciledRow(NamedTuple):
    process_id: int          # PK of managed_processes row
    entity_type: str
    entity_id: str
    pid: int
    outcome: ReconcileOutcome


class ReconciliationReport(BaseModel):
    """Aggregate result of one reconcile() call."""

    re_attached: list[int] = Field(default_factory=list)   # PKs
    pid_recycled: list[int] = Field(default_factory=list)
    daemon_restart: list[int] = Field(default_factory=list)
    inspected: int = 0

    @property
    def all_outcomes(self) -> list[ReconciledRow]:  # pragma: no cover (tested via callers)
        # Not stored on the model; callers receive ReconciledRow events
        # directly via the return value of reconcile().
        raise NotImplementedError("Use reconcile() return value, not this property.")


# ── public API ────────────────────────────────────────────────────────────


def reconcile(conn: sqlite3.Connection, now_iso: str | None = None) -> list[ReconciledRow]:
    """Run reconciliation against the live ``managed_processes`` table.

    Returns one :class:`ReconciledRow` per inspected row. Caller is
    responsible for emitting WebSocket events / audit log entries based on
    the outcomes.
    """

    timestamp = now_iso or datetime.now(timezone.utc).isoformat()
    rows = conn.execute(
        "SELECT id, entity_type, entity_id, pid, cmdline "
        "FROM managed_processes "
        "WHERE stopped_at IS NULL"
    ).fetchall()

    outcomes: list[ReconciledRow] = []
    for row in rows:
        outcome = _classify(row["pid"], row["cmdline"])
        outcomes.append(
            ReconciledRow(
                process_id=row["id"],
                entity_type=row["entity_type"],
                entity_id=row["entity_id"],
                pid=row["pid"],
                outcome=outcome,
            )
        )

        if outcome == ReconcileOutcome.RE_ATTACHED:
            # Leave the row alone; status stays whatever it was.
            continue

        conn.execute(
            "UPDATE managed_processes "
            "SET stopped_at = ?, stop_reason = ?, status = 'stopped' "
            "WHERE id = ?",
            (timestamp, outcome.value, row["id"]),
        )

    if outcomes:
        log.info(
            "Reconciled %d managed process row(s): %d re-attached, %d pid-recycled, %d daemon-restart",
            len(outcomes),
            sum(1 for o in outcomes if o.outcome == ReconcileOutcome.RE_ATTACHED),
            sum(1 for o in outcomes if o.outcome == ReconcileOutcome.PID_RECYCLED),
            sum(1 for o in outcomes if o.outcome == ReconcileOutcome.DAEMON_RESTART),
        )

    return outcomes


def reconcile_project_statuses(conn: sqlite3.Connection, now_iso: str | None = None) -> list[str]:
    """Reset projects stuck in a running state with no live process.

    ``reconcile()`` fixes the ``managed_processes`` rows, but a project row can
    still read ``launched`` -- e.g. the daemon was killed before ``stop()``
    ran ``_finalise_stop``. This sweep catches that: any project in
    ``launching`` / ``launched`` / ``stopping`` with no open ``managed_processes``
    row is forced back to ``stopped``. Returns the project IDs it reset.

    Run once at boot, AFTER ``reconcile()``.
    """

    timestamp = now_iso or datetime.now(timezone.utc).isoformat()
    rows = conn.execute(
        "SELECT id FROM projects "
        "WHERE deleted_at IS NULL "
        "  AND status IN ('launching', 'launched', 'stopping') "
        "  AND id NOT IN ("
        "    SELECT entity_id FROM managed_processes "
        "    WHERE stopped_at IS NULL AND entity_type = 'project'"
        "  )"
    ).fetchall()

    reset_ids: list[str] = []
    for row in rows:
        conn.execute(
            "UPDATE projects "
            "SET status = 'stopped', last_transition_at = ?, updated_at = ? "
            "WHERE id = ?",
            (timestamp, timestamp, row["id"]),
        )
        reset_ids.append(row["id"])

    if reset_ids:
        log.info("Reset %d stale project status(es) to stopped: %s", len(reset_ids), reset_ids)
    return reset_ids


def summarise(outcomes: list[ReconciledRow]) -> ReconciliationReport:
    """Roll up reconciler outcomes for the daemon's startup log."""

    report = ReconciliationReport(inspected=len(outcomes))
    for o in outcomes:
        bucket = {
            ReconcileOutcome.RE_ATTACHED: report.re_attached,
            ReconcileOutcome.PID_RECYCLED: report.pid_recycled,
            ReconcileOutcome.DAEMON_RESTART: report.daemon_restart,
        }[o.outcome]
        bucket.append(o.process_id)
    return report


# ── internals ─────────────────────────────────────────────────────────────


def _classify(pid: int, recorded_cmdline: str) -> ReconcileOutcome:
    """Compare the live process at ``pid`` to the cmdline we recorded."""

    if not psutil.pid_exists(pid):
        return ReconcileOutcome.DAEMON_RESTART

    try:
        live_argv = psutil.Process(pid).cmdline()
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
        return ReconcileOutcome.DAEMON_RESTART

    live_cmdline = " ".join(live_argv)
    if _cmdline_matches(live_cmdline, recorded_cmdline):
        return ReconcileOutcome.RE_ATTACHED
    return ReconcileOutcome.PID_RECYCLED


def _cmdline_matches(live: str, recorded: str) -> bool:
    """Tolerant comparison — Windows reorders quoting between launch + inspect.

    Exact match preferred; otherwise compare the basename + first argv element
    which is enough to tell ``npm start`` from ``firefox.exe``.
    """

    if live == recorded:
        return True
    return _signature(live) == _signature(recorded)


def _signature(cmdline: str) -> tuple[str, ...]:
    """First two tokens, lower-cased, no path. Robust to path differences."""

    parts = cmdline.split()
    head = tuple(p.split("/")[-1].split("\\")[-1].lower() for p in parts[:2])
    return head
