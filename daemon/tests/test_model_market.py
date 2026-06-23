"""Tests for the local-model marketplace (ADR-0014 Phase M). Ollama is mocked."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from synapse_daemon import ollama_client
from synapse_daemon.app import build_app
from synapse_daemon.model_market import ModelPullManager
from synapse_daemon.storage import Storage
from synapse_daemon.ws import EventBus


def _harness(tmp_path: Path) -> TestClient:
    storage = Storage(tmp_path / "data")
    storage.open()
    storage.migrate()
    app = build_app(storage, EventBus())
    return TestClient(app, headers={"X-Synapse-Token": app.state.auth.local_token})


@pytest.fixture
def installed(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_list_models() -> list[dict]:
        return [{"name": "llama3.2:1b", "size": 1, "details": {}}]

    async def fake_delete(model: str) -> bool:
        return True

    monkeypatch.setattr(ollama_client, "is_installed", lambda: True)
    monkeypatch.setattr(ollama_client, "list_models", fake_list_models)
    monkeypatch.setattr(ollama_client, "delete_model", fake_delete)


def test_registry_marks_installed(tmp_path: Path, installed: None) -> None:
    client = _harness(tmp_path)
    res = client.get("/api/v1/models/registry")
    assert res.status_code == 200, res.text
    by_id = {m["id"]: m for m in res.json()["models"]}
    assert by_id["llama3.2:1b"]["installed"] is True  # cross-referenced
    assert by_id["llama3.2:3b"]["installed"] is False
    assert by_id["llama3.2:1b"]["recommended"] is True


def test_registry_renders_without_ollama(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ollama_client, "is_installed", lambda: False)
    client = _harness(tmp_path)
    res = client.get("/api/v1/models/registry")
    assert res.status_code == 200
    assert len(res.json()["models"]) > 0  # catalog still shows; nothing installed
    assert all(m["installed"] is False for m in res.json()["models"])


def test_pull_requires_ollama(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ollama_client, "is_installed", lambda: False)
    client = _harness(tmp_path)
    res = client.post("/api/v1/models/pull", json={"name": "llama3.2:1b"})
    assert res.status_code == 422  # clean error, not a 500


def test_remove_model(tmp_path: Path, installed: None) -> None:
    client = _harness(tmp_path)
    res = client.post("/api/v1/models/remove", json={"name": "llama3.2:1b"})
    assert res.status_code == 200
    assert res.json()["deleted"] is True


def test_pull_manager_streams_to_success(monkeypatch: pytest.MonkeyPatch) -> None:
    # The streaming logic, tested directly (deterministic, no HTTP loop races).
    async def fake_pull(name: str):
        yield {"status": "pulling manifest"}
        yield {"status": "downloading", "total": 100, "completed": 40}
        yield {"status": "downloading", "total": 100, "completed": 100}
        yield {"status": "success"}

    monkeypatch.setattr(ollama_client, "pull", fake_pull)
    mgr = ModelPullManager(EventBus())

    async def run() -> None:
        state = mgr.start("llama3.2:1b")
        assert state.status == "queued"
        await mgr._tasks["llama3.2:1b"]

    asyncio.run(run())
    final = mgr.get("llama3.2:1b")
    assert final is not None
    assert final.status == "success"
    assert final.percent == 100.0
    assert final.total == 100


def test_pull_manager_records_error(monkeypatch: pytest.MonkeyPatch) -> None:
    async def boom_pull(name: str):
        yield {"status": "starting"}
        yield {"error": "model not found"}

    monkeypatch.setattr(ollama_client, "pull", boom_pull)
    mgr = ModelPullManager(EventBus())

    async def run() -> None:
        mgr.start("does-not-exist")
        await mgr._tasks["does-not-exist"]

    asyncio.run(run())
    final = mgr.get("does-not-exist")
    assert final is not None
    assert final.status == "error"
    assert final.error == "model not found"


def test_pull_is_idempotent_while_active(monkeypatch: pytest.MonkeyPatch) -> None:
    async def slow_pull(name: str):
        await asyncio.sleep(0.05)
        yield {"status": "success"}

    monkeypatch.setattr(ollama_client, "pull", slow_pull)
    mgr = ModelPullManager(EventBus())

    async def run() -> None:
        a = mgr.start("m")
        b = mgr.start("m")  # second call must not spawn a 2nd task
        assert a is b
        assert len(mgr.list()) == 1
        await mgr._tasks["m"]

    asyncio.run(run())
    assert mgr.get("m").status == "success"
