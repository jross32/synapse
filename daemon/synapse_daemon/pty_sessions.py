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

    def spawn(self, argv: list[str], cwd: str | None, env: dict[str, str]) -> None:
        from winpty import PtyProcess  # type: ignore[import-not-found]

        self.proc = PtyProcess.spawn(argv, cwd=cwd, env=env)

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
        # pywinpty's .write() wants str; encode-decode round-trip is safe
        # because the renderer sends UTF-8 from the keyboard.
        self.proc.write(data.decode("utf-8", errors="replace"))

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


# ── session ────────────────────────────────────────────────────────────────


class PtySession:
    """One interactive child process under a PTY."""

    def __init__(
        self,
        session_id: str,
        argv: list[str],
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
        self.argv = list(argv)
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
        self._env = env

    # ── lifecycle ───────────────────────────────────────────────────────

    async def start(self) -> None:
        await asyncio.to_thread(self._backend.spawn, self.argv, self.cwd, self._env)
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
            if self.exit_code is None:
                self.exit_code = await asyncio.to_thread(self._backend.reap) or -1
            await self._bus.publish(
                event_name("pty", "session_exited"),
                {"session_id": self.session_id, "exit_code": self.exit_code},
            )
            await self._maybe_persist_transcript()
            await self._bus.publish(
                event_name("pty", "session_finalized"),
                {"session_id": self.session_id, "exit_code": self.exit_code},
            )

    # ── I/O ─────────────────────────────────────────────────────────────

    async def write(self, data: bytes) -> None:
        await asyncio.to_thread(self._backend.write, data)

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
        self._scrollback.append(chunk)
        self._scrollback_size += len(chunk)
        while self._scrollback_size > SCROLLBACK_BYTES and self._scrollback:
            dropped = self._scrollback.popleft()
            self._scrollback_size -= len(dropped)
        # Fan out as base64 so any byte (incl. control chars / non-UTF8) rides
        # cleanly through JSON / the WebSocket layer.
        asyncio.ensure_future(
            self._bus.publish(
                event_name("pty", "session_output"),
                {
                    "session_id": self.session_id,
                    "data": base64.b64encode(chunk).decode("ascii"),
                },
            )
        )

    async def _on_eof(self) -> None:
        if self.exit_code is not None:
            return
        self.exit_code = await asyncio.to_thread(self._backend.reap)
        if self.exit_code is None:
            self.exit_code = 0
        await self._bus.publish(
            event_name("pty", "session_exited"),
            {"session_id": self.session_id, "exit_code": self.exit_code},
        )
        await self._maybe_persist_transcript()
        await self._bus.publish(
            event_name("pty", "session_finalized"),
            {"session_id": self.session_id, "exit_code": self.exit_code},
        )

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
            argv=[resolved, *argv[1:]],
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
