"""Durable models + SQLite CRUD for per-project decision records (ADR-0011).

Three planes, all scoped by ``project_id``:

* **ADRs** -- architecture/decision records with a quick-idea -> promote
  lifecycle. A "quick idea" is just an ADR row with ``status='idea'`` and no
  ``number``; promoting it assigns the next per-project number and marks it
  ``accepted``.
* **Backlog** -- durable planning items (distinct from ephemeral squad work).
* **Versions** -- a per-project changelog (version + what changed).

CRUD here is module-level functions taking a ``sqlite3.Connection``, matching
the convention in :mod:`agent_squads`. Routes call them inside
``storage.transaction()``.
"""

from __future__ import annotations

import json
import secrets
import sqlite3
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field

from .errors import not_found
from .models import AuditSource
from .time_utils import from_iso, to_iso, utc_now


# ── Enums ────────────────────────────────────────────────────────────────────


class ProjectAdrStatus(str, Enum):
    IDEA = "idea"
    DRAFT = "draft"
    PROPOSED = "proposed"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"


class ProjectBacklogStatus(str, Enum):
    TODO = "todo"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    WONTFIX = "wontfix"


class ProjectBacklogPriority(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


# Statuses an ADR can be promoted *from* (a settled ADR isn't re-promotable).
_PROMOTABLE_FROM = {
    ProjectAdrStatus.IDEA,
    ProjectAdrStatus.DRAFT,
    ProjectAdrStatus.PROPOSED,
}


# ── Models ───────────────────────────────────────────────────────────────────


class ProjectAdr(BaseModel):
    id: str
    project_id: str
    number: int | None = None
    title: str
    status: ProjectAdrStatus = ProjectAdrStatus.IDEA
    body_md: str = ""
    tags: list[str] = Field(default_factory=list)
    supersedes_id: str | None = None
    source: AuditSource = AuditSource.DESKTOP
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    decided_at: datetime | None = None


class ProjectAdrCreate(BaseModel):
    # Title alone is enough -- that's the frictionless "quick idea" path.
    title: str
    status: ProjectAdrStatus = ProjectAdrStatus.IDEA
    body_md: str = ""
    tags: list[str] = Field(default_factory=list)
    supersedes_id: str | None = None
    source: AuditSource = AuditSource.DESKTOP


class ProjectAdrUpdate(BaseModel):
    title: str | None = None
    status: ProjectAdrStatus | None = None
    body_md: str | None = None
    tags: list[str] | None = None
    supersedes_id: str | None = None
    source: AuditSource = AuditSource.DESKTOP


class ProjectBacklogItem(BaseModel):
    id: str
    project_id: str
    title: str
    body_md: str = ""
    status: ProjectBacklogStatus = ProjectBacklogStatus.TODO
    priority: ProjectBacklogPriority = ProjectBacklogPriority.MEDIUM
    order_index: int = 0
    source: AuditSource = AuditSource.DESKTOP
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    completed_at: datetime | None = None


class ProjectBacklogItemCreate(BaseModel):
    title: str
    body_md: str = ""
    status: ProjectBacklogStatus = ProjectBacklogStatus.TODO
    priority: ProjectBacklogPriority = ProjectBacklogPriority.MEDIUM
    order_index: int = 0
    source: AuditSource = AuditSource.DESKTOP


class ProjectBacklogItemUpdate(BaseModel):
    title: str | None = None
    body_md: str | None = None
    status: ProjectBacklogStatus | None = None
    priority: ProjectBacklogPriority | None = None
    order_index: int | None = None
    source: AuditSource = AuditSource.DESKTOP


class ProjectVersion(BaseModel):
    id: str
    project_id: str
    version: str
    released_at: str | None = None
    changes_md: str = ""
    source: AuditSource = AuditSource.DESKTOP
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class ProjectVersionCreate(BaseModel):
    version: str
    released_at: str | None = None
    changes_md: str = ""
    source: AuditSource = AuditSource.DESKTOP


class ProjectVersionUpdate(BaseModel):
    version: str | None = None
    released_at: str | None = None
    changes_md: str | None = None
    source: AuditSource = AuditSource.DESKTOP


class ProjectRecords(BaseModel):
    """The full per-project record bundle for the detail view."""

    project_id: str
    adrs: list[ProjectAdr] = Field(default_factory=list)
    backlog: list[ProjectBacklogItem] = Field(default_factory=list)
    versions: list[ProjectVersion] = Field(default_factory=list)


# ── Helpers ──────────────────────────────────────────────────────────────────


def _new_id() -> str:
    return secrets.token_hex(6)


def _dumps(values: list[str]) -> str:
    return json.dumps(list(values))


def _loads_list(payload: str | None) -> list[str]:
    if not payload:
        return []
    try:
        raw = json.loads(payload)
    except json.JSONDecodeError:
        return []
    return [str(item) for item in raw] if isinstance(raw, list) else []


def _row_to_adr(row: sqlite3.Row) -> ProjectAdr:
    return ProjectAdr(
        id=row["id"],
        project_id=row["project_id"],
        number=row["number"],
        title=row["title"],
        status=ProjectAdrStatus(row["status"]),
        body_md=row["body_md"] or "",
        tags=_loads_list(row["tags_json"]),
        supersedes_id=row["supersedes_id"],
        source=AuditSource(row["source"]),
        created_at=from_iso(row["created_at"]),
        updated_at=from_iso(row["updated_at"]),
        decided_at=from_iso(row["decided_at"]) if row["decided_at"] else None,
    )


def _row_to_backlog(row: sqlite3.Row) -> ProjectBacklogItem:
    return ProjectBacklogItem(
        id=row["id"],
        project_id=row["project_id"],
        title=row["title"],
        body_md=row["body_md"] or "",
        status=ProjectBacklogStatus(row["status"]),
        priority=ProjectBacklogPriority(row["priority"]),
        order_index=row["order_index"],
        source=AuditSource(row["source"]),
        created_at=from_iso(row["created_at"]),
        updated_at=from_iso(row["updated_at"]),
        completed_at=from_iso(row["completed_at"]) if row["completed_at"] else None,
    )


def _row_to_version(row: sqlite3.Row) -> ProjectVersion:
    return ProjectVersion(
        id=row["id"],
        project_id=row["project_id"],
        version=row["version"],
        released_at=row["released_at"],
        changes_md=row["changes_md"] or "",
        source=AuditSource(row["source"]),
        created_at=from_iso(row["created_at"]),
        updated_at=from_iso(row["updated_at"]),
    )


# ── ADR CRUD ─────────────────────────────────────────────────────────────────


def list_adrs(conn: sqlite3.Connection, project_id: str) -> list[ProjectAdr]:
    rows = conn.execute(
        "SELECT * FROM project_adrs WHERE project_id = ? "
        "ORDER BY (number IS NULL), number, created_at",
        (project_id,),
    ).fetchall()
    return [_row_to_adr(row) for row in rows]


def get_adr(conn: sqlite3.Connection, adr_id: str) -> ProjectAdr:
    row = conn.execute("SELECT * FROM project_adrs WHERE id = ?", (adr_id,)).fetchone()
    if row is None:
        raise not_found("project_adr", adr_id)
    return _row_to_adr(row)


def create_adr(
    conn: sqlite3.Connection, project_id: str, payload: ProjectAdrCreate
) -> ProjectAdr:
    now = to_iso(utc_now())
    adr_id = _new_id()
    decided = now if payload.status == ProjectAdrStatus.ACCEPTED else None
    number = _next_adr_number(conn, project_id) if payload.status == ProjectAdrStatus.ACCEPTED else None
    conn.execute(
        "INSERT INTO project_adrs "
        "(id, project_id, number, title, status, body_md, tags_json, supersedes_id, "
        " source, created_at, updated_at, decided_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            adr_id,
            project_id,
            number,
            payload.title.strip(),
            payload.status.value,
            payload.body_md,
            _dumps(payload.tags),
            payload.supersedes_id,
            payload.source.value,
            now,
            now,
            decided,
        ),
    )
    return get_adr(conn, adr_id)


