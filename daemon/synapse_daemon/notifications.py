"""Native system notifications (Contract #22).

Daemon emits a structured ``v1.notification`` WebSocket event whenever a
notification-worthy state change occurs. Electron renders these as Windows
toasts; mobile users opt in to Web Push separately (v0.2+).

Per-event opt-out is stored in the ``notification_preferences`` SQLite table.
Never globally muted by default — the user explicitly opts each event-kind in
or out from the UI.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field

from .time_utils import utc_now


class NotificationLevel(str, Enum):
    INFO = "info"
    SUCCESS = "success"
    WARNING = "warning"
    ERROR = "error"


# Canonical event kinds. Any new emission must use a name from this set OR
# add itself here in the same commit.
KNOWN_EVENT_KINDS: frozenset[str] = frozenset(
    {
        "process.crashed",
        "process.over_budget",
        "project.health_unhealthy",
        "project.health_recovered",
        "project.restart_attempted",
        "project.restart_exhausted",
        "tunnel.live",
        "tunnel.dropped",
        "scheduled.fired",
        "scheduled.failed",
        "manifest.error",
        "daemon.started",
    }
)


class Notification(BaseModel):
    """One emitted notification."""

    event_kind: str = Field(..., description="Canonical event kind; see KNOWN_EVENT_KINDS.")
    level: NotificationLevel
    title: str
    body: str
    entity_type: str | None = None
    entity_id: str | None = None
    timestamp_utc: datetime = Field(default_factory=utc_now)
    action_url: str | None = Field(
        default=None,
        description="Optional UI route the user lands on when clicking the toast.",
    )


def assert_known_event_kind(kind: str) -> None:
    if kind not in KNOWN_EVENT_KINDS:
        raise ValueError(
            f"Unknown notification event_kind '{kind}'. "
            "Add it to notifications.KNOWN_EVENT_KINDS in the same commit "
            "that introduces the emission."
        )
