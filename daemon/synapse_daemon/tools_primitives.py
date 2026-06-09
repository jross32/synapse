"""Vetted primitives for declarative tools (v0.1.22 · ADR-0001 step 2).

A *declarative* tool's manifest declares actions like::

    {
      "id": "open-docs",
      "label": "Open docs",
      "primitive": "url.open",
      "params": {"url": "https://example.com/{section}"}
    }

and the daemon runs them through this module -- no Python handler shipped,
no untrusted code imported. The primitives are a small audited set; adding
one is a deliberate API decision (see ADR-0001 "Open questions").

Field substitution
------------------
Strings in ``params`` are substituted before execution: ``{key}`` is replaced
by ``str(fields[key])`` (empty string if the field is missing). This is *not*
a template language -- there is no expression evaluation. ``argv`` stays a
list, never a shell string, so a value like ``"; rm -rf /"`` cannot inject a
command.

Primitives
----------
- ``url.open`` -- opens a URL in the user's default browser. Refuses
  non-``http(s)`` schemes.
- ``process.spawn`` -- spawns a one-shot subprocess (argv list, no shell),
  captures combined stdout/stderr, waits with a timeout (default 5 s,
  capped at 30 s). Returns the output in the tool state's ``result``.
"""

from __future__ import annotations

import asyncio
import logging
import re
import webbrowser
from typing import Any

from .api_versions import event_name
from .models import EntityStatus, ErrorRef, ToolState
from .ws import EventBus

log = logging.getLogger(__name__)

#: Public set of primitive ids the registry will dispatch to. Order matters
#: for documentation only -- runtime is keyed by exact match.
PRIMITIVES: frozenset[str] = frozenset({"url.open", "process.spawn", "pty.spawn"})

_SPAWN_TIMEOUT_DEFAULT = 5.0
_SPAWN_TIMEOUT_MAX = 30.0
_OUTPUT_TAIL_BYTES = 4096

_FIELD_RE = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}")


def is_known_primitive(name: str) -> bool:
    return name in PRIMITIVES


def substitute(template: str, fields: dict[str, Any]) -> str:
    """Replace ``{name}`` placeholders with stringified field values."""

    def repl(match: re.Match[str]) -> str:
        value = fields.get(match.group(1), "")
        return "" if value is None else str(value)

    return _FIELD_RE.sub(repl, template)


async def run_primitive(
    primitive: str,
    params: dict[str, Any],
    fields: dict[str, Any],
    bus: EventBus,
    tool_id: str,
) -> ToolState:
    """Dispatch a declarative action to its primitive implementation."""

    if not is_known_primitive(primitive):
        return _error(
            tool_id,
            "primitive.unknown",
            f"Unknown primitive '{primitive}'. Known: {sorted(PRIMITIVES)}.",
        )

    if primitive == "url.open":
        return await _url_open(params, fields, bus, tool_id)
    if primitive == "process.spawn":
        return await _process_spawn(params, fields, bus, tool_id)
    if primitive == "pty.spawn":
        return await _pty_spawn(params, fields, bus, tool_id)
    # The guard above keeps us out of here; this is for type-checkers.
    return _error(tool_id, "primitive.unknown", primitive)


# ── url.open ───────────────────────────────────────────────────────────────


async def _url_open(
    params: dict[str, Any],
    fields: dict[str, Any],
    bus: EventBus,
    tool_id: str,
) -> ToolState:
    template = params.get("url")
    if not isinstance(template, str) or not template.strip():
        return _error(
            tool_id,
            "primitive.bad_params",
            "url.open requires a non-empty 'url' string param.",
        )
    url = substitute(template, fields).strip()
    if not re.match(r"^https?://", url, flags=re.IGNORECASE):
        return _error(
            tool_id,
            "primitive.bad_url",
            f"Refusing to open non-http(s) URL: {url!r}",
        )
    try:
        opened = await asyncio.to_thread(webbrowser.open, url)
    except Exception as exc:  # pragma: no cover -- webbrowser raises rarely
        return _error(tool_id, "primitive.open_failed", str(exc))
    if not opened:
        return _error(
            tool_id,
            "primitive.open_failed",
            "Operating system reported no browser was launched.",
        )
    await bus.publish(
        event_name("tool", "primitive_ran"),
        {"tool_id": tool_id, "primitive": "url.open", "url": url},
    )
    return ToolState(
        tool_id=tool_id,
        status=EntityStatus.LAUNCHED,
        result={"primitive": "url.open", "url": url},
        message=f"Opened {url}",
    )


# ── process.spawn ──────────────────────────────────────────────────────────


