"""Durable, project-scoped Synapse Active Tasks.

This subsystem is deliberately independent of ChatGPT's built-in Tasks product.
It stores recurrence and run history in Synapse SQLite and lets a daemon-owned
scheduler dispatch bounded project iterations through an external execution
bridge. The first dispatcher reuses Chat Foreman's one-iteration campaign path.
"""
from __future__ import annotations

import asyncio
import json
import math
import os
import sqlite3
import subprocess
import sys
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Protocol

from pydantic import BaseModel, Field, field_validator, model_validator

from .models import AuditSource
from .storage import Storage
from .time_utils import from_iso, to_iso, utc_now

MIN_INTERVAL_SECONDS = 60
DEFAULT_INTERVAL_SECONDS = 3600
DEFAULT_MAX_RUNTIME_SECONDS = 3600
ACTIVE_DISPATCH_STATUSES = {"active", "queued", "running", "waiting_for_writer", "waiting_for_capacity", "needs_attention"}


class ActiveTaskScheduleKind(str, Enum):
    INTERVAL = "interval"
    ONCE = "once"


class ActiveTaskDispatchKind(str, Enum):
    FOREMAN_ITERATION = "foreman_iteration"


class ActiveTaskRunStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    DISPATCHED = "dispatched"
    SKIPPED_OVERLAP = "skipped_overlap"
    FAILED = "failed"
    INTERRUPTED = "interrupted"


class ActiveTask(BaseModel):
    id: str
    project_id: str
    name: str
    prompt: str = ""
    dispatch_kind: ActiveTaskDispatchKind = ActiveTaskDispatchKind.FOREMAN_ITERATION
    preferred_runtime: str = "chatgpt_web"
    schedule_kind: ActiveTaskScheduleKind = ActiveTaskScheduleKind.INTERVAL
    interval_seconds: int | None = DEFAULT_INTERVAL_SECONDS
    next_run_at: str | None = None
    end_at: str | None = None
    max_runs: int | None = None
    run_count: int = 0
    enabled: bool = True
    no_overlap: bool = True
    max_runtime_seconds: int = DEFAULT_MAX_RUNTIME_SECONDS
    last_started_at: str | None = None
    last_finished_at: str | None = None
    last_status: str | None = None
    last_error: str = ""
    last_dispatch_ref: str | None = None
    created_at: str
    updated_at: str
    source: AuditSource = AuditSource.DESKTOP


class ActiveTaskCreate(BaseModel):
    project_id: str
    name: str = Field(min_length=1, max_length=160)
    prompt: str = Field(default="", max_length=12000)
    dispatch_kind: ActiveTaskDispatchKind = ActiveTaskDispatchKind.FOREMAN_ITERATION
    preferred_runtime: str = Field(default="chatgpt_web", max_length=40)
    schedule_kind: ActiveTaskScheduleKind = ActiveTaskScheduleKind.INTERVAL
    interval_seconds: int | None = DEFAULT_INTERVAL_SECONDS
    next_run_at: str | None = None
    end_at: str | None = None
    max_runs: int | None = Field(default=None, ge=1)
    enabled: bool = True
    no_overlap: bool = True
    max_runtime_seconds: int = Field(default=DEFAULT_MAX_RUNTIME_SECONDS, ge=60, le=86400)
    source: AuditSource = AuditSource.DESKTOP

    @field_validator("interval_seconds")
    @classmethod
    def _validate_interval(cls, value: int | None) -> int | None:
        if value is not None and value < MIN_INTERVAL_SECONDS:
            raise ValueError(f"interval_seconds must be >= {MIN_INTERVAL_SECONDS}")
        return value

    @model_validator(mode="after")
    def _schedule_consistency(self):
        if self.schedule_kind == ActiveTaskScheduleKind.INTERVAL and self.interval_seconds is None:
            raise ValueError("interval schedule requires interval_seconds")
        if self.schedule_kind == ActiveTaskScheduleKind.ONCE:
            self.interval_seconds = None
        for value in (self.next_run_at, self.end_at):
            if value:
                from_iso(value)
        return self


class ActiveTaskUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    prompt: str | None = Field(default=None, max_length=12000)
    preferred_runtime: str | None = Field(default=None, max_length=40)
    schedule_kind: ActiveTaskScheduleKind | None = None
    interval_seconds: int | None = Field(default=None, ge=MIN_INTERVAL_SECONDS)
    next_run_at: str | None = None
    end_at: str | None = None
    max_runs: int | None = Field(default=None, ge=1)
    enabled: bool | None = None
    no_overlap: bool | None = None
    max_runtime_seconds: int | None = Field(default=None, ge=60, le=86400)
    source: AuditSource = AuditSource.DESKTOP


