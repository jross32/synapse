"""REST routes for the local-LLM assistant (ADR-0014)."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter

from . import agent_squads as squads
from . import assistant as asst
from . import ollama_client
from . import projects as projects_module
from .assistant import (
    AssistantChatCreate,
    AssistantRole,
    AssistantSendMessage,
    AssistantSettingsUpdate,
)
from .audit import AuditRecord, audit
from .errors import invalid
from .models import AuditSource
from .storage import Storage
from .tools_registry import ToolRegistry


def _context_message(storage: Storage, registry: ToolRegistry) -> str:
    """A compact system prompt describing the live Synapse state so the
    assistant can answer 'what's the boss doing?' / questions about the app."""
    projects = projects_module.list_projects(storage.conn)
    squad_list = squads.list_squads(storage.conn)
    lines = [
        "You are Synapse's built-in assistant -- a helpful guide to this local "
        "Synapse install (a developer command center for projects, tools, and AI "
        "coder sessions). Answer questions about the app and help the user. Be "
        "concise and friendly.",
        "",
        "Live Synapse state:",
        f"- Projects ({len(projects)}): "
        + (", ".join(f"{p.name} [{p.status.value}]" for p in projects[:25]) or "none"),
    ]
    if squad_list:
        lines.append(
            f"- Agent squads ({len(squad_list)}): "
            + ", ".join(f"{s.name} [{s.status.value}]" for s in squad_list[:25])
        )
    else:
        lines.append("- Agent squads: none active")
    try:
        tool_names = [m.name for m in registry.list_manifests()]
        if tool_names:
            lines.append("- Installed tools: " + ", ".join(tool_names[:25]))
    except Exception:  # noqa: BLE001
        pass
    return "\n".join(lines)


def build_assistant_router(storage: Storage, registry: ToolRegistry) -> APIRouter:
    router = APIRouter(tags=["assistant"])

    @router.get("/assistant/status", response_model=None)
    async def status() -> dict[str, Any]:
        settings = asst.get_settings(storage.conn)
        installed = ollama_client.is_installed()
        up = await ollama_client.server_up() if installed else False
        models = await ollama_client.list_models() if up else []
        return asst.AssistantStatus(
            installed=installed,
            server_up=up,
            enabled=settings.enabled,
            default_model=settings.default_model,
            models=[asst.OllamaModelInfo(**m) for m in models],
        ).model_dump(mode="json")

    @router.get("/assistant/settings", response_model=None)
    async def get_settings() -> dict[str, Any]:
        return asst.get_settings(storage.conn).model_dump(mode="json")

    @router.patch("/assistant/settings", response_model=None)
    async def patch_settings(payload: AssistantSettingsUpdate) -> dict[str, Any]:
        with storage.transaction() as conn:
            settings = asst.update_settings(conn, payload)
            audit(
                conn,
                AuditRecord(
                    entity_type="assistant",
                    entity_id="settings",
                    action="update",
                    source=AuditSource.DESKTOP,
                    result="success",
                    details={"enabled": settings.enabled, "default_model": settings.default_model},
                ),
            )
        return settings.model_dump(mode="json")

    # ── Engine lifecycle ─────────────────────────────────────────────────────

    @router.post("/assistant/engine/start", response_model=None)
    async def engine_start() -> dict[str, Any]:
        if not ollama_client.is_installed():
            raise invalid("assistant", "Ollama is not installed. Install it, then start the engine.")
        if not await ollama_client.server_up():
            ollama_client.start_server()
            for _ in range(20):
                if await ollama_client.server_up():
                    break
                await asyncio.sleep(0.5)
        up = await ollama_client.server_up()
        with storage.transaction() as conn:
            audit(
                conn,
                AuditRecord(
                    entity_type="assistant",
                    entity_id="engine",
                    action="start",
                    source=AuditSource.DESKTOP,
                    result="success" if up else "error",
                ),
            )
        return {"server_up": up}

    @router.post("/assistant/engine/stop", response_model=None)
    async def engine_stop() -> dict[str, Any]:
        stopped = ollama_client.stop_server()
        with storage.transaction() as conn:
            audit(
                conn,
                AuditRecord(
                    entity_type="assistant",
                    entity_id="engine",
                    action="stop",
                    source=AuditSource.DESKTOP,
                    result="success",
                    details={"stopped": stopped},
                ),
            )
        return {"stopped": stopped}

    # ── Chats ────────────────────────────────────────────────────────────────

    @router.get("/assistant/chats", response_model=None)
    async def list_chats() -> dict[str, Any]:
        return {"chats": [c.model_dump(mode="json") for c in asst.list_chats(storage.conn)]}

    @router.post("/assistant/chats", response_model=None, status_code=201)
    async def create_chat(payload: AssistantChatCreate) -> dict[str, Any]:
        with storage.transaction() as conn:
            chat = asst.create_chat(conn, payload)
        return chat.model_dump(mode="json")

    @router.get("/assistant/chats/{chat_id}", response_model=None)
    async def get_chat(chat_id: str) -> dict[str, Any]:
        return asst.chat_detail(storage.conn, chat_id).model_dump(mode="json")

    @router.patch("/assistant/chats/{chat_id}", response_model=None)
    async def rename_chat(chat_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        title = str(payload.get("title", "")).strip()
        with storage.transaction() as conn:
            chat = asst.rename_chat(conn, chat_id, title)
        return chat.model_dump(mode="json")

    @router.delete("/assistant/chats/{chat_id}", status_code=204, response_model=None)
    async def delete_chat(chat_id: str) -> None:
        with storage.transaction() as conn:
            asst.delete_chat(conn, chat_id)

    @router.post("/assistant/chats/{chat_id}/messages", response_model=None)
    async def send_message(chat_id: str, payload: AssistantSendMessage) -> dict[str, Any]:
        chat = asst.get_chat(storage.conn, chat_id)
        settings = asst.get_settings(storage.conn)

        # Resolve the model: explicit -> this chat's -> default -> first installed.
        model = payload.model or chat.model or settings.default_model
        if not model:
            installed = await ollama_client.list_models()
            model = installed[0]["name"] if installed else None
        if not model:
            raise invalid(
                "assistant",
                "No model selected and none installed. Pull a model in the marketplace first.",
            )

        content = payload.content.strip()
        if not content:
            raise invalid("assistant", "Message content is required.")

        # Persist the user's turn first so it survives an inference failure.
        with storage.transaction() as conn:
            asst.add_message(conn, chat_id, AssistantRole.USER, content)
            asst.set_chat_model(conn, chat_id, model)

        # Build the prompt: optional live-state system message + full history.
        wire: list[dict[str, str]] = []
        if payload.include_context:
            wire.append({"role": "system", "content": _context_message(storage, registry)})
        for message in asst.list_messages(storage.conn, chat_id):
            wire.append({"role": message.role.value, "content": message.content})

        try:
            reply = await ollama_client.chat(model, wire)
        except Exception as exc:  # noqa: BLE001 -- surface as a readable error
            raise invalid("assistant", f"The local model could not respond: {exc}") from exc

        with storage.transaction() as conn:
            assistant_msg = asst.add_message(conn, chat_id, AssistantRole.ASSISTANT, reply)
            audit(
                conn,
                AuditRecord(
                    entity_type="assistant_chat",
                    entity_id=chat_id,
                    action="message",
                    source=AuditSource.DESKTOP,
                    result="success",
                    details={"model": model},
                ),
            )
        return assistant_msg.model_dump(mode="json")

    return router
