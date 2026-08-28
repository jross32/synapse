"""Durable per-thread presence and work-time accounting.

Coordination sessions answer "is this AI connection alive right now?".  This
module answers the longer-lived operator questions:

* Which real ChatGPT/AI conversations belong to the same project/request?
* Which conversation is working, idle, stale, gone, or in error?
* How much actual turn time has each conversation accumulated?
* What is the aggregate time for the whole request when multiple AIs collaborate?

Thread identity survives a coordination-session timeout.  Turn accounting is
append-only and idempotent: finishing the same turn twice never double-counts.

For Synapse-managed browser workers, begin/heartbeat/finish calls are made by
the browser controller itself, so no model cooperation is required.  Manual
ChatGPT tabs can report the same signals through the local browser companion.
Connector-only clients use the same API cooperatively.
"""

from __future__ import annotations

import re
import secrets
import sqlite3
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from .errors import conflict, invalid, not_found
from .time_utils import from_iso, to_iso, utc_now

THREAD_STALE_SECONDS = 120
_TOKEN_RE = re.compile(r"[a-z0-9]{2,}", re.I)


class ThreadStatus(StrEnum):
    ACTIVE = "active"
    IDLE = "idle"
    ERROR = "error"
    GONE = "gone"
    ARCHIVED = "archived"


class ThreadDisplayStatus(StrEnum):
    ACTIVE = "active"
    IDLE = "idle"
    ERROR = "error"
    STALE = "stale"
    GONE = "gone"
    ARCHIVED = "archived"


class ThreadSource(StrEnum):
    CONNECTOR = "connector"
    BROWSER_OBSERVER = "browser_observer"
    MANAGED_BROWSER = "managed_browser"
    CLI = "cli"
    OTHER = "other"


class DurationSource(StrEnum):
    UI_DISPLAY = "ui_display"
    WALL_CLOCK = "wall_clock"
    REPORTED = "reported"
    RECOVERED = "recovered"


class TurnStatus(StrEnum):
    ACTIVE = "active"
    SUCCESS = "success"
    ERROR = "error"
    CANCELLED = "cancelled"


class WorkGroup(BaseModel):
    id: str
    project_id: str
    external_group_key: str = ""
    name: str
    description: str = ""
    status: str = "active"
    created_at: datetime
    updated_at: datetime
    thread_count: int = 0
    active_count: int = 0
    idle_count: int = 0
    error_count: int = 0
    stale_count: int = 0
    gone_count: int = 0
    total_work_seconds: float = 0.0


class AIThread(BaseModel):
    id: str
    work_group_id: str
    project_id: str
    session_id: str | None = None
    runtime_id: str = "chatgpt"
    source: ThreadSource = ThreadSource.CONNECTOR
    external_thread_key: str
    conversation_url: str = ""
    title: str = ""
    description: str = ""
    status: ThreadStatus = ThreadStatus.IDLE
    display_status: ThreadDisplayStatus = ThreadDisplayStatus.IDLE
    stale: bool = False
    current_task: str = ""
    total_work_seconds: float = 0.0
    turn_count: int = 0
    current_turn_started_at: datetime | None = None
    last_activity_at: datetime
    last_seen_at: datetime
    last_error: str = ""
    created_at: datetime
    updated_at: datetime


class ThreadTurn(BaseModel):
    id: str
    thread_id: str
    started_at: datetime
    completed_at: datetime | None = None
    duration_seconds: float | None = None
    duration_source: DurationSource = DurationSource.WALL_CLOCK
    status: TurnStatus = TurnStatus.ACTIVE
    prompt_label: str = ""
    summary_md: str = ""
    error: str = ""


class GroupCandidate(BaseModel):
    id: str
    name: str
    description: str = ""
    score: float
    total_work_seconds: float = 0.0
    thread_count: int = 0
    threads: list[dict[str, Any]] = Field(default_factory=list)


class ThreadBootstrap(BaseModel):
    project_id: str
    external_thread_key: str = Field(min_length=1, max_length=500)
    runtime_id: str = Field(default="chatgpt", max_length=100)
    source: ThreadSource = ThreadSource.CONNECTOR
    conversation_url: str = Field(default="", max_length=4000)
    title: str = Field(default="", max_length=500)
    description: str = Field(default="", max_length=4000)
    current_task: str = Field(default="", max_length=4000)
    session_id: str | None = None
    work_group_id: str | None = None
    create_group_name: str | None = Field(default=None, max_length=500)
    create_group_description: str = Field(default="", max_length=4000)