class ActiveTaskRun(BaseModel):
    id: str
    task_id: str
    scheduled_for: str
    started_at: str | None = None
    finished_at: str | None = None
    status: ActiveTaskRunStatus
    manual: bool = False
    dispatch_ref: str | None = None
    error: str = ""
    detail: dict[str, Any] = Field(default_factory=dict)
    created_at: str


@dataclass(frozen=True)
class DispatchReceipt:
    ref_id: str
    status: str
    detail: dict[str, Any]


class ActiveTaskDispatcher(Protocol):
    async def dispatch(self, task: ActiveTask, run_id: str) -> DispatchReceipt: ...
    async def is_active(self, ref_id: str) -> bool: ...


def _new_id() -> str:
    return uuid.uuid4().hex[:12]


def _row_to_task(row: sqlite3.Row) -> ActiveTask:
    return ActiveTask(
        id=row["id"], project_id=row["project_id"], name=row["name"], prompt=row["prompt"] or "",
        dispatch_kind=row["dispatch_kind"], preferred_runtime=row["preferred_runtime"] or "chatgpt_web",
        schedule_kind=row["schedule_kind"], interval_seconds=row["interval_seconds"], next_run_at=row["next_run_at"],
        end_at=row["end_at"], max_runs=row["max_runs"], run_count=int(row["run_count"] or 0), enabled=bool(row["enabled"]),
        no_overlap=bool(row["no_overlap"]), max_runtime_seconds=int(row["max_runtime_seconds"] or DEFAULT_MAX_RUNTIME_SECONDS),
        last_started_at=row["last_started_at"], last_finished_at=row["last_finished_at"], last_status=row["last_status"],
        last_error=row["last_error"] or "", last_dispatch_ref=row["last_dispatch_ref"], created_at=row["created_at"],
        updated_at=row["updated_at"], source=row["source"] or "desktop",
    )


def _row_to_run(row: sqlite3.Row) -> ActiveTaskRun:
    try:
        detail = json.loads(row["detail_json"] or "{}")
    except json.JSONDecodeError:
        detail = {}
    return ActiveTaskRun(
        id=row["id"], task_id=row["task_id"], scheduled_for=row["scheduled_for"], started_at=row["started_at"],
        finished_at=row["finished_at"], status=row["status"], manual=bool(row["manual"]), dispatch_ref=row["dispatch_ref"],
        error=row["error"] or "", detail=detail if isinstance(detail, dict) else {}, created_at=row["created_at"],
    )


def get_task(conn: sqlite3.Connection, task_id: str) -> ActiveTask:
    row = conn.execute("SELECT * FROM active_tasks WHERE id=?", (task_id,)).fetchone()
    if row is None:
        raise KeyError(task_id)
    return _row_to_task(row)


def list_tasks(conn: sqlite3.Connection, project_id: str | None = None, enabled: bool | None = None) -> list[ActiveTask]:
    clauses: list[str] = []
    args: list[Any] = []
    if project_id:
        clauses.append("project_id=?")
        args.append(project_id)
    if enabled is not None:
        clauses.append("enabled=?")
        args.append(1 if enabled else 0)
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    rows = conn.execute(f"SELECT * FROM active_tasks{where} ORDER BY enabled DESC, next_run_at, created_at", args).fetchall()
    return [_row_to_task(row) for row in rows]


