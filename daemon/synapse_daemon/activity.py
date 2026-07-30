"""AI-activity notifications (ADR-0028, PLAN 5 Phase 2).

The operator's "what did the AIs do" feed. A small event->notification **projector**
subscribes to the daemon's own WS events (the same replayable stream every surface
already emits) and persists one truthful row per milestone: an AI session connected
(with its #001 number + green/yellow/red grade), a squad was created (with its real
goal), work was launched / handed off, an idea was filed to the review inbox, a
project launched or errored, a tool primitive ran.

Design rules:
- **Truth from the source**: bodies quote the actual squad goal / proposal title /
  payload facts, and token usage comes from the token ledger when a squad is known.
- **Never crash the bus**: any mapping failure skips that event (the projector is a
  best-effort mirror, not a critical path).
- Storage is daemon-owned (migration 028) so the feed survives reloads; the
  Notification Center reads it via routes_activity.py.
"""

from __future__ import annotations

import json
import secrets
import sqlite3
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from .api_versions import event_name
from .errors import not_found
from .storage import Storage
from .time_utils import from_iso, to_iso, utc_now
from .ws import Event, EventBus


class NotificationLink(BaseModel):
    label: str
    # A renderer NavigationIntent, e.g. {"page": "ai-coding", "section": "review"} --
    # the Notification Center passes it straight to navigate().
    intent: dict[str, Any] = Field(default_factory=dict)


class ActivityNotification(BaseModel):
    id: str
    session_id: str | None = None
    seq: int | None = None
    kind: str
    level: str = "info"
    title: str
    body_md: str = ""
    links: list[NotificationLink] = Field(default_factory=list)
    token_usage: dict[str, Any] | None = None
    created_at: datetime
    read_at: datetime | None = None


def _new_id() -> str:
    return secrets.token_hex(6)


def _row(row: sqlite3.Row) -> ActivityNotification:
    links_raw: list[Any]
    try:
        links_raw = json.loads(row["links_json"] or "[]")
    except json.JSONDecodeError:
        links_raw = []
    token_usage = None
    if row["token_usage_json"]:
        try:
            token_usage = json.loads(row["token_usage_json"])
        except json.JSONDecodeError:
            token_usage = None
    return ActivityNotification(
        id=row["id"],
        session_id=row["session_id"],
        seq=row["seq"],
        kind=row["kind"],
        level=row["level"] or "info",
        title=row["title"],
        body_md=row["body_md"] or "",
        links=[NotificationLink.model_validate(item) for item in links_raw if isinstance(item, dict)],
        token_usage=token_usage,
        created_at=from_iso(row["created_at"]),
        read_at=from_iso(row["read_at"]) if row["read_at"] else None,
    )


# ── CRUD ────────────────────────────────────────────────────────────────────


def create_notification(
    conn: sqlite3.Connection,
    *,
    kind: str,
    title: str,
    level: str = "info",
    body_md: str = "",
    session_id: str | None = None,
    seq: int | None = None,
    links: list[NotificationLink] | None = None,
    token_usage: dict[str, Any] | None = None,
) -> ActivityNotification:
    notification_id = _new_id()
    conn.execute(
        "INSERT INTO activity_notifications "
        "(id, session_id, seq, kind, level, title, body_md, links_json, token_usage_json, created_at, read_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)",
        (
            notification_id,
            session_id,
            seq,
            kind,
            level,
            title,
            body_md,
            json.dumps([link.model_dump(mode="json") for link in (links or [])]),
            json.dumps(token_usage) if token_usage is not None else None,
            to_iso(utc_now()),
        ),
    )
    row = conn.execute(
        "SELECT * FROM activity_notifications WHERE id = ?", (notification_id,)
    ).fetchone()
    return _row(row)


def list_notifications(
    conn: sqlite3.Connection, *, unread_only: bool = False, limit: int = 50
) -> list[ActivityNotification]:
    where = "WHERE read_at IS NULL" if unread_only else ""
    rows = conn.execute(
        f"SELECT * FROM activity_notifications {where} "  # noqa: S608 -- fixed fragment
        "ORDER BY created_at DESC, id DESC LIMIT ?",
        (max(1, min(int(limit), 200)),),
    ).fetchall()
    return [_row(r) for r in rows]


def unread_count(conn: sqlite3.Connection) -> int:
    return int(
        conn.execute(
            "SELECT COUNT(*) FROM activity_notifications WHERE read_at IS NULL"
        ).fetchone()[0]
    )


def mark_read(conn: sqlite3.Connection, notification_id: str) -> ActivityNotification:
    row = conn.execute(
        "SELECT * FROM activity_notifications WHERE id = ?", (notification_id,)
    ).fetchone()
    if row is None:
        raise not_found("activity_notification", notification_id)
    conn.execute(
        "UPDATE activity_notifications SET read_at = ? WHERE id = ? AND read_at IS NULL",
        (to_iso(utc_now()), notification_id),
    )
    return _row(
        conn.execute(
            "SELECT * FROM activity_notifications WHERE id = ?", (notification_id,)
        ).fetchone()
    )


def mark_all_read(conn: sqlite3.Connection) -> int:
    cur = conn.execute(
        "UPDATE activity_notifications SET read_at = ? WHERE read_at IS NULL",
        (to_iso(utc_now()),),
    )
    return cur.rowcount


# ── the projector ───────────────────────────────────────────────────────────

