"""REST routes for native multi-AI coordination (ADR-0024).

Presence registry + advisory file lanes + a git-working-tree collision
detector + disk-truth migration/ADR numbering. Every mutation audits (Contract
#11) and, when a bus is provided, broadcasts a ``v1.coordination.*`` event
(Contract #5) so the cockpit updates live.

NOTE: this router is intentionally standalone. It is mounted into ``app.py``
(``build_coordination_router(storage, bus)``) as a follow-up once the current
concurrent wave is committed -- until then it is fully unit-tested against a
bare app, and ``scripts/coordination-preflight.ps1`` delivers the numbering +
overlap gate independently.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from . import coordination as coord
from .api_versions import event_name
from .audit import AuditRecord, audit
from .runtime_paths import repo_root
from .storage import Storage
from .ws import EventBus


class OverlapRequest(BaseModel):
    paths: list[str] = Field(default_factory=list)
    project_id: str | None = None
    exclude_session_id: str | None = None


class DetectCollisionsRequest(BaseModel):
    project_id: str | None = None
    repo_path: str | None = None


def build_coordination_router(storage: Storage, bus: EventBus | None = None) -> APIRouter:
    router = APIRouter(prefix="/coordination", tags=["coordination"])

    async def _emit(verb: str, payload: dict[str, Any]) -> None:
        if bus is not None:
            await bus.publish(event_name("coordination", verb), payload)

    # -- presence -------------------------------------------------------------

    @router.post("/sessions", response_model=coord.AgentSession)
    async def register_session(payload: coord.AgentSessionRegister) -> coord.AgentSession:
        with storage.transaction() as conn:
            session = coord.register_session(conn, payload)
            audit(
                conn,
                AuditRecord(
                    entity_type="agent_session",
                    entity_id=session.id,
                    action="coordination.register",
                    details={"runtime_id": session.runtime_id, "project_id": session.project_id},
                ),
            )
        await _emit("session_registered", {"session_id": session.id, "project_id": session.project_id})
        return session

    @router.post("/sessions/{session_id}/heartbeat", response_model=coord.AgentSession)
    async def heartbeat_session(
        session_id: str, payload: coord.AgentSessionHeartbeat | None = None
    ) -> coord.AgentSession:
        body = payload or coord.AgentSessionHeartbeat()
        with storage.transaction() as conn:
            session = coord.heartbeat_session(conn, session_id, body)
        await _emit("session_heartbeat", {"session_id": session.id, "status": session.status.value})
        return session

    @router.delete("/sessions/{session_id}", response_model=None)
    async def end_session(session_id: str) -> dict[str, Any]:
        with storage.transaction() as conn:
            coord.end_session(conn, session_id)
            audit(
                conn,
                AuditRecord(
                    entity_type="agent_session",
                    entity_id=session_id,
                    action="coordination.end",
                ),
            )
        await _emit("session_ended", {"session_id": session_id})
        return {"ok": True}

    @router.get("/sessions", response_model=list[coord.AgentSession])
    async def list_sessions(
        project_id: str | None = Query(default=None),
        include_gone: bool = Query(default=False),
    ) -> list[coord.AgentSession]:
        conn = storage.conn
        return coord.list_sessions(conn, project_id, include_gone=include_gone)

    # -- file lanes -----------------------------------------------------------

    @router.post("/lanes", response_model=coord.LaneClaimResult)
    async def claim_lane(
        payload: coord.LaneClaim, project_id: str | None = Query(default=None)
    ) -> coord.LaneClaimResult:
        with storage.transaction() as conn:
            result = coord.claim_lane(conn, project_id, payload)
            audit(
                conn,
                AuditRecord(
                    entity_type="file_lane",
                    entity_id=result.lane.id if result.lane else None,
                    action="coordination.claim_lane",
                    details={
                        "session_id": payload.session_id,
                        "conflicts": len(result.conflicts),
                    },
                ),
            )
        await _emit(
            "lane_claimed",
            {
                "lane_id": result.lane.id if result.lane else None,
                "project_id": project_id,
                "conflicts": len(result.conflicts),
            },
        )
        return result

    @router.delete("/lanes/{lane_id}", response_model=coord.FileLane)
    async def release_lane(lane_id: str) -> coord.FileLane:
        with storage.transaction() as conn:
            lane = coord.release_lane(conn, lane_id)
            audit(
                conn,
                AuditRecord(
                    entity_type="file_lane",
                    entity_id=lane_id,
                    action="coordination.release_lane",
                ),
            )
        await _emit("lane_released", {"lane_id": lane_id})
        return lane

    @router.get("/lanes", response_model=list[coord.FileLane])
    async def list_lanes(project_id: str | None = Query(default=None)) -> list[coord.FileLane]:
        return coord.list_active_lanes(storage.conn, project_id)

    @router.post("/overlap", response_model=None)
    async def check_overlap(payload: OverlapRequest) -> dict[str, Any]:
        conflicts = coord.detect_overlap(
            storage.conn,
            payload.project_id,
            payload.paths,
            exclude_session_id=payload.exclude_session_id,
        )
        return {
            "conflicts": [c.model_dump() for c in conflicts],
            "has_conflicts": bool(conflicts),
            "advisory": coord._LANE_ADVISORY,
        }

    # -- snapshot + detector + numbering --------------------------------------

    @router.get("/snapshot", response_model=coord.CoordinationSnapshot)
    async def snapshot(project_id: str | None = Query(default=None)) -> coord.CoordinationSnapshot:
        with storage.transaction() as conn:
            coord.expire_stale_sessions(conn)
        return coord.get_snapshot(storage.conn, project_id)

    @router.post("/detect-collisions", response_model=None)
    async def detect_collisions(payload: DetectCollisionsRequest | None = None) -> dict[str, Any]:
        body = payload or DetectCollisionsRequest()
        root = Path(body.repo_path) if body.repo_path else repo_root()
        hits = coord.detect_collisions(storage.conn, body.project_id, root)
        if hits and bus is not None:
            await _emit(
                "collision",
                {"project_id": body.project_id, "count": len(hits)},
            )
        return {
            "collisions": [h.model_dump() for h in hits],
            "has_collisions": bool(hits),
            "repo_root": str(root),
        }

    @router.get("/next-numbers", response_model=None)
    async def next_numbers() -> dict[str, Any]:
        root = repo_root()
        return {
            "migration": coord.next_migration_number(root),
            "adr": coord.next_adr_number(root),
            "repo_root": str(root),
        }

    return router