class ThreadBegin(BaseModel):
    prompt_label: str = Field(default="", max_length=1000)
    current_task: str = Field(default="", max_length=4000)
    observed_started_at: datetime | None = None


class ThreadHeartbeat(BaseModel):
    status: ThreadStatus | None = None
    current_task: str | None = Field(default=None, max_length=4000)
    conversation_url: str | None = Field(default=None, max_length=4000)
    title: str | None = Field(default=None, max_length=500)
    error: str | None = Field(default=None, max_length=8000)


class ThreadFinish(BaseModel):
    turn_id: str
    status: TurnStatus = TurnStatus.SUCCESS
    duration_seconds: float | None = Field(default=None, ge=0, le=604800)
    duration_source: DurationSource = DurationSource.WALL_CLOCK
    summary_md: str = Field(default="", max_length=12000)
    error: str = Field(default="", max_length=8000)
    observed_completed_at: datetime | None = None


class ThreadStateUpdate(BaseModel):
    status: ThreadStatus
    current_task: str | None = Field(default=None, max_length=4000)
    error: str | None = Field(default=None, max_length=8000)


class BrowserObservation(BaseModel):
    external_thread_key: str = Field(min_length=1, max_length=500)
    runtime_id: str = Field(default="chatgpt", max_length=100)
    browser_tab_id: str = Field(default="", max_length=100)
    conversation_url: str = Field(default="", max_length=4000)
    title: str = Field(default="", max_length=500)
    status: ThreadStatus = ThreadStatus.IDLE
    current_task: str = Field(default="", max_length=4000)
    generation_started_at: datetime | None = None
    last_duration_seconds: float | None = Field(default=None, ge=0, le=604800)
    error: str = Field(default="", max_length=8000)
    observed_at: datetime | None = None


class BrowserObservationView(BaseModel):
    external_thread_key: str
    runtime_id: str
    browser_tab_id: str = ""
    conversation_url: str = ""
    title: str = ""
    status: ThreadDisplayStatus
    current_task: str = ""
    generation_started_at: datetime | None = None
    last_duration_seconds: float | None = None
    last_error: str = ""
    last_seen_at: datetime
    tracked_thread_id: str | None = None


def _new_id() -> str:
    return secrets.token_hex(6)


def _clean(value: str | None) -> str:
    return (value or "").strip()


def _tokens(*values: str) -> set[str]:
    stop = {
        "the", "and", "for", "with", "from", "this", "that", "into", "work",
        "project", "app", "build", "fix", "continue", "new", "ai", "chatgpt",
    }
    return {
        token.lower()
        for value in values
        for token in _TOKEN_RE.findall(value or "")
        if token.lower() not in stop
    }


