"""ProcessManager — spawns + tracks managed child processes (Contracts #2, #3, #6).

Responsibilities:

  • ``launch(project_id, source)`` — transition the project to LAUNCHING,
    spawn its ``launch_cmd`` detached with stdout/stderr teed to a per-spawn
    log file (Contract #3), record a ``managed_processes`` row, transition
    to LAUNCHED on success or ERROR on spawn failure.
  • ``stop(project_id, source)`` — find the live row for the project, send
    SIGTERM (Windows: terminate), update the row + project status.
  • ``status_of(project_id)`` — cheap in-memory lookup of the current PID.

Every state transition writes the audit log (Contract #11) and emits a
WebSocket event (Contract #5) so the UI tile updates without polling.

The auto-detection of crashes (poll Popen.poll() / wait_for_exit) is added
in Milestone E together with the heartbeat broadcaster. Milestone D ships
launch + stop + audit + WS events; clean-exit tracking is a Round-2 follow-up.
"""

from __future__ import annotations

import logging
import shlex
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import IO

import psutil

from . import projects as projects_module
from .api_versions import event_name
from .audit import AuditRecord, audit
from .errors import SynapseError, conflict, invalid
from .models import AuditSource, EntityStatus, ErrorRef
from .process_log import new_log_path
from .storage import Storage
from .time_utils import to_iso, utc_now
from .ws import EventBus

log = logging.getLogger(__name__)


@dataclass
class _LiveChild:
    """In-memory record of a child this process is currently tracking."""

    project_id: str
    process: subprocess.Popen
    log_file: IO[bytes]
    log_path: Path
    managed_process_row_id: int


