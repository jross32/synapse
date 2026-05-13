"""Project registry — Pydantic models + SQLite CRUD (Contracts #1, #2, #10).

A *project* is a launchable app under Synapse's management (e.g. `wbscrper`,
a future Ollama chat server). Every project carries the universal live-status
fields from :class:`BaseEntity` plus its launch metadata.

This module owns:

  • :class:`Project`     — the Pydantic shape, mirrored to TS via gen-types.
  • CRUD functions       — ``list_projects`` / ``get`` / ``create`` / ``update``
                           / ``soft_delete`` / ``set_status`` / ``set_error``.
  • Validation helpers   — IDs are kebab-case (Contract #10).

Persistent state lives in the ``projects`` table created by migration 001 and
extended by 002 (health probe, restart policy, resource caps).
"""

from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from .errors import SynapseError, conflict, invalid, not_found
from .health import HealthProbe, HealthState
from .models import EntityStatus, ErrorRef
from .resources import ResourceCaps
from .restart_policy import RestartPolicy
from .secrets import EnvVar
from .time_utils import from_iso, to_iso, utc_now

ID_PATTERN = re.compile(r"^[a-z][a-z0-9-]*[a-z0-9]$|^[a-z]$")


class Project(BaseModel):
    """A managed launchable app."""

    id: str
    name: str
    path: str = Field(..., description="Working directory the launch_cmd is invoked from.")
    launch_cmd: str = Field(..., description="Shell command, e.g. 'npm start'.")
    env: list[EnvVar] = Field(default_factory=list)
    icon: str | None = None
    thumbnail: str | None = None
    description: str | None = None
    category: str | None = None
    health: HealthProbe = Field(default_factory=HealthProbe)
    restart: RestartPolicy = Field(default_factory=RestartPolicy)
    resource_caps: ResourceCaps = Field(default_factory=ResourceCaps)
    expected_port: int | None = None

    # Live-status (Contract #2) — always returned, written by process_manager.
    status: EntityStatus = EntityStatus.IDLE
    last_error: ErrorRef | None = None
    current_health: HealthState = HealthState.UNKNOWN
    last_health_at: datetime | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    last_transition_at: datetime = Field(default_factory=utc_now)

    @field_validator("id")
    @classmethod
    def _id_kebab(cls, value: str) -> str:
        if not ID_PATTERN.match(value):
            raise ValueError(
                f"Project id '{value}' is not kebab-case. Use lower-case letters, "
                "digits, and single hyphens; must start with a letter and end alphanumeric."
            )
        return value


class ProjectUpdate(BaseModel):
    """Subset of fields editable via PATCH. Everything is optional."""

    name: str | None = None
    path: str | None = None
    launch_cmd: str | None = None
    icon: str | None = None
    thumbnail: str | None = None
    description: str | None = None
    category: str | None = None
    health: HealthProbe | None = None
    restart: RestartPolicy | None = None
    resource_caps: ResourceCaps | None = None
    expected_port: int | None = None
    env: list[EnvVar] | None = None


# ── row helpers ──────────────────────────────────────────────────────────


def _row_to_project(row: sqlite3.Row) -> Project:
    """Hydrate a Project from a sqlite3.Row from the ``projects`` table."""

    return Project(
        id=row["id"],
        name=row["name"],
        path=row["path"],
        launch_cmd=row["launch_cmd"],
        env=_loads_envvars(row["env_json"]),
        icon=row["icon"],
        thumbnail=row["thumbnail"],
        description=row["description"],
        category=row["category"],
        health=_loads_health(row["health_probe_json"]),
        restart=_loads_restart(row["restart_policy_json"]),
        resource_caps=ResourceCaps(
            max_rss_mb=row["max_rss_mb"], max_cpu_percent=row["max_cpu_percent"]
        ),
        expected_port=row["expected_port"],
        status=EntityStatus(row["status"]),
        last_error=_error_ref(row["last_error_code"], row["last_error_msg"]),
        current_health=HealthState(row["current_health"]),
        last_health_at=from_iso(row["last_health_at"]) if row["last_health_at"] else None,
        created_at=from_iso(row["created_at"]),
        updated_at=from_iso(row["updated_at"]),
        last_transition_at=from_iso(row["last_transition_at"]),
    )


