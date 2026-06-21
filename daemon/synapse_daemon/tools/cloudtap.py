"""Cloudtap — the first built-in Synapse tool (Milestone F · v0.1.9).

Enter a local port; Cloudtap spawns ``cloudflared`` as a quick tunnel and
parses the public ``*.trycloudflare.com`` URL out of its output.

v0.1.9.5 makes Cloudtap **multi-instance**: any number of tunnels can be open
at once, each tracked as its own :class:`~synapse_daemon.models.ToolItem`
with an individual "Close" button. A tunnel is auto-labelled with the
registered project whose ``expected_port`` matches, so you can tell at a
glance which app each tunnel exposes. Tunnels are session-scoped — they are
all killed on daemon shutdown (an exposed tunnel must never outlive its
owner).

Action ids (mirror ``tools/cloudtap/manifest.json``):

  • ``tunnel`` — tool-scoped: open a new tunnel for ``fields["port"]``.
  • ``close``  — item-scoped: close the tunnel identified by ``item_id``.
"""

from __future__ import annotations

import asyncio
import logging
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime

from .. import projects as projects_module
from ..api_versions import event_name
from ..models import EntityStatus, ErrorRef, ToolItem, ToolState
from ..storage import Storage
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


def _utcnow() -> datetime:
    return datetime.now(UTC)


@dataclass
class _Tunnel:
    """One live cloudflared tunnel tracked by :class:`CloudtapTool`."""

    id: str
    port: int
    label: str
    status: EntityStatus = EntityStatus.LAUNCHING
    public_url: str | None = None
    message: str | None = None
    error: ErrorRef | None = None
    proc: asyncio.subprocess.Process | None = None
    reader_task: asyncio.Task | None = None
    url_event: asyncio.Event = field(default_factory=asyncio.Event)
    expected_stop: bool = False
    created_at: datetime = field(default_factory=_utcnow)

    def to_item(self) -> ToolItem:
        result: dict = {"local_port": self.port}
        if self.public_url:
            result["public_url"] = self.public_url
        return ToolItem(
            id=self.id,
            label=self.label,
            status=self.status,
            result=result,
            message=self.message,
            last_error=self.error,
            created_at=self.created_at,
        )


