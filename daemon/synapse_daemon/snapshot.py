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
