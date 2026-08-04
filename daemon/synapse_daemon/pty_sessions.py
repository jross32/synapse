"""Pseudo-terminal session manager (v0.1.25 · ADR-0002 Phase A step 1).

Hosts long-running interactive child processes -- claude, codex, python,
psql, anything -- under a real PTY so ANSI escapes, raw mode and line
editing all work. The renderer (Phase A step 2) embeds xterm.js and binds
each session id to a WebSocket stream.

Layout
------
- :class:`PtySession`         -- one child process under a PTY, with a
                                  bounded output scrollback ring and an
                                  exit code once it ends.
- :class:`PtySessionManager`  -- create / list / lookup / shutdown.
- Bus events                  -- ``v1.pty.session_started``,
                                  ``v1.pty.session_output``,
                                  ``v1.pty.session_exited``.

Platform notes
--------------
- POSIX uses stdlib ``pty.fork`` + ``os.read`` registered with the asyncio
  loop via ``loop.add_reader``.
- Windows uses ``pywinpty`` (an optional dep installed only on Windows --
  see ``pyproject.toml``). Reads happen on a daemon thread that posts to
  the loop via ``run_coroutine_threadsafe``.

Output is fanned out as **base64-encoded** strings on the bus so the JSON
payload survives any byte the child cared to print. The scrollback ring
keeps the last 64 KiB so a subscriber attaching mid-session still gets
useful context.
"""

from __future__ import annotations

import asyncio
import base64
import io
import logging
import os
import secrets
import signal
import sys
import threading
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Awaitable, Callable

from .api_versions import event_name
from .runtime_resolution import resolve_command
from .time_utils import to_iso, utc_now
from .ws import EventBus

if TYPE_CHECKING:
    from .storage import Storage

# Callback shape used by PtySessionManager to persist a session's transcript.
_PersistCallback = Callable[["PtySession"], Awaitable[None]]

log = logging.getLogger(__name__)

#: Soft cap on per-session scrollback. 64 KiB ~= ~800 80-column lines.
SCROLLBACK_BYTES = 64 * 1024

#: How big a chunk we try to read per pump.
READ_CHUNK = 4096

# Environment variables with these names are credentials, not ordinary task
# configuration. Their values may be needed by a child process, but must never
# survive if that child echoes its environment into PTY output, WebSocket
# events, scrollback, or a persisted transcript.
_SENSITIVE_ENV_KEY_PARTS = (
    "TOKEN",
    "SECRET",
    "PASSWORD",
    "API_KEY",
    "PRIVATE_KEY",
    "CREDENTIAL",
)
_MIN_REDACTED_VALUE_BYTES = 8
_OUTPUT_REDACTION_MARKER = b"[REDACTED]"

# How long a held-back split-secret suffix may sit unflushed before the terminal
# self-heals. The chunk-boundary guard retains any trailing bytes that match a *prefix*
# of a tracked value -- down to a single byte -- so an idle prompt ending in a byte that
# merely starts like a credential used to have that byte silently missing until the next
# write, which on an idle interactive session may never come.
#
# A real PTY write that splits a credential across reads is separated by microseconds, so
# after a full second of silence the held bytes were ordinary output and are released
# as-is. Deliberately NOT paired with a "minimum held-back size" rule: refusing to hold
# short prefixes would let a secret split after one byte leak that byte *and* leave the
# remainder unrecognisable as the full value, so it would print unredacted -- trading a
# cosmetic stall for an actual disclosure.
REDACTION_IDLE_FLUSH_SECONDS = 1.0


def _sensitive_output_values(env: dict[str, str]) -> tuple[bytes, ...]:
    """Return unique, non-trivial credential values that PTY output must hide."""

    values: set[bytes] = set()
    for key, value in env.items():
        normalized_key = key.upper()
        if not any(part in normalized_key for part in _SENSITIVE_ENV_KEY_PARTS):
            continue
        encoded = value.encode("utf-8", "surrogatepass")
        if len(encoded) >= _MIN_REDACTED_VALUE_BYTES:
            values.add(encoded)
    return tuple(sorted(values, key=len, reverse=True))


