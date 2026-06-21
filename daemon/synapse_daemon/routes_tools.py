"""REST routes for the tool plugin system (Milestone F · v0.1.9).

  GET  /api/v1/tools
       -> every loaded tool: its manifest + live state.

  GET  /api/v1/tools/{tool_id}
       -> one tool's manifest + live state.

  POST /api/v1/tools/{tool_id}/actions/{action_id}
       -> run a manifest action with the user's field values; returns the
          tool's new state.

All under ``/api/v1`` — mounted by :func:`synapse_daemon.app.build_app`.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from .audit import AuditRecord, audit
from .models import AuditSource
from .profile import ProfileManager
from .storage import Storage
from .tools_registry import ToolRegistry


class ActionRequest(BaseModel):
    """Body for an action POST.

    ``item_id`` targets one live instance for item-scoped actions (e.g. close
    a specific Cloudtap tunnel); it is ``None`` for tool-scoped actions.
    """

    fields: dict[str, Any] = Field(default_factory=dict)
    item_id: str | None = None
    source: AuditSource = AuditSource.DESKTOP


def build_tools_router(
    storage: Storage,
    registry: ToolRegistry,
    profile_manager: ProfileManager | None = None,
) -> APIRouter:
    router = APIRouter(prefix="/tools", tags=["tools"])

    def _entry(tool_id: str) -> dict:
        return {
            "manifest": registry.get_manifest(tool_id).model_dump(mode="json"),
            "state": registry.get_state(tool_id).model_dump(mode="json"),
        }

    @router.get("", response_model=None)
    async def list_all() -> dict:
        return {"tools": [_entry(m.id) for m in registry.list_manifests()]}

    @router.get("/{tool_id}", response_model=None)
    async def get_one(tool_id: str) -> dict:
        return _entry(tool_id)

    @router.post("/{tool_id}/actions/{action_id}", response_model=None)
    async def run_action(
        tool_id: str,
        action_id: str,
        payload: ActionRequest | None = None,
    ) -> dict:
        body = payload or ActionRequest()
        state = await registry.run_action(tool_id, action_id, body.fields, body.item_id)

        with storage.transaction() as conn:
            errored = state.last_error is not None
            audit(
                conn,
                AuditRecord(
                    entity_type="tool",
                    entity_id=tool_id,
                    action=f"action.{action_id}",
                    source=body.source,
                    result="error" if errored else "success",
                    error_code=state.last_error.code if errored else None,
                    details={
                        "status": state.status.value,
                        "item_id": body.item_id,
                        "items": len(state.items),
                    },
                ),
            )
        if profile_manager is not None and state.last_error is None:
            profile_manager.record_catalog_use(kind="tool", item_id=tool_id)

        return {
            "manifest": registry.get_manifest(tool_id).model_dump(mode="json"),
            "state": state.model_dump(mode="json"),
        }

    return router
