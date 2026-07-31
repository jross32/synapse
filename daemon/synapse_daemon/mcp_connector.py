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


def _writes_allowed() -> bool:
    return os.getenv("SYNAPSE_MCP_ALLOW_WRITES", "").strip() in {"1", "true", "yes"}


def _tool_specs() -> list[dict[str, Any]]:
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
    ]
    if _writes_allowed():
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
            ]
        )
    return specs


def build_mcp_router(
    storage: Storage,
    registry: ToolRegistry,
    auth: AuthManager,
) -> APIRouter:
    router = APIRouter(tags=["mcp"])

    def _call_tool(name: str, args: dict[str, Any]) -> Any:
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
        if name == "synapse_get_project_records":
            project_id = str(args.get("project_id", "")).strip()
            projects_module.get(storage.conn, project_id)  # 404s via SynapseError if unknown
            return records.get_records(storage.conn, project_id).model_dump(mode="json")
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
                "writes_enabled": _writes_allowed(),
                "hint": "Use synapse_get_project_records for project decisions and synapse_get_skill_pack for reusable AI instructions.",
            }
        if name == "synapse_add_project_idea":
            if not _writes_allowed():
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
            if not _writes_allowed():
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
            if not _writes_allowed():
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
            if not _writes_allowed():
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
        raise ValueError(f"Unknown tool: {name}")

    def _handle(msg: Any) -> dict[str, Any] | None:
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
                            if _writes_allowed()
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
            return _ok(msg_id, {"tools": _tool_specs()})
        if method == "tools/call":
            name = (params or {}).get("name", "")
            args = (params or {}).get("arguments") or {}
            try:
                data = _call_tool(name, args)
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

        if isinstance(payload, list):
            responses = [r for r in (_handle(m) for m in payload) if r is not None]
            if not responses:
                return Response(status_code=202)
            return JSONResponse(responses)

        response = _handle(payload)
        if response is None:
            return Response(status_code=202)
        return JSONResponse(response)

    @router.get("/mcp/{token}", response_model=None)
    async def mcp_get(token: str) -> Response:
        # No server-initiated SSE stream in v1; tools are request/response.
        return Response(status_code=405)

    return router


def build_mcp_info_router(registry: ToolRegistry, auth: AuthManager) -> APIRouter:
    """Authed (/api/v1) helper so the desktop UI can show + copy the ready-made
    claude.ai connector URL without the user hand-assembling token + tunnel."""

    router = APIRouter(tags=["mcp"])

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
        return {
            "read_only": not _writes_allowed(),
            "writes_enabled": _writes_allowed(),
            "bound_port": port,
            "mcp_path": mcp_path,
            "local_url": f"http://127.0.0.1:{port}{mcp_path}",
            "tunnel_url": tunnel_url,
            "tunnel_open": bool(tunnel_url),
            "connector_url": connector_url,
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
