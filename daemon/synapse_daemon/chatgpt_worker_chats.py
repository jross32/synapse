"""Durable registry for real ChatGPT UI worker conversations.

A coordination session describes one live AI run. A worker chat describes the
longer-lived chatgpt.com conversation that may be resumed for the same work item
or deliberately reused for a related one. Keeping the two identities separate
lets Synapse retire live presence cleanly without losing the worker URL.

Nothing in this module deletes ChatGPT conversations. "archive" only records
operator intent in Synapse; browser automation may separately archive the chat
in ChatGPT when the lifecycle policy decides it is appropriate.
"""

from __future__ import annotations

import secrets
import sqlite3
from datetime import datetime
from enum import Enum

from pydantic import BaseModel

from .errors import conflict, not_found
from .time_utils import from_iso, to_iso, utc_now


WORKER_PROJECT_NAME = "Synapse2GPT Workers"


class ChatGPTWorkerStatus(str, Enum):
    STARTING = "starting"
    ACTIVE = "active"
    IDLE = "idle"
    FAILED = "failed"
    ARCHIVED = "archived"


class ChatGPTWorkerChat(BaseModel):
    id: str
    project_id: str
    owner_session_id: str | None = None
    last_session_id: str | None = None
    role_id: str | None = None
    chatgpt_project_name: str = WORKER_PROJECT_NAME
    conversation_url: str = ""
    title: str
    status: ChatGPTWorkerStatus = ChatGPTWorkerStatus.STARTING
    archived_reason: str = ""
    created_at: datetime
    last_used_at: datetime
    archived_at: datetime | None = None
    work_item_ids: list[str] = []


def _new_id() -> str:
    return secrets.token_hex(6)


def _work_item_ids(conn: sqlite3.Connection, worker_chat_id: str) -> list[str]:
    rows = conn.execute(
        "SELECT work_item_id FROM chatgpt_worker_chat_work_items "
        "WHERE worker_chat_id = ? ORDER BY linked_at ASC",
        (worker_chat_id,),
    ).fetchall()
    return [str(row["work_item_id"]) for row in rows]


def _row_to_chat(conn: sqlite3.Connection, row: sqlite3.Row) -> ChatGPTWorkerChat:
    return ChatGPTWorkerChat(
        id=row["id"],
        project_id=row["project_id"],
        owner_session_id=row["owner_session_id"],
        last_session_id=row["last_session_id"],
        role_id=row["role_id"],
        chatgpt_project_name=row["chatgpt_project_name"] or WORKER_PROJECT_NAME,
        conversation_url=row["conversation_url"] or "",
        title=row["title"],
        status=ChatGPTWorkerStatus(row["status"]),
        archived_reason=row["archived_reason"] or "",
        created_at=from_iso(row["created_at"]),
        last_used_at=from_iso(row["last_used_at"]),
        archived_at=from_iso(row["archived_at"]) if row["archived_at"] else None,
        work_item_ids=_work_item_ids(conn, row["id"]),
    )


def get_chat(conn: sqlite3.Connection, worker_chat_id: str) -> ChatGPTWorkerChat:
    row = conn.execute(
        "SELECT * FROM chatgpt_worker_chats WHERE id = ?", (worker_chat_id,)
    ).fetchone()
    if row is None:
        raise not_found("chatgpt_worker_chat", worker_chat_id)
    return _row_to_chat(conn, row)


def list_chats(
    conn: sqlite3.Connection,
    *,
    project_id: str | None = None,
    include_archived: bool = False,
) -> list[ChatGPTWorkerChat]:
    clauses: list[str] = []
    values: list[object] = []
    if project_id:
        clauses.append("project_id = ?")
        values.append(project_id.strip())
    if not include_archived:
        clauses.append("status != 'archived'")
    where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = conn.execute(
        f"SELECT * FROM chatgpt_worker_chats{where} "
        "ORDER BY last_used_at DESC, created_at DESC",
        values,
    ).fetchall()
    return [_row_to_chat(conn, row) for row in rows]


