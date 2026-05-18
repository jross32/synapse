"""Tests for the Cloudtap tool handler (Milestone F · v0.1.9).

cloudflared is mocked — these tests never spawn a real process or hit the
network, so they are fast and CI-safe.
"""

from __future__ import annotations

import asyncio
from unittest.mock import patch

from synapse_daemon.models import EntityStatus
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


def _fake_exec(proc: _FakeProc):
    async def _exec(*_args, **_kwargs):
        return proc

    return _exec


_URL_LINE = b"INF |  https://demo-tunnel.trycloudflare.com  |\n"


# ── tests ────────────────────────────────────────────────────────────────


async def test_bad_port_errors_without_spawning() -> None:
    tool = CloudtapTool(EventBus())
    state = await tool.run_action("tunnel", {"port": "not-a-number"})
    assert state.status == EntityStatus.ERROR
    assert state.last_error is not None
    assert state.last_error.code == "cloudtap.bad_port"


async def test_port_out_of_range_errors() -> None:
    tool = CloudtapTool(EventBus())
    state = await tool.run_action("tunnel", {"port": 99999})
    assert state.status == EntityStatus.ERROR
    assert state.last_error.code == "cloudtap.bad_port"


async def test_missing_cloudflared_reports_install_hint() -> None:
    tool = CloudtapTool(EventBus())
    with patch("shutil.which", return_value=None):
        state = await tool.run_action("tunnel", {"port": 8080})
    assert state.status == EntityStatus.ERROR
    assert state.last_error.code == "cloudtap.not_installed"


async def test_successful_tunnel_parses_public_url() -> None:
    tool = CloudtapTool(EventBus())
    proc = _FakeProc([b"INF Starting tunnel\n", _URL_LINE])
    with patch("shutil.which", return_value="cloudflared"), patch(
        "asyncio.create_subprocess_exec", _fake_exec(proc)
    ):
        state = await tool.run_action("tunnel", {"port": 8080})

    assert state.status == EntityStatus.LAUNCHED
    assert state.result["public_url"] == "https://demo-tunnel.trycloudflare.com"
    assert state.result["local_port"] == 8080
    assert state.last_error is None

    # Clean up the tracked fake process.
    await tool.shutdown()


async def test_stop_closes_a_running_tunnel() -> None:
    tool = CloudtapTool(EventBus())
    proc = _FakeProc([_URL_LINE])
    with patch("shutil.which", return_value="cloudflared"), patch(
        "asyncio.create_subprocess_exec", _fake_exec(proc)
    ):
        await tool.run_action("tunnel", {"port": 8080})
        stopped = await tool.run_action("stop", {})

    assert stopped.status == EntityStatus.STOPPED
    assert "public_url" not in stopped.result
    assert proc.returncode is not None  # process was terminated


async def test_early_exit_without_url_is_a_spawn_failure() -> None:
    tool = CloudtapTool(EventBus())
    proc = _FakeProc([], exits_immediately=True)
    with patch("shutil.which", return_value="cloudflared"), patch(
        "asyncio.create_subprocess_exec", _fake_exec(proc)
    ):
        state = await tool.run_action("tunnel", {"port": 8080})

    assert state.status == EntityStatus.ERROR
    assert state.last_error.code == "cloudtap.spawn_failed"


async def test_timeout_when_no_url_appears() -> None:
    tool = CloudtapTool(EventBus())
    proc = _FakeProc([b"INF still connecting...\n"])  # never prints a URL
    with patch("shutil.which", return_value="cloudflared"), patch(
        "asyncio.create_subprocess_exec", _fake_exec(proc)
    ), patch.object(cloudtap_mod, "URL_WAIT_TIMEOUT_SECONDS", 0.3):
        state = await tool.run_action("tunnel", {"port": 8080})

    assert state.status == EntityStatus.ERROR
    assert state.last_error.code == "cloudtap.no_url"


async def test_second_tunnel_while_running_is_rejected() -> None:
    tool = CloudtapTool(EventBus())
    proc = _FakeProc([_URL_LINE])
    with patch("shutil.which", return_value="cloudflared"), patch(
        "asyncio.create_subprocess_exec", _fake_exec(proc)
    ):
        await tool.run_action("tunnel", {"port": 8080})
        again = await tool.run_action("tunnel", {"port": 9090})

    assert again.status == EntityStatus.ERROR
    assert again.last_error.code == "cloudtap.already_running"
    await tool.shutdown()


async def test_unknown_action_errors() -> None:
    tool = CloudtapTool(EventBus())
    state = await tool.run_action("teleport", {})
    assert state.status == EntityStatus.ERROR
    assert state.last_error.code == "cloudtap.unknown_action"
