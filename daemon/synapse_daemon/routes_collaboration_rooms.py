"""REST + WebSocket event surface for AI collaboration rooms (ADR-0037)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query

from . import collaboration_rooms as rooms
from .api_versions import event_name
from .audit import AuditRecord, audit
from .storage import Storage
from .ws import EventBus


def build_collaboration_rooms_router(storage: Storage, bus: EventBus) -> APIRouter:
    router = APIRouter(prefix="/collaboration/rooms", tags=["collaboration"])

    async def _emit(verb: str, payload: dict[str, Any]) -> None:
        await bus.publish(event_name("collaboration", verb), payload)

    @router.post("", response_model=rooms.CollaborationRoom, status_code=201)
    async def create_room(payload: rooms.CollaborationRoomCreate) -> rooms.CollaborationRoom:
        with storage.transaction() as conn:
            room = rooms.create_room(conn, payload)
            audit(
                conn,
                AuditRecord(
                    entity_type="collaboration_room",
                    entity_id=room.id,
                    action="collaboration.create",
                    details={"project_id": room.project_id, "name": room.name},
                ),
            )
        await _emit("room_created", {"room": room.model_dump(mode="json")})
        return room

    @router.get("", response_model=list[rooms.CollaborationRoom])
    async def list_rooms(
        project_id: str | None = Query(default=None),
        include_archived: bool = Query(default=False),
    ) -> list[rooms.CollaborationRoom]:
        return rooms.list_rooms(
            storage.conn, project_id=project_id, include_archived=include_archived
        )

    @router.patch("/{room_id}", response_model=rooms.CollaborationRoom)
    async def patch_room(
        room_id: str, payload: rooms.CollaborationRoomPatch
    ) -> rooms.CollaborationRoom:
        with storage.transaction() as conn:
            room = rooms.patch_room(conn, room_id, payload)
            audit(
                conn,
                AuditRecord(
                    entity_type="collaboration_room",
                    entity_id=room.id,
                    action="collaboration.update",
                    details={"status": room.status.value},
                ),
            )
        await _emit("room_updated", {"room": room.model_dump(mode="json")})
        return room

    @router.post("/{room_id}/join", response_model=rooms.CollaborationRoomSync)
    async def join_room(
        room_id: str, payload: rooms.CollaborationRoomJoin
    ) -> rooms.CollaborationRoomSync:
        with storage.transaction() as conn:
            synced = rooms.join_room(conn, room_id, payload)
            audit(
                conn,
                AuditRecord(
                    entity_type="collaboration_room",
                    entity_id=room_id,
                    action="collaboration.join",
                    details={"session_id": payload.session_id},
                ),
            )
        await _emit(
            "room_joined",
            {
                "room_id": room_id,
                "project_id": synced.room.project_id,
                "session_id": payload.session_id,
            },
        )
        return synced

    @router.delete(
        "/{room_id}/members/{session_id}",
        response_model=rooms.CollaborationRoomMember,
    )
    async def leave_room(
        room_id: str, session_id: str
    ) -> rooms.CollaborationRoomMember:
        with storage.transaction() as conn:
            member = rooms.leave_room(conn, room_id, session_id)
            audit(
                conn,
                AuditRecord(
                    entity_type="collaboration_room",
                    entity_id=room_id,
                    action="collaboration.leave",
                    details={"session_id": session_id},
                ),
            )
        await _emit(
            "room_left",
            {"room_id": room_id, "session_id": session_id},
        )
        return member

    @router.post(
        "/{room_id}/messages",
        response_model=rooms.CollaborationRoomMessage,
        status_code=201,
    )
    async def post_message(
        room_id: str, payload: rooms.CollaborationRoomPost
    ) -> rooms.CollaborationRoomMessage:
        with storage.transaction() as conn:
            message = rooms.post_message(conn, room_id, payload)
            audit(
                conn,
                AuditRecord(
                    entity_type="collaboration_room_message",
                    entity_id=str(message.id),
                    action="collaboration.message",
                    details={
                        "room_id": room_id,
                        "session_id": payload.session_id,
                        "kind": payload.kind.value,
                    },
                ),
            )
        await _emit(
            "message_posted",
            {
                "room_id": room_id,
                "message": message.model_dump(mode="json"),
            },
        )
        return message

    @router.get("/{room_id}/sync", response_model=rooms.CollaborationRoomSync)
    async def sync_room(
        room_id: str,
        after_message_id: int = Query(default=0, ge=0),
        limit: int = Query(default=50, ge=1, le=200),
    ) -> rooms.CollaborationRoomSync:
        return rooms.sync_room(
            storage.conn,
            room_id,
            after_message_id=after_message_id,
            limit=limit,
        )

    return router
