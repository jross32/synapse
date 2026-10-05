"""Built-in Synapse Video Studio readiness tool."""

from __future__ import annotations

from typing import Any

from .. import video_assets
from ..models import EntityStatus, ErrorRef, ToolState
from ..storage import Storage
from ..ws import EventBus
from . import ToolHandler


class VideoStudioTool(ToolHandler):
    tool_id = "synapse-video-studio"

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
                    code="video-studio.unavailable",
                    message="Synapse Video Studio needs daemon storage.",
                ),
            )

        status = video_assets.video_generation_status(self._storage)
        configured = bool(status.get("configured"))
        provider = str(status.get("provider") or "provider")
        model = str(status.get("model") or "provider default")
        assembler = status.get("assembler") or {}
        message = (
            (
                f"Ready for connected AIs. Provider: {provider} / {model}. "
                "Long-form storyboard rendering, native audio, continuity groups, and local assembly are enabled."
            )
            if configured
            else (
                "Video Studio is installed. Configure a Google/Gemini video credential and the local ffmpeg "
                "assembler to enable provider-backed rendering. Storyboard/provenance infrastructure is available."
            )
        )
        supports = status.get("supports") or {}
        return ToolState(
            tool_id=self.tool_id,
            status=EntityStatus.LAUNCHED if configured else EntityStatus.IDLE,
            result={
                "installed": True,
                "configured": configured,
                "provider": provider,
                "model": status.get("model"),
                "credential_source": status.get("credential_source"),
                "assembler_ready": bool(assembler.get("configured")),
                "max_video_seconds": supports.get("max_video_seconds"),
                "shot_seconds": supports.get("shot_seconds"),
                "continuity_group_seconds": supports.get("continuity_group_seconds"),
                "native_audio": bool(supports.get("native_audio")),
                "dialogue": bool(supports.get("dialogue")),
                "reference_images": bool(supports.get("reference_images")),
                "detached_render_jobs": bool(supports.get("detached_render_jobs")),
                "project_scoped_output": bool(supports.get("project_scoped_output")),
                "asset_manifest": bool(supports.get("asset_manifest")),
            },
            message=message,
        )

    def state(self) -> ToolState:
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
                    code="video-studio.unknown_action",
                    message=f"Synapse Video Studio has no action '{action_id}'.",
                ),
            )
            return self._state
        self._state = self._build_state()
        return self._state