def _similarity(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def _display_status(row: sqlite3.Row, *, now: datetime | None = None) -> tuple[ThreadDisplayStatus, bool]:
    status = ThreadStatus(row["status"])
    if status != ThreadStatus.ACTIVE:
        return ThreadDisplayStatus(status.value), False
    ref = now or utc_now()
    stale = (ref - from_iso(row["last_seen_at"])) > timedelta(seconds=THREAD_STALE_SECONDS)
    return (ThreadDisplayStatus.STALE if stale else ThreadDisplayStatus.ACTIVE), stale


def _row_to_thread(row: sqlite3.Row, *, now: datetime | None = None) -> AIThread:
    display, stale = _display_status(row, now=now)
    return AIThread(
        id=row["id"],
        work_group_id=row["work_group_id"],
        project_id=row["project_id"],
        session_id=row["session_id"],
        runtime_id=row["runtime_id"] or "chatgpt",
        source=ThreadSource(row["source"]),
        external_thread_key=row["external_thread_key"],
        conversation_url=row["conversation_url"] or "",
        title=row["title"] or "",
        description=row["description"] or "",
        status=ThreadStatus(row["status"]),
        display_status=display,
        stale=stale,
        current_task=row["current_task"] or "",
        total_work_seconds=float(row["total_work_seconds"] or 0),
        turn_count=int(row["turn_count"] or 0),
        current_turn_started_at=(
            from_iso(row["current_turn_started_at"])
            if row["current_turn_started_at"]
            else None
        ),
        last_activity_at=from_iso(row["last_activity_at"]),
        last_seen_at=from_iso(row["last_seen_at"]),
        last_error=row["last_error"] or "",
        created_at=from_iso(row["created_at"]),
        updated_at=from_iso(row["updated_at"]),
    )


def _observation_display_status(
    row: sqlite3.Row, *, now: datetime | None = None
) -> ThreadDisplayStatus:
    status = str(row["status"] or "idle")
    if status == "active":
        ref = now or utc_now()
        if (ref - from_iso(row["last_seen_at"])) > timedelta(seconds=THREAD_STALE_SECONDS):
            return ThreadDisplayStatus.STALE
    return ThreadDisplayStatus(status)


def _row_to_observation(
    conn: sqlite3.Connection, row: sqlite3.Row, *, now: datetime | None = None
) -> BrowserObservationView:
    tracked = conn.execute(
        "SELECT id FROM ai_threads WHERE runtime_id = ? AND external_thread_key = ?",
        (row["runtime_id"], row["external_thread_key"]),
    ).fetchone()
    return BrowserObservationView(
        external_thread_key=row["external_thread_key"],
        runtime_id=row["runtime_id"] or "chatgpt",
        browser_tab_id=row["browser_tab_id"] or "",
        conversation_url=row["conversation_url"] or "",
        title=row["title"] or "",
        status=_observation_display_status(row, now=now),
        current_task=row["current_task"] or "",
        generation_started_at=(
            from_iso(row["generation_started_at"]) if row["generation_started_at"] else None
        ),
        last_duration_seconds=(
            float(row["last_duration_seconds"])
            if row["last_duration_seconds"] is not None
            else None
        ),
        last_error=row["last_error"] or "",
        last_seen_at=from_iso(row["last_seen_at"]),
        tracked_thread_id=str(tracked["id"]) if tracked is not None else None,
    )


def _row_to_turn(row: sqlite3.Row) -> ThreadTurn:
    return ThreadTurn(
        id=row["id"],
        thread_id=row["thread_id"],
        started_at=from_iso(row["started_at"]),
        completed_at=from_iso(row["completed_at"]) if row["completed_at"] else None,
        duration_seconds=(
            float(row["duration_seconds"]) if row["duration_seconds"] is not None else None
        ),
        duration_source=DurationSource(row["duration_source"]),
        status=TurnStatus(row["status"]),
        prompt_label=row["prompt_label"] or "",
        summary_md=row["summary_md"] or "",
        error=row["error"] or "",
    )


def get_thread(conn: sqlite3.Connection, thread_id: str) -> AIThread:
    row = conn.execute("SELECT * FROM ai_threads WHERE id = ?", (thread_id,)).fetchone()
    if row is None:
        raise not_found("ai_thread", thread_id)
    return _row_to_thread(row)


def get_thread_by_external_key(
    conn: sqlite3.Connection, runtime_id: str, external_thread_key: str
) -> AIThread | None:
    row = conn.execute(
        "SELECT * FROM ai_threads WHERE runtime_id = ? AND external_thread_key = ?",
        (_clean(runtime_id) or "chatgpt", _clean(external_thread_key)),
    ).fetchone()
    return _row_to_thread(row) if row is not None else None


def _group_rows(conn: sqlite3.Connection, project_id: str) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM ai_work_groups WHERE project_id = ? AND status != 'archived' "
        "ORDER BY updated_at DESC",
        (project_id,),
    ).fetchall()


def suggest_groups(
    conn: sqlite3.Connection,
    project_id: str,
    *,
    title: str = "",
    description: str = "",
    current_task: str = "",
    limit: int = 8,
) -> list[GroupCandidate]:
    needle = _tokens(title, description, current_task)
    candidates: list[GroupCandidate] = []
    for row in _group_rows(conn, project_id):
        group_threads = list_threads(conn, work_group_id=row["id"], include_archived=False)
        thread_text = " ".join(
            f"{item.title} {item.description} {item.current_task}" for item in group_threads[:8]
        )
        score = _similarity(
            needle,
            _tokens(row["name"] or "", row["description"] or "", thread_text),
        )
        candidates.append(
            GroupCandidate(
                id=row["id"],
                name=row["name"],
                description=row["description"] or "",
                score=round(score, 3),
                total_work_seconds=round(sum(t.total_work_seconds for t in group_threads), 1),
                thread_count=len(group_threads),
                threads=[
                    {
                        "id": t.id,
                        "title": t.title,
                        "description": t.description,
                        "current_task": t.current_task,
                        "display_status": t.display_status.value,
                        "total_work_seconds": t.total_work_seconds,
                    }
                    for t in sorted(
                        group_threads, key=lambda item: item.total_work_seconds, reverse=True
                    )[:6]
                ],
            )
        )
    candidates.sort(key=lambda item: (item.score, item.total_work_seconds), reverse=True)
    return candidates[: max(1, min(limit, 25))]


