"""AI-facing context endpoint (v0.1.29 · ADR-0002 Phase B).

  GET /api/v1/ai/context
      Returns a compact, AI-readable digest of the running Synapse instance:
      projects, installed tools, active PTY sessions, recent audit entries.
      Designed for a Claude / Codex session running inside a Sessions tab to
      grab so it can introspect "what's here" without sifting through the
      individual REST endpoints.

The shape stays small and deliberately flat: the AI is the consumer, not a
TS-codegen target. Anything noisy (full transcripts, full audit log) is
linked by id so the AI can fetch on demand.
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter

from . import projects as projects_module
from .storage import Storage
from .pty_sessions import PtySessionManager
from .tools_registry import ToolRegistry


def build_ai_router(
    storage: Storage,
    registry: ToolRegistry,
    manager: PtySessionManager,
) -> APIRouter:
    router = APIRouter(prefix="/ai", tags=["ai"])

    @router.get("/context", response_model=None)
    async def context() -> dict[str, Any]:
        projects = [
            {
                "id": p.id,
                "name": p.name,
                "path": p.path,
                "kind": p.kind.value,
                "status": p.status.value,
                "launch_cmd": p.launch_cmd,
                "expected_port": p.expected_port,
                "group": p.group,
                "tags": p.tags,
                "pinned": p.pinned,
                "description": p.description,
                "current_health": p.current_health.value,
            }
            for p in projects_module.list_projects(storage.conn)
        ]

        tools = [
            {
                "id": m.id,
                "name": m.name,
                "version": m.version,
                "runnable": m.runnable,
                "description": m.description,
                "actions": [
                    {"id": a.id, "label": a.label, "scope": a.scope.value}
                    for a in m.actions
                ],
            }
            for m in registry.list_manifests()
        ]

        sessions = [
            {
                "session_id": s.session_id,
                "argv": s.argv,
                "cwd": s.cwd,
                "started_at": s.summary().started_at,
                "exit_code": s.exit_code,
            }
            for s in manager.list()
        ]

        # Tail of audit so the AI can spot "what just happened" without
        # pulling the whole table.
        cursor = storage.conn.execute(
            "SELECT id, timestamp_utc, entity_type, entity_id, action, source, "
            "result, error_code, details_json "
            "FROM audit_log ORDER BY id DESC LIMIT 25"
        )
        audit_tail = []
        for row in cursor.fetchall():
            details = (
                json.loads(row["details_json"]) if row["details_json"] else None
            )
            audit_tail.append(
                {
                    "id": row["id"],
                    "at": row["timestamp_utc"],
                    "entity_type": row["entity_type"],
                    "entity_id": row["entity_id"],
                    "action": row["action"],
                    "source": row["source"],
                    "result": row["result"],
                    "error_code": row["error_code"],
                    "details": details,
                }
            )

        return {
            "schema": "synapse.ai.context/v1",
            "projects": projects,
            "tools": tools,
            "sessions": sessions,
            "audit_tail": audit_tail,
            "endpoints_for_ai": [
                {
                    "purpose": "list registered projects",
                    "method": "GET",
                    "path": "/api/v1/projects",
                },
                {
                    "purpose": "launch / stop a project",
                    "method": "POST",
                    "path": "/api/v1/projects/{id}/launch | /stop",
                },
                {
                    "purpose": "open a coder pre-cd'd into a project",
                    "method": "POST",
                    "path": "/api/v1/projects/{id}/workbench",
                },
                {
                    "purpose": "list installed tools (declarative + handler tiers)",
                    "method": "GET",
                    "path": "/api/v1/tools",
                },
                {
                    "purpose": "run an action on a tool",
                    "method": "POST",
                    "path": "/api/v1/tools/{id}/actions/{action}",
                },
                {
                    "purpose": "list / spawn PTY sessions",
                    "method": "GET | POST",
                    "path": "/api/v1/pty",
                },
                {
                    "purpose": "install a tool from the marketplace by id",
                    "method": "POST",
                    "path": "/api/v1/marketplace/install/{id}",
                },
                {
                    "purpose": "the full audit log (paginated)",
                    "method": "GET",
                    "path": "/api/v1/audit",
                },
            ],
        }

    return router