async def _process_spawn(
    params: dict[str, Any],
    fields: dict[str, Any],
    bus: EventBus,
    tool_id: str,
) -> ToolState:
    raw_argv = params.get("argv")
    if not isinstance(raw_argv, list) or not raw_argv:
        return _error(
            tool_id,
            "primitive.bad_params",
            "process.spawn requires a non-empty 'argv' list param.",
        )
    argv = [substitute(str(part), fields) for part in raw_argv]
    if not argv[0]:
        return _error(tool_id, "primitive.bad_params", "process.spawn argv[0] is empty.")

    cwd_template = params.get("cwd")
    cwd = (
        substitute(cwd_template, fields)
        if isinstance(cwd_template, str) and cwd_template.strip()
        else None
    )

    raw_timeout = params.get("timeout", _SPAWN_TIMEOUT_DEFAULT)
    try:
        timeout = float(raw_timeout)
        timeout = min(_SPAWN_TIMEOUT_MAX, max(0.1, timeout))
    except (TypeError, ValueError):
        timeout = _SPAWN_TIMEOUT_DEFAULT

    try:
        proc = await asyncio.create_subprocess_exec(
            *argv,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            stdin=asyncio.subprocess.DEVNULL,
            cwd=cwd,
        )
    except (OSError, FileNotFoundError) as exc:
        return _error(
            tool_id,
            "primitive.spawn_failed",
            f"Could not spawn {argv[0]!r}: {exc}",
        )

    try:
        stdout_bytes, _stderr = await asyncio.wait_for(
            proc.communicate(), timeout=timeout
        )
    except asyncio.TimeoutError:
        try:
            proc.kill()
        except ProcessLookupError:  # pragma: no cover -- race
            pass
        return _error(
            tool_id,
            "primitive.timeout",
            f"Process did not finish within {timeout:.1f}s; argv[0]={argv[0]!r}.",
        )

    output = stdout_bytes.decode("utf-8", errors="replace") if stdout_bytes else ""
    output_tail = output[-_OUTPUT_TAIL_BYTES:] if len(output) > _OUTPUT_TAIL_BYTES else output
    exit_code = proc.returncode if proc.returncode is not None else -1

    if exit_code != 0:
        state = _error(
            tool_id,
            "primitive.exit_nonzero",
            f"Process exited with code {exit_code}.",
        )
        state.result = {
            "primitive": "process.spawn",
            "argv": argv,
            "exit_code": exit_code,
            "output": output_tail,
        }
        return state

    await bus.publish(
        event_name("tool", "primitive_ran"),
        {
            "tool_id": tool_id,
            "primitive": "process.spawn",
            "argv": argv,
            "exit_code": exit_code,
        },
    )
    return ToolState(
        tool_id=tool_id,
        status=EntityStatus.LAUNCHED,
        result={
            "primitive": "process.spawn",
            "argv": argv,
            "exit_code": exit_code,
            "output": output_tail,
        },
        message=f"Ran: {' '.join(argv)}",
    )


# ── helpers ────────────────────────────────────────────────────────────────


async def _pty_spawn(
    params: dict[str, Any],
    fields: dict[str, Any],
    bus: EventBus,
    tool_id: str,
) -> ToolState:
    """Launch an interactive child under a PTY (v0.1.25 · ADR-0002 Phase A).

    The session manager is resolved lazily via the bus's ``_pty_manager``
    attribute, which the app wires up at boot. We avoid a hard import cycle
    that way and the primitive stays optional in cut-down test harnesses.
    """

    manager = getattr(bus, "_pty_manager", None)
    if manager is None:
        return _error(
            tool_id,
            "primitive.unavailable",
            "pty.spawn primitive needs a PtySessionManager wired on the bus.",
        )

    raw_argv = params.get("argv")
    if not isinstance(raw_argv, list) or not raw_argv:
        return _error(
            tool_id,
            "primitive.bad_params",
            "pty.spawn requires a non-empty 'argv' list param.",
        )
    argv = [substitute(str(part), fields) for part in raw_argv]
    if not argv[0]:
        return _error(tool_id, "primitive.bad_params", "pty.spawn argv[0] is empty.")

    cwd_template = params.get("cwd")
    cwd = (
        substitute(cwd_template, fields)
        if isinstance(cwd_template, str) and cwd_template.strip()
        else None
    )

    rows = int(params.get("rows", 24))
    cols = int(params.get("cols", 80))

    try:
        session = await manager.spawn(argv=argv, cwd=cwd, rows=rows, cols=cols)
    except FileNotFoundError as exc:
        return _error(tool_id, "primitive.spawn_failed", str(exc))
    except Exception as exc:  # pragma: no cover -- defensive
        return _error(tool_id, "primitive.spawn_failed", f"PTY spawn failed: {exc}")

    return ToolState(
        tool_id=tool_id,
        status=EntityStatus.LAUNCHED,
        result={
            "primitive": "pty.spawn",
            "session_id": session.session_id,
            "argv": session.argv,
            "rows": session.rows,
            "cols": session.cols,
        },
        message=f"Opened PTY session {session.session_id}",
    )


def _error(tool_id: str, code: str, message: str) -> ToolState:
    return ToolState(
        tool_id=tool_id,
        status=EntityStatus.ERROR,
        last_error=ErrorRef(code=code, message=message),
    )
