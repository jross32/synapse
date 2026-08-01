"""Tests for the PTY session manager (v0.1.25 · ADR-0002 Phase A)."""

from __future__ import annotations

import asyncio
import base64
import os
import sys
import threading
import time
import types
from pathlib import Path

import pytest

from synapse_daemon.pty_sessions import (
    PtySession,
    PtySessionManager,
    _WindowsBackend,
    _normalize_windows_input,
)
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


async def test_sensitive_env_values_are_redacted_across_output_chunks() -> None:
    bus = EventBus()
    seen: list[Event] = []

    async def sub(event: Event) -> None:
        seen.append(event)

    await bus.subscribe(sub)
    secret = "worker-token-value-123456"
    session = PtySession(
        session_id="redaction-test",
        argv=["demo"],
        spawn_argv=["demo"],
        cwd=None,
        env={"SYNAPSE_TOKEN": secret, "NORMAL_SETTING": "visible-value"},
        rows=24,
        cols=80,
        bus=bus,
        loop=asyncio.get_running_loop(),
    )

    session._handle_chunk(b"before worker-token-\x1b[0K")  # noqa: SLF001
    session._handle_chunk(b"value-123456 after visible-value")  # noqa: SLF001
    await asyncio.sleep(0)

    scrollback = session.scrollback_bytes()
    output = b"".join(
        base64.b64decode(event.payload["data"])
        for event in seen
        if event.name.endswith("session_output")
    )
    assert secret.encode() not in scrollback
    assert secret.encode() not in output
    assert b"[REDACTED]" in scrollback
    assert b"visible-value" in scrollback


async def test_partial_sensitive_value_is_redacted_when_output_finishes() -> None:
    bus = EventBus()
    session = PtySession(
        session_id="partial-redaction-test",
        argv=["demo"],
        spawn_argv=["demo"],
        cwd=None,
        env={"API_KEY": "credential-value-987654"},
        rows=24,
        cols=80,
        bus=bus,
        loop=asyncio.get_running_loop(),
    )

    session._handle_chunk(b"credential-value-")  # noqa: SLF001
    session._flush_redaction_pending()  # noqa: SLF001

    assert session.scrollback_bytes() == b"[REDACTED]"


async def test_sensitive_value_inside_terminal_escape_payload_is_redacted() -> None:
    bus = EventBus()
    secret = b"terminal-secret-123456"
    session = PtySession(
        session_id="escape-redaction-test",
        argv=["demo"],
        spawn_argv=["demo"],
        cwd=None,
        env={"TEST_TOKEN": secret.decode(), "CSI_TOKEN": "123456789"},
        rows=24,
        cols=80,
        bus=bus,
        loop=asyncio.get_running_loop(),
    )

    session._handle_chunk(b"\x1b]0;" + secret + b"\x07")  # noqa: SLF001
    session._handle_chunk(b"\x1b[123456789m")  # noqa: SLF001

    assert secret not in session.scrollback_bytes()
    assert b"123456789" not in session.scrollback_bytes()
    assert session.scrollback_bytes().count(b"[REDACTED]") == 2


def test_public_argv_redacts_sensitive_environment_values() -> None:
    bus = EventBus()
    secret = "argv-secret-value-123456"
    session = PtySession(
        session_id="argv-redaction-test",
        argv=["demo", "--token", secret],
        spawn_argv=["demo", "--token", secret],
        cwd=None,
        env={"SERVICE_TOKEN": secret},
        rows=24,
        cols=80,
        bus=bus,
        loop=asyncio.new_event_loop(),
    )
    try:
        assert secret not in " ".join(session.summary().argv)
        assert session.summary().argv[-1] == "[REDACTED]"
    finally:
        session._loop.close()  # noqa: SLF001


async def test_incomplete_terminal_escape_does_not_drop_visible_prefix() -> None:
    bus = EventBus()
    session = PtySession(
        session_id="incomplete-escape-test",
        argv=["demo"],
        spawn_argv=["demo"],
        cwd=None,
        env={"TEST_TOKEN": "another-secret-value-123456"},
        rows=24,
        cols=80,
        bus=bus,
        loop=asyncio.get_running_loop(),
    )

    session._handle_chunk(b"ordinary output\x1b[31")  # noqa: SLF001
    session._flush_redaction_pending()  # noqa: SLF001

    assert session.scrollback_bytes() == b"ordinary output"


