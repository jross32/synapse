"""Durable thread-first workspace records for the chat-style coder surface.

The UI may change shape, but the durable objects here are the stable contract:
threads, messages, runtime switches, review passes, and concrete linked runs.
The benchmark layer links to these records rather than to a specific renderer.
"""

from __future__ import annotations

import json
import secrets
import sqlite3
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from .errors import not_found
from .time_utils import from_iso, to_iso, utc_now


class CoderThreadStatus(str, Enum):
    ACTIVE = "active"
    ARCHIVED = "archived"
    CLOSED = "closed"


class CoderMessageRole(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    REVIEWER = "reviewer"


class CoderReviewPassStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class CoderRunStatus(str, Enum):
    CREATED = "created"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CRASHED = "crashed"
    STOPPED = "stopped"
    UNAVAILABLE = "unavailable"


class CoderWorkspacePreferences(BaseModel):
    advanced_terminal_enabled: bool = False
    raw_pty_enabled: bool = True
    updated_at: datetime = Field(default_factory=utc_now)


class CoderThread(BaseModel):
    id: str
    project_id: str
    title: str
    status: CoderThreadStatus = CoderThreadStatus.ACTIVE
    active_runtime_id: str | None = None
    active_provider: str | None = None
    active_model: str | None = None
    workspace_context_mode: str = "project"
    pinned: bool = False
    archived: bool = False
    thread_kind: str = "chat"
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    last_message_at: datetime | None = None
    last_run_at: datetime | None = None


class CoderThreadSummary(BaseModel):
    thread: CoderThread
    message_count: int = 0
    review_pass_count: int = 0
    run_count: int = 0
    last_message_preview: str = ""


class CoderMessage(BaseModel):
    id: str
    thread_id: str
    role: CoderMessageRole
    content_md: str = ""
    runtime_id: str | None = None
    provider: str | None = None
    model: str | None = None
    coder_run_id: str | None = None
    artifact_ids: list[str] = Field(default_factory=list)
    usage_summary: dict[str, Any] = Field(default_factory=dict)
    benchmark_attempt_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)


class CoderRuntimeSwitch(BaseModel):
    id: str
    thread_id: str
    from_runtime_id: str | None = None
    from_provider: str | None = None
    from_model: str | None = None
    to_runtime_id: str | None = None
    to_provider: str | None = None
    to_model: str | None = None
    reason: str = ""
    created_at: datetime = Field(default_factory=utc_now)


class CoderReviewPass(BaseModel):
    id: str
    thread_id: str
    requested_runtime_id: str | None = None
    requested_provider: str | None = None
    requested_model: str | None = None
    status: CoderReviewPassStatus = CoderReviewPassStatus.PENDING
    title: str = "Review pass"
    summary_md: str = ""
    coder_run_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class CoderRun(BaseModel):
    id: str
    thread_id: str | None = None
    message_id: str | None = None
    review_pass_id: str | None = None
    runtime_id: str = ""
    provider: str = ""
    model: str = ""
    surface_kind: str
    surface_profile_version: str = ""
    pty_session_id: str | None = None
    project_id: str | None = None
    benchmark_attempt_id: str | None = None
    status: CoderRunStatus = CoderRunStatus.CREATED
    started_at: datetime = Field(default_factory=utc_now)
    first_input_at: datetime | None = None
    first_output_at: datetime | None = None
    ended_at: datetime | None = None
    exit_code: int | None = None
    input_event_count: int = 0
    output_event_count: int = 0
    used_any_input: bool = False
    used_any_output: bool = False
    crash_reason: str | None = None
    workspace_context_mode: str = "project"
    attachments_count: int = 0
    hidden_context_hash: str | None = None
    workspace_overhead_bytes: int = 0
    context_items_injected: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)


class CoderWorkspaceContext(BaseModel):
    thread: CoderThread
    recent_messages: list[CoderMessage] = Field(default_factory=list)
    review_passes: list[CoderReviewPass] = Field(default_factory=list)
    linked_runs: list[CoderRun] = Field(default_factory=list)
    files_count: int = 0
    recent_file_ids: list[str] = Field(default_factory=list)
    records_summary: dict[str, int] = Field(default_factory=dict)
    available_actions: list[str] = Field(default_factory=list)
    preferences: CoderWorkspacePreferences = Field(default_factory=CoderWorkspacePreferences)


