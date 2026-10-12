"""Chrome-created ChatGPT worker catalog preservation and archive tests."""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from synapse_daemon import chatgpt_worker_catalog as catalog
from synapse_daemon import chatgpt_worker_chats as workers
from synapse_daemon import thread_presence
from synapse_daemon.projects import Project, create as create_project
from synapse_daemon.routes_chatgpt_workers import build_chatgpt_workers_router
from synapse_daemon.routes_thread_presence import build_thread_presence_router
from synapse_daemon.storage import Storage


URL = (
    "https://chatgpt.com/g/"
    "g-p-6a91003e980c81919b8920cfc9e0941e-synapse2gpt-workers/"
    "c/6acd5519-c1cc-83e9-94da-d28c4c01edbd"
)


def setup(tmp_path: Path):
    storage = Storage(tmp_path / "data")
    storage.open()
    storage.migrate()
    with storage.transaction() as conn:
        create_project(
            conn,
            Project(id="synapse-self", name="Synapse Self", path=str(tmp_path),
                    launch_cmd="echo ready"),
        )
    app = FastAPI()
    app.include_router(build_thread_presence_router(storage), prefix="/api/v1")
    app.include_router(build_chatgpt_workers_router(storage), prefix="/api/v1")
    return storage, TestClient(app)


def observation(status: str, url: str = URL) -> dict:
    return {
        "external_thread_key": "6acd5519-c1cc-83e9-94da-d28c4c01edbd",
        "runtime_id": "chatgpt",
        "browser_tab_id": "123",
        "conversation_url": url,
        "title": "Synapse Worker 2",
        "status": status,
        "current_task": "Review the companion extension, read only",
    }


def test_observed_worker_auto_registered_parked_reopened(tmp_path: Path):
    storage, client = setup(tmp_path)
    first = client.post("/api/v1/thread-presence/browser-observe", json=observation("active"))
    assert first.status_code == 200, first.text
    worker_id = first.json()["worker_chat_id"]
    assert worker_id
    found = client.get("/api/v1/chatgpt-workers/catalog").json()
    assert found["total"] == 1
    assert found["open_count"] == 1
    assert found["workers"][0]["status"] == "active"
    assert found["workers"][0]["conversation_url"] == URL
    assert found["workers"][0]["metadata"]["current_task"].startswith("Review")

    handoff = client.post(
        f"/api/v1/chatgpt-workers/{worker_id}/handoff",
        json={"handoff_md": "Inspected extension and verified manifest", "next_step": "Run live Chrome QA"},
    )
    assert handoff.status_code == 200, handoff.text
    assert handoff.json()["metadata"]["handoff_md"] == "Inspected extension and verified manifest"
    assert handoff.json()["metadata"]["next_step"] == "Run live Chrome QA"
    second = client.post("/api/v1/thread-presence/browser-observe", json=observation("idle"))
    assert second.status_code == 200
    assert second.json()["worker_chat_id"] == worker_id
    gone = client.post("/api/v1/thread-presence/browser-observe", json=observation("gone"))
    assert gone.status_code == 200
    parked = client.get("/api/v1/chatgpt-workers/catalog").json()
    assert parked["total"] == 1
    assert parked["open_count"] == 0
    assert parked["parked_count"] == 1
    assert parked["workers"][0]["status"] == "idle"
    assert parked["workers"][0]["conversation_url"] == URL
    assert parked["workers"][0]["metadata"]["next_step"] == "Run live Chrome QA"

    resumed = client.post("/api/v1/thread-presence/browser-observe", json=observation("active"))
    assert resumed.status_code == 200
    assert resumed.json()["worker_chat_id"] == worker_id
    assert client.get("/api/v1/chatgpt-workers/catalog").json()["open_count"] == 1

    client.post("/api/v1/thread-presence/browser-observe", json=observation("gone"))
    archived = client.post(f"/api/v1/chatgpt-workers/{worker_id}/archive",
                           json={"reason": "Finished"})
    assert archived.status_code == 200
    assert archived.json()["status"] == "archived"
    still = client.get("/api/v1/chatgpt-workers/catalog").json()["workers"][0]
    assert still["conversation_url"] == URL
    assert still["parked"] is False
    assert client.post("/api/v1/thread-presence/browser-observe",
                       json=observation("idle")).json()["worker_chat_id"] == worker_id
    assert client.get("/api/v1/chatgpt-workers/catalog").json()["workers"][0]["status"] == "archived"
    assert client.post(f"/api/v1/chatgpt-workers/{worker_id}/unarchive").json()["status"] == "idle"
    storage.close()


def test_only_approved_worker_project_is_imported(tmp_path: Path):
    storage, client = setup(tmp_path)
    invalid = (
        "https://evil.example/g/g-p-6a91003e980c81919b8920cfc9e0941e/c/x",
        "https://chatgpt.com/g/g-p-another-project/c/x",
        "https://chatgpt.com/g/g-p-6a91003e980c81919b8920cfc9e0941e/project",
        "http://chatgpt.com/g/g-p-6a91003e980c81919b8920cfc9e0941e/c/x",
        "https://chatgpt.com/c/other-chat",
    )
    for url in invalid:
        result = client.post("/api/v1/thread-presence/browser-observe",
                             json=observation("idle", url))
        assert result.status_code == 200
        assert result.json()["worker_chat_id"] is None
    assert client.get("/api/v1/chatgpt-workers/catalog").json()["total"] == 0
    storage.close()
