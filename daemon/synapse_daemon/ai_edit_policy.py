"""Pure coordination decisions for autonomous, multi-device AI editing.

This module never edits files. Callers must enforce decisions through
workspace isolation, verified leases and merge gates.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class EditAction(str, Enum):
    PROCEED = "proceed"
    ISOLATE = "isolate"
    WAIT = "wait"
    MERGE = "merge"
    REJECT = "reject"


@dataclass(frozen=True)
class EditObservation:
    same_file: bool
    other_agent_active: bool
    other_agent_heartbeat_fresh: bool
    same_base_revision: bool
    local_dirty: bool
    remote_dirty: bool
    remote_available: bool
    compatible_schema: bool


@dataclass(frozen=True)
class EditDecision:
    action: EditAction
    reason: str
    requires_validation: bool = True


def decide_edit(observation: EditObservation) -> EditDecision:
    """Choose a safe next step; never equate silence with an unlocked file."""
    o = observation
    if not o.compatible_schema:
        return EditDecision(EditAction.REJECT, "Incompatible document schema")
    if not o.remote_available and o.same_file and o.remote_dirty:
        return EditDecision(EditAction.WAIT, "Offline remote edits need reconciliation")
    if not o.same_file:
        return EditDecision(EditAction.PROCEED, "Independent file lanes")
    if o.other_agent_active and o.other_agent_heartbeat_fresh:
        return EditDecision(EditAction.ISOLATE, "Use a separate worktree while the other agent edits")
    if not o.same_base_revision:
        return EditDecision(EditAction.MERGE, "Divergent revisions require a verified merge")
    if o.local_dirty and o.remote_dirty:
        return EditDecision(EditAction.MERGE, "Both devices changed this file")
    if o.other_agent_active and not o.other_agent_heartbeat_fresh:
        return EditDecision(EditAction.WAIT, "Stale heartbeat is not proof that editing stopped")
    return EditDecision(EditAction.PROCEED, "Revision and lane checks passed")