def create_task(conn: sqlite3.Connection, payload: ActiveTaskCreate, *, now: datetime | None = None) -> ActiveTask:
    current = now or utc_now()
    now_iso = to_iso(current)
    next_run = payload.next_run_at
    if next_run is None and payload.enabled:
        if payload.schedule_kind == ActiveTaskScheduleKind.INTERVAL:
            next_run = to_iso(current + timedelta(seconds=int(payload.interval_seconds or DEFAULT_INTERVAL_SECONDS)))
        else:
            next_run = now_iso
    task_id = _new_id()
    conn.execute(
        """INSERT INTO active_tasks(
            id,project_id,name,prompt,dispatch_kind,preferred_runtime,schedule_kind,interval_seconds,next_run_at,end_at,
            max_runs,run_count,enabled,no_overlap,max_runtime_seconds,created_at,updated_at,source
        ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            task_id, payload.project_id, payload.name, payload.prompt, payload.dispatch_kind.value,
            payload.preferred_runtime, payload.schedule_kind.value, payload.interval_seconds, next_run, payload.end_at,
            payload.max_runs, 0, int(payload.enabled), int(payload.no_overlap), payload.max_runtime_seconds, now_iso, now_iso,
            payload.source.value,
        ),
    )
    return get_task(conn, task_id)


def update_task(conn: sqlite3.Connection, task_id: str, payload: ActiveTaskUpdate, *, now: datetime | None = None) -> ActiveTask:
    existing = get_task(conn, task_id)
    current = now or utc_now()
    fields = payload.model_dump(exclude_unset=True, exclude={"source"})
    if "schedule_kind" in fields and isinstance(fields["schedule_kind"], Enum):
        fields["schedule_kind"] = fields["schedule_kind"].value
    if fields.get("schedule_kind") == ActiveTaskScheduleKind.ONCE.value:
        fields["interval_seconds"] = None
    if "enabled" in fields:
        fields["enabled"] = int(bool(fields["enabled"]))
        if fields["enabled"] and not existing.next_run_at and "next_run_at" not in fields:
            interval = int(fields.get("interval_seconds") or existing.interval_seconds or DEFAULT_INTERVAL_SECONDS)
            fields["next_run_at"] = to_iso(current + timedelta(seconds=interval))
    if "no_overlap" in fields:
        fields["no_overlap"] = int(bool(fields["no_overlap"]))
    if ("interval_seconds" in fields or "schedule_kind" in fields) and "next_run_at" not in fields and existing.enabled:
        kind = fields.get("schedule_kind", existing.schedule_kind.value)
        if kind == ActiveTaskScheduleKind.INTERVAL.value:
            interval = int(fields.get("interval_seconds") or existing.interval_seconds or DEFAULT_INTERVAL_SECONDS)
            fields["next_run_at"] = to_iso(current + timedelta(seconds=interval))
    fields["updated_at"] = to_iso(current)
    if fields:
        columns = ",".join(f"{key}=?" for key in fields)
        conn.execute(f"UPDATE active_tasks SET {columns} WHERE id=?", [*fields.values(), task_id])
    return get_task(conn, task_id)


def delete_task(conn: sqlite3.Connection, task_id: str) -> None:
    get_task(conn, task_id)
    conn.execute("DELETE FROM active_tasks WHERE id=?", (task_id,))


def list_runs(conn: sqlite3.Connection, task_id: str, limit: int = 50) -> list[ActiveTaskRun]:
    rows = conn.execute(
        "SELECT * FROM active_task_runs WHERE task_id=? ORDER BY created_at DESC LIMIT ?", (task_id, max(1, min(limit, 500)))
    ).fetchall()
    return [_row_to_run(row) for row in rows]


def due_tasks(conn: sqlite3.Connection, now: datetime | None = None) -> list[ActiveTask]:
    current_iso = to_iso(now or utc_now())
    rows = conn.execute(
        """SELECT * FROM active_tasks
           WHERE enabled=1 AND next_run_at IS NOT NULL AND next_run_at <= ?
             AND (end_at IS NULL OR end_at >= ?)
             AND (max_runs IS NULL OR run_count < max_runs)
           ORDER BY next_run_at, created_at""",
        (current_iso, current_iso),
    ).fetchall()
    return [_row_to_task(row) for row in rows]


def recover_interrupted_runs(conn: sqlite3.Connection, now: datetime | None = None) -> int:
    finished = to_iso(now or utc_now())
    rows = conn.execute("SELECT id,task_id FROM active_task_runs WHERE status='running'").fetchall()
    for row in rows:
        conn.execute(
            "UPDATE active_task_runs SET status='interrupted',finished_at=?,error=? WHERE id=?",
            (finished, "Synapse daemon restarted while dispatch was in progress.", row["id"]),
        )
        conn.execute(
            "UPDATE active_tasks SET last_finished_at=?,last_status='interrupted',last_error=? WHERE id=?",
            (finished, "Synapse daemon restarted while dispatch was in progress.", row["task_id"]),
        )
    return len(rows)


def _next_interval_after(scheduled_for: datetime, interval_seconds: int, now: datetime) -> datetime:
    interval = max(MIN_INTERVAL_SECONDS, int(interval_seconds))
    candidate = scheduled_for + timedelta(seconds=interval)
    if candidate > now:
        return candidate
    elapsed = (now - scheduled_for).total_seconds()
    jumps = max(1, math.floor(elapsed / interval) + 1)
    return scheduled_for + timedelta(seconds=jumps * interval)


def _advance_schedule(conn: sqlite3.Connection, task: ActiveTask, scheduled_for: datetime, now: datetime) -> None:
    disable = False
    next_run: str | None
    if task.schedule_kind == ActiveTaskScheduleKind.ONCE:
        next_run = None
        disable = True
    else:
        next_run = to_iso(_next_interval_after(scheduled_for, int(task.interval_seconds or DEFAULT_INTERVAL_SECONDS), now))
    if task.end_at and next_run and from_iso(next_run) > from_iso(task.end_at):
        next_run = None
        disable = True
    conn.execute(
        "UPDATE active_tasks SET next_run_at=?,enabled=CASE WHEN ? THEN 0 ELSE enabled END,updated_at=? WHERE id=?",
        (next_run, int(disable), to_iso(now), task.id),
    )


class ForemanDispatcher:
    """Narrow bridge from Synapse scheduling to Chat Foreman's iteration engine."""

    def __init__(self, root: Path | None = None, python_executable: str | None = None):
        configured = os.environ.get("SYNAPSE_FOREMAN_ROOT", "").strip()
        self.root = Path(configured) if configured else (root or Path.home() / "ChatForeman")
        self.python_executable = python_executable or sys.executable

    @property
    def script(self) -> Path:
        return self.root / "foreman.py"

    async def dispatch(self, task: ActiveTask, run_id: str) -> DispatchReceipt:
        if task.dispatch_kind != ActiveTaskDispatchKind.FOREMAN_ITERATION:
            raise RuntimeError(f"Unsupported active-task dispatch kind: {task.dispatch_kind}")
        if not self.script.is_file():
            raise RuntimeError(f"Chat Foreman entry point not found: {self.script}")
        args = [
            self.python_executable, str(self.script), "iterate", "1", task.project_id,
            "--name", f"Active Task · {task.name} · {run_id[:6]}",
        ]
        runtime = task.preferred_runtime.strip().lower()
        if runtime and runtime != "auto":
            args += ["--runtime", runtime]
        completed = await asyncio.to_thread(
            subprocess.run,
            args,
            cwd=str(self.root),
            capture_output=True,
            text=True,
            timeout=min(60, max(15, task.max_runtime_seconds)),
            check=False,
        )
        if completed.returncode != 0:
            raise RuntimeError((completed.stderr or completed.stdout or f"Foreman exited {completed.returncode}").strip()[:4000])
        try:
            payload = json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Foreman returned non-JSON output: {completed.stdout[:1000]}") from exc
        ref_id = str(payload.get("id") or "")
        if not ref_id:
            raise RuntimeError("Foreman campaign did not return an id")
        return DispatchReceipt(ref_id=ref_id, status=str(payload.get("status") or "created"), detail=payload)

    async def is_active(self, ref_id: str) -> bool:
        if not ref_id or not self.script.is_file():
            return False
        completed = await asyncio.to_thread(
            subprocess.run,
            [self.python_executable, str(self.script), "campaigns"],
            cwd=str(self.root), capture_output=True, text=True, timeout=30, check=False,
        )
        if completed.returncode != 0:
            # Fail closed for overlap: if Foreman status is unavailable, do not
            # launch a potentially colliding writer.
            return True
        try:
            campaigns = json.loads(completed.stdout)
        except json.JSONDecodeError:
            return True
        for campaign in campaigns if isinstance(campaigns, list) else []:
            if str(campaign.get("id")) == ref_id:
                return str(campaign.get("status") or "").lower() in ACTIVE_DISPATCH_STATUSES
        return False


class ActiveTaskScheduler:
    def __init__(self, storage: Storage, dispatcher: ActiveTaskDispatcher, *, poll_seconds: float = 15.0):
        self.storage = storage
        self.dispatcher = dispatcher
        self.poll_seconds = max(0.05, float(poll_seconds))
        self._loop_task: asyncio.Task | None = None
        self._stopping = False
        self._dispatch_lock = asyncio.Lock()

    async def start(self) -> None:
        with self.storage.transaction() as conn:
            recover_interrupted_runs(conn)
        if self._loop_task and not self._loop_task.done():
            return
        self._stopping = False
        self._loop_task = asyncio.create_task(self._loop(), name="synapse-active-tasks")

    async def stop(self) -> None:
        self._stopping = True
        task = self._loop_task
        self._loop_task = None
        if task:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    async def _loop(self) -> None:
        while not self._stopping:
            try:
                await self.run_due()
            except asyncio.CancelledError:
                raise
            except Exception:
                # One bad task must never kill the scheduler loop.
                pass
            await asyncio.sleep(self.poll_seconds)

    async def run_due(self, *, now: datetime | None = None) -> list[ActiveTaskRun]:
        current = now or utc_now()
        with self.storage.transaction() as conn:
            tasks = due_tasks(conn, current)
        results: list[ActiveTaskRun] = []
        for task in tasks:
            results.append(await self._dispatch_task(task, scheduled_for=from_iso(task.next_run_at or to_iso(current)), manual=False, now=current))
        return results

    async def run_now(self, task_id: str) -> ActiveTaskRun:
        with self.storage.transaction() as conn:
            task = get_task(conn, task_id)
        return await self._dispatch_task(task, scheduled_for=utc_now(), manual=True, now=utc_now())

    async def _dispatch_task(self, task: ActiveTask, *, scheduled_for: datetime, manual: bool, now: datetime) -> ActiveTaskRun:
        async with self._dispatch_lock:
            with self.storage.transaction() as conn:
                fresh = get_task(conn, task.id)
                if not manual and not fresh.enabled:
                    raise RuntimeError("Active task is disabled")
                run_id = _new_id()
                created = to_iso(now)
                conn.execute(
                    """INSERT INTO active_task_runs(id,task_id,scheduled_for,status,manual,created_at)
                       VALUES(?,?,?,'queued',?,?)""",
                    (run_id, fresh.id, to_iso(scheduled_for), int(manual), created),
                )

            if fresh.no_overlap and fresh.last_dispatch_ref:
                prior_active = await self.dispatcher.is_active(fresh.last_dispatch_ref)
                if prior_active:
                    finished = utc_now()
                    with self.storage.transaction() as conn:
                        conn.execute(
                            "UPDATE active_task_runs SET status='skipped_overlap',finished_at=?,error=? WHERE id=?",
                            (to_iso(finished), "Prior dispatched campaign is still active or needs attention.", run_id),
                        )
                        conn.execute(
                            "UPDATE active_tasks SET last_finished_at=?,last_status='skipped_overlap',last_error=?,updated_at=? WHERE id=?",
                            (to_iso(finished), "Prior dispatched campaign is still active or needs attention.", to_iso(finished), fresh.id),
                        )
                        if not manual:
                            _advance_schedule(conn, fresh, scheduled_for, finished)
                        return _row_to_run(conn.execute("SELECT * FROM active_task_runs WHERE id=?", (run_id,)).fetchone())

            started = utc_now()
            with self.storage.transaction() as conn:
                conn.execute("UPDATE active_task_runs SET status='running',started_at=? WHERE id=?", (to_iso(started), run_id))
                conn.execute(
                    "UPDATE active_tasks SET last_started_at=?,last_status='running',last_error='',updated_at=? WHERE id=?",
                    (to_iso(started), to_iso(started), fresh.id),
                )

            try:
                receipt = await self.dispatcher.dispatch(fresh, run_id)
            except Exception as exc:
                finished = utc_now()
                error = f"{type(exc).__name__}: {exc}"[:4000]
                with self.storage.transaction() as conn:
                    conn.execute(
                        "UPDATE active_task_runs SET status='failed',finished_at=?,error=? WHERE id=?",
                        (to_iso(finished), error, run_id),
                    )
                    conn.execute(
                        "UPDATE active_tasks SET last_finished_at=?,last_status='failed',last_error=?,updated_at=? WHERE id=?",
                        (to_iso(finished), error, to_iso(finished), fresh.id),
                    )
                    if not manual:
                        _advance_schedule(conn, fresh, scheduled_for, finished)
                    return _row_to_run(conn.execute("SELECT * FROM active_task_runs WHERE id=?", (run_id,)).fetchone())

            finished = utc_now()
            with self.storage.transaction() as conn:
                conn.execute(
                    "UPDATE active_task_runs SET status='dispatched',finished_at=?,dispatch_ref=?,detail_json=? WHERE id=?",
                    (to_iso(finished), receipt.ref_id, json.dumps(receipt.detail), run_id),
                )
                conn.execute(
                    """UPDATE active_tasks SET run_count=run_count+1,last_finished_at=?,last_status='dispatched',last_error='',
                       last_dispatch_ref=?,updated_at=? WHERE id=?""",
                    (to_iso(finished), receipt.ref_id, to_iso(finished), fresh.id),
                )
                updated = get_task(conn, fresh.id)
                if not manual:
                    _advance_schedule(conn, updated, scheduled_for, finished)
                updated = get_task(conn, fresh.id)
                if updated.max_runs is not None and updated.run_count >= updated.max_runs:
                    conn.execute("UPDATE active_tasks SET enabled=0,next_run_at=NULL,updated_at=? WHERE id=?", (to_iso(finished), fresh.id))
                return _row_to_run(conn.execute("SELECT * FROM active_task_runs WHERE id=?", (run_id,)).fetchone())
