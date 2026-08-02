"""Tests for the Cloudtap tool handler (Milestone F · v0.1.9, multi-instance v0.1.9.5).

cloudflared is mocked — these tests never spawn a real process or hit the
network, so they are fast and CI-safe.
"""

from __future__ import annotations

import asyncio
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

from synapse_daemon.models import EntityStatus
from synapse_daemon.projects import Project, create
from synapse_daemon.storage import Storage
from synapse_daemon.tools import cloudtap as cloudtap_mod
from synapse_daemon.tools.cloudtap import CloudtapTool
from synapse_daemon.ws import EventBus

# ── a fake cloudflared process ───────────────────────────────────────────


class _FakeStream:
    """Stands in for ``proc.stdout`` — yields canned lines then blocks."""

    def __init__(self, lines: list[bytes], done: asyncio.Event) -> None:
        self._lines = list(lines)
        self._done = done

    async def readline(self) -> bytes:
        if self._lines:
            return self._lines.pop(0)
        await self._done.wait()  # process still "alive" until terminated
        return b""


class _FakeProc:
    """Minimal asyncio.subprocess.Process stand-in."""

    def __init__(self, lines: list[bytes], *, exits_immediately: bool = False) -> None:
        self.returncode: int | None = None
        self._done = asyncio.Event()
        self.stdout = _FakeStream(lines, self._done)
        if exits_immediately:
            self.returncode = 1
            self._done.set()

    async def wait(self) -> int:
        await self._done.wait()
        if self.returncode is None:
            self.returncode = 0
        return self.returncode

    def terminate(self) -> None:
        if self.returncode is None:
            self.returncode = -15
        self._done.set()

    def kill(self) -> None:
        if self.returncode is None:
            self.returncode = -9
        self._done.set()


def _fake_exec_seq(*procs: _FakeProc):
    """An exec stand-in that hands back the given fake procs in order."""

    queue = list(procs)

    async def _exec(*_args, **_kwargs):
        return queue.pop(0)

    return _exec


def _url_line(host: str = "demo-tunnel") -> bytes:
    return f"INF |  https://{host}.trycloudflare.com  |\n".encode()


# ── tests ────────────────────────────────────────────────────────────────


async def test_bad_port_errors_without_spawning() -> None:
    tool = CloudtapTool(EventBus())
    state = await tool.run_action("tunnel", {"port": "not-a-number"})
    assert state.status == EntityStatus.ERROR
    assert state.last_error is not None
    assert state.last_error.code == "cloudtap.bad_port"
    assert state.items == []


async def test_port_out_of_range_errors() -> None:
    tool = CloudtapTool(EventBus())
    state = await tool.run_action("tunnel", {"port": 99999})
    assert state.last_error.code == "cloudtap.bad_port"


async def test_missing_cloudflared_reports_install_hint() -> None:
    tool = CloudtapTool(EventBus())
    with patch("shutil.which", return_value=None):
        state = await tool.run_action("tunnel", {"port": 8080})
    assert state.status == EntityStatus.ERROR
    assert state.last_error.code == "cloudtap.not_installed"


async def test_successful_tunnel_parses_public_url() -> None:
    tool = CloudtapTool(EventBus())
    proc = _FakeProc([b"INF Starting tunnel\n", _url_line()])
    with patch("shutil.which", return_value="cloudflared"), patch(
        "asyncio.create_subprocess_exec", _fake_exec_seq(proc)
    ):
        state = await tool.run_action("tunnel", {"port": 8080})

    assert state.status == EntityStatus.LAUNCHED
    assert len(state.items) == 1
    item = state.items[0]
    assert item.status == EntityStatus.LAUNCHED
    assert item.result["public_url"] == "https://demo-tunnel.trycloudflare.com"
    assert item.result["local_port"] == 8080
    await tool.shutdown()


async def test_multiple_tunnels_open_concurrently() -> None:
    tool = CloudtapTool(EventBus())
    p1 = _FakeProc([_url_line("first")])
    p2 = _FakeProc([_url_line("second")])
    with patch("shutil.which", return_value="cloudflared"), patch(
        "asyncio.create_subprocess_exec", _fake_exec_seq(p1, p2)
    ):
        await tool.run_action("tunnel", {"port": 8080})
        state = await tool.run_action("tunnel", {"port": 9090})

    assert len(state.items) == 2
    ports = sorted(i.result["local_port"] for i in state.items)
    assert ports == [8080, 9090]
    assert state.status == EntityStatus.LAUNCHED
    await tool.shutdown()