def update_adr(
    conn: sqlite3.Connection, adr_id: str, payload: ProjectAdrUpdate
) -> ProjectAdr:
    existing = get_adr(conn, adr_id)
    fields = payload.model_dump(exclude_unset=True, exclude={"source"})
    sets: list[str] = []
    args: list[object] = []
    for key, value in fields.items():
        if key == "tags":
            sets.append("tags_json = ?")
            args.append(_dumps(value or []))
        elif key == "status":
            sets.append("status = ?")
            args.append(ProjectAdrStatus(value).value)
        else:
            sets.append(f"{key} = ?")
            args.append(value)
    if not sets:
        return existing
    sets.append("updated_at = ?")
    args.append(to_iso(utc_now()))
    args.append(adr_id)
    conn.execute(f"UPDATE project_adrs SET {', '.join(sets)} WHERE id = ?", args)
    return get_adr(conn, adr_id)


def delete_adr(conn: sqlite3.Connection, adr_id: str) -> None:
    get_adr(conn, adr_id)
    conn.execute("DELETE FROM project_adrs WHERE id = ?", (adr_id,))


def promote_adr(conn: sqlite3.Connection, adr_id: str) -> ProjectAdr:
    """Officially write an idea/draft/proposed ADR in: assign the next
    per-project number, mark it accepted, and stamp the decision time. If it
    supersedes another ADR, mark that one superseded (history preserved)."""

    adr = get_adr(conn, adr_id)
    if adr.status not in _PROMOTABLE_FROM:
        # Already settled (accepted/rejected/superseded) -- nothing to do.
        return adr
    now = to_iso(utc_now())
    number = adr.number or _next_adr_number(conn, adr.project_id)
    conn.execute(
        "UPDATE project_adrs SET status = ?, number = ?, decided_at = ?, updated_at = ? "
        "WHERE id = ?",
        (ProjectAdrStatus.ACCEPTED.value, number, now, now, adr_id),
    )
    if adr.supersedes_id:
        conn.execute(
            "UPDATE project_adrs SET status = ?, updated_at = ? WHERE id = ? AND project_id = ?",
            (ProjectAdrStatus.SUPERSEDED.value, now, adr.supersedes_id, adr.project_id),
        )
    return get_adr(conn, adr_id)