class CoderThreadDetail(BaseModel):
    thread: CoderThread
    messages: list[CoderMessage] = Field(default_factory=list)
    runtime_switches: list[CoderRuntimeSwitch] = Field(default_factory=list)
    review_passes: list[CoderReviewPass] = Field(default_factory=list)
    linked_runs: list[CoderRun] = Field(default_factory=list)


class CoderThreadCreate(BaseModel):
    title: str = "New thread"
    active_runtime_id: str | None = None
    active_provider: str | None = None
    active_model: str | None = None
    workspace_context_mode: str = "project"
    pinned: bool = False
    archived: bool = False
    thread_kind: str = "chat"
    metadata: dict[str, Any] = Field(default_factory=dict)


class CoderThreadUpdate(BaseModel):
    title: str | None = None
    status: CoderThreadStatus | None = None
    active_runtime_id: str | None = None
    active_provider: str | None = None
    active_model: str | None = None
    workspace_context_mode: str | None = None
    pinned: bool | None = None
    archived: bool | None = None
    metadata: dict[str, Any] | None = None


class CoderMessageCreate(BaseModel):
    role: CoderMessageRole = CoderMessageRole.USER
    content_md: str
    runtime_id: str | None = None
    provider: str | None = None
    model: str | None = None
    coder_run_id: str | None = None
    artifact_ids: list[str] = Field(default_factory=list)
    usage_summary: dict[str, Any] = Field(default_factory=dict)
    benchmark_attempt_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class CoderRuntimeSwitchRequest(BaseModel):
    runtime_id: str
    provider: str | None = None
    model: str | None = None
    reason: str = ""


class CoderReviewPassCreate(BaseModel):
    requested_runtime_id: str | None = None
    requested_provider: str | None = None
    requested_model: str | None = None
    title: str = "Review pass"
    summary_md: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class CoderWorkspacePreferencesUpdate(BaseModel):
    advanced_terminal_enabled: bool | None = None
    raw_pty_enabled: bool | None = None


class CoderDispatchMessageRequest(BaseModel):
    content_md: str
    runtime_id: str | None = None
    provider: str | None = None
    model: str | None = None
    workspace_context_mode: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class CoderLaunchReviewPassRequest(BaseModel):
    runtime_id: str | None = None
    provider: str | None = None
    model: str | None = None
    prompt_md: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class CoderRunCreate(BaseModel):
    thread_id: str | None = None
    message_id: str | None = None
    review_pass_id: str | None = None
    runtime_id: str
    provider: str = ""
    model: str = ""
    surface_kind: str
    surface_profile_version: str = ""
    pty_session_id: str | None = None
    project_id: str | None = None
    benchmark_attempt_id: str | None = None
    workspace_context_mode: str = "project"
    attachments_count: int = 0
    hidden_context_hash: str | None = None
    workspace_overhead_bytes: int = 0
    context_items_injected: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)


def _new_id() -> str:
    return secrets.token_hex(6)


def _dumps(payload: Any) -> str:
    return json.dumps(payload)


def _loads_dict(payload: str | None) -> dict[str, Any]:
    if not payload:
        return {}
    try:
        decoded = json.loads(payload)
    except json.JSONDecodeError:
        return {}
    return decoded if isinstance(decoded, dict) else {}


def _loads_list(payload: str | None) -> list[Any]:
    if not payload:
        return []
    try:
        decoded = json.loads(payload)
    except json.JSONDecodeError:
        return []
    return decoded if isinstance(decoded, list) else []


def _as_bool(value: Any) -> bool:
    return bool(int(value)) if isinstance(value, (int, str)) else bool(value)


def _row_to_thread(row: sqlite3.Row) -> CoderThread:
    return CoderThread(
        id=row["id"],
        project_id=row["project_id"],
        title=row["title"],
        status=CoderThreadStatus(row["status"]),
        active_runtime_id=row["active_runtime_id"],
        active_provider=row["active_provider"],
        active_model=row["active_model"],
        workspace_context_mode=row["workspace_context_mode"] or "project",
        pinned=_as_bool(row["pinned"]),
        archived=_as_bool(row["archived"]),
        thread_kind=row["thread_kind"] or "chat",
        metadata=_loads_dict(row["metadata_json"]),
        created_at=from_iso(row["created_at"]),
        updated_at=from_iso(row["updated_at"]),
        last_message_at=from_iso(row["last_message_at"]) if row["last_message_at"] else None,
        last_run_at=from_iso(row["last_run_at"]) if row["last_run_at"] else None,
    )


