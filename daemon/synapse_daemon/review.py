"""Needs-Review / approval inbox (ADR-0016, Phase R).

Aggregates the work the AI workforce has handed back to you across *every* squad
and project into one queue you can clear from your phone:

* ``handoff`` items -- a worker finished a chunk and wants your sign-off.
* ``blocked`` items -- the AI is stuck and is effectively asking you a question.

Each item can be **approved** (accept, mark done), **revised** (send back to the
queue with feedback), or **rejected** (block with a reason). This is the
highest-value remote feature: approve work while you're away.
"""

from __future__ import annotations

import sqlite3
from enum import Enum

from pydantic import BaseModel, Field

from . import agent_squads as squads
from . import projects
from . import quality_os
from .agent_squads import AgentWorkItem, AgentWorkItemStatus
from .time_utils import to_iso, utc_now

# Statuses that mean "a human should look at this".
REVIEW_STATUSES = (AgentWorkItemStatus.HANDOFF, AgentWorkItemStatus.BLOCKED)


class ReviewKind(str, Enum):
    HANDOFF = "handoff"  # ready for your review / sign-off
    BLOCKED = "blocked"  # the AI is stuck and needs your input


class ReviewItem(BaseModel):
    id: str
    kind: ReviewKind
    title: str
    squad_id: str
    squad_name: str
    project_id: str
    project_name: str | None = None
    summary_md: str | None = None
    blockers_md: str | None = None
    files_touched: list[str] = Field(default_factory=list)
    suggested_next_role: str | None = None
    assigned_role_id: str | None = None
    pty_session_id: str | None = None
    updated_at: str


class ReviewInbox(BaseModel):
    items: list[ReviewItem] = Field(default_factory=list)
    count: int = 0
    quality_gates: list[quality_os.QualityGate] = Field(default_factory=list)


class ReviewActionRequest(BaseModel):
    note: str | None = None


def _to_item(work_item: AgentWorkItem, squad: squads.AgentSquad, project_name: str | None) -> ReviewItem:
    kind = ReviewKind.HANDOFF if work_item.status == AgentWorkItemStatus.HANDOFF else ReviewKind.BLOCKED
    return ReviewItem(
        id=work_item.id,
        kind=kind,
        title=work_item.title,
        squad_id=squad.id,
        squad_name=squad.name,
        project_id=squad.project_id,
        project_name=project_name,
        summary_md=work_item.summary_md,
        blockers_md=work_item.blockers_md,
        files_touched=work_item.files_touched,
        suggested_next_role=work_item.suggested_next_role,
        assigned_role_id=work_item.assigned_role_id,
        pty_session_id=work_item.pty_session_id,
        updated_at=to_iso(work_item.updated_at),
    )


def build_inbox(conn: sqlite3.Connection) -> ReviewInbox:
    project_names = {p.id: p.name for p in projects.list_projects(conn)}
    items: list[ReviewItem] = []
    for squad in squads.list_squads(conn):
        for work_item in squads.list_work_items(conn, squad.id):
            if work_item.status in REVIEW_STATUSES:
                items.append(_to_item(work_item, squad, project_names.get(squad.project_id)))
    # Most recently touched first -- ISO timestamps sort lexicographically.
    items.sort(key=lambda i: i.updated_at, reverse=True)
    return ReviewInbox(
        items=items,
        count=len(items),
        quality_gates=quality_os.list_gates(
            conn,
            status=quality_os.QualityGateStatus.OPEN,
            blocking=True,
        ),
    )


def approve(conn: sqlite3.Connection, work_item_id: str) -> AgentWorkItem:
    """Accept the handoff -- mark the work item completed."""
    squads.get_work_item(conn, work_item_id)  # raises not_found if missing
    quality_os.assert_subject_can_complete(conn, "agent_work_item", work_item_id)
    return squads.update_work_item_status(conn, work_item_id, AgentWorkItemStatus.COMPLETED)


def revise(conn: sqlite3.Connection, work_item_id: str, note: str | None) -> AgentWorkItem:
    """Send the item back to the queue with feedback the AI will see next run."""
    current = squads.get_work_item(conn, work_item_id)
    instructions = current.instructions_md
    clean = (note or "").strip()
    if clean:
        instructions = f"{current.instructions_md}\n\n---\n**Review feedback ({to_iso(utc_now())}):** {clean}".strip()
    now = utc_now()
    conn.execute(
        "UPDATE agent_work_items SET status = ?, instructions_md = ?, updated_at = ? WHERE id = ?",
        (AgentWorkItemStatus.QUEUED.value, instructions, to_iso(now), work_item_id),
    )
    squads.touch_squad_activity(conn, current.squad_id, when=now)
    return squads.get_work_item(conn, work_item_id)


def reject(conn: sqlite3.Connection, work_item_id: str, note: str | None) -> AgentWorkItem:
    """Block the item with a reason -- it stops until a human revisits it."""
    current = squads.get_work_item(conn, work_item_id)
    blockers = current.blockers_md or ""
    clean = (note or "").strip()
    if clean:
        blockers = f"{blockers}\n\n**Rejected ({to_iso(utc_now())}):** {clean}".strip()
    now = utc_now()
    conn.execute(
        "UPDATE agent_work_items SET status = ?, blockers_md = ?, updated_at = ? WHERE id = ?",
        (AgentWorkItemStatus.BLOCKED.value, blockers, to_iso(now), work_item_id),
    )
    squads.touch_squad_activity(conn, current.squad_id, when=now)
    return squads.get_work_item(conn, work_item_id)
