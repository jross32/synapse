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

import json
import os
from pathlib import Path

from . import local_agent
from . import mcp_servers
from .runtime_paths import repo_root
from .runtime_resolution import resolve_command
from typing import Any

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse

from . import __version__
from . import agent_squads as squads
from . import project_records as records
from . import projects as projects_module
from .auth import AuthManager
from .errors import SynapseError
from .quick_actions import load_templates
from . import skill_packs
from .storage import Storage
from .tools_registry import ToolRegistry

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
    "synapse_recent_activity": {"readOnlyHint": True, "idempotentHint": True},
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
            "name": "synapse_recent_activity",
            "description": (
                "Recent AI-activity feed: what the AIs driving Synapse just did (sessions connecting, "
                "squads created, work handed off, ideas filed to the review inbox)."
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
        # Drive tools -- only advertised when SYNAPSE_MCP_ALLOW_WRITES is set. These let a
        # remote MCP client (e.g. the claude.ai connector over the WAN tunnel) SET UP work:
        # capture context, create a squad, and assign work items. LAUNCHING a worker (which
        # spawns a real process) stays on the REST API (POST /agent-work-items/{id}/launch),
        # reachable over the same tunnel -- see docs/DRIVE-SYNAPSE-FROM-AI.md.
        specs.extend(
            [
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
                        "long-running servers with a project launch instead."
                    ),
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "command": {"type": "string", "description": "The command line to run."},
                            "cwd": {"type": "string", "description": "Absolute working directory. Defaults to the Synapse repo."},
                            "timeout_seconds": {"type": "integer", "description": "Default 120, max 900."},
                        },
                        "required": ["command"],
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
                            "timeout_seconds": {"type": "integer", "description": "Default 60."},
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
                            "arguments": {"type": "object", "description": "Arguments for that tool."},
                            "timeout_seconds": {"type": "integer", "description": "Default 120."},
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


def build_mcp_router(
    storage: Storage,
    registry: ToolRegistry,
    auth: AuthManager,
) -> APIRouter:
    router = APIRouter(tags=["mcp"])

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
            timeout = min(int(args.get("timeout_seconds") or 120), 900)
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

        if name == "synapse_read_file":
            _require_writes()
            target = Path(str(args.get("path", "")).strip()).expanduser()
            if not target.is_file():
                raise ValueError(f"No such file: {target}")
            limit = int(args.get("max_chars") or 40000)
            text = target.read_text(encoding="utf-8", errors="replace")
            return {"path": str(target), "chars": len(text),
                    "truncated": len(text) > limit, "content": text[:limit]}

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
                        request, timeout=int(args.get("timeout_seconds") or 60)) as resp:
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

            timeout = int(args.get("timeout_seconds") or 120)
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
                         {"name": tool, "arguments": args.get("arguments") or {}},
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

        if isinstance(payload, list):
            responses = [r for r in (_handle(m, allow_writes) for m in payload)
                         if r is not None]
            if not responses:
                return Response(status_code=202)
            return JSONResponse(responses)

        response = _handle(payload, allow_writes)
        if response is None:
            return Response(status_code=202)
        return JSONResponse(response)

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
        tunnel_url: str | None = None
        try:
            registry.get_manifest("cloudtap")  # raises if cloudtap absent
            state = registry.get_state("cloudtap")
            item = next(
                (i for i in state.items if i.result.get("local_port") == port),
                None,
            )
            if item is not None:
                tunnel_url = item.result.get("public_url")
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
