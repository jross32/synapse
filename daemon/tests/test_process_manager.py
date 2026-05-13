"""Contracts #2, #3, #6, #11 — ProcessManager spawn / stop flow."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

from synapse_daemon.errors import SynapseError
from synapse_daemon.models import AuditSource, EntityStatus
from synapse_daemon.process_manager import ProcessManager
from synapse_daemon.projects import Project, create, get
from synapse_daemon.storage import Storage
from synapse_daemon.ws import EventBus

LONG_RUNNING_CMD = f'{sys.executable} -c "import time; time.sleep(60)"'
QUICK_CMD = f'{sys.executable} -c "print(123)"'


async def _make_setup(tmp_path: Path, *, launch_cmd: str = LONG_RUNNING_CMD):
    s = Storage(tmp_path / "data")
    s.open()
    s.migrate()
    bus = EventBus()
    pm = ProcessManager(s, bus)
    project_path = tmp_path / "project"
    project_path.mkdir()
    with s.transaction() as conn:
        create(conn, Project(
            id="probe",
            name="Probe",
            path=str(project_path),
            launch_cmd=launch_cmd,
        ))
    return s, bus, pm


@pytest.mark.asyncio
async def test_launch_transitions_status_and_writes_log(tmp_path: Path) -> None:
    s, bus, pm = await _make_setup(tmp_path)
    try:
        events_received: list[tuple[str, dict]] = []
        async def collect(event):
            events_received.append((event.name, event.payload))
        await bus.subscribe(collect)

        await pm.launch("probe", source=AuditSource.DESKTOP)

        try:
            updated = get(s.conn, "probe")
            assert updated.status == EntityStatus.LAUNCHED

            # Log file was created and lives under data/logs/probe/.
            log_dir = (tmp_path / "data" / "logs" / "probe")
            assert log_dir.exists()
            logs = list(log_dir.glob("*.log"))
            assert len(logs) == 1

            # managed_processes row exists.
            row = s.conn.execute(
                "SELECT pid, status FROM managed_processes WHERE entity_id = 'probe'"
            ).fetchone()
            assert row is not None
            assert row["status"] == "launched"
            assert pm.status_of("probe") == row["pid"]

            # Audit log captured both attempt + success.
            audits = s.conn.execute(
                "SELECT action, result FROM audit_log WHERE entity_id = 'probe'"
            ).fetchall()
            actions = [(r["action"], r["result"]) for r in audits]
            assert ("launch.attempt", "success") in actions
            assert ("launch", "success") in actions

            # WebSocket events emitted in order.
            names = [n for n, _ in events_received]
            assert "v1.project.launching" in names
            assert "v1.project.launched" in names
        finally:
            await pm.stop("probe", source=AuditSource.DESKTOP)
    finally:
        pm.shutdown()
        s.close()


@pytest.mark.asyncio
async def test_double_launch_raises_conflict(tmp_path: Path) -> None:
    s, bus, pm = await _make_setup(tmp_path)
    try:
        await pm.launch("probe", source=AuditSource.DESKTOP)
        try:
            with pytest.raises(SynapseError) as exc:
                await pm.launch("probe", source=AuditSource.DESKTOP)
            assert exc.value.envelope.code == "project.conflict"
        finally:
            await pm.stop("probe", source=AuditSource.DESKTOP)
    finally:
        pm.shutdown()
        s.close()


@pytest.mark.asyncio
async def test_launch_missing_project_raises_not_found(tmp_path: Path) -> None:
    s, bus, pm = await _make_setup(tmp_path)
    try:
        with pytest.raises(SynapseError) as exc:
            await pm.launch("does-not-exist", source=AuditSource.DESKTOP)
        assert exc.value.envelope.code == "project.not_found"
    finally:
        pm.shutdown()
        s.close()


@pytest.mark.asyncio
async def test_stop_terminates_and_finalises(tmp_path: Path) -> None:
    s, bus, pm = await _make_setup(tmp_path)
    try:
        await pm.launch("probe", source=AuditSource.DESKTOP)
        live_pid = pm.status_of("probe")
        assert live_pid is not None

        await pm.stop("probe", source=AuditSource.DESKTOP)
        # PM no longer tracking it.
        assert pm.status_of("probe") is None

        proj = get(s.conn, "probe")
        assert proj.status == EntityStatus.STOPPED

        row = s.conn.execute(
            "SELECT stopped_at, stop_reason FROM managed_processes WHERE entity_id = 'probe'"
        ).fetchone()
        assert row["stopped_at"] is not None
        assert row["stop_reason"] == "user"
    finally:
        pm.shutdown()
        s.close()


@pytest.mark.asyncio
async def test_stop_when_not_running_raises_conflict(tmp_path: Path) -> None:
    s, bus, pm = await _make_setup(tmp_path)
    try:
        with pytest.raises(SynapseError) as exc:
            await pm.stop("probe", source=AuditSource.DESKTOP)
        assert exc.value.envelope.code == "project.conflict"
    finally:
        pm.shutdown()
        s.close()


@pytest.mark.asyncio
async def test_launch_with_empty_cmd_raises_invalid(tmp_path: Path) -> None:
    s = Storage(tmp_path / "data")
    s.open()
    s.migrate()
    bus = EventBus()
    pm = ProcessManager(s, bus)
    project_path = tmp_path / "project"
    project_path.mkdir()
    with s.transaction() as conn:
        # Force an empty cmd via direct DB write (Pydantic would reject this).
        conn.execute(
            "INSERT INTO projects (id, name, path, launch_cmd, status, created_at, updated_at, last_transition_at, current_health) "
            "VALUES ('empty', 'Empty', ?, '', 'idle', '2026-05-13T00:00:00+00:00', '2026-05-13T00:00:00+00:00', '2026-05-13T00:00:00+00:00', 'unknown')",
            (str(project_path),),
        )
    try:
        with pytest.raises(SynapseError) as exc:
            await pm.launch("empty", source=AuditSource.DESKTOP)
        assert exc.value.envelope.code == "project.invalid"
    finally:
        pm.shutdown()
        s.close()


@pytest.mark.asyncio
async def test_launch_records_emit_errored_on_spawn_failure(tmp_path: Path, monkeypatch) -> None:
    s, bus, pm = await _make_setup(tmp_path)
    try:
        events: list[str] = []
        async def collect(evt):
            events.append(evt.name)
        await bus.subscribe(collect)

        # Force Popen to raise OSError.
        from synapse_daemon import process_manager as pm_mod
        def boom(*args, **kwargs):
            raise OSError(13, "Permission denied")
        monkeypatch.setattr(pm_mod.subprocess, "Popen", boom)

        await pm.launch("probe", source=AuditSource.DESKTOP)

        proj = get(s.conn, "probe")
        assert proj.status == EntityStatus.ERROR
        assert proj.last_error is not None
        assert proj.last_error.code == "project.spawn_failed"
        assert "v1.project.errored" in events
    finally:
        pm.shutdown()
        s.close()