def _visible_output(raw: bytes) -> tuple[bytes, list[int], int | None]:
    """Return terminal-visible bytes, their raw offsets, and an incomplete escape.

    WinPTY may insert CSI cursor/erase sequences between two reads, including in
    the middle of a value the child wrote contiguously. Credential matching must
    ignore complete terminal escapes while preserving their raw span for
    replacement. An escape cut off at the end is retained for the next read.
    """

    visible = bytearray()
    raw_offsets: list[int] = []
    index = 0
    while index < len(raw):
        if raw[index] != 0x1B:
            visible.append(raw[index])
            raw_offsets.append(index)
            index += 1
            continue
        escape_start = index
        if index + 1 >= len(raw):
            return bytes(visible), raw_offsets, escape_start
        kind = raw[index + 1]
        if kind == ord("["):  # CSI: params, intermediates, final byte.
            index += 2
            while index < len(raw) and 0x30 <= raw[index] <= 0x3F:
                index += 1
            while index < len(raw) and 0x20 <= raw[index] <= 0x2F:
                index += 1
            if index >= len(raw):
                return bytes(visible), raw_offsets, escape_start
            if 0x40 <= raw[index] <= 0x7E:
                index += 1
                continue
            index = escape_start + 1
            continue
        if kind == ord("]"):  # OSC: terminated by BEL or ST (ESC backslash).
            index += 2
            while index < len(raw):
                if raw[index] == 0x07:
                    index += 1
                    break
                if raw[index] == 0x1B and index + 1 < len(raw) and raw[index + 1] == ord("\\"):
                    index += 2
                    break
                index += 1
            else:
                return bytes(visible), raw_offsets, escape_start
            continue
        if 0x40 <= kind <= 0x5F:  # Two-byte Fe escape.
            index += 2
            continue
        index += 1  # Unknown escape: hide ESC, preserve following bytes.
    return bytes(visible), raw_offsets, None


def _redact_display_argv(argv: list[str], values: tuple[bytes, ...]) -> list[str]:
    """Hide known environment credentials from public session argv."""

    text_values = [value.decode("utf-8", "surrogatepass") for value in values]
    safe: list[str] = []
    for argument in argv:
        for value in text_values:
            argument = argument.replace(value, _OUTPUT_REDACTION_MARKER.decode("ascii"))
        safe.append(argument)
    return safe


# ── data classes ───────────────────────────────────────────────────────────


@dataclass
class PtySessionSummary:
    """Wire shape of a session row -- safe to serialise to JSON."""

    session_id: str
    argv: list[str]
    cwd: str | None
    started_at: str
    exit_code: int | None
    rows: int
    cols: int
    project_id: str | None = None


# ── platform backends ──────────────────────────────────────────────────────


