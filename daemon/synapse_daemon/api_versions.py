"""API versioning constants (Contract #7).

Every REST endpoint mounts under ``API_PREFIX``; every WebSocket event name is
prefixed with ``WS_EVENT_PREFIX``. Bumping these requires a new prefix and a
migration entry in ``docs/api-changes.md`` — never break v1 in place.
"""

from __future__ import annotations

from typing import Final

API_VERSION: Final[str] = "v1"
API_PREFIX: Final[str] = f"/api/{API_VERSION}"
WS_EVENT_PREFIX: Final[str] = API_VERSION  # event names: "v1.entity.event"


def event_name(entity: str, verb: str) -> str:
    """Format a WebSocket event name per the naming convention (Contract #10).

    >>> event_name("project", "launched")
    'v1.project.launched'
    """
    return f"{WS_EVENT_PREFIX}.{entity}.{verb}"
