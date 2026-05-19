"""Tests for the Cloudtap tool handler (Milestone F · v0.1.9, multi-instance v0.1.9.5).

cloudflared is mocked — these tests never spawn a real process or hit the
network, so they are fast and CI-safe.
"""

from __future__ import annotations

import asyncio
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
