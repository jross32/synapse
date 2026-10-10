"""Authenticated REST endpoints for Railway cost visibility.

Mounted into the existing Watchdogs router to avoid altering the live daemon app
bootstrap while other workers edit it.
"""
from __future__ import annotations

import math
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from .railway_cost_monitor import get_status, update_thresholds


class RailwayBudgetInput(BaseModel):
    warning_usd: float
    critical_usd: float


def build_railway_costs_router(data_dir: Path) -> APIRouter:
    router = APIRouter(tags=["railway-costs"])

    @router.get("/system/railway-costs")
    async def railway_cost_status(refresh: bool = False):
        return await run_in_threadpool(get_status, data_dir, refresh=refresh)

    @router.post("/system/railway-costs/budget")
    async def save_budget(body: RailwayBudgetInput):
        if not all(math.isfinite(n) for n in (body.warning_usd, body.critical_usd)):
            raise HTTPException(status_code=422, detail="Budget thresholds must be finite")
        try:
            await run_in_threadpool(update_thresholds, data_dir, body.warning_usd, body.critical_usd)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return await run_in_threadpool(get_status, data_dir, refresh=False)

    return router