async def test_close_targets_one_tunnel_only() -> None:
    tool = CloudtapTool(EventBus())
    p1 = _FakeProc([_url_line("first")])
    p2 = _FakeProc([_url_line("second")])
    with patch("shutil.which", return_value="cloudflared"), patch(
        "asyncio.create_subprocess_exec", _fake_exec_seq(p1, p2)
    ):
        await tool.run_action("tunnel", {"port": 8080})
        await tool.run_action("tunnel", {"port": 9090})
        # Two tunnels open -> close the first only.
        first_id = tool.state().items[0].id
        state = await tool.run_action("close", {}, item_id=first_id)

    assert len(state.items) == 1
    assert state.items[0].result["local_port"] == 9090  # the OTHER tunnel survives
    assert p1.returncode is not None  # closed one was terminated
    assert p2.returncode is None      # surviving one still running
    await tool.shutdown()


async def test_close_unknown_tunnel_errors() -> None:
    tool = CloudtapTool(EventBus())
    state = await tool.run_action("close", {}, item_id="nonexistent")
    assert state.last_error is not None
    assert state.last_error.code == "cloudtap.no_tunnel"


async def test_early_exit_marks_the_item_failed() -> None:
    tool = CloudtapTool(EventBus())
    proc = _FakeProc([], exits_immediately=True)
    with patch("shutil.which", return_value="cloudflared"), patch(
        "asyncio.create_subprocess_exec", _fake_exec_seq(proc)
    ):
        state = await tool.run_action("tunnel", {"port": 8080})

    assert len(state.items) == 1
    assert state.items[0].status == EntityStatus.ERROR
    assert state.items[0].last_error.code == "cloudtap.spawn_failed"


async def test_timeout_when_no_url_appears() -> None:
    tool = CloudtapTool(EventBus())
    proc = _FakeProc([b"INF still connecting...\n"])
    with patch("shutil.which", return_value="cloudflared"), patch(
        "asyncio.create_subprocess_exec", _fake_exec_seq(proc)
    ), patch.object(cloudtap_mod, "URL_WAIT_TIMEOUT_SECONDS", 0.3):
        state = await tool.run_action("tunnel", {"port": 8080})

    assert state.items[0].status == EntityStatus.ERROR
    assert state.items[0].last_error.code == "cloudtap.no_url"


async def test_unknown_action_errors() -> None:
    tool = CloudtapTool(EventBus())
    state = await tool.run_action("teleport", {})
    assert state.last_error.code == "cloudtap.unknown_action"


async def test_tunnel_is_labelled_with_matching_project(tmp_path: Path) -> None:
    storage = Storage(tmp_path / "data")
    storage.open()
    storage.migrate()
    with storage.transaction() as conn:
        create(
            conn,
            Project(
                id="wbscrper",
                name="Web Scraper",
                path="C:/x",
                launch_cmd="npm start",
                expected_port=8080,
            ),
        )
    try:
        tool = CloudtapTool(EventBus(), storage)
        proc = _FakeProc([_url_line()])
        with patch("shutil.which", return_value="cloudflared"), patch(
            "asyncio.create_subprocess_exec", _fake_exec_seq(proc)
        ):
            state = await tool.run_action("tunnel", {"port": 8080})
        # Port 8080 matches the registered project -> labelled by its name.
        assert state.items[0].label == "Web Scraper"
        await tool.shutdown()
    finally:
        storage.close()


async def test_unmatched_port_falls_back_to_host_label() -> None:
    tool = CloudtapTool(EventBus())  # no storage -> no project lookup
    proc = _FakeProc([_url_line()])
    with patch("shutil.which", return_value="cloudflared"), patch(
        "asyncio.create_subprocess_exec", _fake_exec_seq(proc)
    ):
        state = await tool.run_action("tunnel", {"port": 4321})
    assert state.items[0].label == "localhost:4321"
    await tool.shutdown()


# ── orphaned-tunnel reconciliation (v0.1.102) ────────────────────────────
#
# A quick tunnel is a public URL into this machine. Before this, the only record of
# one was an in-memory process handle, so any daemon exit that skipped `shutdown()`
# (force-kill, crash, restart) left cloudflared serving its own trycloudflare
# hostname with nothing tracking it. Six such orphans were found on 2026-08-01.


