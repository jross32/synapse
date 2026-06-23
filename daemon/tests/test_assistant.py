"""Tests for the local-LLM assistant (ADR-0014). Ollama is mocked."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from synapse_daemon import ollama_client
from synapse_daemon.app import build_app
from synapse_daemon.projects import Project, create
from synapse_daemon.storage import Storage
from synapse_daemon.ws import EventBus


def _harness(tmp_path: Path) -> TestClient:
    storage = Storage(tmp_path / "data")
    storage.open()
    storage.migrate()
    with storage.transaction() as conn:
        create(
            conn,
            Project(id="demo-project", name="Demo Project", path=str(tmp_path), launch_cmd="echo hi"),
        )
    app = build_app(storage, EventBus())
    return TestClient(app, headers={"X-Synapse-Token": app.state.auth.local_token})


@pytest.fixture
def mock_ollama(monkeypatch: pytest.MonkeyPatch) -> dict:
    captured: dict = {}

    async def fake_server_up(timeout: float = 1.5) -> bool:
        return True

    async def fake_list_models() -> list[dict]:
        return [{"name": "llama3.2", "size": 2000000000, "family": "llama"}]

    async def fake_chat(model: str, messages: list[dict], timeout: float = 180.0) -> str:
        captured["model"] = model
        captured["messages"] = messages
        return "Hi! I'm your local Synapse assistant."

    monkeypatch.setattr(ollama_client, "is_installed", lambda: True)
    monkeypatch.setattr(ollama_client, "server_up", fake_server_up)
    monkeypatch.setattr(ollama_client, "list_models", fake_list_models)
    monkeypatch.setattr(ollama_client, "chat", fake_chat)
    monkeypatch.setattr(ollama_client, "start_server", lambda: True)
    monkeypatch.setattr(ollama_client, "stop_server", lambda: 1)
    return captured


def test_status_off_by_default(tmp_path: Path, mock_ollama: dict) -> None:
    client = _harness(tmp_path)
    res = client.get("/api/v1/assistant/status")
    assert res.status_code == 200, res.text
    d = res.json()
    assert d["installed"] is True
    assert d["server_up"] is True
    assert d["enabled"] is False  # OFF by default
    assert any(m["name"] == "llama3.2" for m in d["models"])


def test_enable_toggle(tmp_path: Path, mock_ollama: dict) -> None:
    client = _harness(tmp_path)
    res = client.patch("/api/v1/assistant/settings", json={"enabled": True, "default_model": "llama3.2"})
    assert res.status_code == 200, res.text
    assert res.json()["enabled"] is True
    assert client.get("/api/v1/assistant/status").json()["enabled"] is True


def test_chat_roundtrip_with_context(tmp_path: Path, mock_ollama: dict) -> None:
    client = _harness(tmp_path)
    chat = client.post("/api/v1/assistant/chats", json={"title": "Hello"}).json()
    res = client.post(
        f"/api/v1/assistant/chats/{chat['id']}/messages",
        json={"content": "what projects do I have?", "include_context": True},
    )
    assert res.status_code == 200, res.text
    assert "local Synapse assistant" in res.json()["content"]
    # The model received a system message naming the live project.
    sys_msgs = [m for m in mock_ollama["messages"] if m["role"] == "system"]
    assert sys_msgs and "Demo Project" in sys_msgs[0]["content"]
    # Both turns persisted.
    detail = client.get(f"/api/v1/assistant/chats/{chat['id']}").json()
    assert [m["role"] for m in detail["messages"]] == ["user", "assistant"]


def test_chat_no_model_is_400(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mock_ollama: dict) -> None:
    # No installed models + no default -> a clean error, not a 500.
    async def empty_models() -> list[dict]:
        return []

    monkeypatch.setattr(ollama_client, "list_models", empty_models)
    client = _harness(tmp_path)
    chat = client.post("/api/v1/assistant/chats", json={}).json()
    res = client.post(f"/api/v1/assistant/chats/{chat['id']}/messages", json={"content": "hi"})
    assert res.status_code == 422  # clean "no model" error, not a 500


def test_engine_start_stop(tmp_path: Path, mock_ollama: dict) -> None:
    client = _harness(tmp_path)
    assert client.post("/api/v1/assistant/engine/start").json()["server_up"] is True
    assert client.post("/api/v1/assistant/engine/stop").json()["stopped"] == 1


def test_delete_chat(tmp_path: Path, mock_ollama: dict) -> None:
    client = _harness(tmp_path)
    chat = client.post("/api/v1/assistant/chats", json={}).json()
    assert client.delete(f"/api/v1/assistant/chats/{chat['id']}").status_code == 204
    assert client.get(f"/api/v1/assistant/chats/{chat['id']}").status_code == 404
