"""REST for the Needs-Review / approval inbox (ADR-0016, Phase R).

GET the cross-squad queue of work the AI handed back; approve / revise / reject
each item. Actions audit + emit ``v1.review.resolved`` so any open inbox (desktop
or phone) clears live.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from . import proposals as proposals_module
from . import review
from .api_versions import event_name
from .audit import AuditRecord, audit
from .models import AuditSource
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

    return router