def _insert_stray_row(storage: Storage, *, pid: int, cmdline: str, entity_id: str) -> int:
    with storage.transaction() as conn:
        cur = conn.execute(
            "INSERT INTO managed_processes "
            "(entity_type, entity_id, pid, cmdline, started_at, log_path, status) "
            "VALUES ('tool', ?, ?, ?, '2026-08-01T00:00:00Z', '', 'launched')",
            (entity_id, pid, cmdline),
        )
        return cur.lastrowid


def _active_cloudtap_rows(storage: Storage) -> list:
    return storage.conn.execute(
        "SELECT * FROM managed_processes "
        "WHERE entity_type = 'tool' AND entity_id LIKE 'cloudtap:%' AND stopped_at IS NULL"
    ).fetchall()


async def test_open_tunnel_is_recorded_so_a_later_daemon_can_find_it(tmp_path: Path) -> None:
    storage = Storage(tmp_path / "data")
    storage.open()
    storage.migrate()
    try:
        tool = CloudtapTool(EventBus(), storage)
        proc = _FakeProc([_url_line()])
        proc.pid = 424242
        with patch("shutil.which", return_value="cloudflared"), patch(
            "asyncio.create_subprocess_exec", _fake_exec_seq(proc)
        ):
            await tool.run_action("tunnel", {"port": 8080})

        rows = _active_cloudtap_rows(storage)
        assert len(rows) == 1, "an open tunnel must leave a durable record"
        assert rows[0]["pid"] == 424242
        assert "--url http://localhost:8080" in rows[0]["cmdline"]

        await tool.shutdown()
        # Closing the tunnel must close its row, or the next boot would sweep a dead pid.
        assert _active_cloudtap_rows(storage) == []
    finally:
        storage.close()


def test_stray_tunnel_from_a_dead_daemon_is_killed_and_row_closed(tmp_path: Path) -> None:
    """The actual bug: a tunnel that outlived its daemon keeps serving a public URL."""
    storage = Storage(tmp_path / "data")
    storage.open()
    storage.migrate()
    try:
        # A *live* process whose cmdline really does look like our cloudflared spawn.
        victim = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(30)  # cloudflared tunnel --url http://localhost:8080"]
        )
        try:
            _insert_stray_row(
                storage,
                pid=victim.pid,
                cmdline="cloudflared tunnel --url http://localhost:8080",
                entity_id="cloudtap:t1",
            )
            killed: list[int] = []
            with storage.transaction() as conn:
                swept = cloudtap_mod.reconcile_cloudtap_strays(conn, killer=killed.append)

            assert killed == [victim.pid], "the orphaned public tunnel must be terminated"
            assert swept[0]["killed"] is True
            assert _active_cloudtap_rows(storage) == [], "its row must not stay open"
        finally:
            victim.kill()
            victim.wait(timeout=10)
    finally:
        storage.close()


def test_reconcile_never_kills_a_recycled_pid(tmp_path: Path) -> None:
    """A stale row must not become a licence to kill whatever now owns that pid.

    PIDs are reused. Guard: the live process must still *be* cloudflared serving the
    port we recorded, otherwise we only close the bookkeeping row.
    """
    storage = Storage(tmp_path / "data")
    storage.open()
    storage.migrate()
    try:
        bystander = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
        try:
            _insert_stray_row(
                storage,
                pid=bystander.pid,
                cmdline="cloudflared tunnel --url http://localhost:8080",
                entity_id="cloudtap:t1",
            )
            killed: list[int] = []
            with storage.transaction() as conn:
                swept = cloudtap_mod.reconcile_cloudtap_strays(conn, killer=killed.append)

            assert killed == [], "an unrelated process on a recycled pid must be left alone"
            assert swept[0]["killed"] is False
            assert bystander.poll() is None, "the bystander must still be running"
            assert _active_cloudtap_rows(storage) == [], "the stale row is still closed out"
        finally:
            bystander.kill()
            bystander.wait(timeout=10)
    finally:
        storage.close()


def test_construction_sweeps_strays(tmp_path: Path) -> None:
    """The sweep runs on construction, which is what makes it happen every boot."""
    storage = Storage(tmp_path / "data")
    storage.open()
    storage.migrate()
    try:
        _insert_stray_row(
            storage,
            pid=999_999_999,  # certainly dead
            cmdline="cloudflared tunnel --url http://localhost:8080",
            entity_id="cloudtap:t7",
        )
        assert len(_active_cloudtap_rows(storage)) == 1
        CloudtapTool(EventBus(), storage)
        assert _active_cloudtap_rows(storage) == [], "boot must clear stale tunnel rows"
    finally:
        storage.close()