class _PosixBackend:
    """``pty.fork`` + ``os.read`` for Linux / macOS."""

    def __init__(self) -> None:
        self.pid: int | None = None
        self.fd: int | None = None

    def spawn(self, argv: list[str], cwd: str | None, env: dict[str, str]) -> None:
        import pty

        pid, fd = pty.fork()
        if pid == 0:  # child
            try:
                if cwd:
                    os.chdir(cwd)
                os.execvpe(argv[0], argv, env)
            except OSError as exc:
                # The exec failed; write a hint to the PTY for the parent to read.
                os.write(2, f"synapse: failed to exec {argv[0]!r}: {exc}\n".encode())
                os._exit(127)
        self.pid = pid
        self.fd = fd

    def fileno(self) -> int:
        assert self.fd is not None
        return self.fd

    def read(self) -> bytes | None:
        try:
            return os.read(self.fd, READ_CHUNK) if self.fd is not None else None
        except OSError:
            return b""  # EIO etc. -- child closed the PTY

    def write(self, data: bytes) -> None:
        if self.fd is not None:
            os.write(self.fd, data)

    def resize(self, rows: int, cols: int) -> None:
        if self.fd is None:
            return
        try:
            import fcntl
            import struct
            import termios

            packed = struct.pack("HHHH", rows, cols, 0, 0)
            fcntl.ioctl(self.fd, termios.TIOCSWINSZ, packed)
        except Exception:  # pragma: no cover -- best effort
            pass

    def is_alive(self) -> bool:
        if self.pid is None:
            return False
        try:
            done, _ = os.waitpid(self.pid, os.WNOHANG)
            return done == 0
        except ChildProcessError:
            return False

    def reap(self) -> int | None:
        if self.pid is None:
            return None
        try:
            done, status = os.waitpid(self.pid, os.WNOHANG)
        except ChildProcessError:
            return None
        if done == 0:
            return None
        return os.waitstatus_to_exitcode(status)

    def terminate(self) -> None:
        if self.pid is None:
            return
        try:
            os.kill(self.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass

    def close(self) -> None:
        if self.fd is not None:
            try:
                os.close(self.fd)
            except OSError:
                pass
            self.fd = None


class _WindowsBackend:
    """``pywinpty`` for Windows. Reads on a daemon thread."""

    def __init__(self) -> None:
        self.proc: Any | None = None
        self._read_thread: threading.Thread | None = None
        self._closed = threading.Event()
        self._enter_needs_crlf = False

    def spawn(self, argv: list[str], cwd: str | None, env: dict[str, str]) -> None:
        from winpty import PtyProcess  # type: ignore[import-not-found]
        from winpty.enums import Backend  # type: ignore[import-not-found]

        # On this stack, pywinpty's default ConPTY path can render initial
        # output but silently drop stdin writes, which makes both xterm typing
        # and the mobile/desktop command pad feel dead. WinPTY keeps sessions
        # fully interactive, so prefer it until the ConPTY path is trustworthy.
        head = Path(argv[0]).stem.lower() if argv else ""
        self._enter_needs_crlf = head in {"powershell", "pwsh"}
        self.proc = PtyProcess.spawn(argv, cwd=cwd, env=env, backend=Backend.WinPTY)

    def fileno(self) -> int:
        return -1  # not used on Windows; the manager treats reads via thread

    def read(self) -> bytes | None:
        if self.proc is None:
            return None
        try:
            data = self.proc.read(READ_CHUNK)
        except EOFError:
            return b""
        if isinstance(data, str):
            return data.encode("utf-8", errors="replace")
        return data

    def write(self, data: bytes) -> None:
        if self.proc is None:
            return
        if self._enter_needs_crlf:
            data = _normalize_windows_input(data)
        # pywinpty's .write() wants str; encode-decode round-trip is safe
        # because the renderer sends UTF-8 from the keyboard.
        try:
            self.proc.write(data.decode("utf-8", errors="replace"))
        except EOFError:
            log.debug("PTY session %s closed, ignoring write", self.session_id)

    def resize(self, rows: int, cols: int) -> None:
        if self.proc is None:
            return
        try:
            self.proc.setwinsize(rows, cols)
        except Exception:  # pragma: no cover
            pass

    def is_alive(self) -> bool:
        return self.proc is not None and self.proc.isalive()

    def reap(self) -> int | None:
        if self.proc is None:
            return None
        if self.proc.isalive():
            return None
        return self.proc.exitstatus

    def terminate(self) -> None:
        if self.proc is None:
            return
        try:
            self.proc.terminate(force=True)
        except Exception:  # pragma: no cover
            pass

    def close(self) -> None:
        self.terminate()
        self._closed.set()


def _make_backend() -> _PosixBackend | _WindowsBackend:
    return _WindowsBackend() if sys.platform == "win32" else _PosixBackend()


def _normalize_windows_input(data: bytes) -> bytes:
    """Expand lone carriage returns to CRLF for shells that need it.

    WinPTY-backed PowerShell sessions do not reliably execute a line on a
    lone ``\\r`` even though xterm emits exactly that for Enter. ``cmd.exe``
    is happy with the raw ``\\r``, so callers opt into this normalization only
    for PowerShell-family runtimes.
    """

    out = bytearray()
    for index, value in enumerate(data):
        out.append(value)
        if value == 13:  # '\r'
            next_value = data[index + 1] if index + 1 < len(data) else None
            if next_value != 10:  # '\n'
                out.append(10)
    return bytes(out)


# ── session ────────────────────────────────────────────────────────────────


class PtySession:
    """One interactive child process under a PTY."""

    def __init__(
        self,
        session_id: str,
        argv: list[str],
        spawn_argv: list[str],
        cwd: str | None,
        env: dict[str, str],
        rows: int,
        cols: int,
        bus: EventBus,
        loop: asyncio.AbstractEventLoop,
        project_id: str | None = None,
        on_exit_persist: "_PersistCallback | None" = None,
    ) -> None:
        self.session_id = session_id
        self.cwd = cwd
        self.rows = rows
        self.cols = cols
        self.started_at: datetime = utc_now()
        self.exit_code: int | None = None
        # Workbench-tagged sessions persist their scrollback to a transcript
        # file (source='transcript') on exit -- ADR-0003 Phase D.
        self.project_id = project_id
        self._on_exit_persist = on_exit_persist
        self._persisted = False
        self._bus = bus
        self._loop = loop
        self._backend = _make_backend()
        self._scrollback: deque[bytes] = deque()
        self._scrollback_size = 0
        self._reader_task: asyncio.Task[Any] | None = None
        self._reader_thread: threading.Thread | None = None
        self._closing = False
        self._finalized = False
        self._finalize_lock = asyncio.Lock()
        self._output_publish_tasks: set[asyncio.Task[None]] = set()
        self._env = env
        self._spawn_argv = list(spawn_argv)
        self._sensitive_output_values = _sensitive_output_values(env)
        self.argv = _redact_display_argv(list(argv), self._sensitive_output_values)
        self._redaction_pending = b""
        self._redaction_idle_handle: asyncio.TimerHandle | None = None

    # ── lifecycle ───────────────────────────────────────────────────────

    async def start(self) -> None:
        await asyncio.to_thread(self._backend.spawn, self._spawn_argv, self.cwd, self._env)
        # Honour the renderer's initial size up front so the child sees a
        # sane TIOCSWINSZ from the first prompt.
        self._backend.resize(self.rows, self.cols)
        await self._bus.publish(
            event_name("pty", "session_started"),
            {
                "session_id": self.session_id,
                "argv": self.argv,
                "cwd": self.cwd,
                "rows": self.rows,
                "cols": self.cols,
                "project_id": self.project_id,
            },
        )

        if sys.platform == "win32":
            self._reader_thread = threading.Thread(
                target=self._windows_read_pump, name=f"pty-{self.session_id}",
                daemon=True,
            )
            self._reader_thread.start()
        else:
            fd = self._backend.fileno()
            self._loop.add_reader(fd, self._posix_on_readable)

    async def shutdown(self) -> None:
        """Close cleanly. Idempotent."""

        if self._closing:
            return
        self._closing = True
        try:
            if sys.platform != "win32":
                fd = self._backend.fileno()
                if fd >= 0:
                    try:
                        self._loop.remove_reader(fd)
                    except (KeyError, ValueError):
                        pass
            await asyncio.to_thread(self._backend.terminate)
            # Give the child a moment to exit so we capture the real code.
            await asyncio.sleep(0.05)
            await asyncio.to_thread(self._backend.close)
        finally:
            await self._finalize(default_exit_code=-1)

    # ── I/O ─────────────────────────────────────────────────────────────

    async def write(self, data: bytes) -> None:
        await asyncio.to_thread(self._backend.write, data)
        await self._bus.publish(
            event_name("pty", "session_input"),
            {
                "session_id": self.session_id,
                "bytes": len(data),
            },
        )

    async def resize(self, rows: int, cols: int) -> None:
        self.rows = max(1, int(rows))
        self.cols = max(1, int(cols))
        await asyncio.to_thread(self._backend.resize, self.rows, self.cols)

    def scrollback_bytes(self) -> bytes:
        return b"".join(self._scrollback)

    # ── read pumps ──────────────────────────────────────────────────────

    def _posix_on_readable(self) -> None:
        chunk = self._backend.read()
        if not chunk:
            # EOF / child gone. Stop watching and finalise.
            try:
                self._loop.remove_reader(self._backend.fileno())
            except (KeyError, ValueError, OSError):
                pass
            self._handle_chunk(b"")
            asyncio.ensure_future(self._on_eof())
            return
        self._handle_chunk(chunk)

    def _windows_read_pump(self) -> None:
        while not self._closing:
            chunk = self._backend.read()
            if not chunk:
                break
            self._loop.call_soon_threadsafe(self._handle_chunk, chunk)
        self._loop.call_soon_threadsafe(
            lambda: asyncio.ensure_future(self._on_eof())
        )

    def _handle_chunk(self, chunk: bytes) -> None:
        if not chunk:
            return
        safe_chunk = self._redact_output_chunk(chunk)
        if not safe_chunk:
            return
        self._record_output(safe_chunk)

    def _redact_output_chunk(self, chunk: bytes) -> bytes:
        """Redact credentials while retaining any split-secret suffix.

        PTY reads are arbitrarily chunked. A token may end one read halfway
        through and continue in the next, so replacement on each read alone is
        unsafe. Hold only a suffix that is a prefix of a protected value; the
        next read either completes and redacts it or proves it was ordinary
        output.
        """

        if not self._sensitive_output_values:
            return chunk
        # New output arrived, so any armed self-heal timer for the previous suffix is
        # moot; it is re-armed below if we end up holding bytes back again.
        self._cancel_redaction_idle_flush()
        combined = self._redaction_pending + chunk
        self._redaction_pending = b""
        # Exact raw replacement catches values inside terminal escape payloads
        # (OSC titles, CSI parameters) before visible-text parsing skips them.
        for value in self._sensitive_output_values:
            combined = combined.replace(value, _OUTPUT_REDACTION_MARKER)
        for value in self._sensitive_output_values:
            visible, raw_offsets, _incomplete = _visible_output(combined)
            matches: list[tuple[int, int]] = []
            start = 0
            while True:
                found = visible.find(value, start)
                if found < 0:
                    break
                matches.append((raw_offsets[found], raw_offsets[found + len(value) - 1] + 1))
                start = found + len(value)
            for raw_start, raw_end in reversed(matches):
                combined = combined[:raw_start] + _OUTPUT_REDACTION_MARKER + combined[raw_end:]

        keep = 0
        keep_start: int | None = None
        visible, raw_offsets, incomplete_escape = _visible_output(combined)
        for value in self._sensitive_output_values:
            for size in range(min(len(value) - 1, len(visible)), 0, -1):
                if visible.endswith(value[:size]):
                    keep = max(keep, size)
                    break
        if keep:
            keep_start = raw_offsets[len(visible) - keep]
        if incomplete_escape is not None:
            keep_start = incomplete_escape if keep_start is None else min(keep_start, incomplete_escape)
        if keep_start is not None:
            self._redaction_pending = combined[keep_start:]
            self._schedule_redaction_idle_flush()
            return combined[:keep_start]
        return combined

    def _cancel_redaction_idle_flush(self) -> None:
        if self._redaction_idle_handle is not None:
            self._redaction_idle_handle.cancel()
            self._redaction_idle_handle = None

    def _schedule_redaction_idle_flush(self) -> None:
        """Arm the self-heal timer for bytes we are holding back (see the constant)."""
        self._cancel_redaction_idle_flush()
        if self._closing:
            return
        self._redaction_idle_handle = self._loop.call_later(
            REDACTION_IDLE_FLUSH_SECONDS, self._on_redaction_idle
        )

    def _on_redaction_idle(self) -> None:
        """No further output arrived, so the held bytes were not a split secret.

        Emitted as-is rather than as the redaction marker: substituting `[REDACTED]` for
        an ordinary prompt tail (`$ w`) would corrupt the visible terminal, which is the
        very problem this fixes. The end-of-session flush stays conservative, because
        there no further output can ever arrive to disambiguate.
        """
        self._redaction_idle_handle = None
        pending = self._redaction_pending
        if not pending:
            return
        self._redaction_pending = b""
        self._record_output(pending)

    def _flush_redaction_pending(self) -> None:
        self._cancel_redaction_idle_flush()
        if not self._redaction_pending:
            return
        pending = self._redaction_pending
        self._redaction_pending = b""
        visible, _raw_offsets, _incomplete_escape = _visible_output(pending)
        if visible and any(value.startswith(visible) for value in self._sensitive_output_values):
            # Do not leak even a credential prefix when a child exits mid-write.
            self._record_output(_OUTPUT_REDACTION_MARKER)

    def _record_output(self, chunk: bytes) -> None:
        self._scrollback.append(chunk)
        self._scrollback_size += len(chunk)
        while self._scrollback_size > SCROLLBACK_BYTES and self._scrollback:
            dropped = self._scrollback.popleft()
            self._scrollback_size -= len(dropped)
        # Fan out as base64 so any byte (incl. control chars / non-UTF8) rides
        # cleanly through JSON / the WebSocket layer.
        publish_task = asyncio.create_task(
            self._bus.publish(
                event_name("pty", "session_output"),
                {
                    "session_id": self.session_id,
                    "data": base64.b64encode(chunk).decode("ascii"),
                },
            )
        )
        self._output_publish_tasks.add(publish_task)

        def _observe_publish(completed: asyncio.Task[None]) -> None:
            self._output_publish_tasks.discard(completed)
            if completed.cancelled():
                return
            error = completed.exception()
            if error is not None:
                log.error(
                    "PTY output publish failed for %s: %s",
                    self.session_id,
                    error,
                    exc_info=(type(error), error, error.__traceback__),
                )

        publish_task.add_done_callback(_observe_publish)

    async def _drain_output_publications(self) -> None:
        while self._output_publish_tasks:
            pending = tuple(self._output_publish_tasks)
            await asyncio.gather(*pending, return_exceptions=True)

    async def _finalize(self, *, default_exit_code: int) -> None:
        """Publish one ordered terminal lifecycle across EOF/shutdown races."""

        async with self._finalize_lock:
            if self._finalized:
                return
            if self.exit_code is None:
                observed = await asyncio.to_thread(self._backend.reap)
                # Shutdown may begin while an EOF-owned reap is running in a
                # worker thread. Re-check the operator-stop flag only after
                # reap returns, while this lock still owns finalization, so a
                # missing child exit code cannot be misreported as success.
                fallback_exit_code = -1 if self._closing else default_exit_code
                self.exit_code = observed if observed is not None else fallback_exit_code
            self._flush_redaction_pending()
            await self._drain_output_publications()
            self._finalized = True
            await self._bus.publish(
                event_name("pty", "session_exited"),
                {"session_id": self.session_id, "exit_code": self.exit_code},
            )
            await self._maybe_persist_transcript()
            await self._bus.publish(
                event_name("pty", "session_finalized"),
                {"session_id": self.session_id, "exit_code": self.exit_code},
            )

    async def _on_eof(self) -> None:
        if self._closing or self._finalized:
            return
        await self._finalize(default_exit_code=0)

    async def _maybe_persist_transcript(self) -> None:
        """ADR-0003 Phase D -- write scrollback to a transcript file row.

        Only runs for workbench-tagged sessions (``project_id`` set) and
        the manager wired a persistence callback. Idempotent across both
        exit paths (clean shutdown + EOF)."""

        if self._persisted or self.project_id is None or self._on_exit_persist is None:
            return
        self._persisted = True
        try:
            await self._on_exit_persist(self)
        except Exception:  # pragma: no cover -- never let transcript I/O kill a session
            log.exception("Failed to persist transcript for session %s", self.session_id)

    # ── summary ─────────────────────────────────────────────────────────

    def summary(self) -> PtySessionSummary:
        return PtySessionSummary(
            session_id=self.session_id,
            argv=self.argv,
            cwd=self.cwd,
            started_at=to_iso(self.started_at),
            exit_code=self.exit_code,
            rows=self.rows,
            cols=self.cols,
            project_id=self.project_id,
        )


# ── manager ────────────────────────────────────────────────────────────────


class PtySessionManager:
    """Track every open PTY session for the daemon lifetime."""

    def __init__(self, bus: EventBus, storage: "Storage | None" = None) -> None:
        self._bus = bus
        # When set, workbench-tagged sessions persist scrollback through
        # files_storage on exit (ADR-0003 Phase D).
        self._storage = storage
        self._sessions: dict[str, PtySession] = {}

    @staticmethod
    def _powershell_quote(value: str) -> str:
        """Quote one argument for a PowerShell ``-Command`` string."""

        return "'" + value.replace("'", "''") + "'"

    def _powershell_wrap(self, argv: list[str], *, lowercase_arg0: bool) -> list[str] | None:
        """Wrap ``argv`` to launch through PowerShell's ``&`` call operator so a
        ``.cmd``/``.bat`` shim (or Copilot) receives ALL its arguments intact
        under winpty. Returns ``None`` if ``powershell.exe`` can't be resolved,
        so the caller decides the fallback.

        ``_powershell_quote`` is a SECURITY BOUNDARY: a single-quoted PowerShell
        literal does no interpolation (``$(...)``, backticks, ``;`` ``%`` ``"``
        and newlines are all inert) and doubling the internal ``'`` is the
        complete escape. Do NOT "simplify" it to double quotes or raw
        concatenation. (The concrete squad arg — a daemon-generated
        ``--mcp-config`` path — is trusted, but this wrapper carries arbitrary
        argv, so treat quoting as the boundary.)
        """

        powershell = resolve_command("powershell.exe")
        if powershell is None:
            return None
        head = argv[0].lower() if lowercase_arg0 else argv[0]
        parts = [head, *argv[1:]]
        command = "& " + " ".join(self._powershell_quote(part) for part in parts)
        return [powershell, "-NoLogo", "-Command", command]

    def _spawn_argv_for_runtime(self, argv: list[str]) -> list[str]:
        """Adjust platform-specific Windows runtimes while keeping the public
        argv (``display_argv`` / ``self.argv``) stable — only ``spawn_argv`` is
        rewritten, so the UI + transcript still show the real runtime argv.

        Two Windows runtimes need a PowerShell ``&`` wrapper under winpty:

        - **GitHub Copilot CLI** is a documented PowerShell experience; the raw
          ``copilot.exe`` under winpty hangs then exits with ``unknown option
          '--no-warnings'``.
        - **``.cmd``/``.bat`` shims WITH arguments** (e.g. ``claude.CMD
          --mcp-config <path>``): winpty drops the trailing args (cmd.exe reports
          the 2nd token as "not recognized"), so EVERY squad-launched ``claude``
          worker silently failed whenever an MCP server was enabled and
          ``--mcp-config`` was appended. Routing through PowerShell's ``&`` makes
          the ``.cmd`` shim forward its args via ``%*``.

        Scoped to the broken case (``.cmd``/``.bat`` with >1 element): a bare
        single-arg ``.cmd`` already launches correctly via raw winpty, so it is
        deliberately left on that proven path (locked by a test) to keep the
        blast radius minimal on this fragile file. ``cmd.exe /c`` wrapping and a
        backend-level fix were rejected — cmd quoting (carets, ``%``, ``&``,
        spaced paths) is materially harder to get right than PowerShell's
        single-quote literal, and ``WinPtyBackend`` should stay a dumb spawn
        primitive rather than learn runtime-shim policy.
        """

        if sys.platform != "win32" or not argv:
            return list(argv)
        # Copilot must stay the FIRST branch so a hypothetical ``copilot.cmd``
        # keeps its (lower-cased) semantics instead of the generic path.
        if Path(argv[0]).stem.lower() == "copilot":
            wrapped = self._powershell_wrap(argv, lowercase_arg0=True)
            return wrapped if wrapped is not None else list(argv)
        # ``.cmd``/``.bat`` shim WITH arguments -> the squad-launch bug. Wrap it.
        if Path(argv[0]).suffix.lower() in (".cmd", ".bat") and len(argv) > 1:
            wrapped = self._powershell_wrap(argv, lowercase_arg0=False)
            if wrapped is None:
                # Do NOT fall back to the known-broken raw argv (it hangs the
                # work item silently). Fail loudly so the caller surfaces it.
                raise RuntimeError(
                    "powershell.exe is required to launch a .cmd/.bat runtime "
                    "with arguments on Windows, but it was not found on PATH"
                )
            return wrapped
        return list(argv)

    async def spawn(
        self,
        argv: list[str],
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        rows: int = 24,
        cols: int = 80,
        project_id: str | None = None,
        session_id: str | None = None,
    ) -> PtySession:
        if not argv:
            raise ValueError("spawn requires a non-empty argv")
        # Resolve the binary so the user gets an honest error before the PTY
        # is even allocated.
        resolved = resolve_command(argv[0])
        if resolved is None:
            raise FileNotFoundError(f"command not found on PATH: {argv[0]!r}")
        display_argv = [resolved, *argv[1:]]
        spawn_argv = self._spawn_argv_for_runtime(display_argv)

        # Default cwd to the user's home directory (v0.1.35). Why: the
        # major AI CLIs we ship in the marketplace (claude, codex) cache
        # their OAuth state in ~/.claude / ~/.config/codex and ALSO key
        # their per-project session state by the cwd they were started
        # in. If we let cwd=None fall through to "wherever the daemon
        # happened to chdir last", every quick-launch lands in a
        # different folder and the CLI re-shows its setup wizard each
        # time. Pinning to ~ means the user goes through Claude/Codex
        # first-run once and then never again.
        if cwd is None:
            cwd = str(Path.home())

        # Validate the working directory up front. Passing a non-existent cwd to
        # the native PTY backend (ConPTY/winpty on Windows) can take the whole
        # daemon process down at a level Python cannot catch -- the WinptyError
        # is raised AND the process still dies. Refuse a bad cwd cleanly here so
        # callers get an honest FileNotFoundError (-> 422) and the daemon lives.
        if cwd is not None and not Path(cwd).is_dir():
            raise FileNotFoundError(f"working directory does not exist: {cwd!r}")

        merged_env = dict(os.environ)
        if env:
            merged_env.update(env)
        # TERM matters: xterm.js renders xterm-256color cleanly.
        merged_env.setdefault("TERM", "xterm-256color")

        session_id = session_id or secrets.token_hex(6)
        session = PtySession(
            session_id=session_id,
            argv=display_argv,
            spawn_argv=spawn_argv,
            cwd=cwd,
            env=merged_env,
            rows=rows,
            cols=cols,
            bus=self._bus,
            loop=asyncio.get_running_loop(),
            project_id=project_id,
            on_exit_persist=self._persist_transcript if self._storage is not None else None,
        )
        await session.start()
        self._sessions[session_id] = session
        return session

    async def _persist_transcript(self, session: PtySession) -> None:
        """Write the session's scrollback as a project_files row tagged
        ``source='transcript'``. Imported lazily so PtySessionManager stays
        importable without the migration applied."""

        from . import files_storage as _fs

        if self._storage is None or session.project_id is None:
            return
        scrollback = session.scrollback_bytes()
        if not scrollback:
            return  # no point storing an empty file

        name = (
            f"transcript-{Path(session.argv[0]).name}-"
            f"{to_iso(session.started_at).replace(':', '-')}.log"
        )
        try:
            blob = _fs.write_streaming_with_hash(
                io.BytesIO(scrollback),
                original_name=name,
                data_dir=self._storage.data_dir,
                max_bytes=_fs.DEFAULT_MAX_FILE_BYTES,
            )
        except _fs.FileTooLargeError:
            log.warning("Transcript for %s exceeded max size; dropped.", session.session_id)
            return

        with self._storage.transaction() as conn:
            _fs.insert_file_row(
                conn,
                file_id=blob.file_id,
                project_id=session.project_id,
                original_name=name,
                on_disk_name=blob.on_disk_name,
                mime="text/plain",
                size_bytes=blob.size_bytes,
                sha256=blob.sha256,
                source="transcript",
                source_session=session.session_id,
            )
            canonical = _fs.find_existing_duplicate(
                conn,
                sha256=blob.sha256,
                project_id=session.project_id,
                exclude_id=blob.file_id,
            )
            if canonical is not None:
                _fs.drop_quarantined(blob)
                conn.execute(
                    "UPDATE project_files SET duplicate_of = ? WHERE id = ?",
                    (canonical, blob.file_id),
                )
            else:
                _fs.finalize_after_scan(blob, self._storage.data_dir, project_id=session.project_id)

    def get(self, session_id: str) -> PtySession | None:
        return self._sessions.get(session_id)

    def list(self) -> list[PtySession]:
        return list(self._sessions.values())

    async def close(self, session_id: str) -> bool:
        session = self._sessions.pop(session_id, None)
        if session is None:
            return False
        await session.shutdown()
        return True

    async def shutdown_all(self) -> None:
        for session in list(self._sessions.values()):
            try:
                await session.shutdown()
            except Exception:  # pragma: no cover -- defensive
                log.exception("Error shutting down session %s", session.session_id)
        self._sessions.clear()