def create_group(
    conn: sqlite3.Connection,
    project_id: str,
    *,
    name: str,
    description: str = "",
    external_group_key: str = "",
) -> WorkGroup:
    group_id = _new_id()
    now = to_iso(utc_now())
    clean_name = _clean(name)
    if not clean_name:
        raise invalid("ai_work_group", "Group name is required.")
    conn.execute(
        "INSERT INTO ai_work_groups "
        "(id, project_id, external_group_key, name, description, status, created_at, updated_at, metadata_json) "
        "VALUES (?, ?, ?, ?, ?, 'active', ?, ?, '{}')",
        (group_id, project_id, _clean(external_group_key), clean_name, _clean(description), now, now),
    )
    return get_group(conn, group_id)


def ensure_external_group(
    conn: sqlite3.Connection,
    project_id: str,
    *,
    external_group_key: str,
    name: str,
    description: str = "",
) -> WorkGroup:
    """Get/create a stable project/request group owned by another Synapse primitive.

    Managed ChatGPT workers use a squad-prefixed key so every worker in the same
    squad contributes to one request total without semantic guessing.
    """

    key = _clean(external_group_key)
    if not key:
        return create_group(conn, project_id, name=name, description=description)
    row = conn.execute(
        "SELECT id FROM ai_work_groups WHERE project_id = ? AND external_group_key = ?",
        (project_id, key),
    ).fetchone()
    if row is not None:
        group = get_group(conn, str(row["id"]))
        clean_name = _clean(name)
        clean_description = _clean(description)
        if clean_name != group.name or clean_description != group.description:
            now = to_iso(utc_now())
            conn.execute(
                "UPDATE ai_work_groups SET name = ?, description = ?, updated_at = ? WHERE id = ?",
                (clean_name or group.name, clean_description, now, group.id),
            )
            group = get_group(conn, group.id)
        return group
    return create_group(
        conn,
        project_id,
        name=name,
        description=description,
        external_group_key=key,
    )


def get_group(conn: sqlite3.Connection, group_id: str) -> WorkGroup:
    row = conn.execute("SELECT * FROM ai_work_groups WHERE id = ?", (group_id,)).fetchone()
    if row is None:
        raise not_found("ai_work_group", group_id)
    threads = list_threads(conn, work_group_id=group_id, include_archived=False)
    counts = {status.value: 0 for status in ThreadDisplayStatus}
    for thread in threads:
        counts[thread.display_status.value] += 1
    return WorkGroup(
        id=row["id"],
        project_id=row["project_id"],
        external_group_key=row["external_group_key"] or "",
        name=row["name"],
        description=row["description"] or "",
        status=row["status"],
        created_at=from_iso(row["created_at"]),
        updated_at=from_iso(row["updated_at"]),
        thread_count=len(threads),
        active_count=counts["active"],
        idle_count=counts["idle"],
        error_count=counts["error"],
        stale_count=counts["stale"],
        gone_count=counts["gone"],
        total_work_seconds=round(sum(t.total_work_seconds for t in threads), 1),
    )


def list_groups(
    conn: sqlite3.Connection,
    *,
    project_id: str | None = None,
    include_archived: bool = False,
) -> list[WorkGroup]:
    clauses: list[str] = []
    values: list[object] = []
    if project_id:
        clauses.append("project_id = ?")
        values.append(project_id)
    if not include_archived:
        clauses.append("status != 'archived'")
    where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = conn.execute(
        f"SELECT id FROM ai_work_groups{where} ORDER BY updated_at DESC", values
    ).fetchall()
    groups = [get_group(conn, row["id"]) for row in rows]
    groups.sort(
        key=lambda item: (
            item.active_count > 0,
            item.stale_count == 0,
            item.total_work_seconds,
            item.updated_at,
        ),
        reverse=True,
    )
    return groups