class CloudtapTool(ToolHandler):
    """Manages any number of concurrent ``cloudflared`` quick tunnels."""

    tool_id = "cloudtap"

    def __init__(self, bus: EventBus, storage: Storage | None = None) -> None:
        self._bus = bus
        self._storage = storage
        self._tunnels: dict[str, _Tunnel] = {}
        self._counter = 0
        self._tool_error: ErrorRef | None = None

    # ── ToolHandler API ──────────────────────────────────────────────────

    def state(self) -> ToolState:
        items = [t.to_item() for t in self._tunnels.values()]
        statuses = {t.status for t in self._tunnels.values()}
        if EntityStatus.LAUNCHED in statuses:
            overall = EntityStatus.LAUNCHED
        elif EntityStatus.LAUNCHING in statuses:
            overall = EntityStatus.LAUNCHING
        elif self._tool_error is not None:
            overall = EntityStatus.ERROR
        else:
            overall = EntityStatus.IDLE
        live = sum(1 for t in self._tunnels.values() if t.status == EntityStatus.LAUNCHED)
        return ToolState(
            tool_id=self.tool_id,
            status=overall,
            items=items,
            message=f"{live} tunnel(s) open" if live else None,
            last_error=self._tool_error,
        )

    async def run_action(
        self, action_id: str, fields: dict, item_id: str | None = None
    ) -> ToolState:
        self._tool_error = None  # cleared on every fresh action
        if action_id == "tunnel":
            return await self._open(fields)
        if action_id == "close":
            return await self._close(item_id)
        self._tool_error = ErrorRef(
            code="cloudtap.unknown_action",
            message=f"Cloudtap has no action '{action_id}'.",
        )
        return self.state()

    async def shutdown(self) -> None:
        for tunnel in list(self._tunnels.values()):
            if tunnel.proc is not None and tunnel.proc.returncode is None:
                log.info("Cloudtap: closing tunnel '%s' on daemon shutdown.", tunnel.id)
                tunnel.expected_stop = True
                await self._kill(tunnel)
        self._tunnels.clear()

    # ── open ─────────────────────────────────────────────────────────────

    async def _open(self, fields: dict) -> ToolState:
        port = self._coerce_port(fields.get("port"))
        if port is None:
            return self.state()

        exe = shutil.which("cloudflared")
        if exe is None:
            self._tool_error = ErrorRef(code="cloudtap.not_installed", message=_INSTALL_HINT)
            return self.state()

        self._counter += 1
        tunnel = _Tunnel(
            id=f"t{self._counter}",
            port=port,
            label=self._label_for_port(port),
        )
        self._tunnels[tunnel.id] = tunnel

        creationflags = 0
        if sys.platform == "win32":
            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)

        try:
            tunnel.proc = await asyncio.create_subprocess_exec(
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
            tunnel.status = EntityStatus.ERROR
            tunnel.error = ErrorRef(
                code="cloudtap.spawn_failed", message=f"Could not start cloudflared: {exc}"
            )
            return self.state()

        tunnel.reader_task = asyncio.create_task(self._read_output(tunnel))

        try:
            await asyncio.wait_for(tunnel.url_event.wait(), timeout=URL_WAIT_TIMEOUT_SECONDS)
        except TimeoutError:
            tunnel.expected_stop = True
            await self._kill(tunnel)
            tunnel.status = EntityStatus.ERROR
            tunnel.error = ErrorRef(
                code="cloudtap.no_url",
                message=(
                    f"cloudflared returned no URL within {int(URL_WAIT_TIMEOUT_SECONDS)}s. "
                    f"Is something serving on port {port}?"
                ),
            )
            return self.state()

        if tunnel.public_url is None:
            tunnel.status = EntityStatus.ERROR
            tunnel.error = ErrorRef(
                code="cloudtap.spawn_failed",
                message="cloudflared exited before a tunnel URL appeared.",
            )
            return self.state()

        tunnel.status = EntityStatus.LAUNCHED
        tunnel.error = None
        tunnel.message = f"Live for {tunnel.label}"
        await self._bus.publish(
            event_name("tool", "tunnel_opened"),
            {
                "tool_id": self.tool_id,
                "tunnel_id": tunnel.id,
                "public_url": tunnel.public_url,
                "local_port": port,
                "label": tunnel.label,
            },
        )
        await self._bus.publish(
            event_name("remote_access", "updated"),
            {"reason": "cloudtap-tunnel-opened", "tunnel_id": tunnel.id},
        )
        log.info(
            "Cloudtap: tunnel '%s' open %s -> localhost:%d (%s)",
            tunnel.id, tunnel.public_url, port, tunnel.label,
        )
        return self.state()

    # ── close ────────────────────────────────────────────────────────────

    async def _close(self, item_id: str | None) -> ToolState:
        if not item_id:
            self._tool_error = ErrorRef(
                code="cloudtap.no_tunnel", message="No tunnel id supplied to close."
            )
            return self.state()
        tunnel = self._tunnels.get(item_id)
        if tunnel is None:
            self._tool_error = ErrorRef(
                code="cloudtap.no_tunnel", message=f"No tunnel '{item_id}' to close."
            )
            return self.state()

        tunnel.expected_stop = True
        closed_url = tunnel.public_url
        if tunnel.proc is not None and tunnel.proc.returncode is None:
            await self._kill(tunnel)
        # Remove it entirely — a closed tunnel just vanishes from the list.
        self._tunnels.pop(item_id, None)
        await self._bus.publish(
            event_name("tool", "tunnel_closed"),
            {"tool_id": self.tool_id, "tunnel_id": item_id, "public_url": closed_url},
        )
        await self._bus.publish(
            event_name("remote_access", "updated"),
            {"reason": "cloudtap-tunnel-closed", "tunnel_id": item_id},
        )
        log.info("Cloudtap: tunnel '%s' closed.", item_id)
        return self.state()

    # ── output reader ────────────────────────────────────────────────────

    async def _read_output(self, tunnel: _Tunnel) -> None:
        """Scan one tunnel's cloudflared output for its URL; watch for exit."""

        proc = tunnel.proc
        if proc is None or proc.stdout is None:
            return
        try:
            while True:
                raw = await proc.stdout.readline()
                if not raw:
                    break
                text = raw.decode("utf-8", errors="replace")
                if tunnel.public_url is None:
                    match = _URL_RE.search(text)
                    if match:
                        tunnel.public_url = match.group(0)
                        tunnel.url_event.set()
        except asyncio.CancelledError:
            return
        finally:
            if not tunnel.url_event.is_set():
                tunnel.url_event.set()
            await self._handle_exit(tunnel)

    async def _handle_exit(self, tunnel: _Tunnel) -> None:
        """The cloudflared process for one tunnel ended."""

        proc = tunnel.proc
        if proc is None:
            return
        try:
            await proc.wait()
        except Exception:  # pragma: no cover — defensive
            pass

        if tunnel.expected_stop:
            return  # _close()/_kill() owns the transition
        if tunnel.status != EntityStatus.LAUNCHED:
            return  # _open() reports its own failure

        # The tunnel was live and cloudflared died on its own.
        tunnel.status = EntityStatus.ERROR
        tunnel.message = None
        tunnel.error = ErrorRef(
            code="cloudtap.tunnel_dropped",
            message=f"cloudflared exited unexpectedly (code {proc.returncode}).",
        )
        await self._bus.publish(
            event_name("tool", "tunnel_closed"),
            {
                "tool_id": self.tool_id,
                "tunnel_id": tunnel.id,
                "public_url": tunnel.public_url,
                "reason": "dropped",
            },
        )
        await self._bus.publish(
            event_name("remote_access", "updated"),
            {"reason": "cloudtap-tunnel-dropped", "tunnel_id": tunnel.id},
        )

    # ── helpers ──────────────────────────────────────────────────────────

    async def _kill(self, tunnel: _Tunnel) -> None:
        proc = tunnel.proc
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
        if tunnel.reader_task is not None:
            tunnel.reader_task.cancel()

    def _label_for_port(self, port: int) -> str:
        """Name a tunnel after the registered project that owns the port."""

        if self._storage is not None:
            try:
                for project in projects_module.list_projects(self._storage.conn):
                    if project.expected_port == port:
                        return project.name
            except Exception:  # pragma: no cover — labelling is best-effort
                log.debug("Cloudtap: project lookup for port %d failed.", port)
        return f"localhost:{port}"

    def _coerce_port(self, value: object) -> int | None:
        try:
            port = int(value)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            self._tool_error = ErrorRef(
                code="cloudtap.bad_port", message="Port must be a whole number."
            )
            return None
        if not (1 <= port <= 65535):
            self._tool_error = ErrorRef(
                code="cloudtap.bad_port", message="Port must be between 1 and 65535."
            )
            return None
        return port
