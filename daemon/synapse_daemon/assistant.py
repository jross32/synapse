"""Models + SQLite CRUD for the local-LLM assistant (ADR-0014).

The assistant is OFF by default (single ``assistant_settings`` row). Chats and
messages are persisted so the user can open / close / resume conversations.
The engine is Ollama (see :mod:`ollama_client`); this module owns the
conversation state, not the inference.
"""

from __future__ import annotations

import secrets
import sqlite3
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field

from .errors import not_found
from .time_utils import from_iso, to_iso, utc_now


class AssistantRole(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class OllamaModelInfo(BaseModel):
    name: str
    size: int | None = None
    modified_at: str | None = None
    family: str | None = None
    parameter_size: str | None = None


class AssistantSettings(BaseModel):
    enabled: bool = False
    default_model: str | None = None
    updated_at: datetime = Field(default_factory=utc_now)


class AssistantSettingsUpdate(BaseModel):
    enabled: bool | None = None
    default_model: str | None = None


class AssistantStatus(BaseModel):
    installed: bool
    server_up: bool
    enabled: bool
    default_model: str | None = None
    models: list[OllamaModelInfo] = Field(default_factory=list)


class AssistantMessage(BaseModel):
    id: str
    chat_id: str
    role: AssistantRole
    content: str
    created_at: datetime = Field(default_factory=utc_now)


class AssistantChat(BaseModel):
    id: str
    title: str = "New chat"
    model: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class AssistantChatDetail(BaseModel):
    chat: AssistantChat
    messages: list[AssistantMessage] = Field(default_factory=list)


class AssistantChatCreate(BaseModel):
    title: str = "New chat"
    model: str | None = None


class AssistantSendMessage(BaseModel):
    content: str
    # When true the daemon prepends a system message describing the current
    # Synapse state (projects, squads) so "what's the boss doing?" gets a real
    # answer.
    include_context: bool = True
    model: str | None = None


def _new_id() -> str:
    return secrets.token_hex(6)


# ── Settings ─────────────────────────────────────────────────────────────────


def get_settings(conn: sqlite3.Connection) -> AssistantSettings:
    row = conn.execute("SELECT * FROM assistant_settings WHERE id = 1").fetchone()
    if row is None:
        now = to_iso(utc_now())
        conn.execute(
            "INSERT INTO assistant_settings (id, enabled, default_model, updated_at) "
            "VALUES (1, 0, NULL, ?)",
            (now,),
        )
        return AssistantSettings(enabled=False, default_model=None)
    return AssistantSettings(
        enabled=bool(row["enabled"]),
        default_model=row["default_model"],
        updated_at=from_iso(row["updated_at"]),
    )


def update_settings(conn: sqlite3.Connection, payload: AssistantSettingsUpdate) -> AssistantSettings:
    current = get_settings(conn)
    enabled = current.enabled if payload.enabled is None else payload.enabled
    default_model = (
        current.default_model if payload.default_model is None else (payload.default_model or None)
    )
    conn.execute(
        "UPDATE assistant_settings SET enabled = ?, default_model = ?, updated_at = ? WHERE id = 1",
        (1 if enabled else 0, default_model, to_iso(utc_now())),
    )
    return get_settings(conn)


# ── Chats + messages ─────────────────────────────────────────────────────────


def _row_to_chat(row: sqlite3.Row) -> AssistantChat:
    return AssistantChat(
        id=row["id"],
        title=row["title"],
        model=row["model"],
        created_at=from_iso(row["created_at"]),
        updated_at=from_iso(row["updated_at"]),
    )


def _row_to_message(row: sqlite3.Row) -> AssistantMessage:
    return AssistantMessage(
        id=row["id"],
        chat_id=row["chat_id"],
        role=AssistantRole(row["role"]),
        content=row["content"] or "",
        created_at=from_iso(row["created_at"]),
    )


def list_chats(conn: sqlite3.Connection) -> list[AssistantChat]:
    rows = conn.execute("SELECT * FROM assistant_chats ORDER BY updated_at DESC").fetchall()
    return [_row_to_chat(row) for row in rows]


def get_chat(conn: sqlite3.Connection, chat_id: str) -> AssistantChat:
    row = conn.execute("SELECT * FROM assistant_chats WHERE id = ?", (chat_id,)).fetchone()
    if row is None:
        raise not_found("assistant_chat", chat_id)
    return _row_to_chat(row)


def list_messages(conn: sqlite3.Connection, chat_id: str) -> list[AssistantMessage]:
    rows = conn.execute(
        "SELECT * FROM assistant_messages WHERE chat_id = ? ORDER BY created_at", (chat_id,)
    ).fetchall()
    return [_row_to_message(row) for row in rows]


def chat_detail(conn: sqlite3.Connection, chat_id: str) -> AssistantChatDetail:
    chat = get_chat(conn, chat_id)
    return AssistantChatDetail(chat=chat, messages=list_messages(conn, chat_id))


def create_chat(conn: sqlite3.Connection, payload: AssistantChatCreate) -> AssistantChat:
    now = to_iso(utc_now())
    chat_id = _new_id()
    conn.execute(
        "INSERT INTO assistant_chats (id, title, model, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (chat_id, payload.title.strip() or "New chat", payload.model, now, now),
    )
    return get_chat(conn, chat_id)


def rename_chat(conn: sqlite3.Connection, chat_id: str, title: str) -> AssistantChat:
    get_chat(conn, chat_id)
    conn.execute(
        "UPDATE assistant_chats SET title = ?, updated_at = ? WHERE id = ?",
        (title.strip() or "New chat", to_iso(utc_now()), chat_id),
    )
    return get_chat(conn, chat_id)


def delete_chat(conn: sqlite3.Connection, chat_id: str) -> None:
    get_chat(conn, chat_id)
    conn.execute("DELETE FROM assistant_chats WHERE id = ?", (chat_id,))


def add_message(
    conn: sqlite3.Connection, chat_id: str, role: AssistantRole, content: str
) -> AssistantMessage:
    now = to_iso(utc_now())
    message_id = _new_id()
    conn.execute(
        "INSERT INTO assistant_messages (id, chat_id, role, content, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (message_id, chat_id, role.value, content, now),
    )
    conn.execute(
        "UPDATE assistant_chats SET updated_at = ? WHERE id = ?", (now, chat_id)
    )
    row = conn.execute("SELECT * FROM assistant_messages WHERE id = ?", (message_id,)).fetchone()
    return _row_to_message(row)


def set_chat_model(conn: sqlite3.Connection, chat_id: str, model: str) -> None:
    conn.execute(
        "UPDATE assistant_chats SET model = ?, updated_at = ? WHERE id = ?",
        (model, to_iso(utc_now()), chat_id),
    )