def find_for_work_item(
    conn: sqlite3.Connection, work_item_id: str
) -> ChatGPTWorkerChat | None:
    row = conn.execute(
        "SELECT c.* FROM chatgpt_worker_chats c "
        "JOIN chatgpt_worker_chat_work_items l ON l.worker_chat_id = c.id "
        "WHERE l.work_item_id = ? AND l.is_current = 1",
        (work_item_id,),
    ).fetchone()
    return _row_to_chat(conn, row) if row is not None else None


def create_chat(
    conn: sqlite3.Connection,
    *,
    project_id: str,
    title: str,
    owner_session_id: str | None,
    role_id: str | None,
    work_item_id: str,
) -> ChatGPTWorkerChat:
    worker_chat_id = _new_id()
    now = to_iso(utc_now())
    conn.execute(
        "INSERT INTO chatgpt_worker_chats "
        "(id, project_id, owner_session_id, role_id, chatgpt_project_name, "
        " conversation_url, title, status, archived_reason, created_at, "
        " last_used_at, archived_at, metadata_json) "
        "VALUES (?, ?, ?, ?, ?, '', ?, 'starting', '', ?, ?, NULL, '{}')",
        (
            worker_chat_id,
            project_id,
            owner_session_id,
            role_id,
            WORKER_PROJECT_NAME,
            title.strip(),
            now,
            now,
        ),
    )
    link_work_item(conn, worker_chat_id, work_item_id, relation="primary")
    return get_chat(conn, worker_chat_id)


def link_work_item(
    conn: sqlite3.Connection,
    worker_chat_id: str,
    work_item_id: str,
    *,
    relation: str = "related",
) -> ChatGPTWorkerChat:
    chat = get_chat(conn, worker_chat_id)
    existing = find_for_work_item(conn, work_item_id)
    if (
        existing is not None
        and existing.id != worker_chat_id
        and existing.status != ChatGPTWorkerStatus.ARCHIVED
    ):
        raise conflict(
            "chatgpt_worker_chat",
            "This work item is already linked to a different active ChatGPT worker chat.",
            work_item_id=work_item_id,
            existing_worker_chat_id=existing.id,
        )
    now = to_iso(utc_now())
    # Preserve historical associations, but keep exactly one resume target.
    conn.execute(
        "UPDATE chatgpt_worker_chat_work_items SET is_current = 0 "
        "WHERE work_item_id = ? AND is_current = 1 AND worker_chat_id != ?",
        (work_item_id, worker_chat_id),
    )
    conn.execute(
        "INSERT INTO chatgpt_worker_chat_work_items "
        "(worker_chat_id, work_item_id, relation, is_current, linked_at) "
        "VALUES (?, ?, ?, 1, ?) "
        "ON CONFLICT(worker_chat_id, work_item_id) DO UPDATE SET "
        "relation = excluded.relation, is_current = 1, linked_at = excluded.linked_at",
        (worker_chat_id, work_item_id, relation, now),
    )
    conn.execute(
        "UPDATE chatgpt_worker_chats SET last_used_at = ? WHERE id = ?",
        (to_iso(utc_now()), chat.id),
    )
    return get_chat(conn, chat.id)


def resolve_for_launch(
    conn: sqlite3.Connection,
    *,
    work_item_id: str,
    project_id: str,
    owner_session_id: str | None,
    role_id: str | None,
    title: str,
    reuse_from_work_item_id: str | None = None,
) -> tuple[ChatGPTWorkerChat, bool]:
    """Return the durable worker chat and whether this launch reuses one.

    Same-work-item retries always resume the same non-archived chat. A related
    work item only reuses a chat when the caller explicitly points at another
    work item; Synapse never guesses semantic relatedness and contaminates a
    clean worker context by accident.
    """

    existing = find_for_work_item(conn, work_item_id)
    if existing is not None and existing.status != ChatGPTWorkerStatus.ARCHIVED:
        conn.execute(
            "UPDATE chatgpt_worker_chats SET owner_session_id = COALESCE(?, owner_session_id), "
            "role_id = COALESCE(?, role_id), last_used_at = ? WHERE id = ?",
            (owner_session_id, role_id, to_iso(utc_now()), existing.id),
        )
        return get_chat(conn, existing.id), True

    if reuse_from_work_item_id:
        reusable = find_for_work_item(conn, reuse_from_work_item_id)
        if reusable is None:
            raise not_found("chatgpt_worker_for_work_item", reuse_from_work_item_id)
        if reusable.project_id != project_id:
            raise conflict(
                "chatgpt_worker_chat",
                "A ChatGPT worker chat can only be reused inside the same Synapse project.",
                worker_project_id=reusable.project_id,
                requested_project_id=project_id,
            )
        if reusable.status == ChatGPTWorkerStatus.ARCHIVED:
            raise conflict(
                "chatgpt_worker_chat",
                "Archived ChatGPT worker chats are not resumed automatically. Unarchive it first.",
                worker_chat_id=reusable.id,
            )
        linked = link_work_item(
            conn, reusable.id, work_item_id, relation="related"
        )
        conn.execute(
            "UPDATE chatgpt_worker_chats SET owner_session_id = COALESCE(?, owner_session_id), "
            "last_used_at = ? WHERE id = ?",
            (owner_session_id, to_iso(utc_now()), linked.id),
        )
        return get_chat(conn, linked.id), True

    return (
        create_chat(
            conn,
            project_id=project_id,
            title=title,
            owner_session_id=owner_session_id,
            role_id=role_id,
            work_item_id=work_item_id,
        ),
        False,
    )