async def test_duplicate_eof_callbacks_publish_one_ordered_finalization() -> None:
    bus = EventBus()
    seen: list[Event] = []

    async def sub(event: Event) -> None:
        seen.append(event)

    await bus.subscribe(sub)
    session = PtySession(
        session_id="duplicate-eof-test",
        argv=["demo"],
        spawn_argv=["demo"],
        cwd=None,
        env={},
        rows=24,
        cols=80,
        bus=bus,
        loop=asyncio.get_running_loop(),
    )

    def slow_reap() -> int:
        time.sleep(0.05)
        return 0

    session._backend.reap = slow_reap  # type: ignore[method-assign]  # noqa: SLF001
    await asyncio.gather(session._on_eof(), session._on_eof())  # noqa: SLF001

    assert len(_drain_events(seen, name_endswith="session_exited")) == 1
    assert len(_drain_events(seen, name_endswith="session_finalized")) == 1


async def test_eof_flushes_final_redaction_before_exit_and_finalize_events() -> None:
    bus = EventBus()
    seen: list[Event] = []

    async def sub(event: Event) -> None:
        seen.append(event)

    await bus.subscribe(sub)
    session = PtySession(
        session_id="ordered-eof-test",
        argv=["demo"],
        spawn_argv=["demo"],
        cwd=None,
        env={"TEST_TOKEN": "credential-value-123456"},
        rows=24,
        cols=80,
        bus=bus,
        loop=asyncio.get_running_loop(),
    )
    session._backend.reap = lambda: 0  # type: ignore[method-assign]  # noqa: SLF001
    session._handle_chunk(b"credential-value-")  # noqa: SLF001

    await session._on_eof()  # noqa: SLF001

    names = [event.name for event in seen]
    output_index = next(index for index, name in enumerate(names) if name.endswith("session_output"))
    exited_index = next(index for index, name in enumerate(names) if name.endswith("session_exited"))
    finalized_index = next(index for index, name in enumerate(names) if name.endswith("session_finalized"))
    assert output_index < exited_index < finalized_index
    output = base64.b64decode(seen[output_index].payload["data"])
    assert output == b"[REDACTED]"


async def test_shutdown_wins_over_concurrent_eof_without_duplicate_events() -> None:
    bus = EventBus()
    seen: list[Event] = []

    async def sub(event: Event) -> None:
        seen.append(event)

    await bus.subscribe(sub)
    session = PtySession(
        session_id="shutdown-eof-test",
        argv=["demo"],
        spawn_argv=["demo"],
        cwd=None,
        env={},
        rows=24,
        cols=80,
        bus=bus,
        loop=asyncio.get_running_loop(),
    )
    backend = types.SimpleNamespace(
        fileno=lambda: -1,
        terminate=lambda: None,
        close=lambda: None,
        reap=lambda: None,
    )
    session._backend = backend  # type: ignore[assignment]  # noqa: SLF001

    shutdown_task = asyncio.create_task(session.shutdown())
    await asyncio.sleep(0)
    await asyncio.gather(session._on_eof(), shutdown_task)  # noqa: SLF001

    exited = _drain_events(seen, name_endswith="session_exited")
    finalized = _drain_events(seen, name_endswith="session_finalized")
    assert len(exited) == 1
    assert len(finalized) == 1
    assert exited[0].payload["exit_code"] == -1


async def test_shutdown_wins_when_eof_reap_started_first() -> None:
    bus = EventBus()
    seen: list[Event] = []

    async def sub(event: Event) -> None:
        seen.append(event)

    await bus.subscribe(sub)
    session = PtySession(
        session_id="eof-first-shutdown-test",
        argv=["demo"],
        spawn_argv=["demo"],
        cwd=None,
        env={},
        rows=24,
        cols=80,
        bus=bus,
        loop=asyncio.get_running_loop(),
    )
    reap_started = threading.Event()
    release_reap = threading.Event()

    def blocked_reap() -> None:
        reap_started.set()
        assert release_reap.wait(timeout=2.0)
        return None

    backend = types.SimpleNamespace(
        fileno=lambda: -1,
        terminate=lambda: None,
        close=lambda: None,
        reap=blocked_reap,
    )
    session._backend = backend  # type: ignore[assignment]  # noqa: SLF001

    eof_task = asyncio.create_task(session._on_eof())  # noqa: SLF001
    assert await asyncio.to_thread(reap_started.wait, 1.0)
    shutdown_task = asyncio.create_task(session.shutdown())
    assert await _wait_for(lambda: session._closing)  # noqa: SLF001
    release_reap.set()
    await asyncio.gather(eof_task, shutdown_task)

    exited = _drain_events(seen, name_endswith="session_exited")
    finalized = _drain_events(seen, name_endswith="session_finalized")
    assert len(exited) == 1
    assert len(finalized) == 1
    assert exited[0].payload["exit_code"] == -1


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


