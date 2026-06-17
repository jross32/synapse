"""Tests for the PTY session manager (v0.1.25 · ADR-0002 Phase A)."""

from __future__ import annotations

import asyncio
import base64
import os
import sys
from pathlib import Path

import pytest

from synapse_daemon.pty_sessions import PtySessionManager
from synapse_daemon.ws import Event, EventBus

# Windows uses pywinpty which isn't installed in the Linux CI we run. The end
# -to-end PTY behaviour is exercised on POSIX; the Windows path is tested via
# routes + import smoke only.
posix_only = pytest.mark.skipif(
    sys.platform == "win32", reason="POSIX-only PTY behaviour test"
)


# ── helpers ────────────────────────────────────────────────────────────────


def _drain_events(events: list[Event], *, name_endswith: str) -> list[Event]:
    return [e for e in events if e.name.endswith(name_endswith)]


async def _wait_for(predicate, timeout: float = 5.0, poll: float = 0.05) -> bool:
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        if predicate():
            return True
        await asyncio.sleep(poll)
    return False


# ── tests ────────────────────────────────────────────────────────────────


@posix_only
async def test_spawn_then_shutdown_emits_lifecycle_events() -> None:
    bus = EventBus()
    seen: list[Event] = []

    async def sub(event: Event) -> None:
        seen.append(event)

    await bus.subscribe(sub)
    manager = PtySessionManager(bus)
    session = await manager.spawn(argv=[sys.executable, "-c", "print('hi'); import sys; sys.stdout.flush()"])
    sid = session.session_id

    # Wait for the child to print + exit (Python is fast on POSIX).
    assert await _wait_for(lambda: any(e.name.endswith("session_exited") for e in seen))

    assert _drain_events(seen, name_endswith="session_started")
    output_events = _drain_events(seen, name_endswith="session_output")
    assert output_events, "expected at least one output chunk"

    payload = b"".join(
        base64.b64decode(e.payload["data"]) for e in output_events
    )
    assert b"hi" in payload

    exit_events = _drain_events(seen, name_endswith="session_exited")
    assert len(exit_events) == 1
    assert exit_events[-1].payload["session_id"] == sid
    assert exit_events[-1].payload["exit_code"] == 0

    await manager.shutdown_all()


@posix_only
async def test_write_input_reaches_child() -> None:
    bus = EventBus()
    seen: list[Event] = []

    async def sub(event: Event) -> None:
        seen.append(event)

    await bus.subscribe(sub)
    manager = PtySessionManager(bus)
    # cat echoes whatever we write -- a clean way to prove the input plane.
    session = await manager.spawn(argv=["/bin/cat"])
    await session.write(b"ping-pong\n")

    def saw_pong() -> bool:
        for e in seen:
            if e.name.endswith("session_output"):
                if b"ping-pong" in base64.b64decode(e.payload["data"]):
                    return True
        return False

    assert await _wait_for(saw_pong)
    await session.write(b"\x04")  # Ctrl-D -- EOF
    assert await _wait_for(
        lambda: any(e.name.endswith("session_exited") for e in seen)
    )
    await manager.shutdown_all()


@posix_only
async def test_scrollback_is_capped_and_replayable() -> None:
    bus = EventBus()
    manager = PtySessionManager(bus)
    # Print a noticeable chunk then exit so the scrollback contains it.
    session = await manager.spawn(
        argv=[sys.executable, "-c", "print('A' * 100); import sys; sys.stdout.flush()"]
    )
    assert await _wait_for(lambda: session.exit_code is not None, timeout=5.0)
    captured = session.scrollback_bytes()
    assert b"A" * 100 in captured
    # Cap is 64 KiB.
    assert len(captured) <= 64 * 1024 + 16


@posix_only
async def test_resize_does_not_error_on_running_session() -> None:
    bus = EventBus()
    manager = PtySessionManager(bus)
    session = await manager.spawn(argv=["/bin/cat"])
    await session.resize(40, 132)
    assert session.rows == 40 and session.cols == 132
    await manager.close(session.session_id)


async def test_spawn_unknown_command_raises_file_not_found() -> None:
    bus = EventBus()
    manager = PtySessionManager(bus)
    with pytest.raises(FileNotFoundError):
        await manager.spawn(argv=["definitely-not-a-real-binary-xyz"])


async def test_close_unknown_session_is_false() -> None:
    bus = EventBus()
    manager = PtySessionManager(bus)
    assert await manager.close("nope") is False


def test_pty_session_manager_imports_on_any_platform() -> None:
    """A smoke test so the Windows path at least loads (winpty is lazy)."""

    bus = EventBus()
    assert PtySessionManager(bus) is not None


async def test_spawn_defaults_cwd_to_user_home() -> None:
    """The marketplace ships claude / codex with NO cwd in their argv;
    the daemon must pin them to the user's home directory so the CLIs'
    OAuth caches (~/.claude, ~/.config/codex) and per-cwd project state
    are consistent across launches. Without this, every quick-launch
    would land in whatever cwd the daemon happened to be in and Claude
    would re-show its setup wizard each time."""

    bus = EventBus()
    manager = PtySessionManager(bus)
    # Pick a binary every platform has.
    argv = ["powershell.exe" if sys.platform == "win32" else "sh"]
    session = await manager.spawn(argv=argv)
    try:
        assert session.cwd == str(Path.home()), (
            f"expected cwd={Path.home()!s}, got {session.cwd!r}"
        )
    finally:
        await manager.close(session.session_id)


async def test_spawn_explicit_cwd_is_not_overridden() -> None:
    """If the caller passes a cwd (e.g. the workbench, which pins to a
    project's path), the default-to-home logic must NOT clobber it."""

    bus = EventBus()
    manager = PtySessionManager(bus)
    argv = ["powershell.exe" if sys.platform == "win32" else "sh"]
    custom = str(Path.home())  # any real dir; we just check the field is preserved
    # Use a different real directory than home to make the assertion
    # actually meaningful.
    custom = os.path.dirname(custom)
    session = await manager.spawn(argv=argv, cwd=custom)
    try:
        assert session.cwd == custom, (
            f"explicit cwd={custom!r} was clobbered to {session.cwd!r}"
        )
    finally:
        await manager.close(session.session_id)
