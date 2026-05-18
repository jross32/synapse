"""Cloudtap — the first built-in Synapse tool (Milestone F · v0.1.9).

Enter a local port; Cloudtap spawns ``cloudflared`` as a quick tunnel and
parses the public ``*.trycloudflare.com`` URL out of its output. One tunnel
at a time. The tunnel is tied to the daemon session — :meth:`shutdown` kills
it when the daemon stops (unlike a managed project, an exposed tunnel should
never outlive its owner).

Action ids (mirror ``tools/cloudtap/manifest.json``):

  • ``tunnel`` — start a tunnel for ``fields["port"]``; blocks until the URL
                 is parsed or a timeout elapses, then returns it.
  • ``stop``   — terminate the running tunnel.
"""

from __future__ import annotations

import asyncio
import logging
import re
import shutil
import subprocess
import sys

from ..api_versions import event_name
from ..models import EntityStatus, ErrorRef, ToolState
from ..ws import EventBus
from . import ToolHandler

log = logging.getLogger(__name__)

# cloudflared prints the public URL inside a boxed banner on stderr.
_URL_RE = re.compile(r"https://[a-z0-9][a-z0-9-]*\.trycloudflare\.com")

# How long to wait for cloudflared to hand back a URL before giving up.
URL_WAIT_TIMEOUT_SECONDS = 25.0

_INSTALL_HINT = (
    "cloudflared is not on PATH. Install it from "
    "https://developers.cloudflare.com/cloudflare-one/connections/"
    "connect-networks/downloads/"
)


