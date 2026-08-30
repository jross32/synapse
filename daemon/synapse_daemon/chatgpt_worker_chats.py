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

import json
import secrets
import sqlite3
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel

from .errors import conflict, not_found
from .time_utils import from_iso, to_iso, utc_now

WORKER_PROJECT_NAME = "Synapse2GPT Workers"


class ChatGPTWorkerStatus(StrEnum):
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
    metadata: dict[str, object] = {}
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
        metadata=_metadata_from_row(row),
        work_item_ids=_work_item_ids(conn, row["id"]),
    )



def _metadata_from_row(row: sqlite3.Row) -> dict[str, object]:
    try:
        value = json.loads(row["metadata_json"] or "{}")
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def record_recovery(
    conn: sqlite3.Connection,
    worker_chat_id: str,
    *,
    outcome: str,
    error: str = "",
) -> ChatGPTWorkerChat:
    """Persist one bounded same-conversation recovery observation.

    Recovery bookkeeping lives in metadata_json so the worker registry can expose
    it immediately without a schema migration colliding with unrelated in-flight
    migrations. The history is intentionally compact and append-bounded.
    """
    row = conn.execute(
        "SELECT metadata_json FROM chatgpt_worker_chats WHERE id = ?",
        (worker_chat_id,),
    ).fetchone()
    if row is None:
        raise not_found("chatgpt_worker_chat", worker_chat_id)
    metadata = _metadata_from_row(row)
    recovery = metadata.get("recovery")
    if not isinstance(recovery, dict):
        recovery = {}
    attempts = int(recovery.get("attempts") or 0) + 1
    successes = int(recovery.get("successes") or 0) + (1 if outcome == "succeeded" else 0)
    now = to_iso(utc_now())
    history = recovery.get("history")
    if not isinstance(history, list):
        history = []
    history = [*history[-9:], {"at": now, "outcome": outcome, "error": error[:1000]}]
    metadata["recovery"] = {
        "attempts": attempts,
        "successes": successes,
        "last_at": now,
        "last_outcome": outcome,
        "last_error": error[:1000],
        "history": history,
    }
    conn.execute(
        "UPDATE chatgpt_worker_chats SET metadata_json = ?, last_used_at = ? WHERE id = ?",
        (json.dumps(metadata, separators=(",", ":"), sort_keys=True), now, worker_chat_id),
    )
    return get_chat(conn, worker_chat_id)

def get_chat(conn: sqlite3.Connection, worker_chat_id: str) -> ChatGPTWorkerChat:
    row = conn.execute(
        "SELECT * FROM chatgpt_worker_chats WHERE id = ?", (worker_chat_id,)
    ).fetchone()
    if row is None:
        raise not_found("chatgpt_worker_chat", worker_chat_id)
    return _row_to_chat(conn, row)



def reconcile_interrupted_workers(conn: sqlite3.Connection) -> list[str]:
    """Convert daemon-interrupted managed ChatGPT workers into resumable idle chats.

    The browser controller lives inside the daemon process, so an ``active`` or
    ``starting`` row cannot truthfully remain active across a daemon restart. The
    durable conversation URL is still valuable, though: relaunching the work item
    can safely resume that exact conversation. Record the interruption in metadata
    and move only those transient states to ``idle``; failed/archived/ordinary idle
    workers are untouched.
    """
    rows = conn.execute(
        "SELECT id, status, metadata_json FROM chatgpt_worker_chats "
        "WHERE status IN ('starting', 'active')"
    ).fetchall()
    changed: list[str] = []
    now = to_iso(utc_now())
    for row in rows:
        metadata = _metadata_from_row(row)
        restart = metadata.get("restart_recovery")
        if not isinstance(restart, dict):
            restart = {}
        restart.update({
            "pending": True,
            "at": now,
            "previous_status": str(row["status"]),
            "reason": "daemon-restart",
        })
        metadata["restart_recovery"] = restart
        conn.execute(
            "UPDATE chatgpt_worker_chats SET status = 'idle', metadata_json = ?, last_used_at = ? WHERE id = ?",
            (json.dumps(metadata, separators=(",", ":"), sort_keys=True), now, row["id"]),
        )
        changed.append(str(row["id"]))
    return changed

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


def _conversation_url_for_update(
    conn: sqlite3.Connection,
    worker_chat_id: str,
    requested: str | None,
    existing: str,
) -> str:
    """Normalize and reserve one real ChatGPT conversation for one worker row."""

    value = existing if requested is None else requested.strip()
    if not value:
        return ""
    row = conn.execute(
        "SELECT id FROM chatgpt_worker_chats WHERE conversation_url = ? AND id != ? LIMIT 1",
        (value, worker_chat_id),
    ).fetchone()
    if row is not None:
        raise conflict(
            "chatgpt_worker_chat",
            "That ChatGPT conversation is already owned by another durable worker. Reuse or unarchive the existing worker instead of duplicating it.",
            conversation_url=value,
            existing_worker_chat_id=row["id"],
            requested_worker_chat_id=worker_chat_id,
        )
    return value


def mark_active(
    conn: sqlite3.Connection,
    worker_chat_id: str,
    *,
    session_id: str,
    conversation_url: str | None = None,
    title: str | None = None,
) -> ChatGPTWorkerChat:
    existing = get_chat(conn, worker_chat_id)
    now = to_iso(utc_now())
    metadata = dict(existing.metadata)
    restart = metadata.get("restart_recovery")
    if isinstance(restart, dict) and restart.get("pending"):
        restart = dict(restart)
        restart["pending"] = False
        restart["resumed_at"] = now
        metadata["restart_recovery"] = restart
    conn.execute(
        "UPDATE chatgpt_worker_chats SET last_session_id = ?, conversation_url = ?, "
        "title = ?, status = 'active', archived_reason = '', archived_at = NULL, "
        "metadata_json = ?, last_used_at = ? WHERE id = ?",
        (
            session_id,
            _conversation_url_for_update(
                conn, worker_chat_id, conversation_url, existing.conversation_url
            ),
            (title.strip() if title else existing.title),
            json.dumps(metadata, separators=(",", ":"), sort_keys=True),
            now,
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
            _conversation_url_for_update(
                conn, worker_chat_id, conversation_url, existing.conversation_url
            ),
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
            _conversation_url_for_update(
                conn, worker_chat_id, conversation_url, existing.conversation_url
            ),
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