def _row_to_message(row: sqlite3.Row) -> CoderMessage:
    return CoderMessage(
        id=row["id"],
        thread_id=row["thread_id"],
        role=CoderMessageRole(row["role"]),
        content_md=row["content_md"] or "",
        runtime_id=row["runtime_id"],
        provider=row["provider"],
        model=row["model"],
        coder_run_id=row["coder_run_id"],
        artifact_ids=[str(item) for item in _loads_list(row["artifact_ids_json"])],
        usage_summary=_loads_dict(row["usage_summary_json"]),
        benchmark_attempt_id=row["benchmark_attempt_id"],
        metadata=_loads_dict(row["metadata_json"]),
        created_at=from_iso(row["created_at"]),
    )


def _row_to_runtime_switch(row: sqlite3.Row) -> CoderRuntimeSwitch:
    return CoderRuntimeSwitch(
        id=row["id"],
        thread_id=row["thread_id"],
        from_runtime_id=row["from_runtime_id"],
        from_provider=row["from_provider"],
        from_model=row["from_model"],
        to_runtime_id=row["to_runtime_id"],
        to_provider=row["to_provider"],
        to_model=row["to_model"],
        reason=row["reason"] or "",
        created_at=from_iso(row["created_at"]),
    )


def _row_to_review_pass(row: sqlite3.Row) -> CoderReviewPass:
    return CoderReviewPass(
        id=row["id"],
        thread_id=row["thread_id"],
        requested_runtime_id=row["requested_runtime_id"],
        requested_provider=row["requested_provider"],
        requested_model=row["requested_model"],
        status=CoderReviewPassStatus(row["status"]),
        title=row["title"] or "Review pass",
        summary_md=row["summary_md"] or "",
        coder_run_id=row["coder_run_id"],
        metadata=_loads_dict(row["metadata_json"]),
        created_at=from_iso(row["created_at"]),
        updated_at=from_iso(row["updated_at"]),
    )


def _row_to_run(row: sqlite3.Row) -> CoderRun:
    return CoderRun(
        id=row["id"],
        thread_id=row["thread_id"],
        message_id=row["message_id"],
        review_pass_id=row["review_pass_id"],
        runtime_id=row["runtime_id"] or "",
        provider=row["provider"] or "",
        model=row["model"] or "",
        surface_kind=row["surface_kind"],
        surface_profile_version=row["surface_profile_version"] or "",
        pty_session_id=row["pty_session_id"],
        project_id=row["project_id"],
        benchmark_attempt_id=row["benchmark_attempt_id"],
        status=CoderRunStatus(row["status"]),
        started_at=from_iso(row["started_at"]),
        first_input_at=from_iso(row["first_input_at"]) if row["first_input_at"] else None,
        first_output_at=from_iso(row["first_output_at"]) if row["first_output_at"] else None,
        ended_at=from_iso(row["ended_at"]) if row["ended_at"] else None,
        exit_code=row["exit_code"],
        input_event_count=row["input_event_count"] or 0,
        output_event_count=row["output_event_count"] or 0,
        used_any_input=_as_bool(row["used_any_input"]),
        used_any_output=_as_bool(row["used_any_output"]),
        crash_reason=row["crash_reason"],
        workspace_context_mode=row["workspace_context_mode"] or "project",
        attachments_count=row["attachments_count"] or 0,
        hidden_context_hash=row["hidden_context_hash"],
        workspace_overhead_bytes=row["workspace_overhead_bytes"] or 0,
        context_items_injected=row["context_items_injected"] or 0,
        metadata=_loads_dict(row["metadata_json"]),
    )


