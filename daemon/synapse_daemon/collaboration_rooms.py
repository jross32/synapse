"""Durable project-scoped AI collaboration rooms (ADR-0037).

Rooms extend the existing ADR-0024 coordination substrate.  A room never
spawns an AI and never captures private chain-of-thought; already-registered
Synapse sessions explicitly join and exchange concise messages, status,
questions, decisions and handoffs.  Presence is derived from the canonical
agent_sessions heartbeat so there is still one source of truth for "who is
here".
"""

from __future__ import annotations

import secrets
import sqlite3
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field

from . import coordination
from . import projects as projects_module
from .errors import invalid, not_found
from .time_utils import from_iso, to_iso, utc_now


class CollaborationRoomStatus(str, Enum):
    OPEN = "open"
    ARCHIVED = "archived"


class CollaborationMessageKind(str, Enum):
    MESSAGE = "message"
    STATUS = "status"
    HANDOFF = "handoff"
    DECISION = "decision"
    QUESTION = "question"
    ANSWER = "answer"


class CollaborationRoom(BaseModel):
    id: str
    project_id: str
    name: str
    goal_md: str = ""
    summary_md: str = ""
    status: CollaborationRoomStatus = CollaborationRoomStatus.OPEN
    created_by_session_id: str | None = None
    created_at: datetime
    updated_at: datetime


class CollaborationRoomCreate(BaseModel):
    project_id: str
    name: str = Field(min_length=1, max_length=160)
    goal_md: str = Field(default="", max_length=32000)
    summary_md: str = Field(default="", max_length=32000)
    created_by_session_id: str | None = None


class CollaborationRoomPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    goal_md: str | None = Field(default=None, max_length=32000)
    summary_md: str | None = Field(default=None, max_length=32000)
    status: CollaborationRoomStatus | None = None


class CollaborationRoomJoin(BaseModel):
    session_id: str
    role_label: str = Field(default="", max_length=160)


class CollaborationRoomPost(BaseModel):
    session_id: str
    body_md: str = Field(min_length=1, max_length=16000)
    kind: CollaborationMessageKind = CollaborationMessageKind.MESSAGE


class CollaborationRoomMember(BaseModel):
    room_id: str
    session_id: str
    agent_label: str = ""
    runtime_id: str = ""
    role_label: str = ""
    task: str = ""
    session_status: coordination.AgentSessionStatus
    stale: bool = False
    present: bool = False
    joined_at: datetime
    last_seen_at: datetime
    left_at: datetime | None = None


class CollaborationRoomMessage(BaseModel):
    id: int
    room_id: str
    session_id: str | None = None
    agent_label: str = ""
    runtime_id: str = ""
    kind: CollaborationMessageKind = CollaborationMessageKind.MESSAGE
    body_md: str
    created_at: datetime


class CollaborationRoomSync(BaseModel):
    room: CollaborationRoom
    members: list[CollaborationRoomMember] = Field(default_factory=list)
    messages: list[CollaborationRoomMessage] = Field(default_factory=list)
    latest_message_id: int = 0
    generated_at: datetime


def _new_id() -> str:
    return secrets.token_hex(6)


def _row_to_room(row: sqlite3.Row) -> CollaborationRoom:
    return CollaborationRoom(
        id=row["id"],
        project_id=row["project_id"],
        name=row["name"],
        goal_md=row["goal_md"] or "",
        summary_md=row["summary_md"] or "",
        status=CollaborationRoomStatus(row["status"]),
        created_by_session_id=row["created_by_session_id"],
        created_at=from_iso(row["created_at"]),
        updated_at=from_iso(row["updated_at"]),
    )


def _assert_session_project(
    conn: sqlite3.Connection, session_id: str, project_id: str
) -> coordination.AgentSession:
    session = coordination.get_session(conn, session_id)
    if session.project_id != project_id:
        raise invalid(
            "collaboration_room",
            "The AI session must be registered to the same project as the room.",
            session_id=session_id,
            session_project_id=session.project_id,
            room_project_id=project_id,
        )
    return session


def create_room(
    conn: sqlite3.Connection, payload: CollaborationRoomCreate
) -> CollaborationRoom:
    project_id = payload.project_id.strip()
    projects_module.get(conn, project_id)
    creator = (payload.created_by_session_id or "").strip() or None
    if creator is not None:
        _assert_session_project(conn, creator, project_id)
    room_id = _new_id()
    now = to_iso(utc_now())
    conn.execute(
        "INSERT INTO collaboration_rooms "
        "(id, project_id, name, goal_md, summary_md, status, created_by_session_id, "
        " created_at, updated_at, metadata_json) "
        "VALUES (?, ?, ?, ?, ?, 'open', ?, ?, ?, '{}')",
        (
            room_id,
            project_id,
            payload.name.strip(),
            payload.goal_md.strip(),
            payload.summary_md.strip(),
            creator,
            now,
            now,
        ),
    )
    return get_room(conn, room_id)


