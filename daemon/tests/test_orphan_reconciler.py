"""Contract #6 — daemon orphan reconciliation."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import patch

from synapse_daemon.orphan_reconciler import (
    ReconcileOutcome,
    ReconciledRow,
    reconcile,
    summarise,
)
from synapse_daemon.storage import Storage


def _seed_managed_process(
    storage: Storage,
    *,
    entity_id: str,
    pid: int,
    cmdline: str,
) -> int:
    """Insert one ``managed_processes`` row and return its PK."""

    with storage.transaction() as conn:
        # Need a project row to satisfy nothing — managed_processes has no FK
        # to projects in migration 001, so we can insert directly.
        cursor = conn.execute(
            "INSERT INTO managed_processes "
            "(entity_type, entity_id, pid, cmdline, started_at, log_path, status) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("project", entity_id, pid, cmdline, "2026-05-13T00:00:00+00:00",
             "data/logs/x.log", "launched"),
        )
        return cursor.lastrowid


def _open(tmp_path: Path) -> Storage:
    s = Storage(tmp_path / "data")
    s.open()
    s.migrate()
    return s


def test_empty_table_returns_empty_outcomes(tmp_path: Path) -> None:
    s = _open(tmp_path)
    try:
        assert reconcile(s.conn) == []
    finally:
        s.close()


def test_dead_pid_marked_daemon_restart(tmp_path: Path) -> None:
    s = _open(tmp_path)
    try:
        # PID 1 on Windows is reserved; pick something almost-certainly free.
        dead_pid = 999_999
        pk = _seed_managed_process(s, entity_id="wbscrper", pid=dead_pid, cmdline="npm start")

        with patch("synapse_daemon.orphan_reconciler.psutil.pid_exists", return_value=False):
            outcomes = reconcile(s.conn)

        assert len(outcomes) == 1
        assert outcomes[0].outcome == ReconcileOutcome.DAEMON_RESTART
        assert outcomes[0].process_id == pk

        row = s.conn.execute(
            "SELECT stop_reason, stopped_at, status FROM managed_processes WHERE id = ?",
            (pk,),
        ).fetchone()
        assert row["stop_reason"] == "daemon-restart"
        assert row["stopped_at"] is not None
        assert row["status"] == "stopped"
    finally:
        s.close()


def test_alive_matching_cmdline_re_attaches_without_writing(tmp_path: Path) -> None:
    s = _open(tmp_path)
    try:
        pk = _seed_managed_process(s, entity_id="self", pid=os.getpid(), cmdline=sys.executable)

        with patch(
            "synapse_daemon.orphan_reconciler.psutil.Process"
        ) as proc_cls:
            proc_cls.return_value.cmdline.return_value = [sys.executable]
            with patch(
                "synapse_daemon.orphan_reconciler.psutil.pid_exists",
                return_value=True,
            ):
                outcomes = reconcile(s.conn)

        assert outcomes[0].outcome == ReconcileOutcome.RE_ATTACHED

        # Row should be untouched — stopped_at still NULL.
        row = s.conn.execute(
            "SELECT stopped_at, status FROM managed_processes WHERE id = ?",
            (pk,),
        ).fetchone()
        assert row["stopped_at"] is None
        assert row["status"] == "launched"
    finally:
        s.close()


def test_alive_but_different_cmdline_marks_pid_recycled(tmp_path: Path) -> None:
    s = _open(tmp_path)
    try:
        pk = _seed_managed_process(
            s, entity_id="wbscrper", pid=12345, cmdline="node start.js"
        )

        with patch(
            "synapse_daemon.orphan_reconciler.psutil.Process"
        ) as proc_cls:
            proc_cls.return_value.cmdline.return_value = ["chrome.exe", "--no-sandbox"]
            with patch(
                "synapse_daemon.orphan_reconciler.psutil.pid_exists",
                return_value=True,
            ):
                outcomes = reconcile(s.conn)

        assert outcomes[0].outcome == ReconcileOutcome.PID_RECYCLED
        row = s.conn.execute(
            "SELECT stop_reason FROM managed_processes WHERE id = ?", (pk,)
        ).fetchone()
        assert row["stop_reason"] == "pid-recycled"
    finally:
        s.close()


def test_summarise_buckets_outcomes_correctly() -> None:
    outcomes = [
        ReconciledRow(1, "project", "a", 1, ReconcileOutcome.RE_ATTACHED),
        ReconciledRow(2, "project", "b", 2, ReconcileOutcome.PID_RECYCLED),
        ReconciledRow(3, "project", "c", 3, ReconcileOutcome.DAEMON_RESTART),
        ReconciledRow(4, "project", "d", 4, ReconcileOutcome.DAEMON_RESTART),
    ]
    report = summarise(outcomes)
    assert report.inspected == 4
    assert report.re_attached == [1]
    assert report.pid_recycled == [2]
    assert report.daemon_restart == [3, 4]
