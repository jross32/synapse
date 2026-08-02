"""AI-activity REST surface (ADR-0028, PLAN 5 Phase 2).

  GET  /api/v1/activity/notifications?unread=&limit=   -> {notifications, unread_count}
  POST /api/v1/activity/notifications/{id}/read        -> the notification, read
  POST /api/v1/activity/notifications/read-all         -> {marked_read}
  GET  /api/v1/activity/sessions                       -> sessions (seq + grade), newest first
  GET  /api/v1/activity/sessions/{id}                  -> session + squads + journal + tokens
  POST /api/v1/activity/sessions/{id}/events           -> structured operator-facing receipt
  GET/POST/PATCH/DELETE /api/v1/activity/sessions/{id}/goals -> editable milestones

Read side of activity.py; the Notification Center + Live View consume these.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query

from . import activity
from . import agent_squads as squads
from . import coordination as coord
from . import connection_codes
from . import token_ledger
from .api_versions import event_name
from .audit import AuditRecord, audit
from .errors import invalid
from .ws import EventBus
from .storage import Storage


def build_activity_router(storage: Storage, bus: EventBus | None = None) -> APIRouter:
    router = APIRouter(prefix="/activity", tags=["activity"])

    def _session_view(session: coord.AgentSession) -> dict[str, Any]:
        connection = connection_codes.get(session.connection_code)
        return {
            **session.model_dump(mode="json"),
            "connection_help": {
                "title": connection.title,
                "explanation": connection.explanation,
                "remedy": connection.remedy,
            },
        }

    async def _publish_goals(session_id: str) -> None:
        if bus is None:
            return
        goals = activity.list_session_goals(storage.conn, session_id)
        await bus.publish(
            event_name("activity", "goals_updated"),
            {
                "session_id": session_id,
                "goals": [goal.model_dump(mode="json") for goal in goals],
            },
        )

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
        # Live View is the primary presence surface, so it must perform the
        # same stale sweep as the coordination snapshot. Otherwise an exited
        # legacy worker can remain labelled "active · stale" indefinitely.
        with storage.transaction() as conn:
            coord.expire_stale_sessions(conn)
        # Roots only. A squad worker is already shown inside its parent (and inside the
        # squad drawer), so listing it here as well is what made the rail unreadable --
        # 84 sessions for a handful of real tasks. Its children ride along so the UI can
        # nest them without a second round trip.
        roots = coord.list_root_sessions(storage.conn)
        views = []
        for session in roots:
            view = _session_view(session)
            children = coord.list_child_sessions(storage.conn, session.id)
            view["children"] = [_session_view(child) for child in children]
            view["child_count"] = len(children)
            views.append(view)
        return {"sessions": views}

    @router.get("/sessions/{session_id}", response_model=None)
    async def session_detail(session_id: str) -> dict[str, Any]:
        session = coord.get_session(storage.conn, session_id)
        session_journal = activity.list_journal_events(
            storage.conn,
            session_id=session.id,
            limit=500,
        )
        linked_squad_ids = {
            event.squad_id for event in session_journal if event.squad_id is not None
        }
        # The session's working context: squads on its project (when bound), each with
        # its work items + real token rollup -- the truthful "what this AI run did".
        squad_views: list[dict[str, Any]] = []
        if session.project_id:
            for squad in squads.list_squads(storage.conn):
                if squad.project_id != session.project_id:
                    continue
                items = squads.list_work_items(storage.conn, squad.id)
                owns_worker = bool(
                    session.coder_thread_id
                    and any(item.pty_session_id == session.coder_thread_id for item in items)
                )
                if squad.id not in linked_squad_ids and not owns_worker:
                    continue
                rollup = token_ledger.sum_squad_tokens(storage.conn, squad.id)
                worker_profiles: list[dict[str, Any]] = []
                for item in items:
                    role = None
                    personality = None
                    if item.assigned_role_id:
                        try:
                            role = squads.get_role_template(storage.conn, item.assigned_role_id)
                        except Exception:  # noqa: BLE001 -- deleted templates remain historical ids
                            role = None
                    if item.personality_id:
                        try:
                            from . import personalities

                            personality = personalities.get_personality(storage.conn, item.personality_id)
                        except Exception:  # noqa: BLE001 -- deleted personalities remain historical ids
                            personality = None
                    token_entries = token_ledger.list_for_work_item(storage.conn, item.id)
                    linked_session = None
                    if item.pty_session_id:
                        linked_row = storage.conn.execute(
                            "SELECT id FROM agent_sessions WHERE coder_thread_id = ? "
                            "ORDER BY registered_at DESC LIMIT 1",
                            (item.pty_session_id,),
                        ).fetchone()
                        if linked_row is not None:
                            linked_session = coord.get_session(storage.conn, linked_row["id"])
                    worker_profiles.append(
                        {
                            "work_item_id": item.id,
                            "role": role.model_dump(mode="json") if role else None,
                            "personality": personality.model_dump(mode="json") if personality else None,
                            "runtime": item.preferred_runtime,
                            "pty_session_id": item.pty_session_id,
                            "coordination_session": (
                                linked_session.model_dump(mode="json") if linked_session else None
                            ),
                            "token_usage": {
                                "entries": len(token_entries),
                                "input_tokens": sum(entry.input_tokens for entry in token_entries),
                                "output_tokens": sum(entry.output_tokens for entry in token_entries),
                                "total_tokens": sum(entry.total_tokens for entry in token_entries),
                            },
                            "status_changed_at": item.updated_at.isoformat(),
                        }
                    )
                squad_views.append(
                    {
                        "squad": squad.model_dump(mode="json"),
                        "work_items": [i.model_dump(mode="json") for i in items],
                        "worker_profiles": worker_profiles,
                        "token_usage": rollup.model_dump(mode="json"),
                    }
                )
        notifications = [
            n.model_dump(mode="json")
            for n in activity.list_notifications(storage.conn, limit=200)
            if n.session_id == session.id
        ]
        journal = activity.list_journal_events(
            storage.conn,
            session_id=session.id,
            squad_ids=[str(view["squad"]["id"]) for view in squad_views],
            limit=300,
        )
        return {
            "session": _session_view(session),
            "squads": squad_views,
            "notifications": notifications,
            "journal": [event.model_dump(mode="json") for event in journal],
            "goals": [
                goal.model_dump(mode="json")
                for goal in activity.list_session_goals(storage.conn, session.id)
            ],
        }

    @router.get("/sessions/{session_id}/goals", response_model=None)
    async def list_session_goals(session_id: str) -> dict[str, Any]:
        goals = activity.list_session_goals(storage.conn, session_id)
        return {"goals": [goal.model_dump(mode="json") for goal in goals]}

    @router.post(
        "/sessions/{session_id}/goals",
        response_model=activity.ActivityGoal,
        status_code=201,
    )
    async def create_session_goal(
        session_id: str, payload: activity.ActivityGoalCreate
    ) -> activity.ActivityGoal:
        with storage.transaction() as conn:
            goal = activity.create_session_goal(conn, session_id, payload)
            audit(
                conn,
                AuditRecord(
                    entity_type="activity_goal",
                    entity_id=goal.id,
                    action="activity_goal.create",
                    source="desktop",
                    details={"session_id": session_id, "status": goal.status.value},
                ),
            )
        await _publish_goals(session_id)
        return goal

    @router.patch(
        "/sessions/{session_id}/goals/{goal_id}",
        response_model=activity.ActivityGoal,
    )
    async def update_session_goal(
        session_id: str,
        goal_id: str,
        payload: activity.ActivityGoalUpdate,
    ) -> activity.ActivityGoal:
        with storage.transaction() as conn:
            goal = activity.update_session_goal(conn, session_id, goal_id, payload)
            audit(
                conn,
                AuditRecord(
                    entity_type="activity_goal",
                    entity_id=goal.id,
                    action="activity_goal.update",
                    source="desktop",
                    details={"session_id": session_id, "status": goal.status.value},
                ),
            )
        await _publish_goals(session_id)
        return goal

    @router.delete("/sessions/{session_id}/goals/{goal_id}", response_model=None)
    async def delete_session_goal(session_id: str, goal_id: str) -> dict[str, bool]:
        with storage.transaction() as conn:
            goal = activity.delete_session_goal(conn, session_id, goal_id)
            audit(
                conn,
                AuditRecord(
                    entity_type="activity_goal",
                    entity_id=goal.id,
                    action="activity_goal.delete",
                    source="desktop",
                    details={"session_id": session_id},
                ),
            )
        await _publish_goals(session_id)
        return {"ok": True}

    @router.post(
        "/sessions/{session_id}/events",
        response_model=activity.ActivityJournalEvent,
        status_code=201,
    )
    async def report_session_event(
        session_id: str, payload: activity.ActivityJournalCreate
    ) -> activity.ActivityJournalEvent:
        """Record a concise Live View receipt, never raw private reasoning."""

        with storage.transaction() as conn:
            session = coord.get_session(conn, session_id)
            normalized = payload
            if payload.work_item_id:
                work_item = squads.get_work_item(conn, payload.work_item_id)
                if payload.squad_id and payload.squad_id != work_item.squad_id:
                    raise invalid("activity", "The work item does not belong to that squad.")
                normalized = payload.model_copy(update={"squad_id": work_item.squad_id})
            if normalized.squad_id:
                squad = squads.get_squad(conn, normalized.squad_id)
                if session.project_id and squad.project_id != session.project_id:
                    raise invalid("activity", "The squad belongs to a different project.")
            if normalized.mcp_server_id:
                from . import mcp_servers

                mcp_servers.get_server(conn, normalized.mcp_server_id)
            created = activity.create_journal_event(
                conn, normalized, session_id=session.id, source="agent"
            )
            audit(
                conn,
                AuditRecord(
                    entity_type="activity_journal",
                    entity_id=created.id,
                    action="activity.report",
                    source="auto",
                    details={
                        "session_id": session.id,
                        "category": created.category.value,
                        "status": created.status.value,
                        "squad_id": created.squad_id,
                        "mcp_server_id": created.mcp_server_id,
                        "authority": created.authority.value,
                    },
                ),
            )
        if bus is not None:
            await bus.publish(
                event_name("activity", "journaled"),
                {"event": created.model_dump(mode="json")},
            )
        return created

    return router
