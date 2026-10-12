"""Durable catalog for ChatGPT UI conversations observed in the owner's Chrome.

Browser presence is ephemeral. Closing a tab must never delete/archive a worker.
Managed work-item workers retain ownership of their lifecycle; the observer only
manages records which it explicitly imported.
"""
from __future__ import annotations

import json
import re
import sqlite3
from datetime import timedelta
from urllib.parse import urlsplit, urlunsplit

from . import chatgpt_worker_chats as workers
from . import thread_presence
from .time_utils import to_iso, utc_now

_PROJECT_KEY = "g-p-6a91003e980c81919b8920cfc9e0941e"
_CONVERSATION_PATH = re.compile(
    rf"^/g/{re.escape(_PROJECT_KEY)}(?:-synapse2gpt-workers)?/c/[A-Za-z0-9-]+/?$"
)
DEFAULT_PROJECT_ID = "synapse-self"
PRESENCE_TTL_SECONDS = 90


def canonical_worker_url(value: str) -> str:
    """Accept only canonical conversation URLs in the approved Workers project."""
    try:
        parsed = urlsplit(value.strip())
    except ValueError:
        return ""
    if (
        parsed.scheme != "https"
        or parsed.netloc != "chatgpt.com"
        or not _CONVERSATION_PATH.fullmatch(parsed.path)
    ):
        return ""
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path.rstrip("/"), "", ""))


def import_observation(
    conn: sqlite3.Connection, payload: thread_presence.BrowserObservation
) -> workers.ChatGPTWorkerChat | None:
    """Idempotently register a browser-created chat without inventing a work item.

    This never modifies managed worker state and never unarchives a retired worker.
    """
    url = canonical_worker_url(payload.conversation_url)
    if not url:
        return None
    row = conn.execute(
        "SELECT * FROM chatgpt_worker_chats WHERE conversation_url = ?", (url,)
    ).fetchone()
    status = {
        "active": "active",
        "error": "failed",
        "idle": "idle",
        "gone": "idle",
    }.get(payload.status.value, "idle")
    now = to_iso(utc_now())
    if row is not None:
        existing = workers.get_chat(conn, str(row["id"]))
        if existing.status == workers.ChatGPTWorkerStatus.ARCHIVED:
            return existing
        metadata = dict(existing.metadata)
        if metadata.get("source") != "chrome_observer":
            return existing
        metadata["browser_status"] = payload.status.value
        if payload.current_task:
            metadata["current_task"] = payload.current_task[:4000]
        conn.execute(
            "UPDATE chatgpt_worker_chats SET title = ?, status = ?, "
            "metadata_json = ?, last_used_at = ? WHERE id = ?",
            (
                (payload.title.strip() or existing.title)[:500],
                status,
                json.dumps(metadata, separators=(",", ":"), sort_keys=True),
                now,
                existing.id,
            ),
        )
        return workers.get_chat(conn, existing.id)

    import secrets
    worker_id = secrets.token_hex(6)
    metadata = {
        "source": "chrome_observer",
        "browser_status": payload.status.value,
        "current_task": payload.current_task[:4000],
    }
    conn.execute(
        "INSERT INTO chatgpt_worker_chats "
        "(id, project_id, owner_session_id, last_session_id, role_id, "
        "chatgpt_project_name, conversation_url, title, status, archived_reason, "
        "created_at, last_used_at, archived_at, metadata_json) "
        "VALUES (?, ?, NULL, NULL, NULL, ?, ?, ?, ?, '', ?, ?, NULL, ?)",
        (
            worker_id,
            DEFAULT_PROJECT_ID,
            workers.WORKER_PROJECT_NAME,
            url,
            (payload.title.strip() or "ChatGPT UI worker")[:500],
            status,
            now,
            now,
            json.dumps(metadata, separators=(",", ":"), sort_keys=True),
        ),
    )
    return workers.get_chat(conn, worker_id)


def catalog(conn: sqlite3.Connection, *, include_archived: bool = True) -> dict:
    """Combine persisted worker records with best-effort live browser presence."""
    observations = thread_presence.list_browser_observations(conn, include_gone=True)
    now = utc_now()
    by_url = {}
    for item in observations:
        url = canonical_worker_url(item.conversation_url)
        if not url or url in by_url:
            continue  # observations are newest-first
        age = max(0, (now - item.last_seen_at).total_seconds())
        open_now = item.status.value not in {"gone", "stale"} and age <= PRESENCE_TTL_SECONDS
        by_url[url] = {
            "open": open_now,
            "activity": "active" if open_now and item.status.value == "active" else "idle",
            "last_seen_at": item.last_seen_at.isoformat(),
        }
    records = workers.list_chats(conn, include_archived=include_archived)
    result = []
    for item in records:
        presence = by_url.get(canonical_worker_url(item.conversation_url), {})
        item_dict = item.model_dump(mode="json")
        item_dict["open_in_browser"] = bool(presence.get("open", False))
        item_dict["browser_activity"] = presence.get("activity", "unknown")
        item_dict["browser_last_seen_at"] = presence.get("last_seen_at")
        item_dict["parked"] = (
            item.status != workers.ChatGPTWorkerStatus.ARCHIVED
            and not item_dict["open_in_browser"]
        )
        result.append(item_dict)
    return {
        "workers": result,
        "total": len(result),
        "open_count": sum(1 for worker in result if worker["open_in_browser"]),
        "parked_count": sum(1 for worker in result if worker["parked"]),
    }


def save_handoff(
    conn: sqlite3.Connection,
    worker_chat_id: str,
    *,
    handoff_md: str,
    next_step: str,
) -> workers.ChatGPTWorkerChat:
    """Persist bounded operator/AI handoff without modifying worker lifecycle."""
    item = workers.get_chat(conn, worker_chat_id)
    metadata = dict(item.metadata)
    metadata["handoff_md"] = handoff_md[:6000]
    metadata["next_step"] = next_step[:2000]
    metadata["handoff_updated_at"] = to_iso(utc_now())
    conn.execute(
        "UPDATE chatgpt_worker_chats SET metadata_json = ? WHERE id = ?",
        (json.dumps(metadata, separators=(",", ":"), sort_keys=True), item.id),
    )
    return workers.get_chat(conn, item.id)