def get_preferences(conn: sqlite3.Connection) -> CoderWorkspacePreferences:
    row = conn.execute("SELECT * FROM coder_workspace_preferences WHERE id = 1").fetchone()
    if row is None:
        now = to_iso(utc_now())
        conn.execute(
            "INSERT INTO coder_workspace_preferences "
            "(id, advanced_terminal_enabled, raw_pty_enabled, updated_at) "
            "VALUES (1, 0, 1, ?)",
            (now,),
        )
        return CoderWorkspacePreferences(updated_at=from_iso(now))
    return CoderWorkspacePreferences(
        advanced_terminal_enabled=_as_bool(row["advanced_terminal_enabled"]),
        raw_pty_enabled=_as_bool(row["raw_pty_enabled"]),
        updated_at=from_iso(row["updated_at"]),
    )


def update_preferences(
    conn: sqlite3.Connection,
    *,
    advanced_terminal_enabled: bool | None = None,
    raw_pty_enabled: bool | None = None,
) -> CoderWorkspacePreferences:
    current = get_preferences(conn)
    next_advanced = current.advanced_terminal_enabled if advanced_terminal_enabled is None else advanced_terminal_enabled
    next_raw = current.raw_pty_enabled if raw_pty_enabled is None else raw_pty_enabled
    now = to_iso(utc_now())
    conn.execute(
        "UPDATE coder_workspace_preferences "
        "SET advanced_terminal_enabled = ?, raw_pty_enabled = ?, updated_at = ? "
        "WHERE id = 1",
        (1 if next_advanced else 0, 1 if next_raw else 0, now),
    )
    return CoderWorkspacePreferences(
        advanced_terminal_enabled=next_advanced,
        raw_pty_enabled=next_raw,
        updated_at=from_iso(now),
    )


def list_threads(conn: sqlite3.Connection, project_id: str) -> list[CoderThreadSummary]:
    rows = conn.execute(
        """
        SELECT t.*,
               (SELECT COUNT(1) FROM coder_messages m WHERE m.thread_id = t.id) AS message_count,
               (SELECT COUNT(1) FROM coder_review_passes r WHERE r.thread_id = t.id) AS review_pass_count,
               (SELECT COUNT(1) FROM coder_runs cr WHERE cr.thread_id = t.id) AS run_count,
               COALESCE((SELECT substr(m.content_md, 1, 140)
                         FROM coder_messages m
                         WHERE m.thread_id = t.id
                         ORDER BY m.created_at DESC
                         LIMIT 1), '') AS last_message_preview
        FROM coder_threads t
        WHERE t.project_id = ?
        ORDER BY t.archived ASC, t.pinned DESC, t.updated_at DESC
        """,
        (project_id,),
    ).fetchall()
    return [
        CoderThreadSummary(
            thread=_row_to_thread(row),
            message_count=row["message_count"] or 0,
            review_pass_count=row["review_pass_count"] or 0,
            run_count=row["run_count"] or 0,
            last_message_preview=row["last_message_preview"] or "",
        )
        for row in rows
    ]


def get_thread(conn: sqlite3.Connection, thread_id: str) -> CoderThread:
    row = conn.execute("SELECT * FROM coder_threads WHERE id = ?", (thread_id,)).fetchone()
    if row is None:
        raise not_found("coder_thread", thread_id)
    return _row_to_thread(row)