def get_room(conn: sqlite3.Connection, room_id: str) -> CollaborationRoom:
    row = conn.execute(
        "SELECT * FROM collaboration_rooms WHERE id = ?", (room_id,)
    ).fetchone()
    if row is None:
        raise not_found("collaboration_room", room_id)
    return _row_to_room(row)


def list_rooms(
    conn: sqlite3.Connection,
    project_id: str | None = None,
    *,
    include_archived: bool = False,
) -> list[CollaborationRoom]:
    clauses: list[str] = []
    values: list[object] = []
    if project_id is not None:
        clauses.append("project_id = ?")
        values.append(project_id.strip())
    if not include_archived:
        clauses.append("status = 'open'")
    where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = conn.execute(
        f"SELECT * FROM collaboration_rooms{where} ORDER BY updated_at DESC", values
    ).fetchall()
    return [_row_to_room(row) for row in rows]


def patch_room(
    conn: sqlite3.Connection, room_id: str, payload: CollaborationRoomPatch
) -> CollaborationRoom:
    existing = get_room(conn, room_id)
    fields = payload.model_fields_set
    name = payload.name.strip() if payload.name is not None else existing.name
    goal_md = payload.goal_md.strip() if payload.goal_md is not None else existing.goal_md
    summary_md = (
        payload.summary_md.strip() if payload.summary_md is not None else existing.summary_md
    )
    status = payload.status.value if payload.status is not None else existing.status.value
    if not fields:
        return existing
    conn.execute(
        "UPDATE collaboration_rooms SET name = ?, goal_md = ?, summary_md = ?, "
        "status = ?, updated_at = ? WHERE id = ?",
        (name, goal_md, summary_md, status, to_iso(utc_now()), room_id),
    )
    return get_room(conn, room_id)


def join_room(
    conn: sqlite3.Connection, room_id: str, payload: CollaborationRoomJoin
) -> CollaborationRoomSync:
    room = get_room(conn, room_id)
    if room.status != CollaborationRoomStatus.OPEN:
        raise invalid("collaboration_room", "An archived room cannot be joined.")
    _assert_session_project(conn, payload.session_id, room.project_id)
    now = to_iso(utc_now())
    conn.execute(
        "INSERT INTO collaboration_room_members "
        "(room_id, session_id, role_label, joined_at, last_seen_at, left_at, metadata_json) "
        "VALUES (?, ?, ?, ?, ?, NULL, '{}') "
        "ON CONFLICT(room_id, session_id) DO UPDATE SET "
        "role_label = excluded.role_label, joined_at = excluded.joined_at, "
        "last_seen_at = excluded.last_seen_at, left_at = NULL",
        (room_id, payload.session_id, payload.role_label.strip(), now, now),
    )
    conn.execute(
        "UPDATE collaboration_rooms SET updated_at = ? WHERE id = ?", (now, room_id)
    )
    return sync_room(conn, room_id)


def leave_room(
    conn: sqlite3.Connection, room_id: str, session_id: str
) -> CollaborationRoomMember:
    get_room(conn, room_id)
    row = conn.execute(
        "SELECT 1 FROM collaboration_room_members WHERE room_id = ? AND session_id = ?",
        (room_id, session_id),
    ).fetchone()
    if row is None:
        raise not_found("collaboration_room_member", f"{room_id}:{session_id}")
    now = to_iso(utc_now())
    conn.execute(
        "UPDATE collaboration_room_members SET left_at = ?, last_seen_at = ? "
        "WHERE room_id = ? AND session_id = ?",
        (now, now, room_id, session_id),
    )
    conn.execute(
        "UPDATE collaboration_rooms SET updated_at = ? WHERE id = ?", (now, room_id)
    )
    members = list_members(conn, room_id, include_left=True)
    return next(member for member in members if member.session_id == session_id)


def _active_membership(conn: sqlite3.Connection, room_id: str, session_id: str) -> None:
    row = conn.execute(
        "SELECT 1 FROM collaboration_room_members "
        "WHERE room_id = ? AND session_id = ? AND left_at IS NULL",
        (room_id, session_id),
    ).fetchone()
    if row is None:
        raise invalid(
            "collaboration_room",
            "Join the collaboration room before posting to it.",
            room_id=room_id,
            session_id=session_id,
        )


