"""AI-visible REST API for the native ChatGPT UI fleet controller."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .fleet_controller import get_controller
from .storage import Storage


class LaneRequest(BaseModel):
    name: str
    task: str
    files: list[str] = Field(default_factory=list)
    power: str = "High"


class FleetStart(BaseModel):
    project_url: str
    repo: str
    base_ref: str
    workers: int | None = None
    lanes: list[LaneRequest] | None = None
    interval_minutes: int = Field(default=15, ge=1, le=1440)
    plugins: list[str] = Field(default_factory=lambda: ["Connect To Synapse"])
    parent: str | None = None
    backend: str = "chatgpt-ui"


def build_fleet_router(storage: Storage) -> APIRouter:
    router = APIRouter(prefix="/fleet", tags=["fleet"])
    controller = get_controller(storage)

    @router.post("/start")
    def start_fleet(payload: FleetStart) -> dict[str, Any]:
        try:
            return controller.start(**payload.model_dump(exclude_none=True))
        except (ValueError, FileNotFoundError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @router.get("/status")
    def status_fleets(fleet_id: str | None = None) -> list[dict]:
        try:
            return controller.status(fleet_id)
        except (ValueError, FileNotFoundError) as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.post("/nudge")
    def nudge_fleets(fleet_id: str | None = None) -> dict[str, Any]:
        try:
            return {"errors": controller.nudge(fleet_id), "fleets": controller.status(fleet_id)}
        except (ValueError, FileNotFoundError) as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.post("/stop")
    def stop_fleet(fleet_id: str) -> dict[str, Any]:
        try:
            return controller.stop(fleet_id)
        except (ValueError, FileNotFoundError) as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    return router
