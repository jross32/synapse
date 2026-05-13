"""Shared Pydantic models — the canonical schema (Contract #8).

Every managed entity (Project, Tool, ManagedProcess, Tunnel, etc.) inherits
from :class:`BaseEntity` so they all carry the live-status fields required
by Contract #2.

When ``scripts/gen-types.ps1`` runs, these are exported to
``renderer/lib/generated-types.ts`` — the UI imports those types instead of
hand-maintaining parallel ones.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class EntityStatus(str, Enum):
    """Universal state machine for any managed entity (Contract #2)."""

    IDLE = "idle"
    LAUNCHING = "launching"
    LAUNCHED = "launched"
    STOPPING = "stopping"
    STOPPED = "stopped"
    ERROR = "error"


class AuditSource(str, Enum):
    """Where a state-changing action originated (Contract #11)."""

    DESKTOP = "desktop"
    MOBILE = "mobile"
    TRAY = "tray"
    CLI = "cli"
    AUTO = "auto"


class BaseEntity(BaseModel):
    """Every managed entity carries these fields (Contracts #2, #11).

    Subclasses add their own data (e.g. ``Project.path``, ``Tunnel.public_url``)
    but never override these.
    """

    model_config = ConfigDict(use_enum_values=False, validate_assignment=True)

    id: str = Field(..., description="Kebab-case unique identifier (Contract #10).")
    name: str = Field(..., description="User-facing display name. Editable from the UI (Contract #1).")
    status: EntityStatus = Field(default=EntityStatus.IDLE)
    last_error: ErrorRef | None = Field(
        default=None,
        description="Last error encountered, if any. Cleared on successful action.",
    )
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)
    last_transition_at: datetime = Field(
        default_factory=_utcnow,
        description="When the status field last changed. Drives the UI history strip.",
    )


class ErrorRef(BaseModel):
    """Compact error record stored on an entity's ``last_error`` field.

    The full ``ErrorEnvelope`` is in the audit log; this is the summary the UI
    renders inline on the tile per Contract #2.
    """

    code: str
    message: str
    occurred_at: datetime = Field(default_factory=_utcnow)


# Forward-reference resolution for BaseEntity.last_error
BaseEntity.model_rebuild()


class StateTransition(BaseModel):
    """One step in an entity's status history (Contract #2 history strip)."""

    entity_id: str
    from_status: EntityStatus
    to_status: EntityStatus
    at: datetime = Field(default_factory=_utcnow)
    source: AuditSource = AuditSource.AUTO
    note: str | None = None


class HealthResponse(BaseModel):
    """Returned by ``GET /api/v1/health`` (Contract #7)."""

    ok: bool
    version: str
    started_at: datetime
    contracts: list[int] = Field(
        default_factory=lambda: list(range(1, 17)),
        description="Design contracts honoured by this daemon build (Contracts #1–#16).",
    )


# Convenience export so consumers can do ``from synapse_daemon.models import *``.
__all__ = [
    "AuditSource",
    "BaseEntity",
    "EntityStatus",
    "ErrorRef",
    "HealthResponse",
    "StateTransition",
]


def model_registry() -> dict[str, type[BaseModel]]:
    """Return the models that ``scripts/gen-types.ps1`` should export to TS.

    Update this list whenever a new shared model is added so the type
    generator picks it up automatically.
    """

    from . import errors as _errors

    return {
        "ErrorEnvelope": _errors.ErrorEnvelope,
        "EntityStatus": EntityStatus,  # type: ignore[dict-item]
        "AuditSource": AuditSource,  # type: ignore[dict-item]
        "ErrorRef": ErrorRef,
        "BaseEntity": BaseEntity,
        "StateTransition": StateTransition,
        "HealthResponse": HealthResponse,
    }
