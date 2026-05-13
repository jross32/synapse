"""Resource observability (Contract #19).

Per-process CPU% + RSS MB samples broadcast on the daemon's heartbeat tick.
Optional soft caps on the project manifest raise an ``over-budget`` warning
(not a stop) — Synapse never kills a project for its own metrics.

Actual psutil sampling lands in :mod:`synapse_daemon.process_manager`
(Milestone E). This module owns the data shape + cap logic only.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from .time_utils import utc_now


class ResourceSnapshot(BaseModel):
    """One sample for one managed process."""

    entity_type: str
    entity_id: str
    pid: int
    cpu_percent: float = Field(ge=0.0)
    rss_mb: float = Field(ge=0.0)
    sampled_at: datetime = Field(default_factory=utc_now)


class ResourceCaps(BaseModel):
    """Optional soft caps on a project manifest."""

    max_rss_mb: int | None = Field(default=None, ge=1)
    max_cpu_percent: int | None = Field(default=None, ge=1, le=100)


def over_budget(caps: ResourceCaps, snap: ResourceSnapshot) -> list[str]:
    """Return the names of any cap the snapshot exceeded. Empty list = fine.

    >>> over_budget(ResourceCaps(max_rss_mb=200), ResourceSnapshot(
    ...     entity_type="project", entity_id="x", pid=1, cpu_percent=10, rss_mb=250))
    ['max_rss_mb']
    """

    breaches: list[str] = []
    if caps.max_rss_mb is not None and snap.rss_mb > caps.max_rss_mb:
        breaches.append("max_rss_mb")
    if caps.max_cpu_percent is not None and snap.cpu_percent > caps.max_cpu_percent:
        breaches.append("max_cpu_percent")
    return breaches
