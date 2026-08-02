"""Improvement proposals -- the "agents brainstorm, you approve" inbox (ADR-0025).

An AI (or a squad's brainstormer role) files a proposal -- an improvement idea for
an app or for Synapse itself -- into the human review inbox instead of acting on it
unilaterally. You approve (accept the idea) or reject it. Surfaced alongside
work-item handoffs in ``GET /review/inbox``.

Module-level CRUD taking a ``sqlite3.Connection`` (matching :mod:`project_records`
/ :mod:`token_ledger`); routes call them inside ``storage.transaction()``.
"""

from __future__ import annotations

import json
import re
import secrets
import sqlite3
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field

from .errors import invalid, not_found
from .time_utils import from_iso, to_iso, utc_now


class ProposalStatus(str, Enum):
    OPEN = "open"
    APPROVED = "approved"
    REJECTED = "rejected"


class Proposal(BaseModel):
    id: str
    title: str
    rationale_md: str = ""
    project_id: str | None = None
    source_runtime: str = ""
    est_effort: str = ""
    est_token_cost: int = 0
    status: ProposalStatus = ProposalStatus.OPEN
    resolution_note: str = ""
    created_at: datetime
    updated_at: datetime
    resolved_at: datetime | None = None
    metadata: dict = Field(default_factory=dict)


class ProposalCreate(BaseModel):
    title: str
    rationale_md: str = ""
    project_id: str | None = None
    source_runtime: str = ""
    est_effort: str = ""
    est_token_cost: int = 0
    metadata: dict = Field(default_factory=dict)


class ProposalResolveRequest(BaseModel):
    note: str = ""


def _new_id() -> str:
    return secrets.token_hex(6)


def _loads_dict(payload: str | None) -> dict:
    if not payload:
        return {}
    try:
        raw = json.loads(payload)
    except json.JSONDecodeError:
        return {}
    return raw if isinstance(raw, dict) else {}


def _row_to_proposal(row: sqlite3.Row) -> Proposal:
    return Proposal(
        id=row["id"],
        title=row["title"],
        rationale_md=row["rationale_md"] or "",
        project_id=row["project_id"],
        source_runtime=row["source_runtime"] or "",
        est_effort=row["est_effort"] or "",
        est_token_cost=row["est_token_cost"],
        status=ProposalStatus(row["status"]),
        resolution_note=row["resolution_note"] or "",
        created_at=from_iso(row["created_at"]),
        updated_at=from_iso(row["updated_at"]),
        resolved_at=from_iso(row["resolved_at"]) if row["resolved_at"] else None,
        metadata=_loads_dict(row["metadata_json"]),
    )


def create_proposal(conn: sqlite3.Connection, payload: ProposalCreate) -> Proposal:
    title = payload.title.strip()
    if not title:
        raise invalid("proposal", "A proposal needs a title.")
    now = to_iso(utc_now())
    proposal_id = _new_id()
    conn.execute(
        "INSERT INTO improvement_proposals "
        "(id, title, rationale_md, project_id, source_runtime, est_effort, est_token_cost, "
        " status, resolution_note, created_at, updated_at, resolved_at, metadata_json) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, 'open', '', ?, ?, NULL, ?)",
        (
            proposal_id,
            title,
            payload.rationale_md,
            payload.project_id,
            payload.source_runtime.strip(),
            payload.est_effort.strip(),
            payload.est_token_cost,
            now,
            now,
            json.dumps(payload.metadata or {}),
        ),
    )
    return get_proposal(conn, proposal_id)


def get_proposal(conn: sqlite3.Connection, proposal_id: str) -> Proposal:
    row = conn.execute(
        "SELECT * FROM improvement_proposals WHERE id = ?", (proposal_id,)
    ).fetchone()
    if row is None:
        raise not_found("proposal", proposal_id)
    return _row_to_proposal(row)


def list_proposals(
    conn: sqlite3.Connection, status: ProposalStatus | None = None
) -> list[Proposal]:
    if status is None:
        rows = conn.execute(
            "SELECT * FROM improvement_proposals ORDER BY created_at DESC"
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM improvement_proposals WHERE status = ? ORDER BY created_at DESC",
            (status.value,),
        ).fetchall()
    return [_row_to_proposal(row) for row in rows]


