"""REST routes for per-work-item token accounting (Plan 3 Phase 2, ADR-0025).

A squad worker reports its own token usage (the CLI usage line) so Synapse can
roll it up per squad and, later, prove "fewer tokens than a non-Synapse agent"
honestly. Every record audits (Contract #11).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from . import token_ledger
from .audit import AuditRecord, audit
from .storage import Storage


def build_token_ledger_router(storage: Storage) -> APIRouter:
    router = APIRouter(tags=["token-ledger"])

    @router.post("/agent-work-items/{work_item_id}/tokens", response_model=token_ledger.WorkItemTokenUsage)
    async def record_work_item_tokens(
        work_item_id: str, payload: token_ledger.WorkItemTokenUsageCreate
    ) -> token_ledger.WorkItemTokenUsage:
        with storage.transaction() as conn:
            usage = token_ledger.record_tokens(conn, work_item_id, payload)
            audit(
                conn,
                AuditRecord(
                    entity_type="agent_work_item",
                    entity_id=work_item_id,
                    action="token_ledger.record",
                    details={"total_tokens": usage.total_tokens, "squad_id": usage.squad_id},
                ),
            )
        return usage

    @router.get(
        "/agent-work-items/{work_item_id}/tokens",
        response_model=list[token_ledger.WorkItemTokenUsage],
    )
    async def list_work_item_tokens(work_item_id: str) -> list[token_ledger.WorkItemTokenUsage]:
        return token_ledger.list_for_work_item(storage.conn, work_item_id)

    @router.get("/agent-squads/{squad_id}/token-usage", response_model=token_ledger.SquadTokenRollup)
    async def squad_token_usage(squad_id: str) -> token_ledger.SquadTokenRollup:
        return token_ledger.sum_squad_tokens(storage.conn, squad_id)

    return router
