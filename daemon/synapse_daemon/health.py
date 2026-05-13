"""Health-check protocol per project (Contract #17).

Every project carries one ``HealthProbe``; the daemon polls it on a separate
cadence from process liveness so the UI can render a second state-pill:
"alive but unhealthy". Skeleton only — actual polling loop wires in during
Milestone E.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field

from .time_utils import utc_now


class HealthState(str, Enum):
    UNKNOWN = "unknown"
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


class HealthProbe(BaseModel):
    """Declarative health probe — one per project."""

    kind: Literal["none", "http", "tcp", "command"] = "none"
    target: str | None = Field(
        default=None,
        description="URL for http, port number for tcp, shell command for command.",
    )
    interval_seconds: int = Field(default=15, ge=1, le=3600)
    timeout_seconds: int = Field(default=5, ge=1, le=60)
    expect_status: int | None = Field(
        default=200,
        description="HTTP status to consider healthy. Only meaningful when kind='http'.",
    )
    consecutive_failures_to_unhealthy: int = Field(default=3, ge=1, le=20)


class HealthSnapshot(BaseModel):
    """Latest probe result for one project."""

    project_id: str
    state: HealthState = HealthState.UNKNOWN
    last_probed_at: datetime | None = None
    last_state_change_at: datetime = Field(default_factory=utc_now)
    consecutive_failures: int = 0
    last_error: str | None = None


def is_terminal(state: HealthState) -> bool:
    """A terminal health state (other than ``UNKNOWN``) — used by UI badges."""

    return state in (HealthState.HEALTHY, HealthState.UNHEALTHY)