def create_thread(conn: sqlite3.Connection, project_id: str, payload: CoderThreadCreate) -> CoderThread:
    thread_id = _new_id()
    now = to_iso(utc_now())
    conn.execute(
        """
        INSERT INTO coder_threads (
            id, project_id, title, status, active_runtime_id, active_provider,
            active_model, workspace_context_mode, pinned, archived, thread_kind,
            metadata_json, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            thread_id,
            project_id,
            payload.title.strip() or "New thread",
            CoderThreadStatus.ARCHIVED.value if payload.archived else CoderThreadStatus.ACTIVE.value,
            payload.active_runtime_id,
            payload.active_provider,
            payload.active_model,
            payload.workspace_context_mode or "project",
            1 if payload.pinned else 0,
            1 if payload.archived else 0,
            payload.thread_kind or "chat",
            _dumps(payload.metadata),
            now,
            now,
        ),
    )
    return get_thread(conn, thread_id)


def update_thread(conn: sqlite3.Connection, thread_id: str, payload: CoderThreadUpdate) -> CoderThread:
    current = get_thread(conn, thread_id)
    status = payload.status or (CoderThreadStatus.ARCHIVED if payload.archived else current.status)
    archived = current.archived if payload.archived is None else payload.archived
    now = to_iso(utc_now())
    conn.execute(
        """
        UPDATE coder_threads
        SET title = ?, status = ?, active_runtime_id = ?, active_provider = ?, active_model = ?,
            workspace_context_mode = ?, pinned = ?, archived = ?, metadata_json = ?, updated_at = ?
        WHERE id = ?
        """,
        (
            payload.title.strip() if payload.title is not None and payload.title.strip() else current.title,
            status.value,
            current.active_runtime_id if payload.active_runtime_id is None else payload.active_runtime_id,
            current.active_provider if payload.active_provider is None else payload.active_provider,
            current.active_model if payload.active_model is None else payload.active_model,
            payload.workspace_context_mode or current.workspace_context_mode,
            1 if (current.pinned if payload.pinned is None else payload.pinned) else 0,
            1 if archived else 0,
            _dumps(current.metadata if payload.metadata is None else payload.metadata),
            now,
            thread_id,
        ),
    )
    return get_thread(conn, thread_id)


def delete_thread(conn: sqlite3.Connection, thread_id: str) -> None:
    get_thread(conn, thread_id)
    conn.execute("DELETE FROM coder_threads WHERE id = ?", (thread_id,))


def list_messages(conn: sqlite3.Connection, thread_id: str) -> list[CoderMessage]:
    get_thread(conn, thread_id)
    rows = conn.execute(
        "SELECT * FROM coder_messages WHERE thread_id = ? ORDER BY created_at",
        (thread_id,),
    ).fetchall()
    return [_row_to_message(row) for row in rows]


def add_message(conn: sqlite3.Connection, thread_id: str, payload: CoderMessageCreate) -> CoderMessage:
    thread = get_thread(conn, thread_id)
    now = to_iso(utc_now())
    message_id = _new_id()
    conn.execute(
        """
        INSERT INTO coder_messages (
            id, thread_id, role, content_md, runtime_id, provider, model,
            coder_run_id, artifact_ids_json, usage_summary_json,
            benchmark_attempt_id, metadata_json, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            message_id,
            thread_id,
            payload.role.value,
            payload.content_md,
            payload.runtime_id,
            payload.provider,
            payload.model,
            payload.coder_run_id,
            _dumps(payload.artifact_ids),
            _dumps(payload.usage_summary),
            payload.benchmark_attempt_id,
            _dumps(payload.metadata),
            now,
        ),
    )
    next_title = thread.title
    if thread.title.strip().lower() == "new thread" and payload.role == CoderMessageRole.USER:
        preview = payload.content_md.strip().splitlines()[0][:80]
        if preview:
            next_title = preview
    conn.execute(
        "UPDATE coder_threads SET title = ?, updated_at = ?, last_message_at = ? WHERE id = ?",
        (next_title, now, now, thread_id),
    )
    row = conn.execute("SELECT * FROM coder_messages WHERE id = ?", (message_id,)).fetchone()
    assert row is not None
    return _row_to_message(row)


def list_runtime_switches(conn: sqlite3.Connection, thread_id: str) -> list[CoderRuntimeSwitch]:
    get_thread(conn, thread_id)
    rows = conn.execute(
        "SELECT * FROM coder_runtime_switches WHERE thread_id = ? ORDER BY created_at",
        (thread_id,),
    ).fetchall()
    return [_row_to_runtime_switch(row) for row in rows]