async def test_windows_copilot_spawn_wraps_through_powershell(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bus = EventBus()
    manager = PtySessionManager(bus)
    seen: dict[str, list[str] | None] = {"argv": None}

    async def fake_start(self) -> None:  # type: ignore[no-untyped-def]
        seen["argv"] = list(self._spawn_argv)

    monkeypatch.setattr("synapse_daemon.pty_sessions.sys.platform", "win32")
    monkeypatch.setattr(
        "synapse_daemon.pty_sessions.resolve_command",
        lambda cmd: {
            "copilot": r"C:\Users\justi\AppData\Roaming\npm\copilot.cmd",
            "powershell.exe": r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe",
        }.get(cmd),
    )
    monkeypatch.setattr("synapse_daemon.pty_sessions.PtySession.start", fake_start)

    session = await manager.spawn(["copilot"])
    assert session.argv[0] == r"C:\Users\justi\AppData\Roaming\npm\copilot.cmd"
    assert seen["argv"] == [
        r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe",
        "-NoLogo",
        "-Command",
        "& 'c:\\users\\justi\\appdata\\roaming\\npm\\copilot.cmd'",
    ]


# ── Windows .cmd/.bat multi-arg squad-launch fix (regression for the bug where
#    `claude.CMD --mcp-config <path>` dropped its args under winpty) ──────────

_PS = r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"
_CLAUDE = r"C:\Users\justi\AppData\Roaming\npm\claude.CMD"


def _win_resolver(extra: dict[str, str] | None = None):
    table = {"powershell.exe": _PS}
    if extra:
        table.update(extra)
    return lambda cmd: table.get(cmd)


async def _capture_spawn_argv(monkeypatch, resolver, argv):
    """Spawn with PtySession.start stubbed; return (session, captured spawn_argv)."""
    bus = EventBus()
    manager = PtySessionManager(bus)
    seen: dict[str, list[str] | None] = {"argv": None}

    async def fake_start(self) -> None:  # type: ignore[no-untyped-def]
        seen["argv"] = list(self._spawn_argv)

    monkeypatch.setattr("synapse_daemon.pty_sessions.sys.platform", "win32")
    monkeypatch.setattr("synapse_daemon.pty_sessions.resolve_command", resolver)
    monkeypatch.setattr("synapse_daemon.pty_sessions.PtySession.start", fake_start)
    session = await manager.spawn(argv)
    return session, seen["argv"]


async def test_windows_cmd_runtime_with_args_wraps_through_powershell(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The squad-launch bug: `claude.CMD --mcp-config <path>` must wrap through
    PowerShell so the .cmd shim forwards ALL args via %*. Full-equality assert
    (not a partial `in`) so an arg-dropping regression can't slip through — that
    dropping is exactly what failed live."""

    cfg = r"C:\Users\justi\synapse\data\mcp\claude-mcp.json"
    session, spawn_argv = await _capture_spawn_argv(
        monkeypatch, _win_resolver({"claude": _CLAUDE}), ["claude", "--mcp-config", cfg]
    )
    # Public argv (UI + transcript) is preserved with ORIGINAL casing + all args.
    assert session.argv == [_CLAUDE, "--mcp-config", cfg]
    # spawn_argv wraps through PowerShell with BOTH args single-quoted; the .cmd
    # path casing is preserved (NOT lower-cased like the copilot branch).
    assert spawn_argv == [
        _PS,
        "-NoLogo",
        "-Command",
        f"& '{_CLAUDE}' '--mcp-config' '{cfg}'",
    ]


async def test_windows_single_arg_cmd_stays_unwrapped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Deliberate divergence, locked by test: a bare single-arg .cmd already
    launches via raw winpty, so it is NOT wrapped (minimal blast radius)."""

    _, spawn_argv = await _capture_spawn_argv(
        monkeypatch, _win_resolver({"claude": _CLAUDE}), ["claude"]
    )
    assert spawn_argv == [_CLAUDE]  # unwrapped — raw winpty path


async def test_windows_copilot_with_args_still_routes_copilot_branch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The new .cmd branch must not shadow copilot: a copilot.cmd (even with
    args) keeps the copilot branch's lower-cased path semantics."""

    copilot = r"C:\Users\justi\AppData\Roaming\npm\copilot.cmd"
    _, spawn_argv = await _capture_spawn_argv(
        monkeypatch, _win_resolver({"copilot": copilot}), ["copilot", "--banner", "false"]
    )
    assert spawn_argv == [
        _PS,
        "-NoLogo",
        "-Command",
        f"& '{copilot.lower()}' '--banner' 'false'",
    ]


async def test_windows_cmd_with_args_raises_loudly_when_powershell_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If powershell.exe can't be resolved we must NOT fall back to the
    known-broken raw argv (which hangs the work item silently) — fail loud."""

    bus = EventBus()
    manager = PtySessionManager(bus)
    monkeypatch.setattr("synapse_daemon.pty_sessions.sys.platform", "win32")
    # Resolver knows claude but NOT powershell.exe.
    monkeypatch.setattr(
        "synapse_daemon.pty_sessions.resolve_command", _win_resolver({"claude": _CLAUDE, "powershell.exe": None})  # type: ignore[dict-item]
    )
    with pytest.raises(RuntimeError, match="powershell.exe is required"):
        await manager.spawn(["claude", "--mcp-config", "x"])


windows_only = pytest.mark.skipif(
    sys.platform != "win32", reason="real .cmd %* forwarding is a Windows-only path"
)


@windows_only
async def test_windows_cmd_forwards_hostile_path_args_end_to_end(
    tmp_path: Path,
) -> None:
    """The proof the unit tests can't give: spawn a REAL .cmd that echoes its
    args, with an mcp-config path containing a space AND parens (the exact
    hostile case winpty's command-line joining + the cmd.exe %* re-parse must
    survive). This is the test that would have caught the live bug."""

    echo_cmd = tmp_path / "echo_args.cmd"
    echo_cmd.write_text("@echo off\r\necho ARGS:%*\r\n", encoding="ascii")
    hostile_dir = tmp_path / "a b (x86)"
    hostile_dir.mkdir()
    cfg = hostile_dir / "mcp.json"
    cfg.write_text("{}", encoding="ascii")

    bus = EventBus()
    manager = PtySessionManager(bus)
    session = await manager.spawn([str(echo_cmd), "--mcp-config", str(cfg)])
    try:
        got = await _wait_for(lambda: b"ARGS:" in session.scrollback_bytes(), timeout=20.0)
        text = session.scrollback_bytes().decode("utf-8", "replace")
        assert got, f"child never echoed its args; scrollback={text!r}"
        # Both the flag and the full spaced/paren path survived both parser hops.
        assert "--mcp-config" in text
        assert "a b (x86)" in text
        assert "mcp.json" in text
    finally:
        await manager.close(session.session_id)


def test_windows_backend_forces_winpty_for_interactive_input(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    forced_backend = object()
    seen: dict[str, object] = {}

    class FakePtyProcess:
        @staticmethod
        def spawn(argv, cwd=None, env=None, backend=None):  # type: ignore[no-untyped-def]
            seen["argv"] = argv
            seen["cwd"] = cwd
            seen["env"] = env
            seen["backend"] = backend
            return object()

    monkeypatch.setitem(
        sys.modules,
        "winpty",
        types.SimpleNamespace(PtyProcess=FakePtyProcess),
    )
    monkeypatch.setitem(
        sys.modules,
        "winpty.enums",
        types.SimpleNamespace(Backend=types.SimpleNamespace(WinPTY=forced_backend)),
    )

    backend = _WindowsBackend()
    backend.spawn(["powershell.exe", "-NoLogo"], cwd=r"C:\Users\justi", env={"PATH": r"C:\Windows"})

    assert backend.proc is not None
    assert seen["argv"] == ["powershell.exe", "-NoLogo"]
    assert seen["cwd"] == r"C:\Users\justi"
    assert seen["env"] == {"PATH": r"C:\Windows"}
    assert seen["backend"] is forced_backend


def test_normalize_windows_input_expands_only_lone_carriage_returns() -> None:
    assert _normalize_windows_input(b"alpha\rbeta\r\ngamma") == b"alpha\r\nbeta\r\ngamma"


def test_windows_backend_normalizes_enter_for_powershell() -> None:
    writes: list[str] = []

    class FakeProc:
        def write(self, text: str) -> None:
            writes.append(text)

    backend = _WindowsBackend()
    backend.proc = FakeProc()
    backend._enter_needs_crlf = True

    backend.write(b"Write-Output 'hi'\r")

    assert writes == ["Write-Output 'hi'\r\n"]


def test_windows_backend_leaves_cmd_input_unchanged() -> None:
    writes: list[str] = []

    class FakeProc:
        def write(self, text: str) -> None:
            writes.append(text)

    backend = _WindowsBackend()
    backend.proc = FakeProc()
    backend._enter_needs_crlf = False

    backend.write(b"echo hi\r")

    assert writes == ["echo hi\r"]


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
