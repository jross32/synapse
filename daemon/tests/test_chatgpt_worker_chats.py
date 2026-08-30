"""Tests for durable ChatGPT UI worker-chat lifecycle."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from synapse_daemon import agent_squads, coordination, routes_chatgpt_workers
from synapse_daemon import chatgpt_worker_chats as workers
from synapse_daemon.errors import SynapseError
from synapse_daemon.projects import Project
from synapse_daemon.projects import create as create_project
from synapse_daemon.routes_chatgpt_workers import build_chatgpt_workers_router
from synapse_daemon.storage import Storage


def _storage(tmp_path: Path) -> Storage:
    storage = Storage(tmp_path / "data")
    storage.open()
    storage.migrate()
    return storage


def _seed(storage: Storage, tmp_path: Path) -> tuple[str, str, str]:
    with storage.transaction() as conn:
        create_project(
            conn,
            Project(
                id="p1",
                name="Project One",
                path=str(tmp_path),
                launch_cmd="echo ready",
            ),
        )
        owner = coordination.register_session(
            conn,
            coordination.AgentSessionRegister(
                project_id="p1",
                runtime_id="chatgpt",
                agent_label="Parent ChatGPT",
            ),
        )
        squad = agent_squads.create_squad(
            conn,
            agent_squads.AgentSquadCreate(
                project_id="p1",
                name="Workers",
                lead_role_id=None,
            ),
        )
        work = agent_squads.create_work_item(
            conn,
            squad.id,
            agent_squads.AgentWorkItemCreate(
                title="Test the login flow",
            ),
        )
    return owner.id, squad.id, work.id


def _add_work(storage: Storage, squad_id: str, title: str) -> str:
    with storage.transaction() as conn:
        item = agent_squads.create_work_item(
            conn,
            squad_id,
            agent_squads.AgentWorkItemCreate(
                title=title,
            ),
        )
    return item.id


def test_same_work_item_resumes_same_worker_chat(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    owner_id, _squad_id, work_id = _seed(storage, tmp_path)

    with storage.transaction() as conn:
        first, reused_first = workers.resolve_for_launch(
            conn,
            work_item_id=work_id,
            project_id="p1",
            owner_session_id=owner_id,
            role_id=None,
            title="QA · Project One · Test the login flow",
        )
        workers.mark_active(
            conn,
            first.id,
            session_id=owner_id,
            conversation_url="https://chatgpt.com/c/worker-1",
        )
        workers.mark_idle(conn, first.id)
        second, reused_second = workers.resolve_for_launch(
            conn,
            work_item_id=work_id,
            project_id="p1",
            owner_session_id=owner_id,
            role_id=None,
            title="QA · Project One · Test the login flow",
        )

    assert reused_first is False
    assert reused_second is True
    assert second.id == first.id
    assert second.conversation_url == "https://chatgpt.com/c/worker-1"
    assert second.status == workers.ChatGPTWorkerStatus.IDLE


def test_related_work_item_reuses_only_when_explicitly_requested(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    owner_id, squad_id, first_work_id = _seed(storage, tmp_path)
    unrelated_id = _add_work(storage, squad_id, "Audit settings")
    related_id = _add_work(storage, squad_id, "Retest login after the fix")

    with storage.transaction() as conn:
        original, _ = workers.resolve_for_launch(
            conn,
            work_item_id=first_work_id,
            project_id="p1",
            owner_session_id=owner_id,
            role_id=None,
            title="QA · Project One · Test the login flow",
        )
        independent, reused_independent = workers.resolve_for_launch(
            conn,
            work_item_id=unrelated_id,
            project_id="p1",
            owner_session_id=owner_id,
            role_id=None,
            title="QA · Project One · Audit settings",
        )
        related, reused_related = workers.resolve_for_launch(
            conn,
            work_item_id=related_id,
            project_id="p1",
            owner_session_id=owner_id,
            role_id=None,
            title="QA · Project One · Retest login after the fix",
            reuse_from_work_item_id=first_work_id,
        )

    assert reused_independent is False
    assert independent.id != original.id
    assert reused_related is True
    assert related.id == original.id
    assert set(related.work_item_ids) == {first_work_id, related_id}


def test_archived_worker_is_never_automatically_resumed(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    owner_id, _squad_id, work_id = _seed(storage, tmp_path)

    with storage.transaction() as conn:
        original, _ = workers.resolve_for_launch(
            conn,
            work_item_id=work_id,
            project_id="p1",
            owner_session_id=owner_id,
            role_id=None,
            title="QA · Project One · Test the login flow",
        )
        archived = workers.archive_chat(conn, original.id, reason="Project shipped")
        assert archived.status == workers.ChatGPTWorkerStatus.ARCHIVED

        # A same-work-item launch gets a fresh worker instead of silently reviving
        # something the operator intentionally retired.
        replacement, reused = workers.resolve_for_launch(
            conn,
            work_item_id=work_id,
            project_id="p1",
            owner_session_id=owner_id,
            role_id=None,
            title="QA · Project One · Test the login flow",
        )

    assert reused is False
    assert replacement.id != original.id


def test_archived_related_worker_must_be_unarchived_first(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    owner_id, squad_id, work_id = _seed(storage, tmp_path)
    related_id = _add_work(storage, squad_id, "Follow-up")

    with storage.transaction() as conn:
        original, _ = workers.resolve_for_launch(
            conn,
            work_item_id=work_id,
            project_id="p1",
            owner_session_id=owner_id,
            role_id=None,
            title="QA · Project One · Test the login flow",
        )
        workers.archive_chat(conn, original.id, reason="One-off task")
        with pytest.raises(SynapseError):
            workers.resolve_for_launch(
                conn,
                work_item_id=related_id,
                project_id="p1",
                owner_session_id=owner_id,
                role_id=None,
                title="QA · Project One · Follow-up",
                reuse_from_work_item_id=work_id,
            )


def _client(storage: Storage) -> TestClient:
    app = FastAPI()

    async def _synapse_error_handler(_request, exc: SynapseError):
        return JSONResponse(status_code=exc.status, content=exc.envelope.model_dump())

    app.add_exception_handler(SynapseError, _synapse_error_handler)
    app.include_router(build_chatgpt_workers_router(storage), prefix="/api/v1")
    return TestClient(app)


def test_worker_routes_list_archive_and_unarchive_without_delete(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    owner_id, _squad_id, work_id = _seed(storage, tmp_path)
    with storage.transaction() as conn:
        worker, _ = workers.resolve_for_launch(
            conn,
            work_item_id=work_id,
            project_id="p1",
            owner_session_id=owner_id,
            role_id=None,
            title="QA · Project One · Test the login flow",
        )

    client = _client(storage)
    listed = client.get("/api/v1/chatgpt-workers?project_id=p1")
    assert listed.status_code == 200, listed.text
    assert listed.json()["project_name"] == workers.WORKER_PROJECT_NAME
    assert [item["id"] for item in listed.json()["workers"]] == [worker.id]

    archived = client.post(
        f"/api/v1/chatgpt-workers/{worker.id}/archive",
        json={"reason": "Project finished"},
    )
    assert archived.status_code == 200, archived.text
    assert archived.json()["status"] == "archived"

    hidden = client.get("/api/v1/chatgpt-workers?project_id=p1").json()["workers"]
    assert hidden == []
    all_workers = client.get(
        "/api/v1/chatgpt-workers?project_id=p1&include_archived=true"
    ).json()["workers"]
    assert len(all_workers) == 1
    assert all_workers[0]["conversation_url"] == ""

    restored = client.post(f"/api/v1/chatgpt-workers/{worker.id}/unarchive")
    assert restored.status_code == 200, restored.text
    assert restored.json()["status"] == "idle"


def test_worker_routes_expose_readiness_and_safe_setup_browser(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    storage = _storage(tmp_path)
    client = _client(storage)

    readiness = client.get("/api/v1/chatgpt-workers/readiness")
    assert readiness.status_code == 200, readiness.text
    state = readiness.json()
    assert state["ready"] is False
    assert state["worker_project_name"] == "Synapse2GPT Workers"
    assert state["recommended_project_memory"] == "default"
    assert state["recommended_project_sharing"] == "private"

    captured: dict[str, object] = {}

    def fake_launch(data_dir: Path) -> dict[str, object]:
        captured["data_dir"] = data_dir
        return {
            "launched": True,
            "pid": 4242,
            "profile_dir": str(data_dir / "chatgpt-browser-profile"),
            "worker_project_name": "Synapse2GPT Workers",
        }

    monkeypatch.setattr(
        routes_chatgpt_workers.chatgpt_child_agents, "launch_setup_browser", fake_launch
    )
    opened = client.post("/api/v1/chatgpt-workers/setup-browser")
    assert opened.status_code == 200, opened.text
    assert opened.json()["launched"] is True
    assert captured["data_dir"] == storage.data_dir


def test_two_worker_rows_cannot_claim_the_same_chatgpt_conversation_url(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    owner_id, squad_id, first_work_id = _seed(storage, tmp_path)
    second_work_id = _add_work(storage, squad_id, "Independent second task")

    with storage.transaction() as conn:
        first, _ = workers.resolve_for_launch(
            conn, work_item_id=first_work_id, project_id="p1", owner_session_id=owner_id,
            role_id=None, title="First worker",
        )
        second, _ = workers.resolve_for_launch(
            conn, work_item_id=second_work_id, project_id="p1", owner_session_id=owner_id,
            role_id=None, title="Second worker",
        )
        workers.mark_active(
            conn, first.id, session_id=owner_id, conversation_url="https://chatgpt.com/c/one-real-chat"
        )
        with pytest.raises(SynapseError) as exc_info:
            workers.mark_active(
                conn, second.id, session_id=owner_id, conversation_url="https://chatgpt.com/c/one-real-chat"
            )

    assert exc_info.value.envelope.code == "chatgpt_worker_chat.conflict"
    assert exc_info.value.status == 409
    assert exc_info.value.envelope.details["existing_worker_chat_id"] == first.id
    assert workers.get_chat(storage.conn, second.id).conversation_url == ""

    # Migration 040 is the final backstop: even code that bypasses the helper
    # cannot make two durable worker rows claim one real ChatGPT conversation.
    with pytest.raises(sqlite3.IntegrityError):
        with storage.transaction() as conn:
            conn.execute(
                "UPDATE chatgpt_worker_chats SET conversation_url = ? WHERE id = ?",
                ("https://chatgpt.com/c/one-real-chat", second.id),
            )



def test_recovery_accounting_is_durable_and_bounded(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    owner_id, _squad_id, work_id = _seed(storage, tmp_path)
    with storage.transaction() as conn:
        chat = workers.create_chat(
            conn, project_id="p1", owner_session_id=owner_id, role_id=None, title="Worker", work_item_id=work_id
        )
        workers.record_recovery(conn, chat.id, outcome="failed", error="tab frozen")
        workers.record_recovery(conn, chat.id, outcome="succeeded")
        current = workers.get_chat(conn, chat.id)

    recovery = current.metadata["recovery"]
    assert recovery["attempts"] == 2
    assert recovery["successes"] == 1
    assert recovery["last_outcome"] == "succeeded"
    assert recovery["last_error"] == ""
    assert [entry["outcome"] for entry in recovery["history"]] == ["failed", "succeeded"]


def test_recovery_accounting_keeps_only_last_ten_events(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    owner_id, _squad_id, work_id = _seed(storage, tmp_path)
    with storage.transaction() as conn:
        chat = workers.create_chat(
            conn, project_id="p1", owner_session_id=owner_id, role_id=None, title="Worker", work_item_id=work_id
        )
        for i in range(12):
            workers.record_recovery(conn, chat.id, outcome="failed", error=f"e{i}")
        current = workers.get_chat(conn, chat.id)

    history = current.metadata["recovery"]["history"]
    assert len(history) == 10
    assert history[0]["error"] == "e2"
    assert history[-1]["error"] == "e11"


def test_restart_reconciliation_makes_interrupted_worker_resumable(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    owner_id, _squad_id, work_id = _seed(storage, tmp_path)
    with storage.transaction() as conn:
        chat = workers.create_chat(
            conn, project_id="p1", owner_session_id=owner_id, role_id=None,
            title="Worker", work_item_id=work_id
        )
        workers.mark_active(
            conn, chat.id, session_id=owner_id,
            conversation_url="https://chatgpt.com/c/resumable-worker"
        )
        changed = workers.reconcile_interrupted_workers(conn)
        current = workers.get_chat(conn, chat.id)

    assert changed == [chat.id]
    assert current.status == workers.ChatGPTWorkerStatus.IDLE
    assert current.conversation_url == "https://chatgpt.com/c/resumable-worker"
    assert current.metadata["restart_recovery"]["pending"] is True
    assert current.metadata["restart_recovery"]["previous_status"] == "active"


def test_mark_active_clears_restart_recovery_pending(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    owner_id, _squad_id, work_id = _seed(storage, tmp_path)
    with storage.transaction() as conn:
        chat = workers.create_chat(
            conn, project_id="p1", owner_session_id=owner_id, role_id=None,
            title="Worker", work_item_id=work_id
        )
        workers.mark_active(
            conn, chat.id, session_id=owner_id,
            conversation_url="https://chatgpt.com/c/resume-me"
        )
        workers.reconcile_interrupted_workers(conn)
        resumed = workers.mark_active(
            conn, chat.id, session_id=owner_id,
            conversation_url="https://chatgpt.com/c/resume-me"
        )

    restart = resumed.metadata["restart_recovery"]
    assert restart["pending"] is False
    assert restart["resumed_at"]
