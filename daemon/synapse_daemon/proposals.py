"""Durable improvement backlog with human decision + work lifecycle (ADR-0025 evolution).

A proposal is an AI- or human-filed observation worth preserving. Two independent axes keep
its meaning honest:

* ``decision`` answers "do we want this?" (pending / accepted / declined).
* ``status`` answers "has work happened?" (proposed / in_progress / done).

Lifecycle transitions may be inferred from strong, inspectable signals (a commit explicitly
closing the proposal id, or a live work item/session that explicitly references it). Every
automatic transition persists its evidence; a weak guess never silently closes backlog work.
"""

from __future__ import annotations

import json
import re
import secrets
import sqlite3
from datetime import datetime, timedelta
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from .errors import invalid, not_found
from .time_utils import from_iso, to_iso, utc_now


class ProposalStatus(str, Enum):
    PROPOSED = "proposed"
    IN_PROGRESS = "in_progress"
    DONE = "done"


class ProposalDecision(str, Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    DECLINED = "declined"


class ProposalSort(str, Enum):
    CREATED_AT = "created_at"
    UPDATED_AT = "updated_at"
    TITLE = "title"
    KIND = "kind"
    STATUS = "status"
    DECISION = "decision"


class SortDirection(str, Enum):
    ASC = "asc"
    DESC = "desc"


# Stable vocabulary for common categories. Unknown slugs remain valid so integrations can extend
# the taxonomy without requiring a schema migration.
KNOWN_KINDS = (
    "bug",
    "improvement",
    "ui-ux",
    "backend",
    "frontend",
    "performance",
    "reliability",
    "security",
    "testing",
    "docs",
    "developer-experience",
    "architecture",
    "data",
    "automation",
    "measurement",
    "design-decision",
    "maintenance",
    "other",
)

_KIND_ALIASES = {
    "error": "bug",
    "idea": "improvement",
    "feature": "improvement",
    "ui": "ui-ux",
    "ux": "ui-ux",
    "ui/ux": "ui-ux",
    "perf": "performance",
    "devex": "developer-experience",
    "doc-drift": "docs",
    "dedup": "maintenance",
}


class LifecycleEvidence(BaseModel):
    source: str
    observed_at: datetime
    detail: str = ""
    ref_id: str | None = None
    status: str | None = None


class Proposal(BaseModel):
    id: str
    title: str
    rationale_md: str = ""
    project_id: str | None = None
    source_runtime: str = ""
    kind: str = "improvement"
    est_effort: str = ""
    est_token_cost: int = 0
    status: ProposalStatus = ProposalStatus.PROPOSED
    decision: ProposalDecision = ProposalDecision.PENDING
    resolution_note: str = ""
    lifecycle_source: str = ""
    lifecycle_evidence: list[LifecycleEvidence] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime
    decision_at: datetime | None = None
    started_at: datetime | None = None
    done_at: datetime | None = None
    # Backward-compatible alias for clients written against the original approve/reject schema.
    resolved_at: datetime | None = None
    metadata: dict = Field(default_factory=dict)


class ProposalCreate(BaseModel):
    title: str
    rationale_md: str = ""
    project_id: str | None = None
    source_runtime: str = ""
    kind: str = "improvement"
    est_effort: str = ""
    est_token_cost: int = 0
    metadata: dict = Field(default_factory=dict)


class ProposalResolveRequest(BaseModel):
    note: str = ""


class ProposalLifecycleRequest(BaseModel):
    status: ProposalStatus
    note: str = ""


def _new_id() -> str:
    return secrets.token_hex(6)


def normalize_kind(value: str | None) -> str:
    clean = (value or "").strip().lower()
    if not clean:
        return "improvement"
    clean = _KIND_ALIASES.get(clean, clean)
    clean = re.sub(r"[^a-z0-9]+", "-", clean).strip("-")
    return _KIND_ALIASES.get(clean, clean or "improvement")


def _loads_dict(payload: str | None) -> dict:
    if not payload:
        return {}
    try:
        raw = json.loads(payload)
    except json.JSONDecodeError:
        return {}
    return raw if isinstance(raw, dict) else {}


def _loads_evidence(payload: str | None) -> list[LifecycleEvidence]:
    if not payload:
        return []
    try:
        raw = json.loads(payload)
    except json.JSONDecodeError:
        return []
    if not isinstance(raw, list):
        return []
    out: list[LifecycleEvidence] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        try:
            out.append(LifecycleEvidence.model_validate(item))
        except Exception:  # noqa: BLE001 - malformed old evidence should not break the backlog
            continue
    return out


def _row_to_proposal(row: sqlite3.Row) -> Proposal:
    decision_at = from_iso(row["decision_at"]) if row["decision_at"] else None
    return Proposal(
        id=row["id"],
        title=row["title"],
        rationale_md=row["rationale_md"] or "",
        project_id=row["project_id"],
        source_runtime=row["source_runtime"] or "",
        kind=normalize_kind(row["kind"]),
        est_effort=row["est_effort"] or "",
        est_token_cost=row["est_token_cost"],
        status=ProposalStatus(row["status"]),
        decision=ProposalDecision(row["decision"]),
        resolution_note=row["resolution_note"] or "",
        lifecycle_source=row["lifecycle_source"] or "",
        lifecycle_evidence=_loads_evidence(row["lifecycle_evidence_json"]),
        created_at=from_iso(row["created_at"]),
        updated_at=from_iso(row["updated_at"]),
        decision_at=decision_at,
        started_at=from_iso(row["started_at"]) if row["started_at"] else None,
        done_at=from_iso(row["done_at"]) if row["done_at"] else None,
        resolved_at=decision_at,
        metadata=_loads_dict(row["metadata_json"]),
    )


def create_proposal(conn: sqlite3.Connection, payload: ProposalCreate) -> Proposal:
    title = payload.title.strip()
    if not title:
        raise invalid("proposal", "A proposal needs a title.")
    metadata = dict(payload.metadata or {})
    # Old callers put kind only in metadata. Keep accepting that while making kind first-class.
    requested_kind = payload.kind
    if requested_kind == "improvement" and isinstance(metadata.get("kind"), str):
        requested_kind = str(metadata["kind"])
    kind = normalize_kind(requested_kind)
    metadata.pop("kind", None)
    now = to_iso(utc_now())
    proposal_id = _new_id()
    conn.execute(
        "INSERT INTO improvement_proposals "
        "(id, title, rationale_md, project_id, source_runtime, kind, est_effort, est_token_cost, "
        " status, decision, resolution_note, lifecycle_source, lifecycle_evidence_json, "
        " created_at, updated_at, decision_at, started_at, done_at, metadata_json) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'proposed', 'pending', '', 'filed', '[]', ?, ?, NULL, NULL, NULL, ?)",
        (
            proposal_id,
            title,
            payload.rationale_md,
            payload.project_id,
            payload.source_runtime.strip(),
            kind,
            payload.est_effort.strip(),
            payload.est_token_cost,
            now,
            now,
            json.dumps(metadata),
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
    conn: sqlite3.Connection,
    status: ProposalStatus | None = None,
    *,
    decision: ProposalDecision | None = None,
    kind: str | None = None,
    project_id: str | None = None,
    sort_by: ProposalSort = ProposalSort.UPDATED_AT,
    sort_dir: SortDirection = SortDirection.DESC,
) -> list[Proposal]:
    clauses: list[str] = []
    args: list[Any] = []
    if status is not None:
        clauses.append("status = ?")
        args.append(status.value)
    if decision is not None:
        clauses.append("decision = ?")
        args.append(decision.value)
    if kind is not None:
        clauses.append("kind = ?")
        args.append(normalize_kind(kind))
    if project_id is not None:
        clauses.append("project_id = ?")
        args.append(project_id)
    where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
    # Enum values are the whitelist; never interpolate arbitrary user input into SQL.
    order = sort_by.value
    direction = "ASC" if sort_dir == SortDirection.ASC else "DESC"
    rows = conn.execute(
        f"SELECT * FROM improvement_proposals{where} ORDER BY {order} {direction}, id ASC",  # noqa: S608
        tuple(args),
    ).fetchall()
    return [_row_to_proposal(row) for row in rows]


def set_proposal_decision(
    conn: sqlite3.Connection,
    proposal_id: str,
    decision: ProposalDecision,
    note: str = "",
) -> Proposal:
    get_proposal(conn, proposal_id)  # 404 if missing
    now = to_iso(utc_now())
    conn.execute(
        "UPDATE improvement_proposals SET decision = ?, resolution_note = ?, updated_at = ?, "
        "decision_at = ? WHERE id = ?",
        (decision.value, note.strip(), now, now, proposal_id),
    )
    return get_proposal(conn, proposal_id)


def resolve_proposal(
    conn: sqlite3.Connection, proposal_id: str, decision: ProposalDecision, note: str = ""
) -> Proposal:
    """Compatibility name for the original approve/reject route implementation."""
    if decision not in (ProposalDecision.ACCEPTED, ProposalDecision.DECLINED):
        raise invalid("proposal", "Resolve a proposal decision as accepted or declined.")
    return set_proposal_decision(conn, proposal_id, decision, note)


def _evidence_dict(evidence: LifecycleEvidence) -> dict[str, Any]:
    return evidence.model_dump(mode="json", exclude_none=True)


def _append_evidence(existing: list[LifecycleEvidence], evidence: LifecycleEvidence) -> str:
    # Keep a useful audit trail without allowing one noisy proposal to grow without bound.
    values = [_evidence_dict(item) for item in existing[-24:]]
    values.append(_evidence_dict(evidence))
    return json.dumps(values)


def transition_proposal(
    conn: sqlite3.Connection,
    proposal_id: str,
    status: ProposalStatus,
    *,
    source: str,
    detail: str = "",
    ref_id: str | None = None,
    evidence_status: str | None = None,
) -> Proposal:
    proposal = get_proposal(conn, proposal_id)
    if proposal.status == status:
        return proposal
    now_dt = utc_now()
    now = to_iso(now_dt)
    evidence = LifecycleEvidence(
        source=source,
        observed_at=now_dt,
        detail=detail.strip(),
        ref_id=ref_id,
        status=evidence_status,
    )
    started_at = proposal.started_at
    done_at = proposal.done_at
    if status == ProposalStatus.IN_PROGRESS and started_at is None:
        started_at = now_dt
    if status == ProposalStatus.DONE:
        done_at = now_dt
    elif proposal.status == ProposalStatus.DONE:
        # Explicit manual reopen: retain evidence history but clear the current completion time.
        done_at = None
    conn.execute(
        "UPDATE improvement_proposals SET status = ?, lifecycle_source = ?, "
        "lifecycle_evidence_json = ?, updated_at = ?, started_at = ?, done_at = ? WHERE id = ?",
        (
            status.value,
            source,
            _append_evidence(proposal.lifecycle_evidence, evidence),
            now,
            to_iso(started_at) if started_at else None,
            to_iso(done_at) if done_at else None,
            proposal_id,
        ),
    )
    return get_proposal(conn, proposal_id)


# A commit must make a direct completion claim on the same line as the proposal id.
_RESOLUTION_MARKERS = re.compile(
    r"\b(close[sd]?|fix(e[sd])?|resolv(e|es|ed)|address(es|ed)?|implement(s|ed)?)\b",
    re.IGNORECASE,
)
_NEGATING_CONTEXT = re.compile(
    r"\b(skip(?:ped)?|defer(?:red)?|do not|does not|did not|not fixed|not resolved|not closed|"
    r"already fixed|already resolved|already closed|mention(?:s|ed)?|warning|example|fixture|"
    r"should not|doesn't|isn't|wasn't|flag(?:s|ged|ging)?)\b",
    re.IGNORECASE,
)


def find_addressed_proposal_hints(
    proposals: list[Proposal], commit_texts: list[str]
) -> dict[str, str]:
    """Map proposal id -> high-confidence commit line claiming completion.

    Bare mentions, skips, warnings, reconciliation examples, and "already fixed" commentary are
    deliberately excluded. False negatives leave a proposal visible; false positives silently
    erase work, so this detector is intentionally conservative.
    """
    hints: dict[str, str] = {}
    ids = {p.id for p in proposals if p.id}
    if not ids:
        return hints
    for text in commit_texts:
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line or not _RESOLUTION_MARKERS.search(line) or _NEGATING_CONTEXT.search(line):
                continue
            for proposal_id in ids:
                if proposal_id not in hints and proposal_id in line:
                    hints[proposal_id] = line[:240]
    return hints


def find_addressed_proposal_ids(proposals: list[Proposal], commit_texts: list[str]) -> set[str]:
    return set(find_addressed_proposal_hints(proposals, commit_texts))


def _text_references_proposal(proposal_id: str, *values: object) -> bool:
    return any(proposal_id in str(value) for value in values if value is not None)


def find_active_work_evidence(conn: sqlite3.Connection, proposal: Proposal) -> LifecycleEvidence | None:
    """Return a strong live-work signal only when the proposal id is explicitly linked.

    Correlation by title similarity is intentionally excluded: it looked attractive in testing but
    produced ambiguous matches. An id in a running/handoff/blocked work item or a recently-live
    session is cheap for an AI to provide and unambiguous for both humans and machines.
    """
    rows = conn.execute(
        "SELECT w.id, w.status, w.title, w.instructions_md, w.summary_md, w.blockers_md, s.project_id "
        "FROM agent_work_items w JOIN agent_squads s ON s.id = w.squad_id "
        "WHERE w.status IN ('running', 'handoff', 'blocked')"
    ).fetchall()
    for row in rows:
        if proposal.project_id and row["project_id"] != proposal.project_id:
            continue
        if _text_references_proposal(
            proposal.id,
            row["title"],
            row["instructions_md"],
            row["summary_md"],
            row["blockers_md"],
        ):
            return LifecycleEvidence(
                source="work_item",
                observed_at=utc_now(),
                detail=f"Active work item explicitly references proposal {proposal.id}",
                ref_id=row["id"],
                status=row["status"],
            )

    cutoff = utc_now() - timedelta(minutes=15)
    sessions = conn.execute(
        "SELECT id, project_id, status, task, last_intent, metadata_json, last_heartbeat_at "
        "FROM agent_sessions WHERE status IN ('active', 'idle', 'blocked', 'holding')"
    ).fetchall()
    for row in sessions:
        if proposal.project_id and row["project_id"] != proposal.project_id:
            continue
        try:
            heartbeat = from_iso(row["last_heartbeat_at"])
        except Exception:  # noqa: BLE001
            continue
        if heartbeat < cutoff:
            continue
        if _text_references_proposal(
            proposal.id,
            row["task"],
            row["last_intent"],
            row["metadata_json"],
        ):
            return LifecycleEvidence(
                source="session",
                observed_at=utc_now(),
                detail=f"Live session explicitly references proposal {proposal.id}",
                ref_id=row["id"],
                status=row["status"],
            )
    return None


_AUTO_ACTIVE_SOURCES = {"work_item", "session"}


def reconcile_proposals(conn: sqlite3.Connection, commit_texts: list[str]) -> list[Proposal]:
    """Reconcile backlog lifecycle from high-confidence real-world signals.

    * explicit completion commit -> ``done`` (durable; never auto-reopened)
    * explicitly linked live work/session -> ``in_progress``
    * vanished live signal -> auto-started ``in_progress`` falls back to ``proposed``

    Declined proposals are left alone. Every transition stores evidence and its source.
    """
    candidates = [
        p
        for p in list_proposals(conn)
        if p.decision != ProposalDecision.DECLINED and p.status != ProposalStatus.DONE
    ]
    commit_hints = find_addressed_proposal_hints(candidates, commit_texts)
    changed: list[Proposal] = []
    for proposal in candidates:
        hint = commit_hints.get(proposal.id)
        if hint:
            changed.append(
                transition_proposal(
                    conn,
                    proposal.id,
                    ProposalStatus.DONE,
                    source="commit",
                    detail=hint,
                )
            )
            continue
        active = find_active_work_evidence(conn, proposal)
        if active is not None:
            if proposal.status != ProposalStatus.IN_PROGRESS:
                changed.append(
                    transition_proposal(
                        conn,
                        proposal.id,
                        ProposalStatus.IN_PROGRESS,
                        source=active.source,
                        detail=active.detail,
                        ref_id=active.ref_id,
                        evidence_status=active.status,
                    )
                )
            continue
        if proposal.status == ProposalStatus.IN_PROGRESS and proposal.lifecycle_source in _AUTO_ACTIVE_SOURCES:
            changed.append(
                transition_proposal(
                    conn,
                    proposal.id,
                    ProposalStatus.PROPOSED,
                    source="reconcile",
                    detail="Previously detected live work is no longer active; proposal returned to proposed.",
                )
            )
    return changed


# Compatibility wrappers retained for callers/tests from the original addressed_by implementation.
def mark_proposal_addressed(conn: sqlite3.Connection, proposal_id: str, commit_hint: str) -> Proposal:
    return transition_proposal(
        conn,
        proposal_id,
        ProposalStatus.DONE,
        source="commit",
        detail=commit_hint,
    )


def reconcile_addressed_proposals(conn: sqlite3.Connection, commit_texts: list[str]) -> list[Proposal]:
    return reconcile_proposals(conn, commit_texts)
