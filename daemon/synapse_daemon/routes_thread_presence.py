"""REST API for durable AI thread presence and work-time accounting."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query

from . import thread_presence
from .api_versions import event_name
from .audit import AuditRecord, audit
from .projects import get as get_project
from .storage import Storage
from .ws import EventBus


def build_thread_presence_router(storage: Storage, bus: EventBus | None = None) -> APIRouter:
    router = APIRouter(prefix="/thread-presence", tags=["thread-presence"])

    async def publish(verb: str, payload: dict[str, Any]) -> None:
        if bus is not None:
            await bus.publish(event_name("thread_presence", verb), payload)

    @router.get("/overview", response_model=None)
    async def get_overview() -> dict[str, Any]:
        return thread_presence.overview(storage.conn)

    @router.post("/browser-observe", response_model=None)
    async def browser_observe(
        payload: thread_presence.BrowserObservation,
    ) -> dict[str, Any]:
        with storage.transaction() as conn:
            observation, tracked = thread_presence.observe_browser_thread(conn, payload)
        result = {
            "observation": observation.model_dump(mode="json"),
            "tracked_thread": tracked.model_dump(mode="json") if tracked else None,
        }
        await publish("browser_observed", result)
        return result

    @router.get("/groups", response_model=None)
    async def list_groups(
        project_id: str | None = Query(default=None),
        include_archived: bool = Query(default=False),
    ) -> dict[str, Any]:
        groups = thread_presence.list_groups(
            storage.conn, project_id=project_id, include_archived=include_archived
        )
        return {
            "groups": [
                {
                    **group.model_dump(mode="json"),
                    "threads": [
                        item.model_dump(mode="json")
                        for item in thread_presence.list_threads(
                            storage.conn,
                            work_group_id=group.id,
                            include_archived=include_archived,
                        )
                    ],
                }
                for group in groups
            ]
        }

    @router.post("/bootstrap", response_model=None)
    async def bootstrap(payload: thread_presence.ThreadBootstrap) -> dict[str, Any]:
        with storage.transaction() as conn:
            get_project(conn, payload.project_id)
            item, candidates, needs_decision = thread_presence.bootstrap_thread(conn, payload)
            if item is not None:
                audit(
                    conn,
                    AuditRecord(
                        entity_type="ai_thread",
                        entity_id=item.id,
                        action="thread_presence.bootstrap",
                        source="desktop",
                        details={
                            "project_id": item.project_id,
                            "work_group_id": item.work_group_id,
                            "source": item.source.value,
                        },
                    ),
                )
        result = {
            "thread": item.model_dump(mode="json") if item is not None else None,
            "needs_group_decision": needs_decision,
            "group_candidates": [candidate.model_dump(mode="json") for candidate in candidates],
            "instruction": (
                "Inspect the candidate names/descriptions/thread tasks. If this is the same "
                "request, call bootstrap again with work_group_id. Otherwise call bootstrap "
                "again with create_group_name and a concise request description."
                if needs_decision
                else "Thread tracking is active. Begin a turn when work starts; heartbeat "
                "while working; finish the turn before returning the final response."
            ),
        }
        if item is not None:
            await publish("thread_bootstrapped", {"thread": result["thread"]})
        return result

    @router.post("/threads/{thread_id}/begin", response_model=thread_presence.ThreadTurn)
    async def begin_thread_turn(
        thread_id: str, payload: thread_presence.ThreadBegin
    ) -> thread_presence.ThreadTurn:
        with storage.transaction() as conn:
            turn = thread_presence.begin_turn(conn, thread_id, payload)
        await publish(
            "turn_started",
            {"thread_id": thread_id, "turn": turn.model_dump(mode="json")},
        )
        return turn

    @router.post("/threads/{thread_id}/heartbeat", response_model=thread_presence.AIThread)
    async def heartbeat(
        thread_id: str, payload: thread_presence.ThreadHeartbeat
    ) -> thread_presence.AIThread:
        with storage.transaction() as conn:
            item = thread_presence.heartbeat_thread(conn, thread_id, payload)
        await publish("thread_updated", {"thread": item.model_dump(mode="json")})
        return item

    @router.post("/threads/{thread_id}/finish", response_model=None)
    async def finish(
        thread_id: str, payload: thread_presence.ThreadFinish
    ) -> dict[str, Any]:
        with storage.transaction() as conn:
            turn, item = thread_presence.finish_turn(conn, thread_id, payload)
            audit(
                conn,
                AuditRecord(
                    entity_type="ai_thread_turn",
                    entity_id=turn.id,
                    action="thread_presence.finish",
                    source="desktop",
                    details={
                        "thread_id": thread_id,
                        "duration_seconds": turn.duration_seconds,
                        "duration_source": turn.duration_source.value,
                        "status": turn.status.value,
                    },
                ),
            )
        result = {
            "turn": turn.model_dump(mode="json"),
            "thread": item.model_dump(mode="json"),
        }
        await publish("turn_finished", result)
        return result

    @router.post("/threads/{thread_id}/state", response_model=thread_presence.AIThread)
    async def set_state(
        thread_id: str, payload: thread_presence.ThreadStateUpdate
    ) -> thread_presence.AIThread:
        with storage.transaction() as conn:
            item = thread_presence.set_thread_state(conn, thread_id, payload)
        await publish("thread_updated", {"thread": item.model_dump(mode="json")})
        return item

    @router.get("/threads/{thread_id}/turns", response_model=None)
    async def turns(
        thread_id: str, limit: int = Query(default=100, ge=1, le=500)
    ) -> dict[str, Any]:
        return {
            "turns": [
                item.model_dump(mode="json")
                for item in thread_presence.list_turns(storage.conn, thread_id, limit=limit)
            ]
        }

    return router
