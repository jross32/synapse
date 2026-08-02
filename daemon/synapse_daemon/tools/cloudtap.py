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

import psutil

from .. import projects as projects_module
from ..api_versions import event_name
from ..models import EntityStatus, ErrorRef, ToolItem, ToolState
from ..storage import Storage
from ..time_utils import to_iso, utc_now
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


# ── durable tunnel identity (Contract #6, orphan-safe) ───────────────────────
#
# A quick tunnel is a *public* URL into this machine, and until 0.1.102 the only
# record of one was the in-memory `_Tunnel.proc` handle. `shutdown()` closes them on
# a graceful exit, but nothing survives a force-kill, a crash, or a restart that
# takes the daemon down without running it -- and the child cloudflared keeps serving
# its own trycloudflare hostname regardless. Observed on 2026-08-01: seven cloudflared
# processes for one tracked tunnel, six of them orphans dating back two days, each
# still exposing localhost to the internet with nothing in the UI to show or close it.
#
# So tunnels are now also recorded in `managed_processes` (the same table Contract #6
# uses for project processes, which already accepts entity_type='tool'), and a sweep on
# construction terminates any that outlived the daemon that spawned them.
_MANAGED_ENTITY_TYPE = "tool"
_MANAGED_ENTITY_PREFIX = "cloudtap:"


def _looks_like_recorded_cloudflared(pid: int, recorded_cmdline: str) -> bool:
    """Is the live process at ``pid`` still the cloudflared we spawned?

    PIDs are recycled, so a stale row must never be allowed to kill an unrelated
    process. Requires both that the executable is still cloudflared and that the
    tunnel target matches what we recorded.
    """
    try:
        live = " ".join(psutil.Process(pid).cmdline())
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
        return False
    if "cloudflared" not in live.lower():
        return False
    # `--url http://localhost:<port>` is the distinguishing part of our spawn.
    marker = recorded_cmdline.split("--url", 1)
    if len(marker) == 2:
        return marker[1].strip() in live
    return live == recorded_cmdline


def reconcile_cloudtap_strays(conn, *, killer=None) -> list[dict]:
    """Terminate cloudflared tunnels left behind by a previous daemon.

    Kill rather than re-attach: the public URL is only ever printed on the child's
    stdout at startup, and a new daemon has no handle on that stream, so an inherited
    tunnel could never be shown or closed through the UI. Leaving it running is the
    exact failure being fixed. WAN auto-start opens a fresh tunnel on boot anyway.

    ``killer`` is injectable so tests can assert the decision without killing anything.
    Returns one dict per swept row for logging/audit.
    """
    rows = conn.execute(
        "SELECT id, entity_id, pid, cmdline FROM managed_processes "
        "WHERE entity_type = ? AND entity_id LIKE ? AND stopped_at IS NULL",
        (_MANAGED_ENTITY_TYPE, f"{_MANAGED_ENTITY_PREFIX}%"),
    ).fetchall()

    def _default_killer(pid: int) -> None:
        proc = psutil.Process(pid)
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except psutil.TimeoutExpired:
            proc.kill()

    kill = killer or _default_killer
    swept: list[dict] = []
    for row in rows:
        pid = int(row["pid"])
        alive = _looks_like_recorded_cloudflared(pid, row["cmdline"] or "")
        killed = False
        if alive:
            try:
                kill(pid)
                killed = True
            except Exception:  # noqa: BLE001 -- a stray we cannot kill must not block boot
                log.exception("Cloudtap: could not terminate stray tunnel pid %s.", pid)
        conn.execute(
            "UPDATE managed_processes "
            "SET stopped_at = ?, stop_reason = ?, status = 'stopped' WHERE id = ?",
            (to_iso(utc_now()), "daemon-restart", row["id"]),
        )
        swept.append({"pid": pid, "entity_id": row["entity_id"], "killed": killed})
    return swept


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
    # Durable identity for the orphan sweep (see reconcile_cloudtap_strays).
    cmdline: str = ""
    row_id: int | None = None

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
        self._sweep_strays_on_start()

    def _sweep_strays_on_start(self) -> None:
        """Close any public tunnel that outlived the daemon which opened it."""
        if self._storage is None:
            return
        try:
            with self._storage.transaction() as conn:
                swept = reconcile_cloudtap_strays(conn)
        except Exception:  # noqa: BLE001 -- never let cleanup stop the daemon booting
            log.exception("Cloudtap: stray-tunnel reconciliation failed.")
            return
        killed = [row for row in swept if row["killed"]]
        if killed:
            log.warning(
                "Cloudtap: terminated %d orphaned tunnel(s) from a previous daemon: %s",
                len(killed),
                ", ".join(f"{row['entity_id']} (pid {row['pid']})" for row in killed),
            )

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
        tunnel.cmdline = f"{exe} tunnel --url http://localhost:{port}"
        self._record_tunnel_row(tunnel)

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

        # The child is gone either way, so its tracking row must not stay open --
        # otherwise the next boot's sweep sees a live-looking row for a dead pid.
        self._close_tunnel_row(tunnel, reason="user" if tunnel.expected_stop else "crashed")

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

    def _record_tunnel_row(self, tunnel: _Tunnel) -> None:
        """Persist this tunnel's pid so a later daemon can find and close it."""
        pid = getattr(tunnel.proc, "pid", None) if tunnel.proc is not None else None
        if self._storage is None or pid is None:
            return
        try:
            with self._storage.transaction() as conn:
                cursor = conn.execute(
                    "INSERT INTO managed_processes "
                    "(entity_type, entity_id, pid, cmdline, started_at, log_path, status) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        _MANAGED_ENTITY_TYPE,
                        f"{_MANAGED_ENTITY_PREFIX}{tunnel.id}",
                        pid,
                        tunnel.cmdline,
                        to_iso(utc_now()),
                        "",  # cloudflared output is scanned in-process, not written to a log file
                        "launched",
                    ),
                )
                tunnel.row_id = cursor.lastrowid
        except Exception:  # noqa: BLE001 -- bookkeeping must never break opening a tunnel
            log.exception("Cloudtap: could not record tunnel '%s' for orphan tracking.", tunnel.id)

    def _close_tunnel_row(self, tunnel: _Tunnel, *, reason: str) -> None:
        if self._storage is None or tunnel.row_id is None:
            return
        try:
            with self._storage.transaction() as conn:
                conn.execute(
                    "UPDATE managed_processes "
                    "SET stopped_at = ?, stop_reason = ?, status = 'stopped' WHERE id = ?",
                    (to_iso(utc_now()), reason, tunnel.row_id),
                )
        except Exception:  # noqa: BLE001
            log.exception("Cloudtap: could not close tracking row for tunnel '%s'.", tunnel.id)
        tunnel.row_id = None

    async def _kill(self, tunnel: _Tunnel) -> None:
        proc = tunnel.proc
        self._close_tunnel_row(tunnel, reason="user" if tunnel.expected_stop else "crashed")
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
