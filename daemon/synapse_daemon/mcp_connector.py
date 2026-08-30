"""Minimal MCP (Model Context Protocol) server for the claude.ai custom
connector (ADR-0012).

Hand-rolled, stateless, Streamable-HTTP-compatible JSON-RPC 2.0 endpoint at
``/mcp/{token}``. Read-only by default: it wraps the daemon's existing
in-process reads (projects, tools, quick-actions, squads, per-project records)
so Claude (web/desktop) can introspect Synapse over the user's own Cloudtap
tunnel. The ``{token}`` path segment is the secret -- it must equal the
daemon's local auth token.

No external MCP SDK dependency: the protocol surface we need (initialize /
tools/list / tools/call / ping + the initialized notification) is small enough
to implement directly beside the REST API.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse

from . import __version__, boot_config, local_agent, mcp_servers, quality_os, skill_packs
from . import agent_squads as squads
from . import collaboration_rooms as collaboration_rooms_module
from . import project_records as records
from . import projects as projects_module
from .api_versions import event_name
from .auth import AuthManager
from .errors import SynapseError
from .quick_actions import load_templates
from .runtime_paths import repo_root
from .runtime_resolution import resolve_command
from .storage import Storage
from .time_utils import from_iso, to_iso, utc_now
from .tools_registry import ToolRegistry
from .ws import EventBus

# A recent MCP protocol revision. We echo the client's requested version when
# it sends one (forward-compatible), else fall back to this.
DEFAULT_PROTOCOL_VERSION = "2025-06-18"
JSONRPC = "2.0"


def _writes_allowed(data_dir: Path) -> bool:
    """Whether the connector serves its write/dispatch tools.

    `data_dir` is required rather than defaulted, on purpose: this used to fall back to a
    hardcoded `repo_root() / "data"` when no override was set, which silently read the
    WRONG config for a daemon started with a non-default `--data-dir`, and for any isolated
    test using its own `Storage` - caught by a test in this suite that set
    `mcp_writes_enabled=False` in a scratch data dir and watched a write tool succeed
    anyway, because this function was reading the real repo's config instead. There is no
    silent fallback left to get wrong; every caller passes `storage.data_dir` explicitly.

    The persisted setting is the source of truth. `SYNAPSE_MCP_ALLOW_WRITES` still wins when
    it is set, so a locked-down deployment can force it either way without touching the
    file - but it is no longer how a person turns this on, because an environment variable
    has to exist in whichever shell launched the app and silently reverted otherwise.
    """
    override = os.getenv("SYNAPSE_MCP_ALLOW_WRITES", "").strip().lower()
    if override in {"1", "true", "yes"}:
        return True
    if override in {"0", "false", "no"}:
        return False
    try:
        from . import boot_config

        return boot_config.load(data_dir).mcp_writes_enabled
    except Exception:  # noqa: BLE001 -- a missing config must not disable the connector
        return True




def _http_mcp(server: Any, method: str, params: dict[str, Any], timeout: int) -> Any:
    """Speak MCP to a server that listens over HTTP rather than stdio.

    The web scraper is registered this way - it is a long-running service on its own port,
    not a process to spawn per call - so a stdio-only proxy could not reach any of its ~93
    tools. Same JSON-RPC, different pipe.

    Streamable HTTP servers may answer with `text/event-stream`, so the response is scanned
    for `data:` frames as well as parsed as plain JSON.
    """
    import json as _json
    import urllib.error
    import urllib.request

    headers = {"Content-Type": "application/json",
               "Accept": "application/json, text/event-stream",
               "MCP-Protocol-Version": "2024-11-05"}

    def _post(payload: dict[str, Any]) -> Any:
        request = urllib.request.Request(
            server.url, data=_json.dumps(payload).encode(),
            headers=dict(headers), method="POST")
        try:
            with urllib.request.urlopen(request, timeout=timeout) as resp:
                body = resp.read().decode("utf-8", "replace")
                session = resp.headers.get("Mcp-Session-Id")
                if session:
                    # Streamable-HTTP servers hand out a session on `initialize` and reject
                    # everything after it with 400 unless the id comes back. Without this the
                    # web scraper's ~93 tools were unreachable for that one header.
                    headers["Mcp-Session-Id"] = session
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:300]
            raise ValueError(f"{server.id} returned {exc.code}: {detail}")
        for line in body.splitlines():
            line = line.strip()
            if line.startswith("data:"):
                line = line[5:].strip()
            if not line.startswith("{"):
                continue
            try:
                message = _json.loads(line)
            except ValueError:
                continue
            if message.get("id") == payload.get("id"):
                if "error" in message:
                    raise ValueError(f"{server.id}: {message['error']}")
                return message.get("result")
        raise ValueError(f"{server.id} gave no reply to {payload.get('method')}")

    _post({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
        "protocolVersion": "2024-11-05", "capabilities": {},
        "clientInfo": {"name": "synapse", "version": __version__}}})
    return _post({"jsonrpc": "2.0", "id": 2, "method": method, "params": params})

def _stdio_mcp(server: Any, method: str, params: dict[str, Any], timeout: int) -> Any:
    """Speak MCP to a stdio server for exactly one call, then shut it down.

    A short-lived process per call rather than a pool: these servers are cheap to start,
    and a long-lived one held across a remote chat's idle time is a process nobody is
    watching. Correctness first; if the startup cost ever matters it can be pooled later.

    Handshake is required - a server that has not seen `initialize` is entitled to refuse
    everything after it, and several do.
    """
    import json as _json
    import subprocess

    # `npx` and friends are `.cmd` shims on Windows, and CreateProcess will not find them
    # from a bare name - every npx-launched server failed with
    # "[WinError 2] The system cannot find the file specified". resolve_command already
    # knows how to look beyond PATH, so reuse it rather than guessing at extensions.
    executable = resolve_command(server.command) or server.command
    argv = [executable, *(server.args or [])]
    env = {**os.environ, **{k: str(v) for k, v in (server.env or {}).items()}}
    proc = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, text=True, encoding="utf-8",
                            env=env)
    try:
        lines = [
            _json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
                "protocolVersion": "2024-11-05", "capabilities": {},
                "clientInfo": {"name": "synapse", "version": __version__}}}),
            _json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}),
            _json.dumps({"jsonrpc": "2.0", "id": 2, "method": method, "params": params}),
        ]
        out, err = proc.communicate("\n".join(lines) + "\n", timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        raise ValueError(f"{server.id} did not answer within {timeout}s")
    finally:
        if proc.poll() is None:
            proc.kill()

    for line in (out or "").splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            message = _json.loads(line)
        except ValueError:
            continue
        if message.get("id") == 2:
            if "error" in message:
                raise ValueError(f"{server.id}: {message['error']}")
            return message.get("result")
    raise ValueError(
        f"{server.id} returned no reply to {method}. stderr: {(err or '')[-400:]}")

_TOOL_ANNOTATIONS: dict[str, dict[str, bool]] = {
    # ChatGPT (and other MCP clients) read `annotations.readOnlyHint` to decide whether a
    # tool call needs confirmation - and per OpenAI's own docs, a tool with NO annotation is
    # treated as a write action by default. Every tool here was shipped with none, so every
    # single one - including plain listing/reading tools - was classified as a write action
    # and gated behind confirmation, which is very likely why ChatGPT could see and list all
    # 24 tools but denied calling them: nothing told it which of them were actually safe.
    #
    # These are load-bearing claims, not decoration: getting one wrong in the permissive
    # direction is a real safety problem (a client may skip confirmation on a tool marked
    # readOnlyHint: true), so `test_every_tool_is_annotated_and_matches_its_handler` checks
    # each one against what the handler actually does, not just that a value is present.
    #
    # -- genuinely read-only: nothing here can change state on this machine --
    "synapse_get_context": {"readOnlyHint": True, "idempotentHint": True},
    "synapse_list_projects": {"readOnlyHint": True, "idempotentHint": True},
    "synapse_get_project_records": {"readOnlyHint": True, "idempotentHint": True},
    "synapse_get_project_ai_context": {"readOnlyHint": True, "idempotentHint": True},
    "synapse_list_tools": {"readOnlyHint": True, "idempotentHint": True},
    "synapse_list_quick_actions": {"readOnlyHint": True, "idempotentHint": True},
    "synapse_list_skill_packs": {"readOnlyHint": True, "idempotentHint": True},
    "synapse_get_skill_pack": {"readOnlyHint": True, "idempotentHint": True},
    "synapse_list_agent_squads": {"readOnlyHint": True, "idempotentHint": True},
    "synapse_list_sessions": {"readOnlyHint": True, "idempotentHint": True},
    "synapse_list_collaboration_rooms": {"readOnlyHint": True, "idempotentHint": True},
    "synapse_sync_collaboration_room": {"readOnlyHint": True, "idempotentHint": True},
    "synapse_recent_activity": {"readOnlyHint": True, "idempotentHint": True},
    "synapse_quality_summary": {"readOnlyHint": True, "idempotentHint": True},
    "synapse_watch_repo": {"readOnlyHint": True, "idempotentHint": False},
    "synapse_runtime_status": {"readOnlyHint": True, "idempotentHint": True},
    "synapse_list_blueprints": {"readOnlyHint": True, "idempotentHint": True},
    "synapse_list_mcp_tools": {"readOnlyHint": True, "idempotentHint": True},
    "synapse_read_file": {"readOnlyHint": True, "idempotentHint": True},
    # Looks up a work item and returns the REST call that starts it - it does not spawn
    # anything itself (see the handler), so it genuinely is read-only despite the name.
    "synapse_launch_work_item": {"readOnlyHint": True, "idempotentHint": True},
    "synapse_list_playbooks": {"readOnlyHint": True, "idempotentHint": True},
    "synapse_get_playbook": {"readOnlyHint": True, "idempotentHint": True},
    # -- additive writes: create a new record, never delete or overwrite an existing one --
    "synapse_add_project_idea": {"readOnlyHint": False, "destructiveHint": False,
                                 "idempotentHint": False},
    "synapse_capture_note": {"readOnlyHint": False, "destructiveHint": False,
                             "idempotentHint": False},
    "synapse_create_squad": {"readOnlyHint": False, "destructiveHint": False,
                             "idempotentHint": False},
    "synapse_add_work_item": {"readOnlyHint": False, "destructiveHint": False,
                              "idempotentHint": False},
    "synapse_create_collaboration_room": {"readOnlyHint": False, "destructiveHint": False,
                                          "idempotentHint": False},
    "synapse_join_collaboration_room": {"readOnlyHint": False, "destructiveHint": False,
                                        "idempotentHint": False},
    "synapse_post_collaboration_message": {"readOnlyHint": False, "destructiveHint": False,
                                           "idempotentHint": False},
    "synapse_leave_collaboration_room": {"readOnlyHint": False, "destructiveHint": False,
                                         "idempotentHint": False},
    "synapse_thread_bootstrap": {"readOnlyHint": False, "destructiveHint": False,
                                 "idempotentHint": True},
    "synapse_thread_begin_turn": {"readOnlyHint": False, "destructiveHint": False,
                                  "idempotentHint": True},
    "synapse_thread_heartbeat": {"readOnlyHint": False, "destructiveHint": False,
                                 "idempotentHint": True},
    "synapse_thread_finish_turn": {"readOnlyHint": False, "destructiveHint": False,
                                   "idempotentHint": True},
    "synapse_set_project_chat_url": {"readOnlyHint": False, "destructiveHint": False,
                                     "idempotentHint": True},
    "synapse_report_playbook_status": {"readOnlyHint": False, "destructiveHint": False,
                                       "idempotentHint": False},
    # -- writes that can overwrite or replace content that already exists --
    "synapse_delegate_module": {"readOnlyHint": False, "destructiveHint": True,
                                "idempotentHint": False, "openWorldHint": True},
    "synapse_write_file": {"readOnlyHint": False, "destructiveHint": True,
                           "idempotentHint": False},
    # -- genuinely open-ended. Annotated as what they are, not softened to get past a
    #    client's safety layer: synapse_run_command runs arbitrary shell, synapse_http can
    #    issue DELETE against anything on the local network, and synapse_call_mcp_tool
    #    proxies to reflex's ~103 tools including full desktop mouse/keyboard control. A
    #    client asking for confirmation before any of these run is correct behaviour, not a
    #    bug to route around. --
    "synapse_run_command": {"readOnlyHint": False, "destructiveHint": True,
                            "idempotentHint": False, "openWorldHint": True},
    # Same risk profile as synapse_run_command (arbitrary shell) -- it just returns
    # immediately with a job_id instead of blocking the HTTP request for the command's
    # full duration, so a slow command can never get killed by a tunnel/proxy's own
    # gateway timeout partway through (that read as an opaque 502 with no way to tell
    # whether the daemon or the command was actually the problem).
    "synapse_run_command_async": {"readOnlyHint": False, "destructiveHint": True,
                                  "idempotentHint": False, "openWorldHint": True},
    "synapse_get_command_result": {"readOnlyHint": True, "idempotentHint": True},
    "synapse_http": {"readOnlyHint": False, "destructiveHint": True,
                     "idempotentHint": False, "openWorldHint": False},
    # Reaches the public internet (unlike synapse_http, which is local-only), but it cannot
    # change anything on this machine or anywhere else -- it only returns search results.
    "synapse_web_search": {"readOnlyHint": True, "idempotentHint": False, "openWorldHint": True},
    "synapse_call_mcp_tool": {"readOnlyHint": False, "destructiveHint": True,
                              "idempotentHint": False, "openWorldHint": True},
}


def _tool_specs(allow_writes: bool = False) -> list[dict[str, Any]]:
    """The MCP tool catalogue advertised to the client (read-only v1)."""

    empty = {"type": "object", "properties": {}, "additionalProperties": False}
    specs: list[dict[str, Any]] = [
        {
            "name": "synapse_get_context",
            "description": "Orientation digest: project / tool / squad counts plus the project list. Read this first.",
            "inputSchema": empty,
        },
        {
            "name": "synapse_list_projects",
            "description": "List the projects (apps) registered in Synapse, with status, kind, path, and port.",
            "inputSchema": empty,
        },
        {
            "name": "synapse_get_project_records",
            "description": "Get a project's ADRs (decisions), backlog, and version history (ADR-0011).",
            "inputSchema": {
                "type": "object",
                "properties": {"project_id": {"type": "string", "description": "The project id (kebab-case)."}},
                "required": ["project_id"],
                "additionalProperties": False,
            },
        },
        {
            "name": "synapse_get_project_ai_context",
            "description": (
                "Read a project's shared AI memory (.synapse-ai-context.md) -- the running "
                "notes/objectives/session log that synapse_capture_note writes to. Call this "
                "before starting work on a project so you pick up where the last AI left off."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "project_id": {"type": "string", "description": "The project id (kebab-case)."},
                    "max_chars": {"type": "integer", "description": "Default 40000."},
                },
                "required": ["project_id"],
                "additionalProperties": False,
            },
        },
        {
            "name": "synapse_list_tools",
            "description": "List installed Synapse tools (Synapses) and whether each is runnable.",
            "inputSchema": empty,
        },
        {
            "name": "synapse_list_quick_actions",
            "description": "List curated AI quick-action workflows available in Synapse.",
            "inputSchema": empty,
        },
        {
            "name": "synapse_list_skill_packs",
            "description": "List installed, portable Synapse AI skill packs and their benchmark metadata.",
            "inputSchema": empty,
        },
        {
            "name": "synapse_get_skill_pack",
            "description": "Read an installed Synapse skill pack's full instructions and resource inventory.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "skill_id": {"type": "string", "description": "Installed skill id, for example super-internet-digger."}
                },
                "required": ["skill_id"],
                "additionalProperties": False,
            },
        },
        {
            "name": "synapse_list_agent_squads",
            "description": "List Agent Squads (multi-AI teams) and their high-level state.",
            "inputSchema": empty,
        },
        {
            "name": "synapse_list_sessions",
            "description": (
                "List AI sessions connected to Synapse -- each with its operator-facing number (#001...), "
                "runtime, status, and green/yellow/red connection grade (ADR-0028)."
            ),
            "inputSchema": empty,
        },
        {
            "name": "synapse_list_collaboration_rooms",
            "description": (
                "List durable AI collaboration rooms. Rooms are project-scoped shared channels layered "
                "on the existing Synapse session/presence system; they do not spawn workers."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "project_id": {"type": "string", "description": "Optional project id filter."},
                    "include_archived": {"type": "boolean", "description": "Default false."},
                },
                "additionalProperties": False,
            },
        },
        {
            "name": "synapse_sync_collaboration_room",
            "description": (
                "Catch up on one collaboration room: pinned goal/summary, current members/presence, "
                "and recent or cursor-new explicit messages. Call this when joining/resuming and "
                "periodically while collaborating; Synapse WebSocket clients receive the same changes live."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "room_id": {"type": "string"},
                    "after_message_id": {"type": "integer", "minimum": 0, "description": "Return only messages newer than this cursor; default 0 returns the recent tail."},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 200, "description": "Default 50."},
                },
                "required": ["room_id"],
                "additionalProperties": False,
            },
        },
        {
            "name": "synapse_recent_activity",
            "description": (
                "Recent AI-activity feed: what the AIs driving Synapse just did (sessions connecting, "
                "squads created, work handed off, ideas filed to the review inbox)."
            ),
            "inputSchema": empty,
        },
        {
            "name": "synapse_quality_summary",
            "description": (
                "Quality OS digest: open UI-quality gates (which are blocking), the most recently "
                "failing UI contracts, and the latest browser-proof evidence. Call this before "
                "claiming a UI change is done -- a gate opened by a real failure stays open until "
                "a passing contract run closes it."
            ),
            "inputSchema": empty,
        },
        {
            "name": "synapse_list_playbooks",
            "description": (
                "List AI-facing playbooks -- step-by-step procedures for driving something outside "
                "this codebase (e.g. configuring a third-party web UI), each with a healthy / "
                "needs_attention / broken status. Call this before attempting a task you suspect "
                "already has a known procedure."
            ),
            "inputSchema": empty,
        },
        {
            "name": "synapse_get_playbook",
            "description": "Read one playbook's full steps, status, and status note.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "playbook_id": {"type": "string", "description": "Playbook id, e.g. chatgpt-connector-setup."}
                },
                "required": ["playbook_id"],
                "additionalProperties": False,
            },
        },
    ]
    # The caller is responsible for combining "does the server allow writes right now"
    # with "does this URL allow them" before calling this - `_tool_specs` itself has no
    # storage to check the server-wide setting against, on purpose: the previous version
    # read a hardcoded path here and silently disagreed with the actual configured data
    # directory whenever the daemon was not running out of the repo checkout.
    if allow_writes:

        specs.extend(
            [
                {
                    "name": "synapse_thread_bootstrap",
                    "description": (
                        "Register/resume this AI conversation in Synapse's durable thread tracker. "
                        "Call this at the start of project work. On a new thread, the first call may "
                        "return candidate work groups; inspect them and call again with work_group_id "
                        "for the same request or create_group_name for a genuinely new request."
                    ),
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "project_id": {"type": "string"},
                            "external_thread_key": {"type": "string", "description": "Stable conversation identity. Prefer the chatgpt.com conversation URL/id when known; otherwise use a stable per-thread key."},
                            "runtime_id": {"type": "string", "description": "Default chatgpt."},
                            "source": {"type": "string", "enum": ["connector", "browser_observer", "managed_browser", "cli", "other"]},
                            "conversation_url": {"type": "string"},
                            "title": {"type": "string"},
                            "description": {"type": "string"},
                            "current_task": {"type": "string"},
                            "session_id": {"type": "string"},
                            "work_group_id": {"type": "string", "description": "Join an existing request/group after inspecting candidates."},
                            "create_group_name": {"type": "string", "description": "Create a new request/group when this work is not the same as an existing candidate."},
                            "create_group_description": {"type": "string"},
                        },
                        "required": ["project_id", "external_thread_key"],
                        "additionalProperties": False,
                    },
                },
                {
                    "name": "synapse_thread_begin_turn",
                    "description": (
                        "Mark a tracked conversation as actively working and open one timed turn. "
                        "Call immediately when starting substantive work for the user's prompt."
                    ),
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "thread_id": {"type": "string"},
                            "prompt_label": {"type": "string"},
                            "current_task": {"type": "string"},
                        },
                        "required": ["thread_id"],
                        "additionalProperties": False,
                    },
                },
                {
                    "name": "synapse_thread_heartbeat",
                    "description": (
                        "Refresh a tracked thread's live lease/status while work is still underway. "
                        "Managed browser workers do this automatically; connector-only sessions should "
                        "call it during long work so the operator can distinguish active from stale."
                    ),
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "thread_id": {"type": "string"},
                            "status": {"type": "string", "enum": ["active", "idle", "error", "gone", "archived"]},
                            "current_task": {"type": "string"},
                            "conversation_url": {"type": "string"},
                            "title": {"type": "string"},
                            "error": {"type": "string"},
                        },
                        "required": ["thread_id"],
                        "additionalProperties": False,
                    },
                },
                {
                    "name": "synapse_thread_finish_turn",
                    "description": (
                        "Finalize one timed response/work turn before returning the final answer. "
                        "Adds the duration exactly once to this thread's cumulative worked time. "
                        "Use duration_source=ui_display when a local browser observer captured ChatGPT's "
                        "own 'Worked for …' value; otherwise omit duration_seconds for server wall-clock timing."
                    ),
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "thread_id": {"type": "string"},
                            "turn_id": {"type": "string"},
                            "status": {"type": "string", "enum": ["success", "error", "cancelled"]},
                            "duration_seconds": {"type": "number", "minimum": 0},
                            "duration_source": {"type": "string", "enum": ["ui_display", "wall_clock", "reported", "recovered"]},
                            "summary_md": {"type": "string"},
                            "error": {"type": "string"},
                        },
                        "required": ["thread_id", "turn_id"],
                        "additionalProperties": False,
                    },
                },
            ]
        )

        # Drive tools -- only advertised when SYNAPSE_MCP_ALLOW_WRITES is set. These let a
        # remote MCP client (e.g. the claude.ai connector over the WAN tunnel) SET UP work:
        # capture context, create a squad, and assign work items. LAUNCHING a worker (which
        # spawns a real process) stays on the REST API (POST /agent-work-items/{id}/launch),
        # reachable over the same tunnel -- see docs/DRIVE-SYNAPSE-FROM-AI.md.
        specs.extend(
            [
                {
                    "name": "synapse_set_project_chat_url",
                    "description": (
                        "Set the current canonical AI chat/thread URL for a project. This replaces any "
                        "older pointer so every AI can discover the same live thread with "
                        "synapse_get_project_records. Omit or pass an empty url to clear it."
                    ),
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "project_id": {"type": "string"},
                            "url": {
                                "type": "string",
                                "description": "Absolute http(s) chat/thread URL. Omit or empty to clear.",
                            },
                        },
                        "required": ["project_id"],
                        "additionalProperties": False,
                    },
                },
                {
                    "name": "synapse_add_project_idea",
                    "description": "Capture a quick idea / draft ADR on a project (status=idea). Promote it later in the UI.",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "project_id": {"type": "string"},
                            "title": {"type": "string", "description": "One-line idea or decision."},
                        },
                        "required": ["project_id", "title"],
                        "additionalProperties": False,
                    },
                },
                {
                    "name": "synapse_capture_note",
                    "description": "Append a note to a project's shared AI memory (destination=ai_context) or backlog (destination=backlog) so the next agent run sees it.",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "project_id": {"type": "string"},
                            "content": {"type": "string", "description": "The note text."},
                            "destination": {"type": "string", "enum": ["ai_context", "backlog"], "description": "Default ai_context."},
                            "title": {"type": "string", "description": "Backlog title (defaults to the first line)."},
                        },
                        "required": ["project_id", "content"],
                        "additionalProperties": False,
                    },
                },
                {
                    "name": "synapse_create_squad",
                    "description": "Create an Agent Squad (a team of AI workers) on a project. Returns the squad id. Add work items next, then launch via REST.",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "project_id": {"type": "string"},
                            "name": {"type": "string", "description": "Squad name, e.g. 'Backend hardening'."},
                            "goal_md": {"type": "string", "description": "Optional goal/brief (markdown)."},
                            "lead_role_id": {"type": "string", "description": "Lead role id (default 'planner'). See synapse_list_agent_squads / GET /agent-role-templates."},
                        },
                        "required": ["project_id", "name"],
                        "additionalProperties": False,
                    },
                },
                {
                    "name": "synapse_add_work_item",
                    "description": "Add a work item (a unit of work assigned to a role) to a squad. Returns the work-item id; launch it via REST POST /agent-work-items/{id}/launch.",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "squad_id": {"type": "string"},
                            "title": {"type": "string", "description": "What to do, e.g. 'Add input validation to /orders'."},
                            "instructions_md": {"type": "string", "description": "Optional detailed instructions (markdown)."},
                            "assigned_role_id": {"type": "string", "description": "Role id, e.g. 'implementer' / 'reviewer'."},
                        },
                        "required": ["squad_id", "title"],
                        "additionalProperties": False,
                    },
                },
                {
                    "name": "synapse_create_collaboration_room",
                    "description": (
                        "Create a durable project-scoped AI collaboration room. This only creates shared "
                        "coordination state; it never launches or controls an AI process."
                    ),
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "project_id": {"type": "string"},
                            "name": {"type": "string"},
                            "goal_md": {"type": "string"},
                            "summary_md": {"type": "string", "description": "Pinned catch-up summary for late joiners."},
                            "created_by_session_id": {"type": "string", "description": "Optional existing Synapse session id."},
                        },
                        "required": ["project_id", "name"],
                        "additionalProperties": False,
                    },
                },
                {
                    "name": "synapse_join_collaboration_room",
                    "description": (
                        "Join an existing room using an already-registered Synapse session. Returns the "
                        "full catch-up packet immediately: room goal/summary, current peer presence and recent messages."
                    ),
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "room_id": {"type": "string"},
                            "session_id": {"type": "string"},
                            "role_label": {"type": "string", "description": "Optional room-specific role, e.g. backend/tester/reviewer."},
                        },
                        "required": ["room_id", "session_id"],
                        "additionalProperties": False,
                    },
                },
                {
                    "name": "synapse_post_collaboration_message",
                    "description": (
                        "Post an explicit peer collaboration message to a room. Kinds support status, "
                        "question/answer, decision and handoff. Never post private hidden chain-of-thought or secrets."
                    ),
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "room_id": {"type": "string"},
                            "session_id": {"type": "string"},
                            "body_md": {"type": "string"},
                            "kind": {"type": "string", "enum": ["message", "status", "handoff", "decision", "question", "answer"], "description": "Default message."},
                        },
                        "required": ["room_id", "session_id", "body_md"],
                        "additionalProperties": False,
                    },
                },
                {
                    "name": "synapse_leave_collaboration_room",
                    "description": "Leave a collaboration room while preserving its durable message history.",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "room_id": {"type": "string"},
                            "session_id": {"type": "string"},
                        },
                        "required": ["room_id", "session_id"],
                        "additionalProperties": False,
                    },
                },
                {
                    "name": "synapse_runtime_status",
                    "description": "Which coding runtimes (claude/codex/copilot/gemini/local) can be used right now, what each has spent today, and which are cooling down after running out of credit. Call this BEFORE dispatching work.",
                    "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
                },
                {
                    "name": "synapse_list_blueprints",
                    "description": "Verified recipes that can be built end to end. Each lists what it guarantees and which checks enforce those guarantees.",
                    "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
                },
                {
                    "name": "synapse_delegate_module",
                    "description": (
                        "Have a coding runtime WRITE ONE PYTHON MODULE to a workspace on this machine and return the source it wrote. "
                        "This is the core dispatch primitive: how you get real code written without writing it yourself. Takes 20-120s. "
                        "Pick a runtime with synapse_runtime_status. State the required function signatures IN THE SPEC - withholding "
                        "them measurably triples the repair count."
                    ),
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "spec": {"type": "string", "description": "What to write. Include the exact signatures the caller needs."},
                            "path": {"type": "string", "description": "Filename to write, e.g. parser.py"},
                            "workspace": {"type": "string", "description": "Absolute directory to write into. Created if missing."},
                            "runtime": {"type": "string", "enum": ["claude", "codex", "copilot", "gemini"], "description": "Default: best rung available now."},
                            "model": {"type": "string", "description": "Optional model override, e.g. haiku"},
                            "effort": {"type": "string", "enum": ["low", "medium", "high", "xhigh", "max"], "description": "Default low: measured as good as high on contract-shaped work."},
                        },
                        "required": ["spec", "path", "workspace"],
                        "additionalProperties": False,
                    },
                },
                {
                    "name": "synapse_launch_work_item",
                    "description": "Look up a squad work item and return the exact REST call that starts a real AI worker for it on this machine.",
                    "inputSchema": {
                        "type": "object",
                        "properties": {"work_item_id": {"type": "string"}},
                        "required": ["work_item_id"],
                        "additionalProperties": False,
                    },
                },
                {
                    "name": "synapse_run_command",
                    "description": (
                        "Run a shell command on this machine and return stdout/stderr/exit code. "
                        "This is what makes a remote chat able to actually DO things here: create folders "
                        "anywhere, git clone/commit, npm install, run tests, start a project. Default shell "
                        "is PowerShell on Windows. Blocking, so keep commands under the timeout - start "
                        "long-running servers with a project launch instead. This call blocks the whole "
                        "HTTP request for as long as the command runs, which risks a tunnel/proxy's own "
                        "gateway timeout (commonly under two minutes) killing the connection with a bare "
                        "502 on anything slow, even though the command may still be running fine. For any "
                        "command that might run long (a full test suite, a build, anything you're not sure "
                        "will finish in a few seconds), use synapse_run_command_async instead and poll "
                        "synapse_get_command_result -- it never risks that failure mode."
                    ),
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "command": {"type": "string", "description": "The command line to run."},
                            "cwd": {"type": "string", "description": "Absolute working directory. Defaults to the Synapse repo."},
                            "timeout_seconds": {"type": "integer", "description": "Default 120, capped at 90 regardless -- see the description above."},
                        },
                        "required": ["command"],
                        "additionalProperties": False,
                    },
                },
                {
                    "name": "synapse_run_command_async",
                    "description": (
                        "Start a shell command in the background and return a job_id immediately, "
                        "without waiting for it to finish. Poll synapse_get_command_result(job_id) to get "
                        "the outcome. Use this instead of synapse_run_command for anything that might run "
                        "for more than a few seconds (test suites, builds, multi-step scripts) -- this call "
                        "always returns in milliseconds, so it can never be killed by a tunnel/proxy's own "
                        "gateway timeout the way a long-blocking synapse_run_command call can, which is "
                        "what causes an otherwise-healthy daemon to look like it 502'd. Same command "
                        "semantics as synapse_run_command (PowerShell on Windows) otherwise."
                    ),
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "command": {"type": "string", "description": "The command line to run."},
                            "cwd": {"type": "string", "description": "Absolute working directory. Defaults to the Synapse repo."},
                            "timeout_seconds": {"type": "integer", "description": "Max time the command itself is allowed to run for, once started. Default 120, max 1800."},
                        },
                        "required": ["command"],
                        "additionalProperties": False,
                    },
                },
                {
                    "name": "synapse_get_command_result",
                    "description": (
                        "Check the status/result of a command started with synapse_run_command_async. "
                        "Returns status:\"running\" (with how long it's been running) while still in "
                        "progress, or status:\"done\" plus the same ok/exit_code/stdout/stderr shape "
                        "synapse_run_command returns once it finishes. Poll this every few seconds rather "
                        "than once -- there's no way to block-and-wait here on purpose, since blocking is "
                        "exactly the failure mode the async split exists to avoid."
                    ),
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "job_id": {"type": "string", "description": "The job_id returned by synapse_run_command_async."},
                        },
                        "required": ["job_id"],
                        "additionalProperties": False,
                    },
                },
                {
                    "name": "synapse_read_file",
                    "description": "Read a UTF-8 text file anywhere on this machine.",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "path": {"type": "string", "description": "Absolute path."},
                            "max_chars": {"type": "integer", "description": "Default 40000."},
                        },
                        "required": ["path"],
                        "additionalProperties": False,
                    },
                },
                {
                    "name": "synapse_watch_repo",
                    "description": (
                        "Wait for a git repo's working tree to change (up to timeout_seconds, max 120), "
                        "then return what changed. For waiting on delegated work -- another AI session, "
                        "a background build -- without re-checking on a fixed schedule: hold one call "
                        "open instead of spending a full turn every time you check in. Call again if it "
                        "times out with changed=false and you still want to wait."
                    ),
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "path": {"type": "string", "description": "Absolute path inside a git working tree."},
                            "timeout_seconds": {"type": "number", "description": "Default 60, max 120."},
                        },
                        "required": ["path"],
                        "additionalProperties": False,
                    },
                },
                {
                    "name": "synapse_write_file",
                    "description": (
                        "Write a UTF-8 text file anywhere on this machine, creating parent directories. "
                        "Refuses to overwrite unless overwrite=true, so a mistaken path cannot silently "
                        "destroy work."
                    ),
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "path": {"type": "string", "description": "Absolute path."},
                            "content": {"type": "string"},
                            "overwrite": {"type": "boolean", "description": "Default false."},
                        },
                        "required": ["path", "content"],
                        "additionalProperties": False,
                    },
                },
                {
                    "name": "synapse_http",
                    "description": (
                        "Call an HTTP endpoint from this machine. This is how you reach the web scraper's "
                        "full REST API on http://localhost:12345 (scraping, security headers, broken links, "
                        "screenshots, GraphQL introspection - everything it exposes) and Synapse's own API "
                        "on http://127.0.0.1:7878/api/v1. Localhost and private addresses only."
                    ),
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "url": {"type": "string"},
                            "method": {"type": "string", "enum": ["GET", "POST", "PUT", "PATCH", "DELETE"], "description": "Default GET."},
                            "json_body": {"type": "object", "description": "Optional JSON request body."},
                            "timeout_seconds": {"type": "integer", "description": "Default 60, capped at 90 regardless -- this blocks a shared worker thread for the full duration, so a large value here can stall other tool calls."},
                        },
                        "required": ["url"],
                        "additionalProperties": False,
                    },
                },
                {
                    "name": "synapse_web_search",
                    "description": (
                        "Search the public web (DuckDuckGo, no API key needed) and get back numbered "
                        "title + URL results. This is how you look something up that isn't already on "
                        "this machine -- current docs, an error message, a library's API. Follow a "
                        "result with synapse_http (localhost/private only) or synapse_run_command "
                        "(e.g. curl) to actually fetch a page's contents."
                    ),
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string", "description": "The search query."},
                        },
                        "required": ["query"],
                        "additionalProperties": False,
                    },
                },
                {
                    "name": "synapse_list_mcp_tools",
                    "description": (
                        "List the tools of an MCP server registered in Synapse - reflex (full desktop "
                        "control: screenshots, clicks, typing, windows, processes, files), playwright "
                        "(browser), github, memory. Call this to discover exact tool names and arguments "
                        "before synapse_call_mcp_tool."
                    ),
                    "inputSchema": {
                        "type": "object",
                        "properties": {"server": {"type": "string", "description": "Server id, e.g. reflex"}},
                        "required": ["server"],
                        "additionalProperties": False,
                    },
                },
                {
                    "name": "synapse_call_mcp_tool",
                    "description": (
                        "Call a tool on a registered MCP server on this machine. This is how a remote chat "
                        "drives the desktop through reflex (take_screenshot, click_mouse, type_text, "
                        "run_command, list_windows...) or a browser through playwright. Discover names with "
                        "synapse_list_mcp_tools first."
                    ),
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "server": {"type": "string", "description": "Server id, e.g. reflex"},
                            "tool": {"type": "string", "description": "Tool name on that server."},
                            "arguments": {
                                "type": "object",
                                "description": "Arguments for that tool. Use arguments_json if the calling connector cannot pass arbitrary nested objects.",
                                "additionalProperties": True,
                            },
                            "arguments_json": {
                                "type": "string",
                                "description": "JSON object encoded as a string; compatibility fallback for connector hosts that reject free-form nested objects before dispatch.",
                            },
                            "timeout_seconds": {"type": "integer", "description": "Default 120, capped at 90 regardless -- this blocks a shared worker thread for the full duration, so a large value here can stall other tool calls."},
                        },
                        "required": ["server", "tool"],
                        "additionalProperties": False,
                    },
                },
                {
                    "name": "synapse_report_playbook_status",
                    "description": (
                        "Report the outcome of following a playbook: healthy if every step matched what "
                        "was actually on screen/in the tool, needs_attention if a step no longer matches "
                        "(include what you saw instead in note), broken if the whole approach no longer "
                        "works. This is how a playbook stays trustworthy for the next AI instead of going "
                        "silently stale."
                    ),
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "playbook_id": {"type": "string"},
                            "status": {"type": "string", "enum": ["healthy", "needs_attention", "broken"]},
                            "note": {"type": "string", "description": "What you observed, especially for needs_attention/broken."},
                        },
                        "required": ["playbook_id", "status"],
                        "additionalProperties": False,
                    },
                },
            ]
        )
    for spec in specs:
        annotations = _TOOL_ANNOTATIONS.get(spec["name"])
        if annotations is None:
            # Fail loudly rather than silently advertising an unclassified tool: an
            # unannotated write action is exactly the bug this table exists to prevent, and
            # the earlier state - no annotations on anything - is proof it happens silently
            # if nothing catches it.
            raise RuntimeError(f"{spec['name']!r} has no entry in _TOOL_ANNOTATIONS")
        spec["annotations"] = {"title": spec["name"], **annotations}
    return specs


# ── async command jobs ───────────────────────────────────────────────────────
#
# synapse_run_command blocks the HTTP request for as long as the underlying shell
# command takes (up to 900s). Every hop the request passes through on its way back to a
# remote caller -- a reverse proxy, a Cloudflare Tunnel's own edge, a load balancer --
# typically has a considerably shorter gateway timeout of its own (commonly ~100s for a
# single proxied HTTP request). A command that runs longer than THAT gets its connection
# killed by the middle hop with a bare 502, indistinguishable from the daemon itself being
# down, even though the daemon is fine and the command may go on to finish successfully.
# synapse_run_command_async / synapse_get_command_result exist so a command's actual
# duration never has to fit inside any proxy's timeout: the "start" call returns in
# milliseconds regardless of how long the command takes, and the caller polls for the
# result the same way it already does for other long-running work in this app.
_command_jobs: dict[str, dict[str, Any]] = {}
_COMMAND_JOB_MAX_AGE_SECONDS = 3600  # prune finished jobs after an hour so this never grows unbounded

# synapse_run_command's own hard ceiling -- see the comment at its call site for why this is
# far below the 900s it used to allow.
_SYNC_RUN_TIMEOUT_MAX = 90

# synapse_http and synapse_call_mcp_tool/synapse_list_mcp_tools have the same failure mode as
# synapse_run_command above: each blocks a shared asyncio.to_thread worker for however long the
# caller's timeout_seconds says, with no ceiling. Six concurrent MCP sessions each issuing one
# uncapped call is enough to exhaust that shared executor, which then silently stalls every other
# MCP tool dispatch -- including trivial ones -- with no error and no visibility (confirmed live
# 2026-08-26: exactly this symptom, root-caused after Cloudflare tunnel + daemon health both ruled
# out). Same ceiling as synapse_run_command for the same reason.
_BLOCKING_CALL_TIMEOUT_MAX = 90


logger = logging.getLogger(__name__)


class McpExecutorBusy(RuntimeError):
    """Raised when a dedicated MCP dispatch lane has no bounded queue capacity."""

    def __init__(self, lane: str) -> None:
        self.lane = lane
        super().__init__(
            f"Synapse MCP {lane} lane is busy; retry shortly instead of queueing indefinitely."
        )


@dataclass(frozen=True)
class McpDispatchTiming:
    queue_ms: float
    execution_ms: float


class McpDispatchExecutor:
    """Dedicated bounded executor for synchronous MCP request dispatch.

    MCP calls can legitimately block for tens of seconds while downstream HTTP, stdio,
    or shell work completes. They must therefore never share asyncio's process-wide
    default executor with health probes, repo polling, PTYs, or model calls. A bounded
    semaphore caps both running and queued work so saturation becomes an immediate,
    observable retryable error instead of an invisible queue behind unrelated tasks.
    """

    def __init__(
        self, *, max_workers: int, max_queue: int, name: str = "dispatch"
    ) -> None:
        if max_workers < 1 or max_queue < 0:
            raise ValueError("max_workers must be >= 1 and max_queue must be >= 0")
        self.name = name
        self.max_workers = max_workers
        self.max_queue = max_queue
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers, thread_name_prefix=f"synapse-mcp-{name}"
        )
        self._slots = threading.BoundedSemaphore(max_workers + max_queue)

    async def run(
        self, func: Any, *args: Any, label: str = "mcp"
    ) -> tuple[Any, McpDispatchTiming]:
        if not self._slots.acquire(blocking=False):
            logger.warning(
                "MCP dispatch saturated lane=%s label=%s workers=%s queue_capacity=%s",
                self.name, label, self.max_workers, self.max_queue,
            )
            raise McpExecutorBusy(self.name)

        queued_at = time.perf_counter()
        loop = asyncio.get_running_loop()

        def invoke() -> tuple[Any, Exception | None, McpDispatchTiming]:
            started = time.perf_counter()
            value: Any = None
            error: Exception | None = None
            try:
                value = func(*args)
            except Exception as exc:  # noqa: BLE001 -- preserve original tool error semantics
                error = exc
            finished = time.perf_counter()
            return (
                value,
                error,
                McpDispatchTiming(
                    queue_ms=max(0.0, (started - queued_at) * 1000.0),
                    execution_ms=max(0.0, (finished - started) * 1000.0),
                ),
            )

        try:
            value, error, timing = await loop.run_in_executor(self._executor, invoke)
        finally:
            self._slots.release()

        log = logger.debug
        if timing.queue_ms >= 1000:
            log = logger.warning
        elif timing.queue_ms >= 100:
            log = logger.info
        log(
            "MCP dispatch timing lane=%s label=%s queue_ms=%.1f execution_ms=%.1f",
            self.name, label, timing.queue_ms, timing.execution_ms,
        )
        if error is not None:
            raise error
        return value, timing

    def shutdown(self, *, wait: bool = True) -> None:
        self._executor.shutdown(wait=wait, cancel_futures=True)


# Reserve a small dedicated pool for cheap local control/read operations so
# get_context, session inspection, thread heartbeats, command-result polling, and
# recovery controls are never starved by long-running blocking work. The blocking
# lane serves shell/network/downstream-MCP calls; these are I/O-bound waits (subprocess
# and HTTP calls sitting idle on a syscall, not CPU-bound work), so sizing it well past
# the CPU count is safe -- an oversubscribed thread here costs a stack, not a core.
# Live production load (2026-08-30) showed the previous 12-worker/zero-queue blocking
# lane saturating repeatedly under real concurrent usage (many standing sessions each
# running synapse_run_command/synapse_watch_repo at once), rejecting calls outright
# with no buffer -- raised to 32 workers, and both lanes now carry a small queue so a
# brief burst waits a beat instead of failing immediately.
_MCP_CONTROL_EXECUTOR = McpDispatchExecutor(name="control", max_workers=6, max_queue=6)
_MCP_BLOCKING_EXECUTOR = McpDispatchExecutor(name="blocking", max_workers=32, max_queue=16)

_BLOCKING_MCP_TOOLS = frozenset(
    {
        "synapse_delegate_module",
        "synapse_runtime_status",
        "synapse_run_command",
        "synapse_run_command_async",
        "synapse_watch_repo",
        "synapse_http",
        "synapse_web_search",
        "synapse_list_mcp_tools",
        "synapse_call_mcp_tool",
    }
)


def _mcp_dispatch_executor(msg: Any) -> tuple[str, McpDispatchExecutor]:
    """Choose the reserved control lane or the bounded blocking-work lane."""
    if not isinstance(msg, dict) or msg.get("method") != "tools/call":
        return ("control", _MCP_CONTROL_EXECUTOR)
    params = msg.get("params") or {}
    if not isinstance(params, dict):
        return ("control", _MCP_CONTROL_EXECUTOR)
    tool_name = str(params.get("name") or "")
    if tool_name in _BLOCKING_MCP_TOOLS:
        return ("blocking", _MCP_BLOCKING_EXECUTOR)
    return ("control", _MCP_CONTROL_EXECUTOR)


def _mcp_request_label(msg: Any) -> str:
    if not isinstance(msg, dict):
        return "invalid-request"
    method = str(msg.get("method") or "unknown")
    if method != "tools/call":
        return method
    params = msg.get("params") or {}
    if not isinstance(params, dict):
        return method
    name = str(params.get("name") or "unknown")
    return f"{method}:{name}"


def _mcp_timing_headers(timings: list[McpDispatchTiming]) -> dict[str, str]:
    if not timings:
        return {}
    queue_ms = max(item.queue_ms for item in timings)
    execution_ms = max(item.execution_ms for item in timings)
    return {
        "X-Synapse-MCP-Queue-Ms": f"{queue_ms:.1f}",
        "X-Synapse-MCP-Execution-Ms": f"{execution_ms:.1f}",
        "Server-Timing": (
            f"mcp_queue;dur={queue_ms:.1f}, mcp_execution;dur={execution_ms:.1f}"
        ),
    }


def _proxy_tool_arguments(args: dict[str, Any]) -> dict[str, Any]:
    """Resolve downstream MCP arguments from an object or JSON-string fallback.

    Some connector hosts validate tool schemas before dispatch and reject arbitrary
    nested object keys even though the downstream MCP tool accepts them. A scalar
    JSON transport avoids that host-side schema limitation without weakening the
    normal object path for clients that support free-form nested arguments.
    """

    nested = args.get("arguments")
    raw = args.get("arguments_json")
    if raw not in (None, ""):
        if nested not in (None, {}):
            raise ValueError("Provide either arguments or arguments_json, not both")
        try:
            parsed = json.loads(str(raw))
        except json.JSONDecodeError as exc:
            raise ValueError(f"arguments_json must be valid JSON: {exc.msg}") from exc
        if not isinstance(parsed, dict):
            raise ValueError("arguments_json must encode a JSON object")
        return parsed
    if nested is None:
        return {}
    if not isinstance(nested, dict):
        raise ValueError("arguments must be an object")
    return nested


def _prune_old_command_jobs() -> None:
    now = utc_now()
    stale = [
        job_id
        for job_id, job in _command_jobs.items()
        if job["status"] != "running"
        and (now - job["_finished_at_dt"]).total_seconds() > _COMMAND_JOB_MAX_AGE_SECONDS
    ]
    for job_id in stale:
        _command_jobs.pop(job_id, None)


def _run_command_job_thread(job_id: str, shell_argv: list[str], cwd: str, timeout: float) -> None:
    import subprocess

    try:
        done = subprocess.run(shell_argv, capture_output=True, text=True, timeout=timeout, cwd=cwd)
        result = {
            "ok": done.returncode == 0,
            "exit_code": done.returncode,
            "stdout": (done.stdout or "")[-20000:],
            "stderr": (done.stderr or "")[-8000:],
        }
    except subprocess.TimeoutExpired:
        result = {"ok": False, "timed_out": True, "detail": f"did not finish within {timeout}s"}
    except Exception as exc:  # noqa: BLE001 -- report it through the job, not an unhandled thread crash
        result = {"ok": False, "error": str(exc)}
    job = _command_jobs.get(job_id)
    if job is None:  # pruned or the daemon restarted mid-run; nothing left to update
        return
    finished_at = utc_now()
    job["status"] = "done"
    job["finished_at"] = to_iso(finished_at)
    job["_finished_at_dt"] = finished_at
    job["result"] = result


def build_mcp_router(
    storage: Storage,
    registry: ToolRegistry,
    auth: AuthManager,
    bus: EventBus | None = None,
) -> APIRouter:
    router = APIRouter(tags=["mcp"])
    event_loop: asyncio.AbstractEventLoop | None = None

    def _emit_collaboration_event(verb: str, payload: dict[str, Any]) -> None:
        """Best-effort bridge from the connector worker thread to the daemon event loop."""
        if bus is None or event_loop is None:
            return
        asyncio.run_coroutine_threadsafe(
            bus.publish(event_name("collaboration", verb), payload),
            event_loop,
        )

    def writes_allowed() -> bool:
        return _writes_allowed(storage.data_dir)

    def _call_tool(name: str, args: dict[str, Any], *, allow_writes: bool = True) -> Any:
        def _require_writes() -> None:
            """Refuse a write on the read-only URL, whatever the server-wide setting says.

            The point of handing out a read-only link is that it stays read-only even while
            the machine has writes enabled for the operator's own link.
            """
            if not allow_writes:
                raise ValueError(
                    "This is the read-only connector URL. Use the full-access URL from "
                    "Synapse Settings to write files, run commands or dispatch work.")
            if not writes_allowed():
                raise ValueError(
                    "Writes are disabled. Set SYNAPSE_MCP_ALLOW_WRITES=1 to enable.")

        if name == "synapse_list_projects":
            return [p.model_dump(mode="json") for p in projects_module.list_projects(storage.conn)]
        if name == "synapse_list_tools":
            out = []
            for manifest in registry.list_manifests():
                out.append(
                    {
                        "id": manifest.id,
                        "name": manifest.name,
                        "category": manifest.category,
                        "description": manifest.description,
                        "runnable": manifest.runnable,
                    }
                )
            return out
        if name == "synapse_list_quick_actions":
            return [_quick_action_dict(a) for a in load_templates()]
        if name == "synapse_list_skill_packs":
            return [item.model_dump(mode="json") for item in skill_packs.list_installed(storage.data_dir)]
        if name == "synapse_get_skill_pack":
            skill_id = str(args.get("skill_id", "")).strip()
            if not skill_id:
                raise ValueError("skill_id is required")
            return skill_packs.read_instructions(storage.data_dir, skill_id)
        if name == "synapse_list_agent_squads":
            return [s.model_dump(mode="json") for s in squads.list_squads(storage.conn)]
        if name == "synapse_list_sessions":
            from . import coordination as _coordination

            return [
                {
                    "seq": s.seq,
                    "session_id": s.id,
                    "runtime_id": s.runtime_id,
                    "agent_label": s.agent_label,
                    "task": s.task,
                    "status": s.status.value,
                    "stale": s.stale,
                    "connection_level": s.connection_level,
                    "connection_code": s.connection_code,
                    "project_id": s.project_id,
                }
                for s in _coordination.list_all_sessions(storage.conn)[:25]
            ]
        if name == "synapse_list_collaboration_rooms":
            project_id = str(args.get("project_id") or "").strip() or None
            include_archived = bool(args.get("include_archived", False))
            return [
                room.model_dump(mode="json")
                for room in collaboration_rooms_module.list_rooms(
                    storage.conn,
                    project_id=project_id,
                    include_archived=include_archived,
                )
            ]
        if name == "synapse_sync_collaboration_room":
            room_id = str(args.get("room_id") or "").strip()
            if not room_id:
                raise ValueError("room_id is required")
            return collaboration_rooms_module.sync_room(
                storage.conn,
                room_id,
                after_message_id=max(0, int(args.get("after_message_id") or 0)),
                limit=max(1, min(int(args.get("limit") or 50), 200)),
            ).model_dump(mode="json")
        if name == "synapse_recent_activity":
            from . import activity as _activity

            return [
                {
                    "title": n.title,
                    "kind": n.kind,
                    "level": n.level,
                    "seq": n.seq,
                    "created_at": n.created_at.isoformat(),
                    "body_md": n.body_md,
                }
                for n in _activity.list_notifications(storage.conn, limit=20)
            ]
        if name == "synapse_quality_summary":
            return quality_os.quality_summary(storage.conn)
        if name == "synapse_list_playbooks":
            from . import playbooks as _playbooks

            return [p.model_dump(mode="json") for p in _playbooks.list_playbooks(storage.conn)]
        if name == "synapse_get_playbook":
            from . import playbooks as _playbooks

            playbook_id = str(args.get("playbook_id", "")).strip()
            if not playbook_id:
                raise ValueError("playbook_id is required")
            return _playbooks.get_playbook(storage.conn, playbook_id).model_dump(mode="json")
        if name == "synapse_get_project_records":
            project_id = str(args.get("project_id", "")).strip()
            projects_module.get(storage.conn, project_id)  # 404s via SynapseError if unknown
            return records.get_records(storage.conn, project_id).model_dump(mode="json")
        if name == "synapse_get_project_ai_context":
            project_id = str(args.get("project_id", "")).strip()
            projects_module.get(storage.conn, project_id)  # 404s via SynapseError if unknown
            from . import ai_context_memory

            meta = ai_context_memory.ai_context_metadata(storage.data_dir, project_id)
            limit = int(args.get("max_chars") or 40000)
            if not meta["exists"]:
                return {**meta, "content": "", "truncated": False}
            path = ai_context_memory.ai_context_path(storage.data_dir, project_id)
            text = path.read_text(encoding="utf-8", errors="replace")
            return {**meta, "content": text[:limit], "truncated": len(text) > limit}
        if name == "synapse_get_context":
            projects = projects_module.list_projects(storage.conn)
            squad_list = squads.list_squads(storage.conn)
            return {
                "synapse_version": __version__,
                "counts": {
                    "projects": len(projects),
                    "tools": len(registry.list_manifests()),
                    "squads": len(squad_list),
                    "skill_packs": len(skill_packs.list_installed_ids(storage.data_dir)),
                },
                "projects": [
                    {"id": p.id, "name": p.name, "kind": p.kind, "status": p.status.value, "path": p.path}
                    for p in projects
                ],
                "writes_enabled": writes_allowed(),
                "hint": "Use synapse_get_project_records for project decisions and synapse_get_skill_pack for reusable AI instructions.",
                "thread_tracking": {
                    "enabled": True,
                    "bootstrap_required_for_project_work": True,
                    "protocol": "bootstrap -> begin turn -> heartbeat while long-running -> finish turn",
                    "why": "Synapse uses this durable identity to show exact active/idle/error/stale threads and cumulative worked time.",
                },
            }
        if name == "synapse_create_collaboration_room":
            _require_writes()
            payload = collaboration_rooms_module.CollaborationRoomCreate(
                project_id=str(args.get("project_id") or ""),
                name=str(args.get("name") or ""),
                goal_md=str(args.get("goal_md") or ""),
                summary_md=str(args.get("summary_md") or ""),
                created_by_session_id=(
                    str(args.get("created_by_session_id") or "").strip() or None
                ),
            )
            with storage.transaction() as conn:
                room = collaboration_rooms_module.create_room(conn, payload)
            dumped = room.model_dump(mode="json")
            _emit_collaboration_event("room_created", {"room": dumped})
            return dumped
        if name == "synapse_join_collaboration_room":
            _require_writes()
            room_id = str(args.get("room_id") or "").strip()
            if not room_id:
                raise ValueError("room_id is required")
            payload = collaboration_rooms_module.CollaborationRoomJoin(
                session_id=str(args.get("session_id") or ""),
                role_label=str(args.get("role_label") or ""),
            )
            with storage.transaction() as conn:
                synced = collaboration_rooms_module.join_room(conn, room_id, payload)
            dumped = synced.model_dump(mode="json")
            _emit_collaboration_event(
                "room_joined",
                {
                    "room_id": room_id,
                    "project_id": synced.room.project_id,
                    "session_id": payload.session_id,
                },
            )
            return dumped
        if name == "synapse_post_collaboration_message":
            _require_writes()
            room_id = str(args.get("room_id") or "").strip()
            if not room_id:
                raise ValueError("room_id is required")
            payload = collaboration_rooms_module.CollaborationRoomPost(
                session_id=str(args.get("session_id") or ""),
                body_md=str(args.get("body_md") or ""),
                kind=collaboration_rooms_module.CollaborationMessageKind(
                    str(args.get("kind") or "message")
                ),
            )
            with storage.transaction() as conn:
                message = collaboration_rooms_module.post_message(conn, room_id, payload)
            dumped = message.model_dump(mode="json")
            _emit_collaboration_event(
                "message_posted", {"room_id": room_id, "message": dumped}
            )
            return dumped
        if name == "synapse_leave_collaboration_room":
            _require_writes()
            room_id = str(args.get("room_id") or "").strip()
            session_id = str(args.get("session_id") or "").strip()
            if not room_id or not session_id:
                raise ValueError("room_id and session_id are required")
            with storage.transaction() as conn:
                member = collaboration_rooms_module.leave_room(conn, room_id, session_id)
            dumped = member.model_dump(mode="json")
            _emit_collaboration_event(
                "room_left", {"room_id": room_id, "session_id": session_id}
            )
            return dumped

        if name == "synapse_set_project_chat_url":
            if not writes_allowed():
                raise ValueError("Writes are disabled. Set SYNAPSE_MCP_ALLOW_WRITES=1 to enable.")
            project_id = str(args.get("project_id", "")).strip()
            projects_module.get(storage.conn, project_id)
            raw_url = args.get("url")
            from .models import AuditSource
            from .project_records import ProjectCanonicalChatUrlUpdate

            payload = ProjectCanonicalChatUrlUpdate(url=raw_url, source=AuditSource.AUTO)
            with storage.transaction() as conn:
                bundle = records.set_canonical_chat_url(conn, project_id, payload.url)
            return bundle.model_dump(mode="json")

        if name == "synapse_thread_bootstrap":
            _require_writes()
            from . import thread_presence as _thread_presence
            payload = _thread_presence.ThreadBootstrap(
                project_id=str(args.get("project_id") or ""),
                external_thread_key=str(args.get("external_thread_key") or ""),
                runtime_id=str(args.get("runtime_id") or "chatgpt"),
                source=_thread_presence.ThreadSource(str(args.get("source") or "connector")),
                conversation_url=str(args.get("conversation_url") or ""),
                title=str(args.get("title") or ""),
                description=str(args.get("description") or ""),
                current_task=str(args.get("current_task") or ""),
                session_id=(str(args.get("session_id") or "").strip() or None),
                work_group_id=(str(args.get("work_group_id") or "").strip() or None),
                create_group_name=(str(args.get("create_group_name") or "").strip() or None),
                create_group_description=str(args.get("create_group_description") or ""),
            )
            with storage.transaction() as conn:
                projects_module.get(conn, payload.project_id)
                item, candidates, needs_decision = _thread_presence.bootstrap_thread(conn, payload)
            return {
                "thread": item.model_dump(mode="json") if item else None,
                "needs_group_decision": needs_decision,
                "group_candidates": [candidate.model_dump(mode="json") for candidate in candidates],
                "instruction": (
                    "Choose whether this is the same request as one candidate. Call synapse_thread_bootstrap "
                    "again with that work_group_id, or create_group_name for a new request."
                    if needs_decision else
                    "Tracking active. Call synapse_thread_begin_turn now, heartbeat during long work, "
                    "and synapse_thread_finish_turn before returning the final answer."
                ),
            }
        if name == "synapse_thread_begin_turn":
            _require_writes()
            from . import thread_presence as _thread_presence
            thread_id = str(args.get("thread_id") or "").strip()
            with storage.transaction() as conn:
                turn = _thread_presence.begin_turn(
                    conn,
                    thread_id,
                    _thread_presence.ThreadBegin(
                        prompt_label=str(args.get("prompt_label") or ""),
                        current_task=str(args.get("current_task") or ""),
                    ),
                )
            return turn.model_dump(mode="json")
        if name == "synapse_thread_heartbeat":
            _require_writes()
            from . import thread_presence as _thread_presence
            thread_id = str(args.get("thread_id") or "").strip()
            payload_args: dict[str, Any] = {}
            for key in ("current_task", "conversation_url", "title", "error"):
                if key in args:
                    payload_args[key] = args.get(key)
            if args.get("status"):
                payload_args["status"] = _thread_presence.ThreadStatus(str(args.get("status")))
            with storage.transaction() as conn:
                item = _thread_presence.heartbeat_thread(
                    conn, thread_id, _thread_presence.ThreadHeartbeat(**payload_args)
                )
            return item.model_dump(mode="json")
        if name == "synapse_thread_finish_turn":
            _require_writes()
            from . import thread_presence as _thread_presence
            thread_id = str(args.get("thread_id") or "").strip()
            with storage.transaction() as conn:
                turn, item = _thread_presence.finish_turn(
                    conn,
                    thread_id,
                    _thread_presence.ThreadFinish(
                        turn_id=str(args.get("turn_id") or ""),
                        status=_thread_presence.TurnStatus(str(args.get("status") or "success")),
                        duration_seconds=(
                            float(args["duration_seconds"]) if args.get("duration_seconds") is not None else None
                        ),
                        duration_source=_thread_presence.DurationSource(
                            str(args.get("duration_source") or "wall_clock")
                        ),
                        summary_md=str(args.get("summary_md") or ""),
                        error=str(args.get("error") or ""),
                    ),
                )
            return {
                "turn": turn.model_dump(mode="json"),
                "thread": item.model_dump(mode="json"),
            }

        if name == "synapse_add_project_idea":
            if not writes_allowed():
                raise ValueError("Writes are disabled. Set SYNAPSE_MCP_ALLOW_WRITES=1 to enable.")
            project_id = str(args.get("project_id", "")).strip()
            title = str(args.get("title", "")).strip()
            if not title:
                raise ValueError("title is required")
            projects_module.get(storage.conn, project_id)
            from .project_records import ProjectAdrCreate

            with storage.transaction() as conn:
                adr = records.create_adr(conn, project_id, ProjectAdrCreate(title=title))
            return adr.model_dump(mode="json")
        if name == "synapse_capture_note":
            if not writes_allowed():
                raise ValueError("Writes are disabled. Set SYNAPSE_MCP_ALLOW_WRITES=1 to enable.")
            from .capture import CaptureDestination, CaptureRequest, capture

            project_id = str(args.get("project_id", "")).strip()
            content = str(args.get("content", "")).strip()
            if not content:
                raise ValueError("content is required")
            dest = str(args.get("destination", "ai_context")).strip() or "ai_context"
            req = CaptureRequest(
                project_id=project_id,
                content=content,
                destination=CaptureDestination(dest),
                title=args.get("title"),
            )
            with storage.transaction() as conn:
                result = capture(conn, storage.data_dir, req)
            return result.model_dump(mode="json")
        if name == "synapse_create_squad":
            if not writes_allowed():
                raise ValueError("Writes are disabled. Set SYNAPSE_MCP_ALLOW_WRITES=1 to enable.")
            project_id = str(args.get("project_id", "")).strip()
            name_arg = str(args.get("name", "")).strip()
            if not name_arg:
                raise ValueError("name is required")
            with storage.transaction() as conn:
                projects_module.get(conn, project_id)  # 404s if the project is unknown
                squad = squads.create_squad(
                    conn,
                    squads.AgentSquadCreate(
                        project_id=project_id,
                        name=name_arg,
                        goal_md=str(args.get("goal_md", "") or ""),
                        lead_role_id=(args.get("lead_role_id") or "planner"),
                    ),
                )
            return squad.model_dump(mode="json")
        if name == "synapse_add_work_item":
            if not writes_allowed():
                raise ValueError("Writes are disabled. Set SYNAPSE_MCP_ALLOW_WRITES=1 to enable.")
            squad_id = str(args.get("squad_id", "")).strip()
            title = str(args.get("title", "")).strip()
            if not title:
                raise ValueError("title is required")
            with storage.transaction() as conn:
                work_item = squads.create_work_item(  # get_squad() inside 404s if squad unknown
                    conn,
                    squad_id,
                    squads.AgentWorkItemCreate(
                        title=title,
                        instructions_md=str(args.get("instructions_md", "") or ""),
                        assigned_role_id=args.get("assigned_role_id"),
                    ),
                )
            return work_item.model_dump(mode="json")
        if name == "synapse_runtime_status":
            _require_writes()
            from . import ai_executions as _ai_executions
            from . import coder_runtimes as _cr

            # preflight()'s cooldown is in-memory and deliberately forgets exhaustion on every
            # daemon restart (coder_runtimes.py's own docstring: "a restart should re-probe
            # rather than inherit a stale belief that a tier is dead"). That is the right
            # default for the squad/blueprint dispatcher this was built for -- one wasted call
            # is cheap. It is the wrong default for an external caller like this MCP tool: right
            # after a restart it reports usable_now=True for a runtime the durable,
            # evidence-backed ai_runtime_capacity ledger still remembers as quota_exhausted from
            # a real provider error. Merge that durable evidence in so a caller sees both.
            durable = {c.runtime_id: c for c in _ai_executions.list_capacity(storage.conn)}
            _STALE_STATES = {
                _ai_executions.RuntimeCapacityState.QUOTA_EXHAUSTED,
                _ai_executions.RuntimeCapacityState.AUTH_REQUIRED,
                _ai_executions.RuntimeCapacityState.DISABLED,
                _ai_executions.RuntimeCapacityState.OFFLINE,
            }
            out = []
            for status in _cr.preflight():
                capacity = durable.get(status.runtime)
                if status.usable_now and capacity is not None and capacity.state in _STALE_STATES:
                    status.usable_now = False
                    evidence = (f" as of {capacity.evidence_at.isoformat()}"
                                if capacity.evidence_at else "")
                    status.note = (
                        f"durable evidence ledger records {capacity.state.value}{evidence} "
                        f"({capacity.reason_code or 'no reason given'}) -- overriding the "
                        f"post-restart cooldown, which had no memory of this yet"
                    )
                out.append(status.model_dump(mode="json"))
            return out

        if name == "synapse_list_blueprints":
            _require_writes()
            from . import blueprints as _bp

            return _bp.summarize_for_ai()

        if name == "synapse_delegate_module":
            _require_writes()
            from . import coder_runtimes as _cr

            spec = str(args.get("spec", "")).strip()
            path = str(args.get("path", "")).strip()
            workspace = Path(str(args.get("workspace", "")).strip()).expanduser()
            if not spec or not path:
                raise ValueError("spec and path are required")
            if not workspace.is_absolute():
                raise ValueError("workspace must be an absolute path")
            workspace.mkdir(parents=True, exist_ok=True)

            wanted = str(args.get("runtime", "") or "").strip()
            runtime = (_cr.CoderRuntime(wanted) if wanted
                       else _cr.CoderRuntime(_cr.pick().chosen))
            if runtime is _cr.CoderRuntime.LOCAL:
                raise ValueError(
                    "The local tier is not reachable through this tool: it takes minutes to "
                    "an hour and would time the call out. Use the blueprint build API."
                )
            profile = _cr.RuntimeProfile(
                model=str(args.get("model", "") or ""),
                effort=str(args.get("effort", "") or "low"),
            )
            result = _cr.write_module(runtime, spec, workspace=workspace, path=path,
                                      profile=profile)
            _cr.record_call(result)
            return {
                "ok": result.ok,
                "runtime": runtime.value,
                "path": str(workspace / path),
                "seconds": result.seconds,
                "usage": result.usage,
                "error": result.error,
                "exhausted": result.exhausted,
                "source": result.source,
            }

        if name == "synapse_launch_work_item":
            _require_writes()
            work_item_id = str(args.get("work_item_id", "")).strip()
            if not work_item_id:
                raise ValueError("work_item_id is required")
            with storage.transaction() as conn:
                item = squads.get_work_item(conn, work_item_id)
            return {
                "work_item_id": work_item_id,
                "title": getattr(item, "title", None),
                "start_with": (
                    "POST /api/v1/agent-work-items/" + work_item_id + "/launch"
                ),
                "why_not_here": (
                    "Spawning goes over REST so the worker outlives this MCP call and keeps "
                    "running after the client disconnects."
                ),
            }

        if name == "synapse_run_command":
            _require_writes()
            import subprocess
            import sys as _sys

            command = str(args.get("command", "")).strip()
            if not command:
                raise ValueError("command is required")
            # Capped well under a typical proxy/tunnel gateway timeout (commonly ~100s for a
            # single proxied request), not at the 900s this tool used to allow. A command that
            # runs longer than the old cap risked the connection getting killed by a middle hop
            # with a bare 502 before this function's own graceful TimeoutExpired handling below
            # ever got a chance to run -- capping here means a slow command now reliably surfaces
            # as the clean, fast "timed_out" response a few lines down instead. Anything that
            # genuinely needs to run longer should use synapse_run_command_async instead, which
            # has no such ceiling because it never holds the HTTP request open in the first place.
            timeout = min(int(args.get("timeout_seconds") or 120), _SYNC_RUN_TIMEOUT_MAX)
            cwd = str(args.get("cwd") or repo_root())
            shell_argv = (["powershell", "-NoProfile", "-Command", command]
                          if _sys.platform == "win32" else ["bash", "-lc", command])
            try:
                done = subprocess.run(shell_argv, capture_output=True, text=True,
                                      timeout=timeout, cwd=cwd)
            except subprocess.TimeoutExpired:
                return {"ok": False, "timed_out": True,
                        "detail": f"did not finish within {timeout}s"}
            return {
                "ok": done.returncode == 0,
                "exit_code": done.returncode,
                "stdout": (done.stdout or "")[-20000:],
                "stderr": (done.stderr or "")[-8000:],
                "cwd": cwd,
            }

        if name == "synapse_run_command_async":
            _require_writes()
            import sys as _sys

            command = str(args.get("command", "")).strip()
            if not command:
                raise ValueError("command is required")
            timeout = min(int(args.get("timeout_seconds") or 120), 1800)
            cwd = str(args.get("cwd") or repo_root())
            shell_argv = (["powershell", "-NoProfile", "-Command", command]
                          if _sys.platform == "win32" else ["bash", "-lc", command])
            job_id = uuid.uuid4().hex[:12]
            _command_jobs[job_id] = {
                "status": "running",
                "command": command,
                "cwd": cwd,
                "started_at": to_iso(utc_now()),
            }
            _prune_old_command_jobs()
            threading.Thread(
                target=_run_command_job_thread,
                args=(job_id, shell_argv, cwd, timeout),
                daemon=True,
            ).start()
            return {
                "job_id": job_id,
                "status": "running",
                "note": "Poll synapse_get_command_result with this job_id. This call itself always "
                        "returns immediately regardless of how long the command takes.",
            }

        if name == "synapse_get_command_result":
            _require_writes()
            job_id = str(args.get("job_id", "")).strip()
            if not job_id:
                raise ValueError("job_id is required")
            job = _command_jobs.get(job_id)
            if job is None:
                raise ValueError(
                    f"Unknown job_id: {job_id!r} (it may have expired -- results are kept for "
                    f"{_COMMAND_JOB_MAX_AGE_SECONDS}s after completion -- or the daemon restarted "
                    "since the command was started)."
                )
            if job["status"] == "running":
                started = from_iso(job["started_at"])
                return {
                    "job_id": job_id,
                    "status": "running",
                    "running_for_seconds": round((utc_now() - started).total_seconds(), 1),
                }
            return {"job_id": job_id, "status": "done", "cwd": job["cwd"], **job["result"]}

        if name == "synapse_read_file":
            _require_writes()
            target = Path(str(args.get("path", "")).strip()).expanduser()
            if not target.is_file():
                raise ValueError(f"No such file: {target}")
            limit = int(args.get("max_chars") or 40000)
            text = target.read_text(encoding="utf-8", errors="replace")
            return {"path": str(target), "chars": len(text),
                    "truncated": len(text) > limit, "content": text[:limit]}

        if name == "synapse_watch_repo":
            _require_writes()
            from . import repo_watch as _repo_watch

            target = Path(str(args.get("path", "")).strip()).expanduser()
            if not target.is_dir():
                raise ValueError(f"No such directory: {target}")
            timeout = float(args.get("timeout_seconds") or _repo_watch.DEFAULT_TIMEOUT_SECONDS)
            result = _repo_watch.wait_for_repo_change_sync(target, timeout_seconds=timeout)
            return result.model_dump(mode="json")

        if name == "synapse_write_file":
            _require_writes()
            target = Path(str(args.get("path", "")).strip()).expanduser()
            if not target.is_absolute():
                raise ValueError("path must be absolute")
            if target.exists() and not bool(args.get("overwrite")):
                # An accidental path should cost a retry, not somebody's work.
                raise ValueError(f"{target} exists. Pass overwrite=true to replace it.")
            target.parent.mkdir(parents=True, exist_ok=True)
            content = str(args.get("content", ""))
            target.write_text(content, encoding="utf-8")
            return {"ok": True, "path": str(target), "bytes": len(content.encode())}

        if name == "synapse_http":
            _require_writes()
            import json as _json
            import urllib.error
            import urllib.request
            from urllib.parse import urlparse

            url = str(args.get("url", "")).strip()
            host = (urlparse(url).hostname or "").lower()
            # Local and private only. This tool runs inside the operator's network, so an
            # arbitrary outbound URL would turn it into an open proxy sitting behind their
            # firewall. Public fetching is the web scraper's job, and it is reachable here.
            allowed = (host in {"localhost", "127.0.0.1", "::1"}
                       or host.startswith(("10.", "192.168.", "169.254."))
                       or (host.startswith("172.") and 16 <= int(host.split(".")[1] or 0) <= 31))
            if not allowed:
                raise ValueError(
                    f"{host!r} is not local. This tool reaches services on this machine "
                    "(the web scraper on :12345, Synapse on :7878). To fetch a public site, "
                    "use the web scraper's own API through this tool."
                )
            method = str(args.get("method") or "GET").upper()
            body = args.get("json_body")
            data = _json.dumps(body).encode() if body is not None else None
            request = urllib.request.Request(
                url, data=data, method=method,
                headers={"Content-Type": "application/json"} if data else {})
            try:
                with urllib.request.urlopen(
                        request,
                        timeout=min(int(args.get("timeout_seconds") or 60), _BLOCKING_CALL_TIMEOUT_MAX)) as resp:
                    return {"ok": True, "status": resp.status,
                            "body": resp.read().decode("utf-8", "replace")[:40000]}
            except urllib.error.HTTPError as exc:
                return {"ok": False, "status": exc.code,
                        "body": exc.read().decode("utf-8", "replace")[:8000]}
            except Exception as exc:  # noqa: BLE001
                return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}

        if name == "synapse_web_search":
            _require_writes()
            query = str(args.get("query", "")).strip()
            if not query:
                raise ValueError("query is required")
            result = local_agent.web_search(query)
            if result.startswith("ERROR:"):
                raise ValueError(result)
            return {"query": query, "results": result}

        if name in ("synapse_list_mcp_tools", "synapse_call_mcp_tool"):
            _require_writes()
            server_id = str(args.get("server", "")).strip()
            if not server_id:
                raise ValueError("server is required")
            with storage.transaction() as conn:
                servers = {row.id: row for row in mcp_servers.list_servers(conn)}
            server = servers.get(server_id)
            if server is None:
                raise ValueError(
                    f"No MCP server {server_id!r}. Registered: {sorted(servers)}")
            if server.transport not in ("stdio", "http"):
                raise ValueError(
                    f"{server_id} uses {server.transport} transport, which is not proxied.")

            timeout = min(int(args.get("timeout_seconds") or 120), _BLOCKING_CALL_TIMEOUT_MAX)
            speak = _http_mcp if server.transport == "http" else _stdio_mcp
            if name == "synapse_list_mcp_tools":
                reply = speak(server, "tools/list", {}, timeout)
                return [
                    {"name": t.get("name"), "description": (t.get("description") or "")[:300],
                     "inputSchema": t.get("inputSchema")}
                    for t in (reply or {}).get("tools", [])
                ]

            tool = str(args.get("tool", "")).strip()
            if not tool:
                raise ValueError("tool is required")
            return speak(server, "tools/call",
                         {"name": tool, "arguments": _proxy_tool_arguments(args)},
                         timeout)

        if name == "synapse_report_playbook_status":
            _require_writes()
            from . import playbooks as _playbooks

            playbook_id = str(args.get("playbook_id", "")).strip()
            status_arg = str(args.get("status", "")).strip()
            if not playbook_id or not status_arg:
                raise ValueError("playbook_id and status are required")
            with storage.transaction() as conn:
                result = _playbooks.record_verification(
                    conn,
                    playbook_id,
                    status=_playbooks.PlaybookStatus(status_arg),
                    note=args.get("note"),
                    verified_by="mcp_connector",
                )
            return result.model_dump(mode="json")

        raise ValueError(f"Unknown tool: {name}")

    def _handle(msg: Any, allow_writes: bool = True) -> dict[str, Any] | None:
        """Handle one JSON-RPC message. Returns a response dict, or None for
        notifications (no id)."""

        if not isinstance(msg, dict):
            return _error(None, -32600, "Invalid Request")
        msg_id = msg.get("id")
        method = msg.get("method")
        params = msg.get("params") or {}
        is_notification = "id" not in msg

        if method == "initialize":
            requested = (params or {}).get("protocolVersion")
            return _ok(
                msg_id,
                {
                    "protocolVersion": requested or DEFAULT_PROTOCOL_VERSION,
                    "capabilities": {"tools": {"listChanged": False}},
                    "serverInfo": {"name": "synapse", "version": __version__},
                    "instructions": (
                        "Synapse connector. Call synapse_get_context first. "
                        + (
                            "Drive tools (create squad / add work item / capture note) are ENABLED; "
                            "launch a work item via REST POST /agent-work-items/{id}/launch."
                            if writes_allowed()
                            else "Read-only (set SYNAPSE_MCP_ALLOW_WRITES=1 to enable drive tools)."
                        )
                    ),
                },
            )
        if method == "ping":
            return _ok(msg_id, {})
        if isinstance(method, str) and method.startswith("notifications/"):
            return None  # client notifications need no response
        if method == "tools/list":
            return _ok(msg_id, {"tools": _tool_specs(writes_allowed() and allow_writes)})
        if method == "tools/call":
            name = (params or {}).get("name", "")
            args = (params or {}).get("arguments") or {}
            try:
                data = _call_tool(name, args, allow_writes=allow_writes)
            except SynapseError as exc:  # not_found / invalid -> tool error, not transport error
                return _tool_error(msg_id, exc.envelope.message)
            except Exception as exc:  # noqa: BLE001 -- surface as an MCP tool error
                return _tool_error(msg_id, str(exc))
            return _ok(
                msg_id,
                {
                    "content": [{"type": "text", "text": json.dumps(data, indent=2, default=str)}],
                    "isError": False,
                },
            )
        if is_notification:
            return None
        return _error(msg_id, -32601, f"Method not found: {method}")

    @router.post("/mcp/{token}", response_model=None)
    async def mcp_post(token: str, request: Request) -> Response:
        nonlocal event_loop
        event_loop = asyncio.get_running_loop()
        if not auth.local_token or token != auth.local_token:
            return JSONResponse(
                _error(None, -32001, "Unauthorized"), status_code=401
            )
        try:
            payload = await request.json()
        except Exception:  # noqa: BLE001
            return JSONResponse(_error(None, -32700, "Parse error"), status_code=400)

        # `?mode=read` pins this URL to the read-only surface regardless of the
        # server-wide setting. That is what makes a read-only link worth handing out: it
        # stays read-only while the operator's own link can still drive the machine.
        allow_writes = request.query_params.get("mode", "").strip().lower() != "read"

        # _handle is synchronous and may block on downstream MCP/HTTP/shell work. Keep
        # it off the event loop *and* off asyncio's process-wide default executor. Long
        # operations use their own bounded lane; a separate reserved control lane keeps
        # cheap local reads/recovery calls responsive even while shell/browser/network
        # work is saturated. Both expose queue-vs-execution timing on every response.
        async def dispatch(message: Any) -> tuple[Any, McpDispatchTiming, str]:
            lane, executor = _mcp_dispatch_executor(message)
            response, timing = await executor.run(
                _handle, message, allow_writes, label=_mcp_request_label(message)
            )
            return response, timing, lane

        try:
            if isinstance(payload, list):
                handled = await asyncio.gather(*(dispatch(m) for m in payload))
                timings = [timing for _, timing, _ in handled]
                lanes = [lane for _, _, lane in handled]
                responses = [
                    response for response, _, _ in handled if response is not None
                ]
                headers = _mcp_timing_headers(timings)
                headers["X-Synapse-MCP-Lane"] = (
                    lanes[0] if lanes and len(set(lanes)) == 1 else "mixed"
                )
                if not responses:
                    return Response(status_code=202, headers=headers)
                return JSONResponse(responses, headers=headers)

            response, timing, lane = await dispatch(payload)
        except McpExecutorBusy as exc:
            return JSONResponse(
                _error(None, -32002, str(exc)),
                status_code=503,
                headers={
                    "Retry-After": "1",
                    "X-Synapse-MCP-Executor": "saturated",
                    "X-Synapse-MCP-Lane": exc.lane,
                },
            )

        headers = _mcp_timing_headers([timing])
        headers["X-Synapse-MCP-Lane"] = lane
        if response is None:
            return Response(status_code=202, headers=headers)
        return JSONResponse(response, headers=headers)

    @router.get("/mcp/{token}", response_model=None)
    async def mcp_get(token: str) -> Response:
        # No server-initiated SSE stream in v1; tools are request/response.
        return Response(status_code=405)

    return router


def build_mcp_info_router(storage: Storage, registry: ToolRegistry,
                          auth: AuthManager) -> APIRouter:
    """Authed (/api/v1) helper so the desktop UI can show + copy the ready-made
    claude.ai connector URL without the user hand-assembling token + tunnel."""

    router = APIRouter(tags=["mcp"])

    def writes_allowed() -> bool:
        return _writes_allowed(storage.data_dir)

    @router.get("/mcp/connector", response_model=None)
    async def connector_info(request: Request) -> dict[str, Any]:
        token = auth.local_token or ""
        port = int(getattr(request.app.state, "bound_port", 7878) or 7878)
        mcp_path = f"/mcp/{token}"

        # A user-configured stable hostname (e.g. a named cloudflared tunnel the operator
        # runs themselves, pointed at this port from outside Synapse entirely) wins over
        # Cloudtap's own ephemeral quick-tunnel. Cloudtap's URL rotates on every daemon
        # restart, which broke the one thing this endpoint exists for: a connector link
        # that ChatGPT/Claude can be configured with ONCE. Synapse has no way to detect
        # such a tunnel automatically (it isn't Cloudtap's own child process), so it has
        # to be told -- see PATCH /api/v1/system/network's `public_hostname` field.
        public_hostname = boot_config.load(storage.data_dir).public_hostname
        tunnel_url: str | None = None
        tunnel_source = "none"
        if public_hostname:
            tunnel_url = f"https://{public_hostname}"
            tunnel_source = "public_hostname"
        else:
            try:
                registry.get_manifest("cloudtap")  # raises if cloudtap absent
                state = registry.get_state("cloudtap")
                item = next(
                    (i for i in state.items if i.result.get("local_port") == port),
                    None,
                )
                if item is not None:
                    tunnel_url = item.result.get("public_url")
                    tunnel_source = "cloudtap" if tunnel_url else "none"
            except Exception:  # noqa: BLE001 -- cloudtap optional / not installed
                tunnel_url = None
        connector_url = f"{tunnel_url.rstrip('/')}{mcp_path}" if tunnel_url else None
        # Two links on purpose. The read-only one is safe to paste anywhere; the full one
        # can write files, run commands and dispatch coding work on this machine.
        read_only_url = f"{connector_url}?mode=read" if connector_url else None
        return {
            "read_only": not writes_allowed(),
            "writes_enabled": writes_allowed(),
            "bound_port": port,
            "mcp_path": mcp_path,
            "local_url": f"http://127.0.0.1:{port}{mcp_path}",
            "tunnel_url": tunnel_url,
            "tunnel_open": bool(tunnel_url),
            "tunnel_source": tunnel_source,
            "public_hostname": public_hostname,
            "connector_url": connector_url,
            "read_only_url": read_only_url,
        }

    return router


def _ok(msg_id: Any, result: Any) -> dict[str, Any]:
    return {"jsonrpc": JSONRPC, "id": msg_id, "result": result}


def _error(msg_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": JSONRPC, "id": msg_id, "error": {"code": code, "message": message}}


def _tool_error(msg_id: Any, message: str) -> dict[str, Any]:
    # Per MCP, tool execution failures are a successful JSON-RPC response with
    # isError=true so the model can read + react to them.
    return _ok(
        msg_id,
        {"content": [{"type": "text", "text": message}], "isError": True},
    )


def _quick_action_dict(action: Any) -> dict[str, Any]:
    to_dict = getattr(action, "to_dict", None)
    if callable(to_dict):
        d = to_dict()
        return {k: d.get(k) for k in ("id", "name", "description", "category", "tags") if k in d}
    return {
        "id": getattr(action, "id", None),
        "name": getattr(action, "name", None),
        "description": getattr(action, "description", None),
        "category": getattr(action, "category", None),
        "tags": list(getattr(action, "tags", []) or []),
    }


# Public aliases. The routes layer needs to speak MCP to an installed server too, and
# reaching for a underscored name across modules is how a private helper quietly becomes an
# API without anyone deciding that it should.
http_mcp = _http_mcp
stdio_mcp = _stdio_mcp