def list_threads(
    conn: sqlite3.Connection,
    *,
    work_group_id: str | None = None,
    project_id: str | None = None,
    include_archived: bool = False,
) -> list[AIThread]:
    clauses: list[str] = []
    values: list[object] = []
    if work_group_id:
        clauses.append("work_group_id = ?")
        values.append(work_group_id)
    if project_id:
        clauses.append("project_id = ?")
        values.append(project_id)
    if not include_archived:
        clauses.append("status != 'archived'")
    where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = conn.execute(
        f"SELECT * FROM ai_threads{where} "
        "ORDER BY total_work_seconds DESC, updated_at DESC",
        values,
    ).fetchall()
    now = utc_now()
    return [_row_to_thread(row, now=now) for row in rows]


def bootstrap_thread(
    conn: sqlite3.Connection, payload: ThreadBootstrap
) -> tuple[AIThread | None, list[GroupCandidate], bool]:
    """Resolve/create durable thread identity.

    Returns (thread, candidates, needs_group_decision). Existing external keys
    always resume directly. New keys without an explicit group return candidate
    groups and require the caller to choose join-vs-new deliberately.
    """

    existing = get_thread_by_external_key(
        conn, payload.runtime_id, payload.external_thread_key
    )
    now = to_iso(utc_now())
    if existing is not None:
        if existing.project_id != payload.project_id:
            raise conflict(
                "ai_thread",
                "This external thread key is already bound to another Synapse project.",
                thread_id=existing.id,
                existing_project_id=existing.project_id,
                requested_project_id=payload.project_id,
            )
        conn.execute(
            "UPDATE ai_threads SET session_id = COALESCE(?, session_id), "
            "conversation_url = CASE WHEN ? != '' THEN ? ELSE conversation_url END, "
            "title = CASE WHEN ? != '' THEN ? ELSE title END, "
            "description = CASE WHEN ? != '' THEN ? ELSE description END, "
            "current_task = CASE WHEN ? != '' THEN ? ELSE current_task END, "
            "source = ?, last_seen_at = ?, updated_at = ? WHERE id = ?",
            (
                payload.session_id,
                _clean(payload.conversation_url), _clean(payload.conversation_url),
                _clean(payload.title), _clean(payload.title),
                _clean(payload.description), _clean(payload.description),
                _clean(payload.current_task), _clean(payload.current_task),
                payload.source.value,
                now, now, existing.id,
            ),
        )
        return get_thread(conn, existing.id), [], False

    group_id = _clean(payload.work_group_id)
    if not group_id and payload.create_group_name:
        group = create_group(
            conn,
            payload.project_id,
            name=payload.create_group_name,
            description=payload.create_group_description or payload.description,
        )
        group_id = group.id

    if not group_id:
        return (
            None,
            suggest_groups(
                conn,
                payload.project_id,
                title=payload.title,
                description=payload.description,
                current_task=payload.current_task,
            ),
            True,
        )

    group = get_group(conn, group_id)
    if group.project_id != payload.project_id:
        raise conflict(
            "ai_thread",
            "A thread can only join a work group inside the same Synapse project.",
            group_project_id=group.project_id,
            requested_project_id=payload.project_id,
        )

    thread_id = _new_id()
    conn.execute(
        "INSERT INTO ai_threads "
        "(id, work_group_id, project_id, session_id, runtime_id, source, "
        " external_thread_key, conversation_url, title, description, status, current_task, "
        " total_work_seconds, turn_count, current_turn_started_at, last_activity_at, "
        " last_seen_at, last_error, created_at, updated_at, metadata_json) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'idle', ?, 0, 0, NULL, ?, ?, '', ?, ?, '{}')",
        (
            thread_id,
            group_id,
            payload.project_id,
            payload.session_id,
            _clean(payload.runtime_id) or "chatgpt",
            payload.source.value,
            _clean(payload.external_thread_key),
            _clean(payload.conversation_url),
            _clean(payload.title),
            _clean(payload.description),
            _clean(payload.current_task),
            now,
            now,
            now,
            now,
        ),
    )
    conn.execute(
        "UPDATE ai_work_groups SET updated_at = ? WHERE id = ?",
        (now, group_id),
    )
    observation = conn.execute(
        "SELECT * FROM chatgpt_tab_observations WHERE runtime_id = ? "
        "AND external_thread_key = ?",
        (_clean(payload.runtime_id) or "chatgpt", _clean(payload.external_thread_key)),
    ).fetchone()
    if observation is not None:
        observed_status = str(observation["status"] or "idle")
        if observed_status == "active":
            begin_turn(
                conn,
                thread_id,
                ThreadBegin(
                    current_task=observation["current_task"] or payload.current_task,
                    observed_started_at=(
                        from_iso(observation["generation_started_at"])
                        if observation["generation_started_at"]
                        else None
                    ),
                ),
            )
        elif observed_status == "error":
            set_thread_state(
                conn,
                thread_id,
                ThreadStateUpdate(
                    status=ThreadStatus.ERROR,
                    current_task=observation["current_task"] or payload.current_task,
                    error=observation["last_error"] or "",
                ),
            )
        elif observed_status == "gone":
            set_thread_state(
                conn, thread_id, ThreadStateUpdate(status=ThreadStatus.GONE)
            )
    return get_thread(conn, thread_id), [], False