def mark_active(
    conn: sqlite3.Connection,
    worker_chat_id: str,
    *,
    session_id: str,
    conversation_url: str | None = None,
    title: str | None = None,
) -> ChatGPTWorkerChat:
    existing = get_chat(conn, worker_chat_id)
    conn.execute(
        "UPDATE chatgpt_worker_chats SET last_session_id = ?, conversation_url = ?, "
        "title = ?, status = 'active', archived_reason = '', archived_at = NULL, "
        "last_used_at = ? WHERE id = ?",
        (
            session_id,
            (conversation_url if conversation_url is not None else existing.conversation_url),
            (title.strip() if title else existing.title),
            to_iso(utc_now()),
            worker_chat_id,
        ),
    )
    return get_chat(conn, worker_chat_id)


def mark_idle(
    conn: sqlite3.Connection,
    worker_chat_id: str,
    *,
    conversation_url: str | None = None,
    title: str | None = None,
) -> ChatGPTWorkerChat:
    existing = get_chat(conn, worker_chat_id)
    conn.execute(
        "UPDATE chatgpt_worker_chats SET conversation_url = ?, title = ?, "
        "status = 'idle', last_used_at = ? WHERE id = ?",
        (
            conversation_url if conversation_url is not None else existing.conversation_url,
            title.strip() if title else existing.title,
            to_iso(utc_now()),
            worker_chat_id,
        ),
    )
    return get_chat(conn, worker_chat_id)


def mark_failed(
    conn: sqlite3.Connection, worker_chat_id: str, *, conversation_url: str | None = None
) -> ChatGPTWorkerChat:
    existing = get_chat(conn, worker_chat_id)
    conn.execute(
        "UPDATE chatgpt_worker_chats SET conversation_url = ?, status = 'failed', "
        "last_used_at = ? WHERE id = ?",
        (
            conversation_url if conversation_url is not None else existing.conversation_url,
            to_iso(utc_now()),
            worker_chat_id,
        ),
    )
    return get_chat(conn, worker_chat_id)


def archive_chat(
    conn: sqlite3.Connection, worker_chat_id: str, *, reason: str = ""
) -> ChatGPTWorkerChat:
    get_chat(conn, worker_chat_id)
    now = to_iso(utc_now())
    conn.execute(
        "UPDATE chatgpt_worker_chats SET status = 'archived', archived_reason = ?, "
        "archived_at = ?, last_used_at = ? WHERE id = ?",
        (reason.strip(), now, now, worker_chat_id),
    )
    return get_chat(conn, worker_chat_id)


def unarchive_chat(conn: sqlite3.Connection, worker_chat_id: str) -> ChatGPTWorkerChat:
    get_chat(conn, worker_chat_id)
    conn.execute(
        "UPDATE chatgpt_worker_chats SET status = 'idle', archived_reason = '', "
        "archived_at = NULL, last_used_at = ? WHERE id = ?",
        (to_iso(utc_now()), worker_chat_id),
    )
    return get_chat(conn, worker_chat_id)