def post_message(
    conn: sqlite3.Connection, room_id: str, payload: CollaborationRoomPost
) -> CollaborationRoomMessage:
    room = get_room(conn, room_id)
    if room.status != CollaborationRoomStatus.OPEN:
        raise invalid("collaboration_room", "An archived room cannot receive messages.")
    _assert_session_project(conn, payload.session_id, room.project_id)
    _active_membership(conn, room_id, payload.session_id)
    body = payload.body_md.strip()
    if not body:
        raise invalid("collaboration_room_message", "A room message cannot be blank.")
    now = to_iso(utc_now())
    cursor = conn.execute(
        "INSERT INTO collaboration_room_messages "
        "(room_id, session_id, kind, body_md, created_at, metadata_json) "
        "VALUES (?, ?, ?, ?, ?, '{}')",
        (room_id, payload.session_id, payload.kind.value, body, now),
    )
    conn.execute(
        "UPDATE collaboration_room_members SET last_seen_at = ? "
        "WHERE room_id = ? AND session_id = ?",
        (now, room_id, payload.session_id),
    )
    conn.execute(
        "UPDATE collaboration_rooms SET updated_at = ? WHERE id = ?", (now, room_id)
    )
    return get_message(conn, int(cursor.lastrowid))


def get_message(conn: sqlite3.Connection, message_id: int) -> CollaborationRoomMessage:
    row = conn.execute(
        "SELECT m.*, s.agent_label, s.runtime_id "
        "FROM collaboration_room_messages m "
        "LEFT JOIN agent_sessions s ON s.id = m.session_id WHERE m.id = ?",
        (message_id,),
    ).fetchone()
    if row is None:
        raise not_found("collaboration_room_message", str(message_id))
    return CollaborationRoomMessage(
        id=int(row["id"]),
        room_id=row["room_id"],
        session_id=row["session_id"],
        agent_label=row["agent_label"] or "",
        runtime_id=row["runtime_id"] or "",
        kind=CollaborationMessageKind(row["kind"]),
        body_md=row["body_md"],
        created_at=from_iso(row["created_at"]),
    )


def list_members(
    conn: sqlite3.Connection, room_id: str, *, include_left: bool = False
) -> list[CollaborationRoomMember]:
    get_room(conn, room_id)
    where = "" if include_left else " AND m.left_at IS NULL"
    rows = conn.execute(
        "SELECT m.* FROM collaboration_room_members m "
        f"WHERE m.room_id = ?{where} ORDER BY m.joined_at ASC",
        (room_id,),
    ).fetchall()
    members: list[CollaborationRoomMember] = []
    for row in rows:
        session = coordination.get_session(conn, row["session_id"])
        present = (
            row["left_at"] is None
            and session.status != coordination.AgentSessionStatus.GONE
            and not session.stale
        )
        members.append(
            CollaborationRoomMember(
                room_id=room_id,
                session_id=session.id,
                agent_label=session.agent_label,
                runtime_id=session.runtime_id,
                role_label=row["role_label"] or "",
                task=session.task,
                session_status=session.status,
                stale=session.stale,
                present=present,
                joined_at=from_iso(row["joined_at"]),
                last_seen_at=from_iso(row["last_seen_at"]),
                left_at=from_iso(row["left_at"]) if row["left_at"] else None,
            )
        )
    return members


def list_messages(
    conn: sqlite3.Connection,
    room_id: str,
    *,
    after_message_id: int = 0,
    limit: int = 50,
) -> list[CollaborationRoomMessage]:
    get_room(conn, room_id)
    safe_limit = max(1, min(int(limit), 200))
    if after_message_id > 0:
        rows = conn.execute(
            "SELECT m.*, s.agent_label, s.runtime_id "
            "FROM collaboration_room_messages m "
            "LEFT JOIN agent_sessions s ON s.id = m.session_id "
            "WHERE m.room_id = ? AND m.id > ? ORDER BY m.id ASC LIMIT ?",
            (room_id, after_message_id, safe_limit),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM ("
            " SELECT m.*, s.agent_label, s.runtime_id "
            " FROM collaboration_room_messages m "
            " LEFT JOIN agent_sessions s ON s.id = m.session_id "
            " WHERE m.room_id = ? ORDER BY m.id DESC LIMIT ?"
            ") recent ORDER BY id ASC",
            (room_id, safe_limit),
        ).fetchall()
    return [
        CollaborationRoomMessage(
            id=int(row["id"]),
            room_id=row["room_id"],
            session_id=row["session_id"],
            agent_label=row["agent_label"] or "",
            runtime_id=row["runtime_id"] or "",
            kind=CollaborationMessageKind(row["kind"]),
            body_md=row["body_md"],
            created_at=from_iso(row["created_at"]),
        )
        for row in rows
    ]


def sync_room(
    conn: sqlite3.Connection,
    room_id: str,
    *,
    after_message_id: int = 0,
    limit: int = 50,
) -> CollaborationRoomSync:
    room = get_room(conn, room_id)
    messages = list_messages(
        conn, room_id, after_message_id=after_message_id, limit=limit
    )
    latest = conn.execute(
        "SELECT COALESCE(MAX(id), 0) FROM collaboration_room_messages WHERE room_id = ?",
        (room_id,),
    ).fetchone()[0]
    return CollaborationRoomSync(
        room=room,
        members=list_members(conn, room_id),
        messages=messages,
        latest_message_id=int(latest or 0),
        generated_at=utc_now(),
    )