def switch_runtime(
    conn: sqlite3.Connection, thread_id: str, payload: CoderRuntimeSwitchRequest
) -> CoderRuntimeSwitch:
    current = get_thread(conn, thread_id)
    now = to_iso(utc_now())
    switch_id = _new_id()
    conn.execute(
        """
        INSERT INTO coder_runtime_switches (
            id, thread_id, from_runtime_id, from_provider, from_model,
            to_runtime_id, to_provider, to_model, reason, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            switch_id,
            thread_id,
            current.active_runtime_id,
            current.active_provider,
            current.active_model,
            payload.runtime_id,
            payload.provider,
            payload.model,
            payload.reason,
            now,
        ),
    )
    conn.execute(
        """
        UPDATE coder_threads
        SET active_runtime_id = ?, active_provider = ?, active_model = ?, updated_at = ?
        WHERE id = ?
        """,
        (payload.runtime_id, payload.provider, payload.model, now, thread_id),
    )
    row = conn.execute("SELECT * FROM coder_runtime_switches WHERE id = ?", (switch_id,)).fetchone()
    assert row is not None
    return _row_to_runtime_switch(row)


def list_review_passes(conn: sqlite3.Connection, thread_id: str) -> list[CoderReviewPass]:
    get_thread(conn, thread_id)
    rows = conn.execute(
        "SELECT * FROM coder_review_passes WHERE thread_id = ? ORDER BY created_at DESC",
        (thread_id,),
    ).fetchall()
    return [_row_to_review_pass(row) for row in rows]


def get_review_pass(conn: sqlite3.Connection, review_pass_id: str) -> CoderReviewPass:
    row = conn.execute(
        "SELECT * FROM coder_review_passes WHERE id = ?",
        (review_pass_id,),
    ).fetchone()
    if row is None:
        raise not_found("coder_review_pass", review_pass_id)
    return _row_to_review_pass(row)


def create_review_pass(
    conn: sqlite3.Connection, thread_id: str, payload: CoderReviewPassCreate
) -> CoderReviewPass:
    get_thread(conn, thread_id)
    pass_id = _new_id()
    now = to_iso(utc_now())
    conn.execute(
        """
        INSERT INTO coder_review_passes (
            id, thread_id, requested_runtime_id, requested_provider, requested_model,
            status, title, summary_md, coder_run_id, metadata_json, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?, ?)
        """,
        (
            pass_id,
            thread_id,
            payload.requested_runtime_id,
            payload.requested_provider,
            payload.requested_model,
            CoderReviewPassStatus.PENDING.value,
            payload.title.strip() or "Review pass",
            payload.summary_md,
            _dumps(payload.metadata),
            now,
            now,
        ),
    )
    conn.execute("UPDATE coder_threads SET updated_at = ? WHERE id = ?", (now, thread_id))
    row = conn.execute("SELECT * FROM coder_review_passes WHERE id = ?", (pass_id,)).fetchone()
    assert row is not None
    return _row_to_review_pass(row)


def get_run(conn: sqlite3.Connection, run_id: str) -> CoderRun:
    row = conn.execute("SELECT * FROM coder_runs WHERE id = ?", (run_id,)).fetchone()
    if row is None:
        raise not_found("coder_run", run_id)
    return _row_to_run(row)


def list_runs_for_thread(conn: sqlite3.Connection, thread_id: str) -> list[CoderRun]:
    get_thread(conn, thread_id)
    rows = conn.execute(
        "SELECT * FROM coder_runs WHERE thread_id = ? ORDER BY started_at DESC",
        (thread_id,),
    ).fetchall()
    return [_row_to_run(row) for row in rows]


def thread_detail(conn: sqlite3.Connection, thread_id: str) -> CoderThreadDetail:
    return CoderThreadDetail(
        thread=get_thread(conn, thread_id),
        messages=list_messages(conn, thread_id),
        runtime_switches=list_runtime_switches(conn, thread_id),
        review_passes=list_review_passes(conn, thread_id),
        linked_runs=list_runs_for_thread(conn, thread_id),
    )


def get_run_by_session_id(conn: sqlite3.Connection, session_id: str) -> CoderRun | None:
    row = conn.execute(
        "SELECT * FROM coder_runs WHERE pty_session_id = ?",
        (session_id,),
    ).fetchone()
    return _row_to_run(row) if row is not None else None


def create_run(conn: sqlite3.Connection, payload: CoderRunCreate) -> CoderRun:
    now = to_iso(utc_now())
    run_id = _new_id()
    conn.execute(
        """
        INSERT INTO coder_runs (
            id, thread_id, message_id, review_pass_id, project_id, pty_session_id,
            benchmark_attempt_id, runtime_id, provider, model, surface_kind,
            surface_profile_version, workspace_context_mode, attachments_count,
            hidden_context_hash, workspace_overhead_bytes, context_items_injected,
            status, started_at, metadata_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            run_id,
            payload.thread_id,
            payload.message_id,
            payload.review_pass_id,
            payload.project_id,
            payload.pty_session_id,
            payload.benchmark_attempt_id,
            payload.runtime_id,
            payload.provider,
            payload.model,
            payload.surface_kind,
            payload.surface_profile_version,
            payload.workspace_context_mode,
            payload.attachments_count,
            payload.hidden_context_hash,
            payload.workspace_overhead_bytes,
            payload.context_items_injected,
            CoderRunStatus.CREATED.value,
            now,
            _dumps(payload.metadata),
        ),
    )
    if payload.thread_id:
        conn.execute(
            "UPDATE coder_threads SET updated_at = ?, last_run_at = ? WHERE id = ?",
            (now, now, payload.thread_id),
        )
    return get_run(conn, run_id)


