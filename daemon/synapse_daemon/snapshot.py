"""Snapshot / restore (Contract #28).

``POST /api/v1/snapshot`` exports daemon state to a single JSON blob:

  • Synapse version + schema migration number (so restore can refuse incompat).
  • All projects, tools, and settings.
  • Tail of the audit log (last N rows).
  • **Secrets are NOT included** — they're DPAPI-bound to the daemon's user
    account and don't survive a move. Restore surfaces the list of secret keys
    that need to be re-entered.

``POST /api/v1/restore`` accepts the same shape and either creates fresh
entities or merges by id (caller chooses).

This module owns the SnapshotPayload schema + pure helpers. Actual DB read
+ write happens in :mod:`synapse_daemon.storage` (Milestone B).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from . import __version__
from .time_utils import utc_now

SNAPSHOT_FORMAT_VERSION = 1


class SnapshotPayload(BaseModel):
    """The on-disk shape of a Synapse snapshot."""

    synapse_version: str = Field(default_factory=lambda: __version__)
    format_version: int = SNAPSHOT_FORMAT_VERSION
    schema_migration: int = Field(
        ..., description="Highest applied migration number at export time."
    )
    exported_at: datetime = Field(default_factory=utc_now)
    projects: list[dict[str, Any]] = Field(default_factory=list)
    tools: list[dict[str, Any]] = Field(default_factory=list)
    settings: dict[str, Any] = Field(default_factory=dict)
    audit_log_tail: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Last N audit rows for context; not authoritative.",
    )
    secret_keys: list[dict[str, str]] = Field(
        default_factory=list,
        description=(
            "Project + key pairs whose values were NOT exported. UI prompts "
            "the user to re-enter each one after a restore on a new machine."
        ),
    )


class RestoreReport(BaseModel):
    """Returned to the caller of POST /api/v1/restore."""

    projects_created: int = 0
    projects_updated: int = 0
    tools_created: int = 0
    tools_updated: int = 0
    settings_changed: int = 0
    secrets_needing_reentry: list[dict[str, str]] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


def assert_compatible(payload: SnapshotPayload, current_schema: int) -> list[str]:
    """Return a list of warnings; raise if outright incompatible."""

    warnings: list[str] = []
    if payload.format_version != SNAPSHOT_FORMAT_VERSION:
        raise ValueError(
            f"Snapshot format_version={payload.format_version} is incompatible "
            f"with daemon format_version={SNAPSHOT_FORMAT_VERSION}."
        )
    if payload.schema_migration > current_schema:
        raise ValueError(
            f"Snapshot was taken at schema_migration={payload.schema_migration} "
            f"but this daemon only has {current_schema} migrations applied. "
            "Upgrade the daemon first."
        )
    if payload.schema_migration < current_schema:
        warnings.append(
            f"Snapshot is from an older schema (migration {payload.schema_migration} < "
            f"current {current_schema}). Restore will apply current defaults to new columns."
        )
    return warnings


# ── build + restore ──────────────────────────────────────────────────────
#
# A snapshot's substance is the *project registry* — the thing worth porting
# to a new machine or keeping as a backup. Tool manifests live as files under
# ``tools/`` (not the DB), so they're exported for reference only and never
# restored. Secret env values are DPAPI-bound and never leave the daemon —
# only their keys travel, so the UI can prompt for re-entry.

_AUDIT_TAIL_DEFAULT = 50


def build_snapshot(storage: Any, *, tool_ids: list[str] | None = None) -> SnapshotPayload:
    """Read the live registry into a :class:`SnapshotPayload`."""

    from . import projects as projects_module

    conn = storage.conn
    rows = projects_module.list_projects(conn)

    projects = [projects_module.model_dump_for_client(p) for p in rows]
    secret_keys = [
        {"project_id": p.id, "key": ev.key}
        for p in rows
        for ev in p.env
        if ev.secret
    ]

    audit_tail: list[dict[str, Any]] = []
    try:
        cursor = conn.execute(
            "SELECT timestamp_utc, entity_type, entity_id, action, source, result "
            "FROM audit_log ORDER BY id DESC LIMIT ?",
            (_AUDIT_TAIL_DEFAULT,),
        )
        audit_tail = [dict(r) for r in cursor.fetchall()]
    except Exception:  # pragma: no cover — audit tail is best-effort context
        audit_tail = []

    return SnapshotPayload(
        schema_migration=storage.schema_migration(),
        projects=projects,
        tools=[{"id": t} for t in (tool_ids or [])],
        settings={},
        audit_log_tail=audit_tail,
        secret_keys=secret_keys,
    )


def _clean_project_dict(raw: dict[str, Any]) -> dict[str, Any]:
    """Normalise a snapshot project for restore.

    Resets runtime state (a restored project is never mid-launch) and blanks
    secret env values — those don't travel and must be re-entered.
    """

    data = dict(raw)
    data["status"] = "idle"
    data["last_error"] = None
    env = data.get("env")
    if isinstance(env, list):
        data["env"] = [
            {**e, "value": None} if isinstance(e, dict) and e.get("secret") else e
            for e in env
        ]
    return data


def restore_snapshot(storage: Any, payload: SnapshotPayload) -> RestoreReport:
    """Merge a snapshot into the live registry: create new, update existing.

    Non-destructive — nothing is deleted. Compatibility is the caller's job
    (run :func:`assert_compatible` first); its warnings should be passed in
    via ``payload`` already validated.
    """

    from . import projects as projects_module
    from .projects import Project, ProjectUpdate

    report = RestoreReport(secrets_needing_reentry=list(payload.secret_keys))

    for raw in payload.projects:
        pid = raw.get("id")
        if not pid:
            report.warnings.append("Skipped a project with no id.")
            continue
        cleaned = _clean_project_dict(raw)
        try:
            with storage.transaction() as conn:
                if projects_module.get_or_none(conn, pid) is None:
                    projects_module.create(conn, Project.model_validate(cleaned))
                    report.projects_created += 1
                else:
                    projects_module.update(conn, pid, ProjectUpdate.model_validate(cleaned))
                    report.projects_updated += 1
        except Exception as exc:
            report.warnings.append(f"Project '{pid}': {exc}")

    return report