def _next_adr_number(conn: sqlite3.Connection, project_id: str) -> int:
    row = conn.execute(
        "SELECT MAX(number) AS n FROM project_adrs WHERE project_id = ?",
        (project_id,),
    ).fetchone()
    current = row["n"] if row and row["n"] is not None else 0
    return int(current) + 1


# ── Backlog CRUD ─────────────────────────────────────────────────────────────


def list_backlog(conn: sqlite3.Connection, project_id: str) -> list[ProjectBacklogItem]:
    rows = conn.execute(
        "SELECT * FROM project_backlog WHERE project_id = ? "
        "ORDER BY order_index, created_at",
        (project_id,),
    ).fetchall()
    return [_row_to_backlog(row) for row in rows]


def get_backlog_item(conn: sqlite3.Connection, item_id: str) -> ProjectBacklogItem:
    row = conn.execute("SELECT * FROM project_backlog WHERE id = ?", (item_id,)).fetchone()
    if row is None:
        raise not_found("project_backlog_item", item_id)
    return _row_to_backlog(row)


def create_backlog_item(
    conn: sqlite3.Connection, project_id: str, payload: ProjectBacklogItemCreate
) -> ProjectBacklogItem:
    now = to_iso(utc_now())
    item_id = _new_id()
    completed = now if payload.status == ProjectBacklogStatus.DONE else None
    conn.execute(
        "INSERT INTO project_backlog "
        "(id, project_id, title, body_md, status, priority, order_index, source, "
        " created_at, updated_at, completed_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            item_id,
            project_id,
            payload.title.strip(),
            payload.body_md,
            payload.status.value,
            payload.priority.value,
            payload.order_index,
            payload.source.value,
            now,
            now,
            completed,
        ),
    )
    return get_backlog_item(conn, item_id)


