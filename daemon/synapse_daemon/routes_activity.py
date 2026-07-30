"""AI-activity REST surface (ADR-0028, PLAN 5 Phase 2).

  GET  /api/v1/activity/notifications?unread=&limit=   -> {notifications, unread_count}
  POST /api/v1/activity/notifications/{id}/read        -> the notification, read
  POST /api/v1/activity/notifications/read-all         -> {marked_read}
  GET  /api/v1/activity/sessions                       -> sessions (seq + grade), newest first
  GET  /api/v1/activity/sessions/{id}                  -> session + project squads/work-items + tokens

Read side of activity.py; the Notification Center + Live View consume these.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query

from . import activity
from . import agent_squads as squads
from . import coordination as coord
from . import token_ledger
from .storage import Storage


def build_activity_router(storage: Storage) -> APIRouter:
    router = APIRouter(prefix="/activity", tags=["activity"])

    @router.get("/notifications", response_model=None)
    async def list_notifications(
        unread: bool = Query(default=False),
        limit: int = Query(default=50, ge=1, le=200),
    ) -> dict[str, Any]:
        items = activity.list_notifications(storage.conn, unread_only=unread, limit=limit)
        return {
            "notifications": [n.model_dump(mode="json") for n in items],
            "unread_count": activity.unread_count(storage.conn),
        }

    @router.post("/notifications/{notification_id}/read", response_model=None)
    async def mark_read(notification_id: str) -> dict[str, Any]:
        with storage.transaction() as conn:
            n = activity.mark_read(conn, notification_id)
        return n.model_dump(mode="json")

    @router.post("/notifications/read-all", response_model=None)
    async def mark_all_read() -> dict[str, Any]:
        with storage.transaction() as conn:
            marked = activity.mark_all_read(conn)
        return {"marked_read": marked}

    @router.get("/sessions", response_model=None)
    async def list_sessions() -> dict[str, Any]:
        sessions = coord.list_all_sessions(storage.conn)
        return {"sessions": [s.model_dump(mode="json") for s in sessions]}

    @router.get("/sessions/{session_id}", response_model=None)
    async def session_detail(session_id: str) -> dict[str, Any]:
        session = coord.get_session(storage.conn, session_id)
        # The session's working context: squads on its project (when bound), each with
        # its work items + real token rollup -- the truthful "what this AI run did".
        squad_views: list[dict[str, Any]] = []
        if session.project_id:
            for squad in squads.list_squads(storage.conn):
                if squad.project_id != session.project_id:
                    continue
                items = squads.list_work_items(storage.conn, squad.id)
                rollup = token_ledger.sum_squad_tokens(storage.conn, squad.id)
                squad_views.append(
                    {
                        "squad": squad.model_dump(mode="json"),
                        "work_items": [i.model_dump(mode="json") for i in items],
                        "token_usage": rollup.model_dump(mode="json"),
                    }
                )
        notifications = [
            n.model_dump(mode="json")
            for n in activity.list_notifications(storage.conn, limit=200)
            if n.session_id == session.id
        ]
        return {
            "session": session.model_dump(mode="json"),
            "squads": squad_views,
            "notifications": notifications,
        }

    return router
