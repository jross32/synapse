"""Shared Pydantic models — the canonical schema (Contract #8).

Every managed entity (Project, Tool, ManagedProcess, Tunnel, etc.) inherits
from :class:`BaseEntity` so they all carry the live-status fields required
by Contract #2.

When ``scripts/gen-types.ps1`` runs, these are exported to
``renderer/lib/generated-types.ts`` — the UI imports those types instead of
hand-maintaining parallel ones.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


def _utcnow() -> datetime:
    return datetime.now(UTC)


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

    @model_validator(mode="before")
    @classmethod
    def _coalesce_default_timestamps(cls, values: Any) -> Any:
        # When a brand-new entity is instantiated with no explicit timestamps,
        # ``created_at == updated_at == last_transition_at`` is part of the
        # Contract #2 invariant ("nothing has changed yet"). Three independent
        # ``default_factory`` calls drift by a few microseconds on faster
        # clocks and break that invariant, so coalesce them here.
        if not isinstance(values, dict):
            return values
        now = _utcnow()
        for key in ("created_at", "updated_at", "last_transition_at"):
            values.setdefault(key, now)
        return values


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
        default_factory=lambda: list(range(1, 29)),
        description="Design contracts honoured by this daemon build (Contracts #1–#28).",
    )


# ── Tool plugin system (Milestone F · v0.1.9) ────────────────────────────────
#
# A tool is a folder under ``tools/`` carrying a ``manifest.json``. The manifest
# is pure data: the daemon never imports code from a tool folder. Actions are
# executed by *curated built-in handlers* compiled into the daemon (the hybrid
# model — see ToolRegistry). This keeps "drop in a folder" plugin ergonomics
# without ever running untrusted Python.


class ToolFieldType(str, Enum):
    """Input field kinds a tool manifest can declare."""

    NUMBER = "number"
    TEXT = "text"
    PATH = "path"
    BOOLEAN = "boolean"


class ToolField(BaseModel):
    """One input a tool collects before an action runs (Contract #1)."""

    key: str
    type: ToolFieldType = ToolFieldType.TEXT
    label: str
    required: bool = False
    placeholder: str | None = None
    min: int | None = None
    max: int | None = None
    default: Any = None
    help: str | None = None


class ToolActionScope(str, Enum):
    """Whether an action acts on the whole tool or one live instance."""

    TOOL = "tool"  # e.g. "Open a new tunnel" — always a card-level button
    ITEM = "item"  # e.g. "Close this tunnel" — rendered per instance row


class ToolAction(BaseModel):
    """A button a tool card exposes.

    ``handler`` is a curated reference (``"<tool-id>:<verb>"``). The daemon
    resolves it against its compiled-in handler table — an unknown reference
    is refused at load time, never imported.

    ``scope`` decides where the button renders: ``tool`` actions are the
    card's own buttons; ``item`` actions render once per live instance (a
    Cloudtap tunnel, a terminal session, …) and carry that instance's id.

    ``available_in`` lists the statuses in which the action is enabled —
    checked against the tool status for ``tool`` actions, or the instance
    status for ``item`` actions. Empty (the default) means "always enabled".
    """

    id: str
    label: str
    handler: str | None = None
    primary: bool = False
    danger: bool = False
    scope: ToolActionScope = ToolActionScope.TOOL
    available_in: list[EntityStatus] = Field(default_factory=list)
    # Declarative tier (v0.1.22 · ADR-0001 step 2). When set, the daemon runs
    # the named vetted primitive (e.g. "process.spawn", "url.open") with
    # params + the user's field values -- no Python handler needed. That's
    # how a third-party tool can ship as pure manifest JSON.
    primitive: str | None = None
    params: dict[str, Any] = Field(default_factory=dict)


class ToolManifest(BaseModel):
    """The parsed, validated ``tools/<id>/manifest.json`` (Contract #8)."""

    id: str
    name: str
    category: str = "tools"
    icon: str = "wrench"
    description: str = ""
    version: str = "0.1.0"
    fields: list[ToolField] = Field(default_factory=list)
    actions: list[ToolAction] = Field(default_factory=list)
    # True once a compiled-in handler has been bound; a manifest with no
    # backing handler still lists but its actions are inert.
    runnable: bool = False


class ToolItem(BaseModel):
    """One live instance owned by a multi-instance tool (Contract #2).

    Cloudtap is the first such tool: each open tunnel is a ToolItem. A
    single-shot tool simply leaves :attr:`ToolState.items` empty.
    """

    id: str
    label: str
    status: EntityStatus = EntityStatus.IDLE
    result: dict[str, Any] = Field(default_factory=dict)
    message: str | None = None
    last_error: ErrorRef | None = None
    created_at: datetime = Field(default_factory=_utcnow)


class ToolState(BaseModel):
    """Live state of one tool — what the card renders (Contract #2).

    ``items`` carries the live instances of a multi-instance tool; each gets
    its own row + per-instance action buttons in the UI. Single-shot tools
    leave it empty and use ``status`` / ``result`` directly.
    """

    tool_id: str
    status: EntityStatus = EntityStatus.IDLE
    fields: dict[str, Any] = Field(default_factory=dict)
    result: dict[str, Any] = Field(default_factory=dict)
    items: list[ToolItem] = Field(default_factory=list)
    message: str | None = None
    last_error: ErrorRef | None = None
    updated_at: datetime = Field(default_factory=_utcnow)


# Convenience export so consumers can do ``from synapse_daemon.models import *``.
__all__ = [
    "AuditSource",
    "BaseEntity",
    "EntityStatus",
    "ErrorRef",
    "HealthResponse",
    "StateTransition",
    "ToolAction",
    "ToolActionScope",
    "ToolField",
    "ToolFieldType",
    "ToolItem",
    "ToolManifest",
    "ToolState",
]


def model_registry() -> dict[str, type[BaseModel]]:
    """Return the models that ``scripts/gen-types.ps1`` should export to TS.

    Update this list whenever a new shared model is added so the type
    generator picks it up automatically.
    """

    from . import errors as _errors
    from . import agent_squads as _agents
    from . import assistant as _assistant
    from . import model_market as _market
    from . import review as _review
    from . import project_records as _records
    from . import health as _health
    from . import notifications as _notif
    from . import profile as _profile
    from . import resources as _res
    from . import restart_policy as _restart
    from . import secrets as _secrets
    from . import snapshot as _snap

    return {
        # Round 1
        "ErrorEnvelope": _errors.ErrorEnvelope,
        "EntityStatus": EntityStatus,  # type: ignore[dict-item]
        "AuditSource": AuditSource,  # type: ignore[dict-item]
        "ErrorRef": ErrorRef,
        "BaseEntity": BaseEntity,
        "StateTransition": StateTransition,
        "HealthResponse": HealthResponse,
        # Round 2
        "HealthState": _health.HealthState,  # type: ignore[dict-item]
        "HealthProbe": _health.HealthProbe,
        "HealthSnapshot": _health.HealthSnapshot,
        "RestartPolicy": _restart.RestartPolicy,
        "ResourceSnapshot": _res.ResourceSnapshot,
        "ResourceCaps": _res.ResourceCaps,
        "Notification": _notif.Notification,
        "NotificationLevel": _notif.NotificationLevel,  # type: ignore[dict-item]
        "EnvVar": _secrets.EnvVar,
        "SnapshotPayload": _snap.SnapshotPayload,
        "RestoreReport": _snap.RestoreReport,
        # Sessions-centric AI squads (v0.1.36-dev)
        "AgentVisibility": _agents.AgentVisibility,  # type: ignore[dict-item]
        "AgentContextMode": _agents.AgentContextMode,  # type: ignore[dict-item]
        "AgentRoleTier": _agents.AgentRoleTier,  # type: ignore[dict-item]
        "AgentSquadStatus": _agents.AgentSquadStatus,  # type: ignore[dict-item]
        "AgentWorkItemStatus": _agents.AgentWorkItemStatus,  # type: ignore[dict-item]
        "AgentRoleTemplate": _agents.AgentRoleTemplate,
        "AgentSquad": _agents.AgentSquad,
        "AgentWorkItem": _agents.AgentWorkItem,
        "AgentSquadDetail": _agents.AgentSquadDetail,
        # Per-project decision records, backlog, versions (ADR-0011)
        "ProjectAdrStatus": _records.ProjectAdrStatus,  # type: ignore[dict-item]
        "ProjectBacklogStatus": _records.ProjectBacklogStatus,  # type: ignore[dict-item]
        "ProjectBacklogPriority": _records.ProjectBacklogPriority,  # type: ignore[dict-item]
        "ProjectAdr": _records.ProjectAdr,
        "ProjectBacklogItem": _records.ProjectBacklogItem,
        "ProjectVersion": _records.ProjectVersion,
        "ProjectRecords": _records.ProjectRecords,
        # Local-LLM assistant (ADR-0014)
        "AssistantRole": _assistant.AssistantRole,  # type: ignore[dict-item]
        "OllamaModelInfo": _assistant.OllamaModelInfo,
        "AssistantSettings": _assistant.AssistantSettings,
        "AssistantStatus": _assistant.AssistantStatus,
        "AssistantMessage": _assistant.AssistantMessage,
        "AssistantChat": _assistant.AssistantChat,
        "AssistantChatDetail": _assistant.AssistantChatDetail,
        # Local-model marketplace (ADR-0014 Phase M)
        "ModelCatalogEntry": _market.ModelCatalogEntry,
        "ModelCatalog": _market.ModelCatalog,
        "ModelPullState": _market.ModelPullState,
        "ModelPullList": _market.ModelPullList,
        # Needs-Review / approval inbox (ADR-0016 Phase R)
        "ReviewKind": _review.ReviewKind,  # type: ignore[dict-item]
        "ReviewItem": _review.ReviewItem,
        "ReviewInbox": _review.ReviewInbox,
        # Profile hub + portable catalog state
        "LinkedIdentity": _profile.LinkedIdentity,
        "HostPresence": _profile.HostPresence,
        "ServiceConnection": _profile.ServiceConnection,
        "CatalogPreferenceItem": _profile.CatalogPreferenceItem,
        "CatalogPreferenceState": _profile.CatalogPreferenceState,
        "ProfilePreferences": _profile.ProfilePreferences,
        "ProfileSummary": _profile.ProfileSummary,
        # Tool plugin system (v0.1.9 · multi-instance v0.1.9.5)
        "ToolFieldType": ToolFieldType,  # type: ignore[dict-item]
        "ToolField": ToolField,
        "ToolActionScope": ToolActionScope,  # type: ignore[dict-item]
        "ToolAction": ToolAction,
        "ToolManifest": ToolManifest,
        "ToolItem": ToolItem,
        "ToolState": ToolState,
    }
