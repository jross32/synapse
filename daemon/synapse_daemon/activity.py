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
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator

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


class ActivityJournalCategory(str, Enum):
    STATUS = "status"
    PLAN = "plan"
    REASONING = "reasoning"
    IDEA = "idea"
    DECISION = "decision"
    ACTION = "action"
    EVIDENCE = "evidence"
    SEARCH = "search"
    BLOCKER = "blocker"
    SQUAD = "squad"
    MCP = "mcp"
    TOOL = "tool"
    RESULT = "result"


class ActivityJournalStatus(str, Enum):
    PLANNED = "planned"
    ACTIVE = "active"
    SUCCESS = "success"
    BLOCKED = "blocked"
    FAILED = "failed"
    INFO = "info"


class ActivityAuthority(str, Enum):
    NONE = "none"
    OBSERVE = "observe"
    CONTROL = "control"
    EXECUTE = "execute"


class ActivityGoalStatus(str, Enum):
    PENDING = "pending"
    ACTIVE = "active"
    COMPLETED = "completed"
    BLOCKED = "blocked"


class ActivityGoal(BaseModel):
    id: str
    session_id: str
    title: str
    detail_md: str = ""
    status: ActivityGoalStatus = ActivityGoalStatus.PENDING
    position: int = 0
    created_at: datetime
    updated_at: datetime


class ActivityGoalCreate(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    detail_md: str = Field(default="", max_length=2000)
    status: ActivityGoalStatus = ActivityGoalStatus.PENDING

    @field_validator("title", "detail_md", mode="before")
    @classmethod
    def sanitize_goal_text(cls, value: Any) -> Any:
        if not isinstance(value, str):
            return value
        return "".join(
            character
            for character in value
            if character in "\n\r\t" or ord(character) >= 32
        )


class ActivityGoalUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=160)
    detail_md: str | None = Field(default=None, max_length=2000)
    status: ActivityGoalStatus | None = None
    position: int | None = Field(default=None, ge=0)

    @field_validator("title", "detail_md", mode="before")
    @classmethod
    def sanitize_goal_text(cls, value: Any) -> Any:
        if not isinstance(value, str):
            return value
        return "".join(
            character
            for character in value
            if character in "\n\r\t" or ord(character) >= 32
        )


class ActivityJournalCreate(BaseModel):
    category: ActivityJournalCategory
    status: ActivityJournalStatus = ActivityJournalStatus.INFO
    title: str = Field(min_length=1, max_length=160)
    # Deep View can carry a substantial deliberate reasoning summary, while
    # remaining bounded and explicitly unsuitable for secrets/raw hidden CoT.
    summary_md: str = Field(default="", max_length=8000)
    squad_id: str | None = Field(default=None, max_length=64)
    work_item_id: str | None = Field(default=None, max_length=64)
    mcp_server_id: str | None = Field(default=None, max_length=100)
    tool_name: str | None = Field(default=None, max_length=160)
    authority: ActivityAuthority = ActivityAuthority.NONE

    @field_validator("title", "summary_md", mode="before")
    @classmethod
    def sanitize_operator_text(cls, value: Any) -> Any:
        if not isinstance(value, str):
            return value
        return "".join(
            character
            for character in value
            if character in "\n\r\t" or ord(character) >= 32
        )


class ActivityJournalEvent(ActivityJournalCreate):
    id: str
    session_id: str | None = None
    source: str = "agent"
    created_at: datetime


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


