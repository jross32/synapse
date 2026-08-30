"""Operator routing API: one small front door over Synapse capabilities."""

from __future__ import annotations

from fastapi import APIRouter

from .mcp_servers import list_servers
from .operator_router import build_operator_plan
from .storage import Storage


def _installed_capabilities(storage: Storage) -> list[str]:
    capabilities = ["synapse", "trace", "watchdogs", "project_doctor"]
    try:
        capabilities.extend(server.id for server in list_servers(storage.conn) if server.enabled)
    except Exception:  # Capability discovery must never take down the operator planner.
        pass
    return capabilities


def build_operator_router(storage: Storage) -> APIRouter:
    router = APIRouter()

    @router.post("/operator/plan", response_model=None)
    async def plan_operator_task(payload: dict):
        intent = str(payload.get("intent") or "").strip()
        capabilities = payload.get("capabilities")
        if isinstance(capabilities, list):
            available = [str(item) for item in capabilities]
            capability_source = "request"
        else:
            available = _installed_capabilities(storage)
            capability_source = "synapse"
        plan = build_operator_plan(intent, available)
        return {**plan.to_dict(), "capability_source": capability_source, "available_capabilities": available}

    return router