def _loads_envvars(payload: str | None) -> list[EnvVar]:
    if not payload:
        return []
    raw = json.loads(payload)
    return [EnvVar(**item) for item in raw]


def _loads_health(payload: str | None) -> HealthProbe:
    if not payload:
        return HealthProbe()
    return HealthProbe(**json.loads(payload))


def _loads_restart(payload: str | None) -> RestartPolicy:
    if not payload:
        return RestartPolicy()
    return RestartPolicy(**json.loads(payload))


def _error_ref(code: str | None, msg: str | None) -> ErrorRef | None:
    if not code or not msg:
        return None
    return ErrorRef(code=code, message=msg)


# ── CRUD ─────────────────────────────────────────────────────────────────


def list_projects(conn: sqlite3.Connection, *, include_deleted: bool = False) -> list[Project]:
    sql = "SELECT * FROM projects"
    if not include_deleted:
        sql += " WHERE deleted_at IS NULL"
    sql += " ORDER BY name"
    return [_row_to_project(row) for row in conn.execute(sql).fetchall()]


def get(conn: sqlite3.Connection, project_id: str) -> Project:
    row = conn.execute(
        "SELECT * FROM projects WHERE id = ? AND deleted_at IS NULL", (project_id,)
    ).fetchone()
    if row is None:
        raise not_found("project", project_id)
    return _row_to_project(row)


def get_or_none(conn: sqlite3.Connection, project_id: str) -> Project | None:
    try:
        return get(conn, project_id)
    except SynapseError:
        return None


