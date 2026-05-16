"""ProcessManager — spawns, monitors + recovers managed child processes.

Contracts: #2 (live status), #3 (log capture), #6 (orphan-safe), #11 (audit),
#18 (restart policy), #19 (resource heartbeat).

Lifecycle of a managed project:

    launch()  -> LAUNCHING -> LAUNCHED   (spawn detached, log file, audit, WS)
              -> watcher task awaits the process
    stop()    -> STOPPING  -> STOPPED    (terminate the whole tree)
    crash     -> ERROR / STOPPED         (watcher detects an unexpected exit;
                                          auto-restarts if the restart policy
                                          allows — Contract #18)

While a project runs, a single heartbeat loop samples CPU% + RSS for every
live child and broadcasts ``v1.process.heartbeat`` (Contract #19).

``start_monitoring()`` / ``shutdown()`` bracket the background tasks; the
FastAPI lifespan owns that pairing.
"""

from __future__ import annotations

import asyncio
import logging
import os
import shlex
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import IO

import psutil

from . import projects as projects_module
from .api_versions import event_name
from .audit import AuditRecord, audit
from .errors import SynapseError, conflict, invalid
from .models import AuditSource, EntityStatus, ErrorRef
from .process_log import latest_log, new_log_path
from .resources import ResourceSnapshot, over_budget
from .restart_policy import next_backoff_seconds, should_restart
from .storage import Storage
from .time_utils import to_iso, utc_now
from .ws import EventBus

log = logging.getLogger(__name__)

# Contract #19 — heartbeat cadence. ~2 s keeps the UI gauges live without
# hammering psutil.
HEARTBEAT_INTERVAL_SECONDS = 2.0


@dataclass
class _LiveChild:
    """In-memory record of a child this manager is currently tracking."""

    project_id: str
    process: subprocess.Popen
    log_file: IO[bytes]
    log_path: Path
    managed_process_row_id: int
    attempt: int = 0                       # 0 = user launch; >0 = auto-restart
    expected_stop: bool = False            # set by stop() so the watcher stays quiet
    watcher_task: asyncio.Task | None = None
    # Persistent psutil handles so cpu_percent() deltas are meaningful across
    # heartbeats. Keyed by pid; refreshed each sample as the tree changes.
    psutil_cache: dict[int, psutil.Process] = field(default_factory=dict)