def _journal_row(row: sqlite3.Row) -> ActivityJournalEvent:
    return ActivityJournalEvent(
        id=row["id"],
        session_id=row["session_id"],
        category=row["category"],
        status=row["status"],
        title=row["title"],
        summary_md=row["summary_md"] or "",
        squad_id=row["squad_id"],
        work_item_id=row["work_item_id"],
        mcp_server_id=row["mcp_server_id"],
        tool_name=row["tool_name"],
        authority=row["authority"] or "none",
        source=row["source"] or "agent",
        created_at=from_iso(row["created_at"]),
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


def create_journal_event(
    conn: sqlite3.Connection,
    payload: ActivityJournalCreate,
    *,
    session_id: str | None,
    source: str = "agent",
) -> ActivityJournalEvent:
    """Persist one concise, operator-facing receipt.

    Callers must not put secrets or hidden chain-of-thought here.  The strict
    fields intentionally make the journal less tempting than an arbitrary log.
    """

    event_id = _new_id()
    conn.execute(
        "INSERT INTO activity_journal "
        "(id, session_id, category, status, title, summary_md, squad_id, work_item_id, "
        "mcp_server_id, tool_name, authority, source, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            event_id,
            session_id,
            payload.category.value,
            payload.status.value,
            payload.title.strip(),
            payload.summary_md.strip(),
            payload.squad_id,
            payload.work_item_id,
            payload.mcp_server_id,
            payload.tool_name,
            payload.authority.value,
            source,
            to_iso(utc_now()),
        ),
    )
    row = conn.execute("SELECT * FROM activity_journal WHERE id = ?", (event_id,)).fetchone()
    return _journal_row(row)


def _session_metadata(conn: sqlite3.Connection, session_id: str) -> dict[str, Any]:
    row = conn.execute(
        "SELECT metadata_json FROM agent_sessions WHERE id = ?", (session_id,)
    ).fetchone()
    if row is None:
        raise not_found("agent_session", session_id)
    try:
        value = json.loads(row["metadata_json"] or "{}")
    except json.JSONDecodeError:
        value = {}
    return value if isinstance(value, dict) else {}


def _write_session_goals(
    conn: sqlite3.Connection, session_id: str, goals: list[ActivityGoal]
) -> None:
    metadata = _session_metadata(conn, session_id)
    metadata["activity_goals"] = [goal.model_dump(mode="json") for goal in goals]
    conn.execute(
        "UPDATE agent_sessions SET metadata_json = ? WHERE id = ?",
        (json.dumps(metadata), session_id),
    )


def list_session_goals(conn: sqlite3.Connection, session_id: str) -> list[ActivityGoal]:
    metadata = _session_metadata(conn, session_id)
    raw_goals = metadata.get("activity_goals")
    if not isinstance(raw_goals, list):
        return []
    goals: list[ActivityGoal] = []
    for raw in raw_goals:
        if not isinstance(raw, dict):
            continue
        try:
            goals.append(ActivityGoal.model_validate(raw))
        except Exception:  # noqa: BLE001 -- skip one malformed legacy metadata entry
            continue
    return sorted(goals, key=lambda goal: (goal.position, goal.created_at, goal.id))


def create_session_goal(
    conn: sqlite3.Connection, session_id: str, payload: ActivityGoalCreate
) -> ActivityGoal:
    goals = list_session_goals(conn, session_id)
    now = utc_now()
    goal = ActivityGoal(
        id=_new_id(),
        session_id=session_id,
        title=payload.title.strip(),
        detail_md=payload.detail_md.strip(),
        status=payload.status,
        position=len(goals),
        created_at=now,
        updated_at=now,
    )
    goals.append(goal)
    _write_session_goals(conn, session_id, goals)
    return goal


def update_session_goal(
    conn: sqlite3.Connection,
    session_id: str,
    goal_id: str,
    payload: ActivityGoalUpdate,
) -> ActivityGoal:
    goals = list_session_goals(conn, session_id)
    for index, existing in enumerate(goals):
        if existing.id != goal_id:
            continue
        changes = payload.model_dump(exclude_none=True)
        if "title" in changes:
            changes["title"] = str(changes["title"]).strip()
        if "detail_md" in changes:
            changes["detail_md"] = str(changes["detail_md"]).strip()
        changes["updated_at"] = utc_now()
        updated = existing.model_copy(update=changes)
        goals[index] = updated
        _write_session_goals(conn, session_id, goals)
        return updated
    raise not_found("activity_goal", goal_id)