class CloudtapTool(ToolHandler):
    """Manages a single ``cloudflared`` quick tunnel."""

    tool_id = "cloudtap"

    def __init__(self, bus: EventBus) -> None:
        self._bus = bus
        self._proc: asyncio.subprocess.Process | None = None
        self._reader_task: asyncio.Task | None = None
        self._url_event = asyncio.Event()
        self._public_url: str | None = None
        self._port: int | None = None
        self._status: EntityStatus = EntityStatus.IDLE
        self._error: ErrorRef | None = None
        self._message: str | None = None
        self._expected_stop = False

    # ── ToolHandler API ──────────────────────────────────────────────────

    def state(self) -> ToolState:
        result: dict = {}
        if self._public_url:
            result["public_url"] = self._public_url
        if self._port is not None:
            result["local_port"] = self._port
        return ToolState(
            tool_id=self.tool_id,
            status=self._status,
            fields={"port": self._port} if self._port is not None else {},
            result=result,
            message=self._message,
            last_error=self._error,
        )

    async def run_action(self, action_id: str, fields: dict) -> ToolState:
        if action_id == "tunnel":
            return await self._start(fields)
        if action_id == "stop":
            return await self._stop(expected=True)
        self._fail("cloudtap.unknown_action", f"Cloudtap has no action '{action_id}'.")
        return self.state()

    async def shutdown(self) -> None:
        if self._proc is not None and self._proc.returncode is None:
            log.info("Cloudtap: closing tunnel on daemon shutdown.")
            await self._stop(expected=True)

    # ── start ────────────────────────────────────────────────────────────

    async def _start(self, fields: dict) -> ToolState:
        if self._proc is not None and self._proc.returncode is None:
            self._fail(
                "cloudtap.already_running",
                "A Cloudtap tunnel is already open. Stop it before starting another.",
            )
            return self.state()

        port = self._coerce_port(fields.get("port"))
        if port is None:
            return self.state()

        exe = shutil.which("cloudflared")
        if exe is None:
            self._fail("cloudtap.not_installed", _INSTALL_HINT)
            return self.state()

        self._reset_run_state(port)

        creationflags = 0
        if sys.platform == "win32":
            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)

        try:
            self._proc = await asyncio.create_subprocess_exec(
                exe,
                "tunnel",
                "--url",
                f"http://localhost:{port}",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                stdin=asyncio.subprocess.DEVNULL,
                creationflags=creationflags,
            )
        except OSError as exc:
            self._fail("cloudtap.spawn_failed", f"Could not start cloudflared: {exc}")
            return self.state()

        self._reader_task = asyncio.create_task(self._read_output())

        try:
            await asyncio.wait_for(
                self._url_event.wait(), timeout=URL_WAIT_TIMEOUT_SECONDS
            )
        except TimeoutError:
            await self._kill_proc()
            self._fail(
                "cloudtap.no_url",
                f"cloudflared did not return a tunnel URL within "
                f"{int(URL_WAIT_TIMEOUT_SECONDS)}s. Is something serving on port {port}?",
            )
            return self.state()

        if self._public_url is None:
            # The reader signalled the event because the process exited first.
            self._fail(
                "cloudtap.spawn_failed",
                "cloudflared exited before a tunnel URL appeared.",
            )
            return self.state()

        self._status = EntityStatus.LAUNCHED
        self._error = None
        self._message = f"Tunnel live for localhost:{port}"
        await self._bus.publish(
            event_name("tool", "tunnel_opened"),
            {"tool_id": self.tool_id, "public_url": self._public_url, "local_port": port},
        )
        log.info("Cloudtap: tunnel open %s -> localhost:%d", self._public_url, port)
        return self.state()

    # ── stop ─────────────────────────────────────────────────────────────

    async def _stop(self, *, expected: bool) -> ToolState:
        if self._proc is None or self._proc.returncode is not None:
            self._status = EntityStatus.STOPPED
            self._message = "No tunnel was running."
            return self.state()

        self._expected_stop = expected
        await self._kill_proc()
        self._status = EntityStatus.STOPPED
        self._error = None
        self._message = "Tunnel closed."
        closed_url = self._public_url
        self._public_url = None
        await self._bus.publish(
            event_name("tool", "tunnel_closed"),
            {"tool_id": self.tool_id, "public_url": closed_url},
        )
        return self.state()

    # ── output reader ────────────────────────────────────────────────────

    async def _read_output(self) -> None:
        """Scan cloudflared output for the tunnel URL; watch for early exit."""

        proc = self._proc
        if proc is None or proc.stdout is None:
            return
        try:
            while True:
                raw = await proc.stdout.readline()
                if not raw:
                    break
                text = raw.decode("utf-8", errors="replace")
                if self._public_url is None:
                    match = _URL_RE.search(text)
                    if match:
                        self._public_url = match.group(0)
                        self._url_event.set()
        except asyncio.CancelledError:
            return
        finally:
            # stdout closed -> the process is exiting. Unblock any waiter.
            if not self._url_event.is_set():
                self._url_event.set()
            await self._handle_exit()

    async def _handle_exit(self) -> None:
        """The cloudflared process ended. Classify expected vs. crash."""

        proc = self._proc
        if proc is None:
            return
        try:
            await proc.wait()
        except Exception:  # pragma: no cover — defensive
            pass

        if self._expected_stop:
            return  # _stop() owns the state transition
        if self._status != EntityStatus.LAUNCHED:
            return  # start() will report its own failure

        # The tunnel was live and cloudflared died on its own.
        self._status = EntityStatus.ERROR
        self._error = ErrorRef(
            code="cloudtap.tunnel_dropped",
            message=f"cloudflared exited unexpectedly (code {proc.returncode}).",
        )
        self._message = None
        dropped_url = self._public_url
        self._public_url = None
        await self._bus.publish(
            event_name("tool", "tunnel_closed"),
            {"tool_id": self.tool_id, "public_url": dropped_url, "reason": "dropped"},
        )

    # ── helpers ──────────────────────────────────────────────────────────

    async def _kill_proc(self) -> None:
        proc = self._proc
        if proc is None or proc.returncode is not None:
            return
        try:
            proc.terminate()
        except ProcessLookupError:
            return
        try:
            await asyncio.wait_for(proc.wait(), timeout=5.0)
        except TimeoutError:
            try:
                proc.kill()
            except ProcessLookupError:
                pass
        if self._reader_task is not None:
            self._reader_task.cancel()

    def _reset_run_state(self, port: int) -> None:
        self._url_event = asyncio.Event()
        self._public_url = None
        self._port = port
        self._status = EntityStatus.LAUNCHING
        self._error = None
        self._message = None
        self._expected_stop = False

    def _coerce_port(self, value: object) -> int | None:
        try:
            port = int(value)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            self._fail("cloudtap.bad_port", "Port must be a whole number.")
            return None
        if not (1 <= port <= 65535):
            self._fail("cloudtap.bad_port", "Port must be between 1 and 65535.")
            return None
        return port

    def _fail(self, code: str, message: str) -> None:
        self._status = EntityStatus.ERROR
        self._error = ErrorRef(code=code, message=message)
        self._message = None
