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
            "name": "synapse_list_agent_squads",
            "description": "List Agent Squads (multi-AI teams) and their high-level state.",
            "inputSchema": empty,
        },
    ]
    if _writes_allowed():
        specs.append(
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
            }
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
        if name == "synapse_list_agent_squads":
            return [s.model_dump(mode="json") for s in squads.list_squads(storage.conn)]
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
                },
                "projects": [
                    {"id": p.id, "name": p.name, "kind": p.kind, "status": p.status.value, "path": p.path}
                    for p in projects
                ],
                "writes_enabled": _writes_allowed(),
                "hint": "Use synapse_get_project_records for a project's ADRs/backlog/versions.",
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
                    "instructions": "Synapse read-only connector. Call synapse_get_context first.",
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
