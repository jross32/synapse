"""Tests for durable project-scoped AI collaboration rooms (ADR-0037)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from synapse_daemon import collaboration_rooms as rooms
from synapse_daemon import coordination
from synapse_daemon.errors import SynapseError
from synapse_daemon.projects import Project, create as create_project
from synapse_daemon.routes_collaboration_rooms import build_collaboration_rooms_router
from synapse_daemon.storage import Storage
from synapse_daemon.ws import EventBus


def _storage(tmp_path: Path) -> Storage:
    storage = Storage(tmp_path / "data")
    storage.open()
    storage.migrate()
    return storage


def _project(conn, project_id: str, path: Path) -> None:
    create_project(
        conn,
        Project(
            id=project_id,
            name=project_id,
            path=str(path),
            launch_cmd="echo ready",
        ),
    )


def _session(conn, project_id: str, runtime: str, label: str):
    return coordination.register_session(
        conn,
        coordination.AgentSessionRegister(
            project_id=project_id,
            runtime_id=runtime,
            agent_label=label,
        ),
    )


def test_two_ais_join_and_second_ai_gets_caught_up(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    with storage.transaction() as conn:
        _project(conn, "p1", tmp_path)
        claude = _session(conn, "p1", "claude", "Claude")
        codex = _session(conn, "p1", "codex", "Codex")
        room = rooms.create_room(
            conn,
            rooms.CollaborationRoomCreate(
                project_id="p1",
                name="Release room",
                goal_md="Ship the release without overlapping work.",
                summary_md="Backend lane is already in progress.",
                created_by_session_id=claude.id,
            ),
        )
        first_sync = rooms.join_room(
            conn,
            room.id,
            rooms.CollaborationRoomJoin(session_id=claude.id, role_label="backend"),
        )
        assert [m.session_id for m in first_sync.members] == [claude.id]
        posted = rooms.post_message(
            conn,
            room.id,
            rooms.CollaborationRoomPost(
                session_id=claude.id,
                kind=rooms.CollaborationMessageKind.STATUS,
                body_md="Migration is drafted; routes are next.",
            ),
        )
        caught_up = rooms.join_room(
            conn,
            room.id,
            rooms.CollaborationRoomJoin(session_id=codex.id, role_label="tester"),
        )

    assert caught_up.room.goal_md.startswith("Ship the release")
    assert caught_up.room.summary_md.startswith("Backend lane")
    assert {m.session_id for m in caught_up.members if m.present} == {
        claude.id,
        codex.id,
    }
    assert [message.id for message in caught_up.messages] == [posted.id]
    assert caught_up.messages[0].agent_label == "Claude"
    assert caught_up.messages[0].kind == rooms.CollaborationMessageKind.STATUS


def test_sync_cursor_returns_only_new_messages(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    with storage.transaction() as conn:
        _project(conn, "p1", tmp_path)
        claude = _session(conn, "p1", "claude", "Claude")
        room = rooms.create_room(
            conn, rooms.CollaborationRoomCreate(project_id="p1", name="Room")
        )
        rooms.join_room(
            conn, room.id, rooms.CollaborationRoomJoin(session_id=claude.id)
        )
        first = rooms.post_message(
            conn,
            room.id,
            rooms.CollaborationRoomPost(session_id=claude.id, body_md="one"),
        )
        second = rooms.post_message(
            conn,
            room.id,
            rooms.CollaborationRoomPost(session_id=claude.id, body_md="two"),
        )
        synced = rooms.sync_room(conn, room.id, after_message_id=first.id)

    assert [m.id for m in synced.messages] == [second.id]
    assert synced.latest_message_id == second.id


def test_room_rejects_cross_project_session_and_non_member_post(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    with storage.transaction() as conn:
        _project(conn, "p1", tmp_path / "p1")
        _project(conn, "p2", tmp_path / "p2")
        owner = _session(conn, "p1", "claude", "Claude")
        outsider = _session(conn, "p2", "codex", "Codex")
        room = rooms.create_room(
            conn,
            rooms.CollaborationRoomCreate(
                project_id="p1", name="Room", created_by_session_id=owner.id
            ),
        )
        with pytest.raises(SynapseError):
            rooms.join_room(
                conn, room.id, rooms.CollaborationRoomJoin(session_id=outsider.id)
            )
        with pytest.raises(SynapseError):
            rooms.post_message(
                conn,
                room.id,
                rooms.CollaborationRoomPost(session_id=owner.id, body_md="not joined"),
            )


def test_session_truth_controls_room_presence(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    with storage.transaction() as conn:
        _project(conn, "p1", tmp_path)
        codex = _session(conn, "p1", "codex", "Codex")
        room = rooms.create_room(
            conn, rooms.CollaborationRoomCreate(project_id="p1", name="Room")
        )
        rooms.join_room(
            conn, room.id, rooms.CollaborationRoomJoin(session_id=codex.id)
        )
        assert rooms.sync_room(conn, room.id).members[0].present is True
        coordination.end_session(conn, codex.id)
        member = rooms.sync_room(conn, room.id).members[0]

    assert member.present is False
    assert member.session_status == coordination.AgentSessionStatus.GONE


def test_leave_preserves_history_but_removes_presence(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    with storage.transaction() as conn:
        _project(conn, "p1", tmp_path)
        claude = _session(conn, "p1", "claude", "Claude")
        room = rooms.create_room(
            conn, rooms.CollaborationRoomCreate(project_id="p1", name="Room")
        )
        rooms.join_room(
            conn, room.id, rooms.CollaborationRoomJoin(session_id=claude.id)
        )
        message = rooms.post_message(
            conn,
            room.id,
            rooms.CollaborationRoomPost(session_id=claude.id, body_md="handoff"),
        )
        left = rooms.leave_room(conn, room.id, claude.id)
        synced = rooms.sync_room(conn, room.id)

    assert left.left_at is not None
    assert synced.members == []
    assert [m.id for m in synced.messages] == [message.id]


def _client(storage: Storage, bus: EventBus) -> TestClient:
    app = FastAPI()

    async def _synapse_error_handler(_request, exc: SynapseError):
        return JSONResponse(status_code=exc.status, content=exc.envelope.model_dump())

    app.add_exception_handler(SynapseError, _synapse_error_handler)
    app.include_router(
        build_collaboration_rooms_router(storage, bus), prefix="/api/v1"
    )
    return TestClient(app)


def test_router_emits_realtime_room_events(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    bus = EventBus()
    with storage.transaction() as conn:
        _project(conn, "p1", tmp_path)
        claude = _session(conn, "p1", "claude", "Claude")

    client = _client(storage, bus)
    created = client.post(
        "/api/v1/collaboration/rooms",
        json={
            "project_id": "p1",
            "name": "Realtime",
            "created_by_session_id": claude.id,
        },
    )
    assert created.status_code == 201, created.text
    room_id = created.json()["id"]

    joined = client.post(
        f"/api/v1/collaboration/rooms/{room_id}/join",
        json={"session_id": claude.id},
    )
    assert joined.status_code == 200, joined.text

    posted = client.post(
        f"/api/v1/collaboration/rooms/{room_id}/messages",
        json={"session_id": claude.id, "kind": "question", "body_md": "Who owns tests?"},
    )
    assert posted.status_code == 201, posted.text

    names = [event.name for event in bus.replay_since(0)]
    assert "v1.collaboration.room_created" in names
    assert "v1.collaboration.room_joined" in names
    assert "v1.collaboration.message_posted" in names
