"""REST routes for native multi-AI coordination (ADR-0024).

Presence registry + advisory file lanes + a git-working-tree collision
detector + disk-truth migration/ADR numbering. Every mutation audits (Contract
#11) and, when a bus is provided, broadcasts a ``v1.coordination.*`` event
(Contract #5) so the cockpit updates live.

This router is mounted into ``app.py`` via ``build_coordination_router(storage, bus)``
so the ``/api/v1/coordination/*`` endpoints are live. ``scripts/coordination-preflight.ps1``
delivers the numbering + overlap gate independently for pre-commit use.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, Field

from . import coordination as coord
from . import collaboration_rooms as collaboration_rooms_module
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

    async def _mcp_all_connected(request: Request) -> bool:
        """Best-effort: are all *enabled* MCP servers available to a new AI session?

        STDIO servers count as available (the AI launches them on demand); HTTP servers
        must be CONNECTED. Any probe failure -- or a bare test app with no mcp_manager --
        defaults to True so we never report a degraded connection on bad information.
        """
        manager = getattr(request.app.state, "mcp_manager", None)
        if manager is None:
            return True
        try:
            from . import mcp_servers as _mcp

            servers = [s for s in _mcp.list_servers(storage.conn) if s.enabled]

            async def _probe() -> bool:
                for server in servers:
                    status, _detail = await manager.status(server)
                    if status not in (_mcp.McpServerStatus.CONNECTED, _mcp.McpServerStatus.STDIO_READY):
                        return False
                return True

            return await asyncio.wait_for(_probe(), timeout=3.0)
        except Exception:  # noqa: BLE001 -- a probe failure must never fail registration
            return True

    @router.post("/sessions", response_model=None)
    async def register_session(
        payload: coord.AgentSessionRegister, request: Request
    ) -> dict[str, Any]:
        mcp_ok = await _mcp_all_connected(request)
        with storage.transaction() as conn:
            # Detect re-attach vs create so the response can say which happened.
            resume_key = (payload.resume_key or "").strip()
            existing_id = None
            if resume_key:
                row = conn.execute(
                    "SELECT id FROM agent_sessions WHERE resume_key = ? "
                    "ORDER BY registered_at DESC LIMIT 1",
                    (resume_key,),
                ).fetchone()
                existing_id = row["id"] if row else None
            session = coord.register_session(conn, payload, mcp_all_connected=mcp_ok)
            resumed = existing_id is not None and session.id == existing_id
            session_key = coord.issue_session_credential(
                conn,
                session.id,
                authority="full",
                ttl_seconds=86_400,
            )
            audit(
                conn,
                AuditRecord(
                    entity_type="agent_session",
                    entity_id=session.id,
                    action="coordination.register",
                    details={
                        "runtime_id": session.runtime_id,
                        "project_id": session.project_id,
                        "seq": session.seq,
                        "connection_level": session.connection_level,
                        "connection_code": session.connection_code,
                    },
                ),
            )
            auto_collaboration = collaboration_rooms_module.ensure_project_collaboration(
                conn, session.id
            )
        # The "an AI connected" signal (ADR-0028): the notification projector + Live View
        # key off this enriched payload.
        await _emit(
            "session_registered",
            {
                "session_id": session.id,
                "project_id": session.project_id,
                "seq": session.seq,
                "runtime_id": session.runtime_id,
                "agent_label": session.agent_label,
                "coder_thread_id": session.coder_thread_id,
                "parent_session_id": session.parent_session_id,
                "task": session.task,
                "connection_level": session.connection_level,
                "connection_code": session.connection_code,
            },
        )
        if auto_collaboration is not None and bus is not None:
            await bus.publish(
                event_name("collaboration", "room_auto_joined"),
                {
                    "room_id": auto_collaboration.sync.room.id,
                    "project_id": auto_collaboration.sync.room.project_id,
                    "session_id": session.id,
                    "created": auto_collaboration.created,
                    "joined_session_ids": auto_collaboration.joined_session_ids,
                },
            )
        return {
            **session.model_dump(mode="json"),
            "auto_collaboration": (
                auto_collaboration.model_dump(mode="json")
                if auto_collaboration is not None
                else None
            ),
            # True when an existing session was re-attached rather than a new one
            # created, so a returning agent can tell it kept its identity.
            "resumed": resumed,
            # Shown once. Only its hash is stored; later list/detail responses
            # never expose the credential.
            "session_key": session_key,
        }

    @router.post("/sessions/{session_id}/heartbeat", response_model=coord.AgentSession)
    async def heartbeat_session(
        session_id: str, payload: coord.AgentSessionHeartbeat | None = None
    ) -> coord.AgentSession:
        body = payload or coord.AgentSessionHeartbeat()
        journal_event = None
        with storage.transaction() as conn:
            previous = coord.get_session(conn, session_id)
            session = coord.heartbeat_session(conn, session_id, body)
            if session.last_intent.strip() and session.last_intent != previous.last_intent:
                from . import activity

                journal_status = {
                    coord.AgentSessionStatus.ACTIVE: activity.ActivityJournalStatus.ACTIVE,
                    coord.AgentSessionStatus.BLOCKED: activity.ActivityJournalStatus.BLOCKED,
                    coord.AgentSessionStatus.GONE: activity.ActivityJournalStatus.SUCCESS,
                }.get(session.status, activity.ActivityJournalStatus.INFO)
                journal_event = activity.create_journal_event(
                    conn,
                    activity.ActivityJournalCreate(
                        category=activity.ActivityJournalCategory.STATUS,
                        status=journal_status,
                        title="Current focus updated",
                        summary_md=session.last_intent,
                    ),
                    session_id=session.id,
                    source="synapse",
                )
        await _emit("session_heartbeat", session.model_dump(mode="json"))
        if journal_event is not None and bus is not None:
            await bus.publish(
                event_name("activity", "journaled"),
                {"event": journal_event.model_dump(mode="json")},
            )
        return session

    @router.patch("/sessions/{session_id}", response_model=coord.AgentSession)
    async def patch_session_identity(
        session_id: str,
        payload: coord.AgentSessionIdentityPatch,
        request: Request,
    ) -> coord.AgentSession:
        if "project_id" in payload.model_fields_set and payload.project_id is not None:
            from . import projects

            projects.get(storage.conn, payload.project_id)
        mcp_ok = await _mcp_all_connected(request)
        with storage.transaction() as conn:
            session = coord.patch_session_identity(
                conn,
                session_id,
                payload,
                mcp_all_connected=mcp_ok,
            )
            audit(
                conn,
                AuditRecord(
                    entity_type="agent_session",
                    entity_id=session.id,
                    action="coordination.patch_identity",
                    details={
                        "runtime_id": session.runtime_id,
                        "project_id": session.project_id,
                        "coder_thread_id": session.coder_thread_id,
                        "connection_level": session.connection_level,
                        "connection_code": session.connection_code,
                    },
                ),
            )
        await _emit("session_heartbeat", session.model_dump(mode="json"))
        return session

    @router.delete("/sessions/{session_id}", response_model=None)
    async def end_session(session_id: str) -> dict[str, Any]:
        with storage.transaction() as conn:
            coord.end_session(conn, session_id)
            from . import activity

            journal_event = activity.create_journal_event(
                conn,
                activity.ActivityJournalCreate(
                    category=activity.ActivityJournalCategory.RESULT,
                    status=activity.ActivityJournalStatus.SUCCESS,
                    title="Session released",
                    summary_md="The AI session ended and its active file lanes were released.",
                ),
                session_id=session_id,
                source="synapse",
            )
            audit(
                conn,
                AuditRecord(
                    entity_type="agent_session",
                    entity_id=session_id,
                    action="coordination.end",
                ),
            )
        await _emit("session_ended", {"session_id": session_id})
        if bus is not None:
            await bus.publish(
                event_name("activity", "journaled"),
                {"event": journal_event.model_dump(mode="json")},
            )
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