def begin_turn(
    conn: sqlite3.Connection, thread_id: str, payload: ThreadBegin
) -> ThreadTurn:
    thread = get_thread(conn, thread_id)
    if thread.status == ThreadStatus.ARCHIVED:
        raise conflict("ai_thread", "Archived threads cannot start new work.", thread_id=thread_id)

    open_row = conn.execute(
        "SELECT * FROM ai_thread_turns WHERE thread_id = ? AND status = 'active' "
        "ORDER BY started_at DESC LIMIT 1",
        (thread_id,),
    ).fetchone()
    if open_row is not None:
        # Idempotent begin: browser mutation observers can fire more than once.
        return _row_to_turn(open_row)

    turn_id = _new_id()
    started = payload.observed_started_at or utc_now()
    started_iso = to_iso(started)
    now = to_iso(utc_now())
    conn.execute(
        "INSERT INTO ai_thread_turns "
        "(id, thread_id, started_at, completed_at, duration_seconds, duration_source, "
        " status, prompt_label, summary_md, error, created_at, metadata_json) "
        "VALUES (?, ?, ?, NULL, NULL, 'wall_clock', 'active', ?, '', '', ?, '{}')",
        (turn_id, thread_id, started_iso, _clean(payload.prompt_label), now),
    )
    current_task = _clean(payload.current_task) or thread.current_task
    conn.execute(
        "UPDATE ai_threads SET status = 'active', current_task = ?, "
        "current_turn_started_at = ?, last_activity_at = ?, last_seen_at = ?, "
        "last_error = '', updated_at = ? WHERE id = ?",
        (current_task, started_iso, now, now, now, thread_id),
    )
    conn.execute(
        "UPDATE ai_work_groups SET status = 'active', updated_at = ? WHERE id = ?",
        (now, thread.work_group_id),
    )
    return _row_to_turn(
        conn.execute("SELECT * FROM ai_thread_turns WHERE id = ?", (turn_id,)).fetchone()
    )


def heartbeat_thread(
    conn: sqlite3.Connection, thread_id: str, payload: ThreadHeartbeat
) -> AIThread:
    thread = get_thread(conn, thread_id)
    now = to_iso(utc_now())
    status = payload.status.value if payload.status is not None else thread.status.value
    fields = payload.model_fields_set
    conn.execute(
        "UPDATE ai_threads SET status = ?, "
        "current_task = ?, conversation_url = ?, title = ?, "
        "last_error = ?, last_seen_at = ?, updated_at = ? WHERE id = ?",
        (
            status,
            payload.current_task if "current_task" in fields else thread.current_task,
            payload.conversation_url if "conversation_url" in fields else thread.conversation_url,
            payload.title if "title" in fields else thread.title,
            payload.error if "error" in fields else thread.last_error,
            now,
            now,
            thread_id,
        ),
    )
    return get_thread(conn, thread_id)