def update_backlog_item(
    conn: sqlite3.Connection, item_id: str, payload: ProjectBacklogItemUpdate
) -> ProjectBacklogItem:
    existing = get_backlog_item(conn, item_id)
    fields = payload.model_dump(exclude_unset=True, exclude={"source"})
    sets: list[str] = []
    args: list[object] = []
    now = to_iso(utc_now())
    for key, value in fields.items():
        if key in {"status", "priority"}:
            sets.append(f"{key} = ?")
            args.append(value.value if isinstance(value, Enum) else value)
        else:
            sets.append(f"{key} = ?")
            args.append(value)
    # Keep completed_at consistent with status transitions.
    if "status" in fields:
        new_status = ProjectBacklogStatus(fields["status"])
        if new_status == ProjectBacklogStatus.DONE and existing.completed_at is None:
            sets.append("completed_at = ?")
            args.append(now)
        elif new_status != ProjectBacklogStatus.DONE and existing.completed_at is not None:
            sets.append("completed_at = ?")
            args.append(None)
    if not sets:
        return existing
    sets.append("updated_at = ?")
    args.append(now)
    args.append(item_id)
    conn.execute(f"UPDATE project_backlog SET {', '.join(sets)} WHERE id = ?", args)
    return get_backlog_item(conn, item_id)


def delete_backlog_item(conn: sqlite3.Connection, item_id: str) -> None:
    get_backlog_item(conn, item_id)
    conn.execute("DELETE FROM project_backlog WHERE id = ?", (item_id,))


# ── Version CRUD ─────────────────────────────────────────────────────────────


def list_versions(conn: sqlite3.Connection, project_id: str) -> list[ProjectVersion]:
    rows = conn.execute(
        "SELECT * FROM project_versions WHERE project_id = ? ORDER BY created_at DESC",
        (project_id,),
    ).fetchall()
    return [_row_to_version(row) for row in rows]


def get_version(conn: sqlite3.Connection, version_id: str) -> ProjectVersion:
    row = conn.execute(
        "SELECT * FROM project_versions WHERE id = ?", (version_id,)
    ).fetchone()
    if row is None:
        raise not_found("project_version", version_id)
    return _row_to_version(row)


def create_version(
    conn: sqlite3.Connection, project_id: str, payload: ProjectVersionCreate
) -> ProjectVersion:
    now = to_iso(utc_now())
    version_id = _new_id()
    conn.execute(
        "INSERT INTO project_versions "
        "(id, project_id, version, released_at, changes_md, source, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            version_id,
            project_id,
            payload.version.strip(),
            payload.released_at,
            payload.changes_md,
            payload.source.value,
            now,
            now,
        ),
    )
    return get_version(conn, version_id)


def update_version(
    conn: sqlite3.Connection, version_id: str, payload: ProjectVersionUpdate
) -> ProjectVersion:
    existing = get_version(conn, version_id)
    fields = payload.model_dump(exclude_unset=True, exclude={"source"})
    sets: list[str] = []
    args: list[object] = []
    for key, value in fields.items():
        sets.append(f"{key} = ?")
        args.append(value)
    if not sets:
        return existing
    sets.append("updated_at = ?")
    args.append(to_iso(utc_now()))
    args.append(version_id)
    conn.execute(f"UPDATE project_versions SET {', '.join(sets)} WHERE id = ?", args)
    return get_version(conn, version_id)


def delete_version(conn: sqlite3.Connection, version_id: str) -> None:
    get_version(conn, version_id)
    conn.execute("DELETE FROM project_versions WHERE id = ?", (version_id,))


# ── Bundle ───────────────────────────────────────────────────────────────────


def get_records(conn: sqlite3.Connection, project_id: str) -> ProjectRecords:
    return ProjectRecords(
        project_id=project_id,
        adrs=list_adrs(conn, project_id),
        backlog=list_backlog(conn, project_id),
        versions=list_versions(conn, project_id),
    )
