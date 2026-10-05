"""Built-in Synapse Image Studio tool.

The installable manifest controls visibility/lifecycle. The image-generation/editing engine
itself remains compiled into Synapse so installed copies do not execute downloaded Python.
"""

from __future__ import annotations

from typing import Any

from .. import image_assets
from ..models import EntityStatus, ErrorRef, ToolState
from ..storage import Storage
from ..ws import EventBus
from . import ToolHandler


class ImageStudioTool(ToolHandler):
    tool_id = "synapse-image-studio"

    def __init__(self, bus: EventBus, storage: Storage | None = None) -> None:
        self._bus = bus
        self._storage = storage
        self._state = self._build_state()

    def _build_state(self) -> ToolState:
        if self._storage is None:
            return ToolState(
                tool_id=self.tool_id,
                status=EntityStatus.ERROR,
                last_error=ErrorRef(
                    code="image-studio.unavailable",
                    message="Synapse Image Studio needs daemon storage.",
                ),
            )

        status = image_assets.image_generation_status(self._storage)
        configured = bool(status.get("configured"))
        model = str(status.get("model") or "provider default")
        source = status.get("credential_source")
        message = (
            (
                f"Ready for connected AIs. Provider: {status.get('provider', 'openai')} / {model}. "
                "Native image import and chunked transfer are also available."
            )
            if configured
            else (
                "Native image import/chunked transfer are ready now. Add an OpenAI image "
                "credential in Synapse to also enable provider-backed generation/editing."
            )
        )
        return ToolState(
            tool_id=self.tool_id,
            status=EntityStatus.LAUNCHED if configured else EntityStatus.IDLE,
            result={
                "installed": True,
                "configured": configured,
                "provider": status.get("provider"),
                "model": status.get("model"),
                "credential_source": source,
                "generation": bool((status.get("supports") or {}).get("generation")),
                "editing": bool((status.get("supports") or {}).get("editing")),
                "importing": bool((status.get("supports") or {}).get("importing")),
                "chunked_upload": bool((status.get("supports") or {}).get("chunked_upload")),
                "native_bridge_ready": bool(
                    (status.get("supports") or {}).get("importing")
                    and (status.get("supports") or {}).get("chunked_upload")
                ),
                "project_scoped_output": bool(
                    (status.get("supports") or {}).get("project_scoped_output")
                ),
                "asset_manifest": bool(
                    (status.get("supports") or {}).get("asset_manifest")
                ),
            },
            message=message,
        )

    def state(self) -> ToolState:
        # Credential/configuration can change outside this tool, so state is intentionally live.
        self._state = self._build_state()
        return self._state

    async def run_action(
        self, action_id: str, fields: dict[str, Any], item_id: str | None = None
    ) -> ToolState:
        if action_id != "check":
            self._state = ToolState(
                tool_id=self.tool_id,
                status=EntityStatus.ERROR,
                fields=fields or {},
                last_error=ErrorRef(
                    code="image-studio.unknown_action",
                    message=f"Synapse Image Studio has no action '{action_id}'.",
                ),
            )
            return self._state

        self._state = self._build_state()
        return self._state