def resolve_proposal(
    conn: sqlite3.Connection, proposal_id: str, status: ProposalStatus, note: str = ""
) -> Proposal:
    get_proposal(conn, proposal_id)  # 404 if missing
    if status not in (ProposalStatus.APPROVED, ProposalStatus.REJECTED):
        raise invalid("proposal", "Resolve a proposal as approved or rejected.")
    now = to_iso(utc_now())
    conn.execute(
        "UPDATE improvement_proposals SET status = ?, resolution_note = ?, updated_at = ?, "
        "resolved_at = ? WHERE id = ?",
        (status.value, note.strip(), now, now, proposal_id),
    )
    return get_proposal(conn, proposal_id)


# Words that mean "this commit dealt with it", as opposed to merely naming it.
_RESOLUTION_MARKERS = re.compile(
    r"\b(close[sd]?|fix(e[sd])?|resolv(e|es|ed)|address(es|ed)?|implement(s|ed)?)\b",
    re.IGNORECASE,
)


def find_addressed_proposal_hints(
    proposals: list[Proposal], commit_texts: list[str]
) -> dict[str, str]:
    """Map proposal id -> the commit line that claims to have dealt with it.

    A bare mention is NOT enough. Commits legitimately name a proposal to explain why it
    was *skipped* ("Skipped <id> this pass: it needs a real restart") or to warn the next
    agent ("<id> is already fixed -- do not re-fix"). Flagging those as addressed is worse
    than flagging nothing: the inbox then shows work as done that nobody did. That happened
    twice in one session, on ideas that were explicitly deferred.

    So an id counts only when its own line also carries a resolution word -- uniformly,
    subject line included. An earlier draft exempted the subject on the theory that naming
    an id there is inherently a claim, but "chore: mentions <id>" is a subject too, and one
    rule with no exceptions is both easier to predict and safer: under-flagging costs a
    hint, over-flagging reports work as done.

    The returned line is the matching line -- previously the hint was the commit's first
    line, so a multi-topic commit attached an unrelated summary to the proposal.
    """
    hints: dict[str, str] = {}
    ids = {p.id for p in proposals if p.id}
    if not ids:
        return hints
    for text in commit_texts:
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line or not _RESOLUTION_MARKERS.search(line):
                continue
            for proposal_id in ids:
                if proposal_id not in hints and proposal_id in line:
                    hints[proposal_id] = line[:200]
    return hints


def find_addressed_proposal_ids(proposals: list[Proposal], commit_texts: list[str]) -> set[str]:
    """Ids of proposals a recent commit claims to have addressed.

    Pure + side-effect-free so it is trivially testable without a git repo.
    """
    return set(find_addressed_proposal_hints(proposals, commit_texts))


def mark_proposal_addressed(conn: sqlite3.Connection, proposal_id: str, commit_hint: str) -> Proposal:
    """Flag a proposal as *possibly addressed* by a commit -- WITHOUT resolving it.

    Sets ``metadata.addressed_by`` and leaves ``status`` open so the human confirms and closes
    it. Deliberately non-destructive: the richer parts of an idea are never removed on a hunch.
    """
    proposal = get_proposal(conn, proposal_id)
    metadata = dict(proposal.metadata)
    metadata["addressed_by"] = commit_hint.strip()
    conn.execute(
        "UPDATE improvement_proposals SET metadata_json = ?, updated_at = ? WHERE id = ?",
        (json.dumps(metadata), to_iso(utc_now()), proposal_id),
    )
    return get_proposal(conn, proposal_id)


def reconcile_addressed_proposals(conn: sqlite3.Connection, commit_texts: list[str]) -> list[Proposal]:
    """Flag every OPEN proposal whose id appears in a recent commit as possibly addressed.

    Fixes the "a bug was fixed but its idea stayed stale in the inbox" case without ever
    auto-closing an idea. Returns the proposals that were newly flagged.
    """
    open_proposals = list_proposals(conn, ProposalStatus.OPEN)
    flagged: list[Proposal] = []
    # The hint is the line that made the claim, not the commit's subject -- a commit that
    # touches several things would otherwise attach an unrelated summary to this proposal.
    for proposal_id, hint in find_addressed_proposal_hints(open_proposals, commit_texts).items():
        flagged.append(mark_proposal_addressed(conn, proposal_id, hint))
    return flagged