class ProcessManager:
    """Owns the spawn / stop / state-transition flow for managed projects."""

    def __init__(self, storage: Storage, bus: EventBus) -> None:
        self._storage = storage
        self._bus = bus
        self._live: dict[str, _LiveChild] = {}

    # ── public API ──────────────────────────────────────────────────────

    async def launch(self, project_id: str, *, source: AuditSource = AuditSource.AUTO) -> None:
        """Spawn the project's launch_cmd. Idempotent: already-running raises."""

        if project_id in self._live:
            raise conflict("project", f"Project '{project_id}' is already running.")

        project = projects_module.get(self._storage.conn, project_id)

        if not project.launch_cmd.strip():
            raise invalid("project", f"Project '{project_id}' has no launch_cmd.")

        # Transition: idle/stopped → launching.
        with self._storage.transaction() as conn:
            projects_module.set_status(conn, project_id, status=EntityStatus.LAUNCHING)
            audit(
                conn,
                AuditRecord(
                    entity_type="project",
                    entity_id=project_id,
                    action="launch.attempt",
                    source=source,
                    result="success",
                ),
            )
        await self._bus.publish(
            event_name("project", "launching"),
            {"id": project_id, "source": source.value},
        )

        # Resolve log file + spawn.
        log_path = new_log_path(self._storage.data_dir, project_id)
        try:
            log_file = log_path.open("ab", buffering=0)
        except OSError as exc:
            await self._fail(project_id, code="project.log_open_failed", message=str(exc), source=source)
            return

        try:
            proc = self._spawn(project.path, project.launch_cmd, project.env, log_file)
        except OSError as exc:
            log_file.close()
            await self._fail(
                project_id,
                code="project.spawn_failed",
                message=f"Failed to spawn '{project.launch_cmd}' in {project.path!r}: {exc}",
                source=source,
            )
            return

        cmdline = " ".join(self._argv_for_record(project.launch_cmd))
        with self._storage.transaction() as conn:
            row_id = self._record_managed_process(
                conn,
                project_id=project_id,
                pid=proc.pid,
                cmdline=cmdline,
                log_path=log_path,
            )
            projects_module.set_status(conn, project_id, status=EntityStatus.LAUNCHED)
            audit(
                conn,
                AuditRecord(
                    entity_type="project",
                    entity_id=project_id,
                    action="launch",
                    source=source,
                    result="success",
                    details={"pid": proc.pid, "log_path": str(log_path)},
                ),
            )

        self._live[project_id] = _LiveChild(
            project_id=project_id,
            process=proc,
            log_file=log_file,
            log_path=log_path,
            managed_process_row_id=row_id,
        )

        await self._bus.publish(
            event_name("project", "launched"),
            {"id": project_id, "pid": proc.pid, "log_path": str(log_path)},
        )

    async def stop(self, project_id: str, *, source: AuditSource = AuditSource.AUTO) -> None:
        live = self._live.get(project_id)
        if live is None:
            # Maybe the row outlived the in-memory cache (e.g. daemon restart).
            row_id = self._find_active_row(project_id)
            if row_id is None:
                raise conflict("project", f"Project '{project_id}' is not running.")
            # Mark stopped without trying to kill (we have no Popen handle).
            await self._finalise_stop(project_id, row_id, reason="user", source=source)
            return

        with self._storage.transaction() as conn:
            projects_module.set_status(conn, project_id, status=EntityStatus.STOPPING)
            audit(
                conn,
                AuditRecord(
                    entity_type="project",
                    entity_id=project_id,
                    action="stop.attempt",
                    source=source,
                    result="success",
                ),
            )
        await self._bus.publish(
            event_name("project", "stopping"),
            {"id": project_id, "source": source.value},
        )

        # Send terminate, fall back to kill after grace period.
        try:
            proc = live.process
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                log.warning("Project '%s' did not exit on terminate; killing.", project_id)
                proc.kill()
                proc.wait(timeout=2)
        except psutil.NoSuchProcess:
            pass
        except Exception as exc:
            log.exception("Error stopping project '%s'", project_id)
            await self._fail(
                project_id,
                code="project.stop_failed",
                message=str(exc),
                source=source,
            )
            return
        finally:
            self._cleanup(project_id)

        await self._finalise_stop(project_id, live.managed_process_row_id, reason="user", source=source)

    def status_of(self, project_id: str) -> int | None:
        """Live PID if we're tracking the project, else None."""

        live = self._live.get(project_id)
        return live.process.pid if live else None

    def shutdown(self) -> None:
        """Best-effort cleanup of file handles on daemon exit.

        We do NOT kill running children here — Contract #6 wants them to
        survive daemon restart. The orphan reconciler picks them up next boot.
        """

        for project_id in list(self._live.keys()):
            self._cleanup(project_id)

    # ── internals ───────────────────────────────────────────────────────

    def _spawn(
        self,
        cwd: str,
        cmd: str,
        env_vars: list,
        log_file: IO[bytes],
    ) -> subprocess.Popen:
        """Spawn the child with platform-appropriate detachment."""

        is_windows = sys.platform == "win32"

        # On Windows the most reliable way to launch tools shipped as .cmd
        # batch wrappers (npm, yarn, etc.) is shell=True. The launch_cmd
        # comes from operator-controlled data in our DB, not user input from
        # a request, so command injection is not a meaningful threat here.
        if is_windows:
            args: list[str] | str = cmd
            shell = True
            creationflags = (
                subprocess.CREATE_NEW_PROCESS_GROUP
                | getattr(subprocess, "DETACHED_PROCESS", 0)
            )
            kwargs: dict = {"creationflags": creationflags}
        else:
            args = shlex.split(cmd)
            shell = False
            kwargs = {"start_new_session": True}

        env = self._resolve_env(env_vars)

        return subprocess.Popen(
            args,
            cwd=cwd,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            shell=shell,
            env=env,
            **kwargs,
        )

    def _resolve_env(self, env_vars: list) -> dict[str, str] | None:
        """Build the child's environment from project env + parent env."""

        if not env_vars:
            return None  # inherit parent env unchanged

        import os
        merged = dict(os.environ)
        for var in env_vars:
            if var.value is None:
                continue
            # Secrets — decrypt before passing to the child.
            # (Decryption against the SecretStore wires up in Milestone J;
            # for v0.1.5 plain values pass through.)
            merged[var.key] = var.value
        return merged

    def _argv_for_record(self, cmd: str) -> list[str]:
        """How we serialise the cmdline for the ``managed_processes`` row."""

        if sys.platform == "win32":
            return [cmd]
        return shlex.split(cmd)

    def _record_managed_process(
        self,
        conn,
        *,
        project_id: str,
        pid: int,
        cmdline: str,
        log_path: Path,
    ) -> int:
        cursor = conn.execute(
            "INSERT INTO managed_processes "
            "(entity_type, entity_id, pid, cmdline, started_at, log_path, status) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("project", project_id, pid, cmdline, to_iso(utc_now()), str(log_path), "launched"),
        )
        return cursor.lastrowid

    def _find_active_row(self, project_id: str) -> int | None:
        row = self._storage.conn.execute(
            "SELECT id FROM managed_processes "
            "WHERE entity_type = 'project' AND entity_id = ? AND stopped_at IS NULL "
            "ORDER BY started_at DESC LIMIT 1",
            (project_id,),
        ).fetchone()
        return row["id"] if row else None

    async def _finalise_stop(
        self,
        project_id: str,
        row_id: int,
        *,
        reason: str,
        source: AuditSource,
    ) -> None:
        with self._storage.transaction() as conn:
            conn.execute(
                "UPDATE managed_processes "
                "SET stopped_at = ?, stop_reason = ?, status = 'stopped' "
                "WHERE id = ?",
                (to_iso(utc_now()), reason, row_id),
            )
            projects_module.set_status(conn, project_id, status=EntityStatus.STOPPED)
            audit(
                conn,
                AuditRecord(
                    entity_type="project",
                    entity_id=project_id,
                    action="stop",
                    source=source,
                    result="success",
                    details={"reason": reason},
                ),
            )
        await self._bus.publish(
            event_name("project", "stopped"),
            {"id": project_id, "reason": reason},
        )

    async def _fail(
        self,
        project_id: str,
        *,
        code: str,
        message: str,
        source: AuditSource,
    ) -> None:
        err = ErrorRef(code=code, message=message)
        with self._storage.transaction() as conn:
            projects_module.set_status(conn, project_id, status=EntityStatus.ERROR, error=err)
            audit(
                conn,
                AuditRecord(
                    entity_type="project",
                    entity_id=project_id,
                    action="launch",
                    source=source,
                    result="error",
                    error_code=code,
                    details={"message": message},
                ),
            )
        await self._bus.publish(
            event_name("project", "errored"),
            {"id": project_id, "error": err.model_dump()},
        )

    def _cleanup(self, project_id: str) -> None:
        live = self._live.pop(project_id, None)
        if live is None:
            return
        try:
            live.log_file.close()
        except Exception:
            pass
