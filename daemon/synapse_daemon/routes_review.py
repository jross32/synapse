"""REST for the Needs-Review / approval inbox (ADR-0016, Phase R).

GET the cross-squad queue of work the AI handed back; approve / revise / reject
each item. Actions audit + emit ``v1.review.resolved`` so any open inbox (desktop
or phone) clears live.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from . import review
from .api_versions import event_name
from .audit import AuditRecord, audit
from .models import AuditSource
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

    return router