def create(conn: sqlite3.Connection, project: Project) -> Project:
    """Insert a fresh project row. Raises ``project.conflict`` if id is taken."""

    existing = conn.execute(
        "SELECT id, deleted_at FROM projects WHERE id = ?", (project.id,)
    ).fetchone()
    if existing is not None:
        if existing["deleted_at"] is None:
            raise conflict("project", f"A project with id '{project.id}' already exists.")
        # Soft-deleted; restore by clearing deleted_at and overwriting.
        conn.execute("DELETE FROM projects WHERE id = ?", (project.id,))

    now = utc_now()
    project = project.model_copy(update={
        "created_at": now, "updated_at": now, "last_transition_at": now,
    })

    conn.execute(
        """
        INSERT INTO projects (
            id, name, path, launch_cmd, env_json, icon, thumbnail, description,
            category, health_url, expected_port, status, last_error_code,
            last_error_msg, created_at, updated_at, last_transition_at,
            health_probe_json, restart_policy_json, max_rss_mb, max_cpu_percent,
            current_health, last_health_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            project.id, project.name, project.path, project.launch_cmd,
            json.dumps([e.model_dump() for e in project.env]),
            project.icon, project.thumbnail, project.description, project.category,
            None, project.expected_port, project.status.value,
            project.last_error.code if project.last_error else None,
            project.last_error.message if project.last_error else None,
            to_iso(project.created_at), to_iso(project.updated_at),
            to_iso(project.last_transition_at),
            json.dumps(project.health.model_dump()),
            json.dumps(project.restart.model_dump()),
            project.resource_caps.max_rss_mb, project.resource_caps.max_cpu_percent,
            project.current_health.value,
            to_iso(project.last_health_at) if project.last_health_at else None,
        ),
    )
    return project


def update(conn: sqlite3.Connection, project_id: str, patch: ProjectUpdate) -> Project:
    """Apply a partial update; returns the post-update project."""

    from datetime import timedelta

    current = get(conn, project_id)
    updates = patch.model_dump(exclude_none=True)
    if not updates:
        raise invalid("project", "Empty update — no fields to change.")

    next_project = current.model_copy(update=updates)
    next_updated_at = max(utc_now(), current.updated_at + timedelta(microseconds=1))
    next_project = next_project.model_copy(update={"updated_at": next_updated_at})

    conn.execute(
        """
        UPDATE projects SET
          name = ?, path = ?, launch_cmd = ?, env_json = ?, icon = ?,
          thumbnail = ?, description = ?, category = ?, expected_port = ?,
          updated_at = ?,
          health_probe_json = ?, restart_policy_json = ?,
          max_rss_mb = ?, max_cpu_percent = ?
        WHERE id = ?
        """,
        (
            next_project.name, next_project.path, next_project.launch_cmd,
            json.dumps([e.model_dump() for e in next_project.env]),
            next_project.icon, next_project.thumbnail, next_project.description,
            next_project.category, next_project.expected_port,
            to_iso(next_project.updated_at),
            json.dumps(next_project.health.model_dump()),
            json.dumps(next_project.restart.model_dump()),
            next_project.resource_caps.max_rss_mb,
            next_project.resource_caps.max_cpu_percent,
            project_id,
        ),
    )
    return next_project


def soft_delete(conn: sqlite3.Connection, project_id: str) -> None:
    current = get(conn, project_id)
    if current.status not in (EntityStatus.IDLE, EntityStatus.STOPPED, EntityStatus.ERROR):
        raise conflict(
            "project",
            f"Project '{project_id}' is currently {current.status.value}; "
            "stop it before deleting.",
        )
    conn.execute(
        "UPDATE projects SET deleted_at = ? WHERE id = ?",
        (to_iso(utc_now()), project_id),
    )


# ── state writers used by the process manager ────────────────────────────


def set_status(
    conn: sqlite3.Connection,
    project_id: str,
    *,
    status: EntityStatus,
    error: ErrorRef | None = None,
) -> Project:
    """Move a project into ``status``; clears or sets ``last_error`` accordingly.

    ``last_transition_at`` always advances when the status itself changes —
    even on coarse clocks (Windows microsecond ticks) we guarantee strict
    monotonicity by nudging forward 1 µs if the wall clock didn't move.
    """

    from datetime import timedelta

    current = get(conn, project_id)
    now = utc_now()
    if current.status != status:
        transition_at = max(now, current.last_transition_at + timedelta(microseconds=1))
    else:
        transition_at = current.last_transition_at
    updated_at = max(now, current.updated_at + timedelta(microseconds=1))
    conn.execute(
        """
        UPDATE projects SET
          status = ?, last_error_code = ?, last_error_msg = ?,
          updated_at = ?, last_transition_at = ?
        WHERE id = ?
        """,
        (
            status.value,
            error.code if error else None,
            error.message if error else None,
            to_iso(updated_at),
            to_iso(transition_at),
            project_id,
        ),
    )
    return get(conn, project_id)


def set_health(
    conn: sqlite3.Connection,
    project_id: str,
    *,
    state: HealthState,
) -> Project:
    """Record the latest probe result for a project."""

    now = utc_now()
    conn.execute(
        """
        UPDATE projects SET
          current_health = ?, last_health_at = ?, updated_at = ?
        WHERE id = ?
        """,
        (state.value, to_iso(now), to_iso(now), project_id),
    )
    return get(conn, project_id)


# Convenience export.
Visibility = Literal["live", "deleted", "all"]


def list_by_visibility(conn: sqlite3.Connection, vis: Visibility) -> list[Project]:
    if vis == "live":
        return list_projects(conn, include_deleted=False)
    if vis == "all":
        return list_projects(conn, include_deleted=True)
    return [
        _row_to_project(row)
        for row in conn.execute(
            "SELECT * FROM projects WHERE deleted_at IS NOT NULL ORDER BY name"
        ).fetchall()
    ]


def model_dump_for_client(project: Project) -> dict[str, Any]:
    """Serialise with secrets redacted (Contract #25) — used by REST handlers."""

    from .secrets import redact

    data = project.model_dump()
    data["env"] = [e.model_dump() for e in redact(project.env)]
    return data