def finish_turn(
    conn: sqlite3.Connection, thread_id: str, payload: ThreadFinish
) -> tuple[ThreadTurn, AIThread]:
    thread = get_thread(conn, thread_id)
    row = conn.execute(
        "SELECT * FROM ai_thread_turns WHERE id = ? AND thread_id = ?",
        (payload.turn_id, thread_id),
    ).fetchone()
    if row is None:
        raise not_found("ai_thread_turn", payload.turn_id)
    existing = _row_to_turn(row)
    if existing.status != TurnStatus.ACTIVE:
        # Idempotent finalization: never add its duration twice.
        return existing, get_thread(conn, thread_id)

    completed = payload.observed_completed_at or utc_now()
    elapsed = max(0.0, (completed - existing.started_at).total_seconds())
    duration = float(payload.duration_seconds) if payload.duration_seconds is not None else elapsed
    duration = round(max(0.0, duration), 3)
    now = to_iso(utc_now())
    completed_iso = to_iso(completed)
    conn.execute(
        "UPDATE ai_thread_turns SET completed_at = ?, duration_seconds = ?, "
        "duration_source = ?, status = ?, summary_md = ?, error = ? WHERE id = ?",
        (
            completed_iso,
            duration,
            payload.duration_source.value,
            payload.status.value,
            _clean(payload.summary_md),
            _clean(payload.error),
            payload.turn_id,
        ),
    )
    next_status = "error" if payload.status == TurnStatus.ERROR else "idle"
    last_error = _clean(payload.error) if payload.status == TurnStatus.ERROR else ""
    conn.execute(
        "UPDATE ai_threads SET status = ?, total_work_seconds = total_work_seconds + ?, "
        "turn_count = turn_count + 1, current_turn_started_at = NULL, "
        "last_activity_at = ?, last_seen_at = ?, last_error = ?, updated_at = ? WHERE id = ?",
        (next_status, duration, completed_iso, now, last_error, now, thread_id),
    )
    group_threads = list_threads(conn, work_group_id=thread.work_group_id, include_archived=False)
    group_status = "active" if any(t.display_status == ThreadDisplayStatus.ACTIVE for t in group_threads) else (
        "error" if any(t.display_status == ThreadDisplayStatus.ERROR for t in group_threads) else "idle"
    )
    conn.execute(
        "UPDATE ai_work_groups SET status = ?, updated_at = ? WHERE id = ?",
        (group_status, now, thread.work_group_id),
    )
    updated_turn = _row_to_turn(
        conn.execute("SELECT * FROM ai_thread_turns WHERE id = ?", (payload.turn_id,)).fetchone()
    )
    return updated_turn, get_thread(conn, thread_id)


def set_thread_state(
    conn: sqlite3.Connection, thread_id: str, payload: ThreadStateUpdate
) -> AIThread:
    thread = get_thread(conn, thread_id)
    now = to_iso(utc_now())
    current_task = (
        payload.current_task
        if "current_task" in payload.model_fields_set
        else thread.current_task
    )
    error = payload.error if "error" in payload.model_fields_set else thread.last_error
    if payload.status != ThreadStatus.ERROR and "error" not in payload.model_fields_set:
        error = ""
    conn.execute(
        "UPDATE ai_threads SET status = ?, current_task = ?, last_error = ?, "
        "last_seen_at = ?, updated_at = ? WHERE id = ?",
        (payload.status.value, current_task, error, now, now, thread_id),
    )
    return get_thread(conn, thread_id)


def list_browser_observations(
    conn: sqlite3.Connection, *, include_gone: bool = False
) -> list[BrowserObservationView]:
    where = "" if include_gone else " WHERE status != 'gone'"
    rows = conn.execute(
        f"SELECT * FROM chatgpt_tab_observations{where} ORDER BY last_seen_at DESC"
    ).fetchall()
    now = utc_now()
    return [_row_to_observation(conn, row, now=now) for row in rows]