_REVIEW_LINK = NotificationLink(label="Open Review inbox", intent={"page": "ai-coding", "section": "review"})
_SQUADS_LINK = NotificationLink(label="Open Squads", intent={"page": "ai-coding", "section": "squads"})
_APPS_LINK = NotificationLink(label="Open Apps", intent={"page": "apps"})


def project_event(conn: sqlite3.Connection, name: str, payload: dict[str, Any]) -> ActivityNotification | None:
    """Map one bus event to a notification row (or None if it isn't a milestone).

    Called inside a storage transaction by the subscriber. Truth-first: reads the
    squad / proposal from the DB where only an id is in the payload.
    """

    if name == event_name("coordination", "session_registered"):
        seq = payload.get("seq")
        runtime = str(payload.get("runtime_id") or "").strip() or "unknown runtime"
        label = str(payload.get("agent_label") or "").strip()
        level = str(payload.get("connection_level") or "green")
        code = str(payload.get("connection_code") or "ok")
        who = f"{label} ({runtime})" if label and label.lower() != runtime.lower() else runtime
        title = f"Session #{seq:03d} — {who} connected" if isinstance(seq, int) else f"{who} connected"
        body_lines = [f"**Status:** {level} (`{code}`)"]
        task = str(payload.get("task") or "").strip()
        if task:
            body_lines.append(f"**Task:** {task}")
        if payload.get("project_id"):
            body_lines.append(f"**Project:** {payload['project_id']}")
        return create_notification(
            conn,
            kind="session.connected",
            level=level,
            title=title,
            body_md="\n\n".join(body_lines),
            session_id=payload.get("session_id"),
            seq=seq if isinstance(seq, int) else None,
        )

    if name == event_name("agent_squad", "created"):
        squad = payload.get("squad") or {}
        squad_name = str(squad.get("name") or "Unnamed squad")
        goal = str(squad.get("goal_md") or "").strip()
        body = f"**Goal:** {goal}" if goal else "_No goal recorded yet._"
        if squad.get("project_id"):
            body += f"\n\n**Project:** {squad['project_id']}"
        return create_notification(
            conn,
            kind="squad.created",
            title=f"New squad: {squad_name}",
            body_md=body,
            links=[_SQUADS_LINK],
        )

    if name in (event_name("agent_work_item", "created"), event_name("agent_work_item", "handoff")):
        item = payload.get("work_item") or {}
        title = str(item.get("title") or "Work item")
        verb = "created" if name.endswith("created") else "handed off"
        role = str(item.get("assigned_role_id") or "")
        body_lines = []
        if role:
            body_lines.append(f"**Role:** {role}")
        if verb == "handed off" and item.get("summary_md"):
            body_lines.append(f"**Handoff:** {str(item['summary_md'])[:500]}")
        token_usage = _squad_tokens(conn, item.get("squad_id"))
        return create_notification(
            conn,
            kind=f"work_item.{ 'created' if verb == 'created' else 'handoff' }",
            title=f"Work item {verb}: {title}",
            body_md="\n\n".join(body_lines),
            links=[_SQUADS_LINK],
            token_usage=token_usage,
        )

    if name == event_name("review", "proposal_filed"):
        proposal_id = str(payload.get("id") or "")
        title = "An idea was filed to your inbox"
        body = ""
        try:
            from . import proposals as _proposals

            p = _proposals.get_proposal(conn, proposal_id)
            title = f"Idea filed to inbox: {p.title}"
            body = (p.rationale_md or "")[:600]
        except Exception:  # noqa: BLE001 -- keep the generic title on any read failure
            pass
        return create_notification(
            conn,
            kind="review.proposal_filed",
            title=title,
            body_md=body,
            links=[_REVIEW_LINK],
        )

    if name in (event_name("project", "launched"), event_name("project", "errored")):
        project_id = str(payload.get("id") or "unknown")
        errored = name.endswith("errored")
        return create_notification(
            conn,
            kind="project.errored" if errored else "project.launched",
            level="red" if errored else "info",
            title=f"Project {project_id} {'errored' if errored else 'launched'}",
            body_md=f"**PID:** {payload['pid']}" if payload.get("pid") else "",
            links=[_APPS_LINK],
        )

    if name == event_name("tool", "primitive_ran"):
        tool_id = str(payload.get("tool_id") or "tool")
        primitive = str(payload.get("primitive") or "action")
        return create_notification(
            conn,
            kind="tool.primitive_ran",
            title=f"Tool ran: {tool_id} · {primitive}",
        )

    return None


def _squad_tokens(conn: sqlite3.Connection, squad_id: Any) -> dict[str, Any] | None:
    if not squad_id:
        return None
    try:
        from . import token_ledger

        rollup = token_ledger.sum_squad_tokens(conn, str(squad_id))
        if rollup.entries == 0:
            return None
        return rollup.model_dump(mode="json")
    except Exception:  # noqa: BLE001 -- token usage is enrichment, never a failure
        return None


async def subscribe_activity_projector(storage: Storage, bus: EventBus) -> None:
    """Wire the projector to the bus (called once at daemon startup)."""

    async def _on_event(event: Event) -> None:
        try:
            with storage.transaction() as conn:
                created = project_event(conn, event.name, event.payload or {})
        except Exception:  # noqa: BLE001 -- a projector failure must never break the bus
            return
        if created is not None:
            # Announce the new notification itself so the bell badge updates live.
            await bus.publish(
                event_name("activity", "notification"),
                {"notification": created.model_dump(mode="json")},
            )

    await bus.subscribe(_on_event)