def delete_session_goal(
    conn: sqlite3.Connection, session_id: str, goal_id: str
) -> ActivityGoal:
    goals = list_session_goals(conn, session_id)
    deleted = next((goal for goal in goals if goal.id == goal_id), None)
    if deleted is None:
        raise not_found("activity_goal", goal_id)
    remaining = [
        goal.model_copy(update={"position": index, "updated_at": utc_now()})
        for index, goal in enumerate(goal for goal in goals if goal.id != goal_id)
    ]
    _write_session_goals(conn, session_id, remaining)
    return deleted


def list_journal_events(
    conn: sqlite3.Connection,
    *,
    session_id: str | None = None,
    squad_ids: list[str] | None = None,
    limit: int = 300,
) -> list[ActivityJournalEvent]:
    clauses: list[str] = []
    args: list[Any] = []
    if session_id is not None:
        clauses.append("session_id = ?")
        args.append(session_id)
    clean_squad_ids = [item for item in (squad_ids or []) if item]
    if clean_squad_ids:
        placeholders = ",".join("?" for _ in clean_squad_ids)
        clauses.append(f"squad_id IN ({placeholders})")  # noqa: S608 -- placeholders only
        args.extend(clean_squad_ids)
    where = f"WHERE {' OR '.join(clauses)}" if clauses else ""
    args.append(max(1, min(int(limit), 500)))
    rows = conn.execute(
        f"SELECT * FROM activity_journal {where} ORDER BY created_at DESC, id DESC LIMIT ?",  # noqa: S608
        args,
    ).fetchall()
    return [_journal_row(row) for row in rows]


# ── the projector ───────────────────────────────────────────────────────────

_REVIEW_LINK = NotificationLink(label="Open Review inbox", intent={"page": "ai-coding", "section": "review"})
_SQUADS_LINK = NotificationLink(label="Open Squads", intent={"page": "ai-coding", "section": "squads"})
_APPS_LINK = NotificationLink(label="Open Apps", intent={"page": "apps"})


def _owner_session_id_for_squad(
    conn: sqlite3.Connection, squad_id: str | None
) -> str | None:
    """Return the coordination session that first attached this squad to Live.

    The squad-created receipt is written with the caller's X-Synapse-Session.
    Reusing that durable link lets later worker starts, MCP attachments, and
    reviewer handoffs roll up into the parent session even when the child call
    itself has no coordination header.
    """

    if not squad_id:
        return None
    row = conn.execute(
        "SELECT session_id FROM activity_journal "
        "WHERE squad_id = ? AND session_id IS NOT NULL "
        "ORDER BY created_at ASC, id ASC LIMIT 1",
        (squad_id,),
    ).fetchone()
    return str(row["session_id"]) if row and row["session_id"] else None


def project_event(conn: sqlite3.Connection, name: str, payload: dict[str, Any]) -> ActivityNotification | None:
    """Map one bus event to a notification row (or None if it isn't a milestone).

    Called inside a storage transaction by the subscriber. Truth-first: reads the
    squad / proposal from the DB where only an id is in the payload.
    """

    if name == event_name("coordination", "session_registered"):
        # A nested worker is displayed inside its parent session, so announcing it at
        # the top of the notification centre was pure noise -- one squad launch could
        # produce a "connected" card per worker for work the operator already sees
        # rolled up. The worker's own record is untouched; only the shout is dropped.
        if payload.get("parent_session_id"):
            return None
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