def update_run_session(conn: sqlite3.Connection, run_id: str, pty_session_id: str) -> CoderRun:
    get_run(conn, run_id)
    conn.execute(
        "UPDATE coder_runs SET pty_session_id = ?, status = ? WHERE id = ?",
        (pty_session_id, CoderRunStatus.RUNNING.value, run_id),
    )
    return get_run(conn, run_id)


def attach_run_to_message(conn: sqlite3.Connection, message_id: str, run_id: str) -> None:
    conn.execute("UPDATE coder_messages SET coder_run_id = ? WHERE id = ?", (run_id, message_id))


def attach_run_to_review_pass(conn: sqlite3.Connection, review_pass_id: str, run_id: str) -> None:
    now = to_iso(utc_now())
    conn.execute(
        "UPDATE coder_review_passes SET coder_run_id = ?, status = ?, updated_at = ? WHERE id = ?",
        (run_id, CoderReviewPassStatus.RUNNING.value, now, review_pass_id),
    )


def record_run_input(conn: sqlite3.Connection, session_id: str) -> CoderRun | None:
    row = conn.execute(
        "SELECT * FROM coder_runs WHERE pty_session_id = ?",
        (session_id,),
    ).fetchone()
    if row is None:
        return None
    run = _row_to_run(row)
    now = to_iso(utc_now())
    conn.execute(
        """
        UPDATE coder_runs
        SET status = ?, first_input_at = COALESCE(first_input_at, ?),
            input_event_count = input_event_count + 1, used_any_input = 1
        WHERE id = ?
        """,
        (CoderRunStatus.RUNNING.value, now, run.id),
    )
    return get_run(conn, run.id)


def record_run_output(conn: sqlite3.Connection, session_id: str) -> CoderRun | None:
    row = conn.execute(
        "SELECT * FROM coder_runs WHERE pty_session_id = ?",
        (session_id,),
    ).fetchone()
    if row is None:
        return None
    run = _row_to_run(row)
    now = to_iso(utc_now())
    conn.execute(
        """
        UPDATE coder_runs
        SET status = ?, first_output_at = COALESCE(first_output_at, ?),
            output_event_count = output_event_count + 1, used_any_output = 1
        WHERE id = ?
        """,
        (CoderRunStatus.RUNNING.value, now, run.id),
    )
    return get_run(conn, run.id)


def finish_run(
    conn: sqlite3.Connection,
    session_id: str,
    *,
    exit_code: int | None,
    crash_reason: str | None = None,
) -> CoderRun | None:
    row = conn.execute(
        "SELECT * FROM coder_runs WHERE pty_session_id = ?",
        (session_id,),
    ).fetchone()
    if row is None:
        return None
    run = _row_to_run(row)
    now = to_iso(utc_now())
    if crash_reason:
        status = CoderRunStatus.CRASHED
    elif exit_code not in (None, 0):
        status = CoderRunStatus.FAILED
    elif exit_code == 0:
        status = CoderRunStatus.COMPLETED
    else:
        status = CoderRunStatus.STOPPED
    conn.execute(
        """
        UPDATE coder_runs
        SET status = ?, ended_at = ?, exit_code = ?, crash_reason = COALESCE(?, crash_reason)
        WHERE id = ?
        """,
        (status.value, now, exit_code, crash_reason, run.id),
    )
    if run.review_pass_id:
        conn.execute(
            "UPDATE coder_review_passes SET status = ?, updated_at = ? WHERE id = ?",
            (
                CoderReviewPassStatus.COMPLETED.value
                if status == CoderRunStatus.COMPLETED
                else CoderReviewPassStatus.FAILED.value,
                now,
                run.review_pass_id,
            ),
        )
    return get_run(conn, run.id)