def observe_browser_thread(
    conn: sqlite3.Connection, payload: BrowserObservation
) -> tuple[BrowserObservationView, AIThread | None]:
    """Upsert one PC-local ChatGPT tab signal and mirror it into a tracked thread.

    The browser is authoritative for generating-vs-idle state when available.
    A transition active -> idle finalizes an open turn automatically.  The UI's
    own Worked for value wins when supplied; otherwise wall-clock elapsed time
    is used.  Unknown/unassigned tabs remain useful observations until a later
    bootstrap binds the same external key to a Synapse project/group.
    """

    now_dt = payload.observed_at or utc_now()
    now = to_iso(now_dt)
    key = _clean(payload.external_thread_key)
    runtime = _clean(payload.runtime_id) or "chatgpt"
    conn.execute(
        "INSERT INTO chatgpt_tab_observations "
        "(external_thread_key, runtime_id, browser_tab_id, conversation_url, title, "
        " status, current_task, generation_started_at, last_duration_seconds, "
        " last_error, last_seen_at, updated_at, metadata_json) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '{}') "
        "ON CONFLICT(external_thread_key) DO UPDATE SET "
        "runtime_id=excluded.runtime_id, browser_tab_id=excluded.browser_tab_id, "
        "conversation_url=excluded.conversation_url, title=excluded.title, "
        "status=excluded.status, current_task=excluded.current_task, "
        "generation_started_at=excluded.generation_started_at, "
        "last_duration_seconds=excluded.last_duration_seconds, "
        "last_error=excluded.last_error, last_seen_at=excluded.last_seen_at, "
        "updated_at=excluded.updated_at",
        (
            key,
            runtime,
            _clean(payload.browser_tab_id),
            _clean(payload.conversation_url),
            _clean(payload.title),
            payload.status.value,
            _clean(payload.current_task),
            to_iso(payload.generation_started_at) if payload.generation_started_at else None,
            payload.last_duration_seconds,
            _clean(payload.error),
            now,
            now,
        ),
    )

    tracked = get_thread_by_external_key(conn, runtime, key)
    if tracked is not None:
        common = ThreadHeartbeat(
            status=payload.status,
            current_task=payload.current_task,
            conversation_url=payload.conversation_url,
            title=payload.title,
            error=payload.error,
        )
        if payload.status == ThreadStatus.ACTIVE:
            begin_turn(
                conn,
                tracked.id,
                ThreadBegin(
                    current_task=payload.current_task,
                    observed_started_at=payload.generation_started_at,
                ),
            )
            tracked = heartbeat_thread(conn, tracked.id, common)
        elif payload.status in {ThreadStatus.IDLE, ThreadStatus.ERROR}:
            open_row = conn.execute(
                "SELECT id FROM ai_thread_turns WHERE thread_id = ? AND status = 'active' "
                "ORDER BY started_at DESC LIMIT 1",
                (tracked.id,),
            ).fetchone()
            if open_row is not None:
                turn_status = (
                    TurnStatus.ERROR
                    if payload.status == ThreadStatus.ERROR
                    else TurnStatus.SUCCESS
                )
                _, tracked = finish_turn(
                    conn,
                    tracked.id,
                    ThreadFinish(
                        turn_id=str(open_row["id"]),
                        status=turn_status,
                        duration_seconds=payload.last_duration_seconds,
                        duration_source=(
                            DurationSource.UI_DISPLAY
                            if payload.last_duration_seconds is not None
                            else DurationSource.WALL_CLOCK
                        ),
                        error=payload.error,
                        observed_completed_at=now_dt,
                    ),
                )
            else:
                tracked = heartbeat_thread(conn, tracked.id, common)
        elif payload.status == ThreadStatus.GONE:
            tracked = set_thread_state(
                conn, tracked.id, ThreadStateUpdate(status=ThreadStatus.GONE)
            )

    row = conn.execute(
        "SELECT * FROM chatgpt_tab_observations WHERE external_thread_key = ?",
        (key,),
    ).fetchone()
    return _row_to_observation(conn, row), tracked


def overview(conn: sqlite3.Connection) -> dict[str, Any]:
    groups = list_groups(conn)
    threads = list_threads(conn)
    observations = list_browser_observations(conn)
    unassigned = [item for item in observations if item.tracked_thread_id is None]
    status_counts = {status.value: 0 for status in ThreadDisplayStatus}
    for thread in threads:
        status_counts[thread.display_status.value] += 1
    return {
        "generated_at": to_iso(utc_now()),
        "stale_after_seconds": THREAD_STALE_SECONDS,
        "counts": {
            "groups": len(groups),
            "threads": len(threads),
            "tracked_in_progress": status_counts["active"],
            "browser_unassigned": len(unassigned),
            "browser_unassigned_active": sum(
                1 for item in unassigned if item.status == ThreadDisplayStatus.ACTIVE
            ),
            "in_progress": status_counts["active"]
            + sum(1 for item in unassigned if item.status == ThreadDisplayStatus.ACTIVE),
            **status_counts,
        },
        "total_work_seconds": round(sum(thread.total_work_seconds for thread in threads), 1),
        "unassigned_browser_threads": [
            item.model_dump(mode="json") for item in unassigned
        ],
        "groups": [
            {
                **group.model_dump(mode="json"),
                "threads": [
                    item.model_dump(mode="json")
                    for item in list_threads(conn, work_group_id=group.id)
                ],
            }
            for group in groups
        ],
    }


def list_turns(
    conn: sqlite3.Connection, thread_id: str, *, limit: int = 100
) -> list[ThreadTurn]:
    get_thread(conn, thread_id)
    rows = conn.execute(
        "SELECT * FROM ai_thread_turns WHERE thread_id = ? "
        "ORDER BY started_at DESC LIMIT ?",
        (thread_id, max(1, min(limit, 500))),
    ).fetchall()
    return [_row_to_turn(row) for row in rows]