def project_journal_events(
    conn: sqlite3.Connection, name: str, payload: dict[str, Any]
) -> list[ActivityJournalEvent]:
    """Project durable squad/MCP receipts from daemon-owned lifecycle events."""

    created: list[ActivityJournalEvent] = []
    if name == event_name("agent_squad", "created"):
        squad = payload.get("squad") or {}
        squad_id = str(squad.get("id") or "") or None
        created.append(
            create_journal_event(
                conn,
                ActivityJournalCreate(
                    category=ActivityJournalCategory.SQUAD,
                    status=ActivityJournalStatus.SUCCESS,
                    title=f"Squad created: {str(squad.get('name') or 'Unnamed squad')}",
                    summary_md=str(squad.get("goal_md") or "")[:2000],
                    squad_id=squad_id,
                    authority=ActivityAuthority.EXECUTE,
                ),
                session_id=str(payload.get("session_id") or "") or None,
                source="synapse",
            )
        )
    elif name in (
        event_name("agent_work_item", "created"),
        event_name("agent_work_item", "handoff"),
        event_name("agent_work_item", "updated"),
    ):
        item = payload.get("work_item") or {}
        item_id = str(item.get("id") or "") or None
        squad_id = str(item.get("squad_id") or "") or None
        verb = name.rsplit(".", 1)[-1]
        status_raw = str(item.get("status") or "info")
        mapped_status = {
            "running": ActivityJournalStatus.ACTIVE,
            "completed": ActivityJournalStatus.SUCCESS,
            "blocked": ActivityJournalStatus.BLOCKED,
            "failed": ActivityJournalStatus.FAILED,
        }.get(status_raw, ActivityJournalStatus.INFO)
        summary = str(item.get("summary_md") or item.get("instructions_md") or "")[:2000]
        owner_session_id = (
            str(payload.get("session_id") or "") or _owner_session_id_for_squad(conn, squad_id)
        )
        created.append(
            create_journal_event(
                conn,
                ActivityJournalCreate(
                    category=ActivityJournalCategory.SQUAD,
                    status=mapped_status,
                    title=f"Work item {verb}: {str(item.get('title') or 'Untitled work item')}",
                    summary_md=summary,
                    squad_id=squad_id,
                    work_item_id=item_id,
                    authority=ActivityAuthority.EXECUTE,
                ),
                session_id=owner_session_id,
                source="synapse",
            )
        )
    elif name == event_name("agent_run", "started"):
        runtime = str(payload.get("runtime") or "unknown")
        execution_mode = str(payload.get("execution_mode") or "interactive")
        authority = str(payload.get("authority") or "workspace")
        timeout_seconds = payload.get("timeout_seconds")
        summary = f"Runtime: {runtime} · Mode: {execution_mode} · Authority: {authority}"
        if execution_mode == "automatic" and timeout_seconds:
            summary += f" · Timeout: {timeout_seconds}s"
        squad_id = str(payload.get("squad_id") or "") or None
        created.append(
            create_journal_event(
                conn,
                ActivityJournalCreate(
                    category=ActivityJournalCategory.ACTION,
                    status=ActivityJournalStatus.ACTIVE,
                    title=f"Worker started: {str(payload.get('role_id') or 'agent')}",
                    summary_md=summary,
                    squad_id=squad_id,
                    work_item_id=str(payload.get("work_item_id") or "") or None,
                    authority=(
                        ActivityAuthority.OBSERVE
                        if authority == "observe"
                        else ActivityAuthority.EXECUTE
                    ),
                ),
                session_id=_owner_session_id_for_squad(conn, squad_id),
                source="synapse",
            )
        )
    elif name == event_name("agent_mcp", "attached"):
        server_ids = [str(item) for item in payload.get("mcp_server_ids") or [] if item]
        if server_ids:
            squad_id = str(payload.get("squad_id") or "") or None
            created.append(
                create_journal_event(
                    conn,
                    ActivityJournalCreate(
                        category=ActivityJournalCategory.MCP,
                        status=ActivityJournalStatus.SUCCESS,
                        title=f"{len(server_ids)} MCP server{'s' if len(server_ids) != 1 else ''} attached",
                        summary_md=", ".join(server_ids),
                        squad_id=squad_id,
                        work_item_id=str(payload.get("work_item_id") or "") or None,
                        authority=ActivityAuthority.OBSERVE,
                    ),
                    session_id=_owner_session_id_for_squad(conn, squad_id),
                    source="synapse",
                )
            )
    return created


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
                journal_events = project_journal_events(conn, event.name, event.payload or {})
        except Exception:  # noqa: BLE001 -- a projector failure must never break the bus
            return
        if created is not None:
            # Announce the new notification itself so the bell badge updates live.
            await bus.publish(
                event_name("activity", "notification"),
                {"notification": created.model_dump(mode="json")},
            )
        for journal_event in journal_events:
            await bus.publish(
                event_name("activity", "journaled"),
                {"event": journal_event.model_dump(mode="json")},
            )

    await bus.subscribe(_on_event)