class ProcessManager:
    """Owns the spawn / monitor / stop / recover flow for managed projects."""

    def __init__(self, storage: Storage, bus: EventBus) -> None:
        self._storage = storage
        self._bus = bus
        self._live: dict[str, _LiveChild] = {}
        self._heartbeat_task: asyncio.Task | None = None
        self._restart_tasks: set[asyncio.Task] = set()

    # ── background lifecycle ────────────────────────────────────────────

    def start_monitoring(self) -> None:
        """Start the heartbeat loop. Call once from the FastAPI lifespan."""

        if self._heartbeat_task is None or self._heartbeat_task.done():
            self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
            log.info("ProcessManager heartbeat loop started (%.1fs).", HEARTBEAT_INTERVAL_SECONDS)

    def shutdown(self) -> None:
        """Cancel background tasks + close log handles on daemon exit.

        Managed children are NOT killed — Contract #6 wants them to survive a
        daemon restart; the orphan reconciler re-attaches them next boot.
        """

        if self._heartbeat_task is not None:
            self._heartbeat_task.cancel()
            self._heartbeat_task = None
        for task in list(self._restart_tasks):
            task.cancel()
        self._restart_tasks.clear()
        for project_id in list(self._live.keys()):
            live = self._live.get(project_id)
            if live and live.watcher_task is not None:
                live.watcher_task.cancel()
            self._cleanup(project_id)

    # ── public API ──────────────────────────────────────────────────────

    async def launch(
        self,
        project_id: str,
        *,
        source: AuditSource = AuditSource.AUTO,
        _restart_attempt: int = 0,
    ) -> None:
        """Spawn the project's launch_cmd. Idempotent: already-running raises."""

        if project_id in self._live:
            raise conflict("project", f"Project '{project_id}' is already running.")

        project = projects_module.get(self._storage.conn, project_id)

        if not project.launch_cmd.strip():
            raise invalid("project", f"Project '{project_id}' has no launch_cmd.")

        # Transition: idle/stopped/error -> launching.
        with self._storage.transaction() as conn:
            projects_module.set_status(conn, project_id, status=EntityStatus.LAUNCHING)
            audit(
                conn,
                AuditRecord(
                    entity_type="project",
                    entity_id=project_id,
                    action="launch.attempt" if _restart_attempt == 0 else "restart.attempt",
                    source=source,
                    result="success",
                    details={"attempt": _restart_attempt} if _restart_attempt else None,
                ),
            )
        await self._bus.publish(
            event_name("project", "launching"),
            {"id": project_id, "source": source.value, "attempt": _restart_attempt},
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

        child = _LiveChild(
            project_id=project_id,
            process=proc,
            log_file=log_file,
            log_path=log_path,
            managed_process_row_id=row_id,
            attempt=_restart_attempt,
        )
        self._live[project_id] = child
        child.watcher_task = asyncio.create_task(self._watch(project_id, proc))

        await self._bus.publish(
            event_name("project", "launched"),
            {"id": project_id, "pid": proc.pid, "log_path": str(log_path), "attempt": _restart_attempt},
        )

    async def stop(self, project_id: str, *, source: AuditSource = AuditSource.AUTO) -> None:
        live = self._live.get(project_id)
        if live is None:
            # Maybe the row outlived the in-memory cache (e.g. daemon restart).
            row_id = self._find_active_row(project_id)
            if row_id is None:
                raise conflict("project", f"Project '{project_id}' is not running.")
            await self._finalise_stop(project_id, row_id, reason="user", source=source)
            return

        # Tell the watcher this exit is intentional BEFORE we kill anything.
        live.expected_stop = True

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

        try:
            await asyncio.to_thread(self._terminate_tree, live.process.pid, 5.0)
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

    def is_running(self, project_id: str) -> bool:
        return project_id in self._live

    def tail_log(self, project_id: str, max_lines: int = 200) -> dict:
        """Return the most recent log file for a project (Contract #3).

        Reads the newest ``data/logs/<id>/*.log`` file. Returns a dict with
        the path, the last ``max_lines`` lines, and total line count.
        """

        path = latest_log(self._storage.data_dir, project_id)
        if path is None:
            return {"project_id": project_id, "log_path": None, "lines": [], "total_lines": 0}

        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            raise invalid("project", f"Could not read log for '{project_id}': {exc}")

        all_lines = text.splitlines()
        return {
            "project_id": project_id,
            "log_path": str(path),
            "lines": all_lines[-max_lines:],
            "total_lines": len(all_lines),
        }

    # ── watcher (Contract #18 crash detection + auto-restart) ────────────

    async def _watch(self, project_id: str, proc: subprocess.Popen) -> None:
        """Await a child's exit; classify it as expected vs unexpected."""

        try:
            exit_code = await asyncio.to_thread(proc.wait)
        except asyncio.CancelledError:
            return

        current = self._live.get(project_id)
        if current is None or current.process is not proc:
            return  # superseded by a newer launch, or already cleaned up
        if current.expected_stop:
            return  # stop() owns the state transition

        await self._handle_unexpected_exit(project_id, exit_code, current)

    async def _handle_unexpected_exit(
        self,
        project_id: str,
        exit_code: int,
        live: _LiveChild,
    ) -> None:
        """A managed process exited on its own — record it, maybe restart."""

        attempt = live.attempt
        row_id = live.managed_process_row_id
        crashed = exit_code != 0
        reason = "crashed" if crashed else "exited"

        self._cleanup(project_id)

        with self._storage.transaction() as conn:
            conn.execute(
                "UPDATE managed_processes "
                "SET stopped_at = ?, stop_reason = ?, status = 'stopped' WHERE id = ?",
                (to_iso(utc_now()), reason, row_id),
            )
            if crashed:
                err = ErrorRef(
                    code="project.crashed",
                    message=f"Process exited unexpectedly with code {exit_code}.",
                )
                projects_module.set_status(
                    conn, project_id, status=EntityStatus.ERROR, error=err
                )
            else:
                projects_module.set_status(conn, project_id, status=EntityStatus.STOPPED)
            audit(
                conn,
                AuditRecord(
                    entity_type="project",
                    entity_id=project_id,
                    action="exit",
                    source=AuditSource.AUTO,
                    result="error" if crashed else "success",
                    error_code="project.crashed" if crashed else None,
                    details={"exit_code": exit_code, "reason": reason},
                ),
            )

        event = "errored" if crashed else "stopped"
        payload: dict = {"id": project_id, "reason": reason, "exit_code": exit_code}
        if crashed:
            payload["error"] = {"code": "project.crashed", "message": f"exit code {exit_code}"}
        await self._bus.publish(event_name("project", event), payload)

        # Contract #18 — auto-restart if the policy allows.
        project = projects_module.get(self._storage.conn, project_id)
        policy = project.restart
        if should_restart(policy, exit_code, attempt):
            delay = next_backoff_seconds(policy, attempt)
            log.info(
                "Auto-restarting '%s' in %ds (attempt %d/%d).",
                project_id, delay, attempt + 1, policy.max_retries,
            )
            await self._bus.publish(
                event_name("project", "restart_scheduled"),
                {"id": project_id, "attempt": attempt + 1, "delay_seconds": delay,
                 "max_retries": policy.max_retries},
            )
            task = asyncio.create_task(self._delayed_restart(project_id, delay, attempt + 1))
            self._restart_tasks.add(task)
            task.add_done_callback(self._restart_tasks.discard)
        elif crashed and policy.mode != "never" and attempt >= policy.max_retries:
            await self._bus.publish(
                event_name("project", "restart_exhausted"),
                {"id": project_id, "attempts": attempt, "max_retries": policy.max_retries},
            )

    async def _delayed_restart(self, project_id: str, delay: int, attempt: int) -> None:
        try:
            await asyncio.sleep(delay)
        except asyncio.CancelledError:
            return
        if project_id in self._live:
            return  # someone launched it manually in the meantime
        try:
            await self.launch(project_id, source=AuditSource.AUTO, _restart_attempt=attempt)
        except SynapseError as exc:
            log.warning("Auto-restart of '%s' failed: %s", project_id, exc.envelope.message)

    # ── heartbeat (Contract #19) ─────────────────────────────────────────

    async def _heartbeat_loop(self) -> None:
        """Sample CPU% + RSS for every live child and broadcast it."""

        while True:
            try:
                await asyncio.sleep(HEARTBEAT_INTERVAL_SECONDS)
                snapshots = []
                budget_warnings = []
                for project_id, live in list(self._live.items()):
                    snap = self._sample(project_id, live)
                    if snap is None:
                        continue
                    snapshots.append(snap)
                    breaches = self._check_budget(project_id, snap)
                    if breaches:
                        budget_warnings.append({"id": project_id, "breached": breaches})
                if snapshots:
                    await self._bus.publish(
                        event_name("process", "heartbeat"),
                        {
                            "processes": [s.model_dump(mode="json") for s in snapshots],
                            "over_budget": budget_warnings,
                        },
                    )
            except asyncio.CancelledError:
                break
            except Exception:  # pragma: no cover — defensive; loop must not die
                log.exception("Heartbeat loop iteration failed.")

    def _sample(self, project_id: str, live: _LiveChild) -> ResourceSnapshot | None:
        """Sum CPU% + RSS across a managed process and all its descendants."""

        root_pid = live.process.pid
        try:
            root = live.psutil_cache.get(root_pid)
            if root is None:
                root = psutil.Process(root_pid)
                live.psutil_cache[root_pid] = root
            tree = [root, *root.children(recursive=True)]
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return None

        cpu_total = 0.0
        rss_total = 0
        seen: set[int] = set()
        for proc in tree:
            pid = proc.pid
            seen.add(pid)
            cached = live.psutil_cache.get(pid)
            if cached is None:
                cached = proc
                live.psutil_cache[pid] = cached
            try:
                # interval=None: non-blocking, delta since the last call on
                # this same object. First call per pid returns 0.0.
                cpu_total += cached.cpu_percent(interval=None)
                rss_total += cached.memory_info().rss
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        # Drop cache entries for processes that have exited.
        for stale in [p for p in live.psutil_cache if p not in seen]:
            live.psutil_cache.pop(stale, None)

        return ResourceSnapshot(
            entity_type="project",
            entity_id=project_id,
            pid=root_pid,
            cpu_percent=round(cpu_total, 1),
            rss_mb=round(rss_total / (1024 * 1024), 1),
        )

    def _check_budget(self, project_id: str, snap: ResourceSnapshot) -> list[str]:
        try:
            project = projects_module.get(self._storage.conn, project_id)
        except SynapseError:
            return []
        return over_budget(project.resource_caps, snap)

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
        #
        # Flags: CREATE_NEW_PROCESS_GROUP isolates the child's process group;
        # CREATE_NO_WINDOW hides the console so no cmd windows flash.
        # We deliberately do NOT use DETACHED_PROCESS -- with shell=True it
        # breaks stdout/stderr redirection (cmd.exe drops the inherited
        # handles when it has no console at all), which silently emptied
        # every process log file. CREATE_NO_WINDOW gives a hidden console
        # so the redirected handles are honoured. The child still outlives
        # the daemon (no Job Object binds it) -- Contract #6 holds.
        if is_windows:
            args: list[str] | str = cmd
            shell = True
            creationflags = (
                subprocess.CREATE_NEW_PROCESS_GROUP
                | getattr(subprocess, "CREATE_NO_WINDOW", 0)
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

        merged = dict(os.environ)
        for var in env_vars:
            if var.value is None:
                continue
            # Secrets — decrypt before passing to the child.
            # (Decryption against the SecretStore wires up in Milestone J;
            # for now plain values pass through.)
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
            {"id": project_id, "error": err.model_dump(mode="json")},
        )

    def _terminate_tree(self, root_pid: int, grace_seconds: float = 5.0) -> None:
        """Terminate a process and every descendant.

        Windows ``shell=True`` spawns put ``cmd.exe`` at the root with the
        real workload (npm -> node, python -> child, etc.) as grandchildren.
        Killing only the root orphans them — that's the bug where wbscrper's
        ``node.exe`` kept holding port 12345 after Stop. We collect the whole
        tree *before* terminating anything (children get reparented once the
        root dies), then escalate terminate -> kill.
        """

        try:
            root = psutil.Process(root_pid)
        except psutil.NoSuchProcess:
            return

        procs = [root]
        try:
            procs.extend(root.children(recursive=True))
        except psutil.NoSuchProcess:
            pass

        for proc in procs:
            try:
                proc.terminate()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

        _gone, alive = psutil.wait_procs(procs, timeout=grace_seconds)
        if alive:
            log.warning(
                "%d process(es) survived terminate; escalating to kill.", len(alive)
            )
        for proc in alive:
            try:
                proc.kill()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        psutil.wait_procs(alive, timeout=2.0)

    def _cleanup(self, project_id: str) -> None:
        live = self._live.pop(project_id, None)
        if live is None:
            return
        try:
            live.log_file.close()
        except Exception:
            pass
