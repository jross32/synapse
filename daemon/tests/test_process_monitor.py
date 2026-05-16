"""Milestone E -- watcher, heartbeat, auto-restart, log tail.

Contracts #2 (status), #3 (logs), #18 (restart policy), #19 (heartbeat).
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

from synapse_daemon.models import AuditSource, EntityStatus
from synapse_daemon.process_manager import ProcessManager
from synapse_daemon.projects import Project, ProjectUpdate, create, get, update
from synapse_daemon.restart_policy import RestartPolicy
from synapse_daemon.storage import Storage
from synapse_daemon.ws import EventBus

CLEAN_EXIT = f'{sys.executable} -c "import sys; sys.exit(0)"'
CRASH_EXIT = f'{sys.executable} -c "import sys; sys.exit(7)"'
LONG_RUN = f'{sys.executable} -c "import time; time.sleep(60)"'


def _setup(tmp_path: Path, launch_cmd: str):
    s = Storage(tmp_path / "data")
    s.open()
    s.migrate()
    bus = EventBus()
    pm = ProcessManager(s, bus)
    proj_dir = tmp_path / "proj"
    proj_dir.mkdir()
    with s.transaction() as conn:
        create(conn, Project(
            id="probe", name="Probe", path=str(proj_dir), launch_cmd=launch_cmd,
        ))
    return s, bus, pm


async def _wait_until(predicate, timeout=12.0, interval=0.2):
    """Poll predicate() until true or timeout. Returns the bool result."""

    elapsed = 0.0
    while elapsed < timeout:
        if predicate():
            return True
        await asyncio.sleep(interval)
        elapsed += interval
    return predicate()


# ── watcher: unexpected exit classification ─────────────────────────────


@pytest.mark.asyncio
async def test_clean_exit_transitions_to_stopped(tmp_path: Path) -> None:
    s, bus, pm = _setup(tmp_path, CLEAN_EXIT)
    try:
        await pm.launch("probe", source=AuditSource.DESKTOP)
        # The process exits ~immediately; watcher should mark it stopped.
        ok = await _wait_until(lambda: get(s.conn, "probe").status == EntityStatus.STOPPED)
        assert ok, f"expected stopped, got {get(s.conn, 'probe').status}"
        assert not pm.is_running("probe")
    finally:
        pm.shutdown()
        s.close()


@pytest.mark.asyncio
async def test_crash_transitions_to_error_with_exit_code(tmp_path: Path) -> None:
    s, bus, pm = _setup(tmp_path, CRASH_EXIT)
    try:
        await pm.launch("probe", source=AuditSource.DESKTOP)
        ok = await _wait_until(lambda: get(s.conn, "probe").status == EntityStatus.ERROR)
        assert ok, f"expected error, got {get(s.conn, 'probe').status}"
        proj = get(s.conn, "probe")
        assert proj.last_error is not None
        assert proj.last_error.code == "project.crashed"
        assert "7" in proj.last_error.message
    finally:
        pm.shutdown()
        s.close()


@pytest.mark.asyncio
async def test_intentional_stop_does_not_trigger_crash_path(tmp_path: Path) -> None:
    s, bus, pm = _setup(tmp_path, LONG_RUN)
    try:
        await pm.launch("probe", source=AuditSource.DESKTOP)
        await asyncio.sleep(0.5)
        await pm.stop("probe", source=AuditSource.DESKTOP)
        # Give the watcher a moment; it must NOT flip the status to error.
        await asyncio.sleep(1.0)
        assert get(s.conn, "probe").status == EntityStatus.STOPPED
    finally:
        pm.shutdown()
        s.close()


# ── auto-restart (Contract #18) ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_crash_with_on_failure_policy_auto_restarts(tmp_path: Path) -> None:
    s, bus, pm = _setup(tmp_path, CRASH_EXIT)
    try:
        # on-failure, 1 retry, 1s backoff -> one restart attempt then exhausted.
        with s.transaction() as conn:
            update(conn, "probe", ProjectUpdate(
                restart=RestartPolicy(mode="on-failure", max_retries=1,
                                      initial_backoff_seconds=1, max_backoff_seconds=2),
            ))

        restart_events: list[str] = []
        async def collect(evt):
            if evt.name.startswith("v1.project."):
                restart_events.append(evt.name)
        await bus.subscribe(collect)

        await pm.launch("probe", source=AuditSource.DESKTOP)
        # Wait long enough for: crash -> schedule -> 1s backoff -> restart -> crash -> exhausted.
        await _wait_until(lambda: "v1.project.restart_exhausted" in restart_events, timeout=15.0)

        assert "v1.project.restart_scheduled" in restart_events
        assert "v1.project.restart_exhausted" in restart_events

        # The audit log should record at least one restart attempt.
        rows = s.conn.execute(
            "SELECT action FROM audit_log WHERE entity_id='probe' AND action='restart.attempt'"
        ).fetchall()
        assert len(rows) >= 1
    finally:
        pm.shutdown()
        s.close()


@pytest.mark.asyncio
async def test_crash_with_never_policy_does_not_restart(tmp_path: Path) -> None:
    s, bus, pm = _setup(tmp_path, CRASH_EXIT)
    try:
        # Default policy is "never".
        scheduled: list[str] = []
        async def collect(evt):
            if evt.name == "v1.project.restart_scheduled":
                scheduled.append(evt.name)
        await bus.subscribe(collect)

        await pm.launch("probe", source=AuditSource.DESKTOP)
        await _wait_until(lambda: get(s.conn, "probe").status == EntityStatus.ERROR)
        await asyncio.sleep(1.5)
        assert scheduled == []
    finally:
        pm.shutdown()
        s.close()


# ── heartbeat sampling (Contract #19) ────────────────────────────────────


@pytest.mark.asyncio
async def test_sample_returns_resource_snapshot(tmp_path: Path) -> None:
    s, bus, pm = _setup(tmp_path, LONG_RUN)
    try:
        await pm.launch("probe", source=AuditSource.DESKTOP)
        live = pm._live["probe"]
        snap = pm._sample("probe", live)
        assert snap is not None
        assert snap.entity_id == "probe"
        assert snap.pid == live.process.pid
        assert snap.rss_mb > 0  # a running python process uses memory
        assert snap.cpu_percent >= 0.0
    finally:
        await pm.stop("probe", source=AuditSource.DESKTOP)
        pm.shutdown()
        s.close()


@pytest.mark.asyncio
async def test_heartbeat_loop_broadcasts_process_heartbeat(tmp_path: Path) -> None:
    s, bus, pm = _setup(tmp_path, LONG_RUN)
    try:
        heartbeats: list[dict] = []
        async def collect(evt):
            if evt.name == "v1.process.heartbeat":
                heartbeats.append(evt.payload)
        await bus.subscribe(collect)

        await pm.launch("probe", source=AuditSource.DESKTOP)
        pm.start_monitoring()
        await _wait_until(lambda: len(heartbeats) >= 1, timeout=8.0)

        assert heartbeats, "expected at least one v1.process.heartbeat"
        procs = heartbeats[-1]["processes"]
        assert any(p["entity_id"] == "probe" for p in procs)
    finally:
        await pm.stop("probe", source=AuditSource.DESKTOP)
        pm.shutdown()
        s.close()


# ── log tail (Contract #3) ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_tail_log_returns_process_output(tmp_path: Path) -> None:
    # Run a real script file rather than `python -c "..."` — nested quotes
    # through cmd.exe shell=True are fragile, and real launch commands
    # (npm start, python app.py) never have that problem.
    s, bus, pm = _setup(tmp_path, f'{sys.executable} printer.py')
    (tmp_path / "proj" / "printer.py").write_text(
        "print('hello-from-synapse')\n", encoding="utf-8"
    )
    try:
        await pm.launch("probe", source=AuditSource.DESKTOP)
        await _wait_until(lambda: get(s.conn, "probe").status != EntityStatus.LAUNCHED)
        await asyncio.sleep(0.5)
        result = pm.tail_log("probe", max_lines=50)
        assert result["log_path"] is not None
        joined = "\n".join(result["lines"])
        assert "hello-from-synapse" in joined
    finally:
        pm.shutdown()
        s.close()


@pytest.mark.asyncio
async def test_tail_log_empty_for_never_launched(tmp_path: Path) -> None:
    s, bus, pm = _setup(tmp_path, LONG_RUN)
    try:
        result = pm.tail_log("probe", max_lines=50)
        assert result["log_path"] is None
        assert result["lines"] == []
        assert result["total_lines"] == 0
    finally:
        pm.shutdown()
        s.close()
