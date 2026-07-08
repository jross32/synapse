"""REST for the Needs-Review / approval inbox (ADR-0016, Phase R).

GET the cross-squad queue of work the AI handed back; approve / revise / reject
each item. Actions audit + emit ``v1.review.resolved`` so any open inbox (desktop
or phone) clears live.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query

from . import project_records
from . import proposals as proposals_module
from . import review
from .api_versions import event_name
from .audit import AuditRecord, audit
from .errors import invalid
from .models import AuditSource
from .project_records import ProjectBacklogItemCreate
from .proposals import ProposalCreate, ProposalResolveRequest, ProposalStatus
from .review import ReviewActionRequest, ReviewInbox
from .storage import Storage
from .ws import EventBus


def build_review_router(storage: Storage, bus: EventBus) -> APIRouter:
    router = APIRouter(prefix="/review", tags=["review"])

    @router.get("/inbox", response_model=ReviewInbox)
    async def inbox() -> ReviewInbox:
        return review.build_inbox(storage.conn)

    async def _act(work_item_id: str, action: str, note: str | None) -> dict[str, Any]:
        with storage.transaction() as conn:
            if action == "approve":
                item = review.approve(conn, work_item_id)
            elif action == "revise":
                item = review.revise(conn, work_item_id, note)
            else:
                item = review.reject(conn, work_item_id, note)
            audit(
                conn,
                AuditRecord(
                    entity_type="agent_work_item",
                    entity_id=work_item_id,
                    action=f"review_{action}",
                    source=AuditSource.DESKTOP,
                    result="success",
                    details={"status": item.status.value},
                ),
            )
        await bus.publish(
            event_name("review", "resolved"),
            {"id": work_item_id, "action": action, "status": item.status.value},
        )
        return item.model_dump(mode="json")

    @router.post("/items/{work_item_id}/approve", response_model=None)
    async def approve(work_item_id: str) -> dict[str, Any]:
        return await _act(work_item_id, "approve", None)

    @router.post("/items/{work_item_id}/revise", response_model=None)
    async def revise(work_item_id: str, payload: ReviewActionRequest) -> dict[str, Any]:
        return await _act(work_item_id, "revise", payload.note)

    @router.post("/items/{work_item_id}/reject", response_model=None)
    async def reject(work_item_id: str, payload: ReviewActionRequest) -> dict[str, Any]:
        return await _act(work_item_id, "reject", payload.note)

    # Improvement proposals -- AIs file ideas here for you to approve/reject (ADR-0025).
    @router.post("/proposals", response_model=proposals_module.Proposal)
    async def file_proposal(payload: ProposalCreate) -> proposals_module.Proposal:
        with storage.transaction() as conn:
            proposal = proposals_module.create_proposal(conn, payload)
            audit(
                conn,
                AuditRecord(
                    entity_type="proposal",
                    entity_id=proposal.id,
                    action="proposal.filed",
                    source=AuditSource.AUTO,
                    result="success",
                    details={"title": proposal.title, "project_id": proposal.project_id},
                ),
            )
        await bus.publish(event_name("review", "proposal_filed"), {"id": proposal.id})
        return proposal

    async def _resolve_proposal(proposal_id: str, status: ProposalStatus, note: str) -> dict[str, Any]:
        with storage.transaction() as conn:
            proposal = proposals_module.resolve_proposal(conn, proposal_id, status, note)
            audit(
                conn,
                AuditRecord(
                    entity_type="proposal",
                    entity_id=proposal_id,
                    action=f"proposal.{status.value}",
                    source=AuditSource.DESKTOP,
                    result="success",
                ),
            )
        await bus.publish(event_name("review", "resolved"), {"id": proposal_id, "action": status.value})
        return proposal.model_dump(mode="json")

    @router.post("/proposals/{proposal_id}/approve", response_model=None)
    async def approve_proposal(
        proposal_id: str, payload: ProposalResolveRequest | None = None
    ) -> dict[str, Any]:
        return await _resolve_proposal(proposal_id, ProposalStatus.APPROVED, payload.note if payload else "")

    @router.post("/proposals/{proposal_id}/reject", response_model=None)
    async def reject_proposal(
        proposal_id: str, payload: ProposalResolveRequest | None = None
    ) -> dict[str, Any]:
        return await _resolve_proposal(proposal_id, ProposalStatus.REJECTED, payload.note if payload else "")

    @router.post("/proposals/{proposal_id}/promote", response_model=None)
    async def promote_proposal(proposal_id: str) -> dict[str, Any]:
        # "Yes, do this" -> turn an approved idea into an actionable project backlog item, closing
        # the brainstorm -> approve -> action loop. Only a project-scoped proposal can be promoted;
        # a Synapse-wide one (project_id is null) has no backlog to land in.
        with storage.transaction() as conn:
            proposal = proposals_module.get_proposal(conn, proposal_id)
            if not proposal.project_id:
                raise invalid(
                    "proposal", "Only a project-scoped proposal can be promoted to a backlog item."
                )
            item = project_records.create_backlog_item(
                conn,
                proposal.project_id,
                ProjectBacklogItemCreate(
                    title=proposal.title,
                    body_md=(proposal.rationale_md.strip() + f"\n\n_Promoted from proposal {proposal.id}._").strip(),
                    source=AuditSource.DESKTOP,
                ),
            )
            resolved = proposals_module.resolve_proposal(
                conn, proposal_id, ProposalStatus.APPROVED, f"Promoted to backlog item {item.id}"
            )
            audit(
                conn,
                AuditRecord(
                    entity_type="proposal",
                    entity_id=proposal_id,
                    action="proposal.promoted",
                    source=AuditSource.DESKTOP,
                    result="success",
                    details={"backlog_item_id": item.id, "project_id": proposal.project_id},
                ),
            )
        await bus.publish(
            event_name("review", "resolved"),
            {"id": proposal_id, "action": "promoted", "backlog_item_id": item.id},
        )
        return {"proposal": resolved.model_dump(mode="json"), "backlog_item": item.model_dump(mode="json")}

    @router.get("/proposals", response_model=list[proposals_module.Proposal])
    async def list_review_proposals(
        status: ProposalStatus | None = Query(default=None),
    ) -> list[proposals_module.Proposal]:
        # Optional status filter (open|approved|rejected) -- lets a brainstormer skip
        # ideas you already rejected, and the UI show the full proposal history.
        return proposals_module.list_proposals(storage.conn, status)

    @router.get("/proposals/{proposal_id}", response_model=proposals_module.Proposal)
    async def get_review_proposal(proposal_id: str) -> proposals_module.Proposal:
        return proposals_module.get_proposal(storage.conn, proposal_id)

    return router
