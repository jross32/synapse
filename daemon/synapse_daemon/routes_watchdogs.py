"""Read-only watchdog dashboard routes."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Query

from .errors import not_found
from .watchdogs import snapshot_watchdogs, watchdog_log


def build_watchdogs_router(data_dir: Path) -> APIRouter:
    router = APIRouter()

    @router.get("/system/watchdogs", response_model=None)
    async def get_watchdogs(force: bool = False):
        return snapshot_watchdogs(data_dir, force=force)

    @router.get("/system/watchdogs/{watchdog_id}/log", response_model=None)
    async def get_watchdog_log(
        watchdog_id: str,
        lines: int = Query(default=120, ge=1, le=500),
    ):
        try:
            return watchdog_log(data_dir, watchdog_id, lines)
        except KeyError:
            raise not_found("watchdog", watchdog_id) from None

    return router
