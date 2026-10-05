"""Connector-level proof for Synapse Video Studio MCP tools."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient
from synapse_daemon import video_assets
from synapse_daemon.app import build_app
from synapse_daemon.projects import Project, create
from synapse_daemon.storage import Storage
from synapse_daemon.ws import EventBus


def _harness(tmp_path: Path) -> tuple[TestClient, str]:
    project_root = tmp_path / "project"
    project_root.mkdir()
    storage = Storage(tmp_path / "data")
    storage.open()
    storage.migrate()
    with storage.transaction() as conn:
        create(conn, Project(id="demo-project", name="Demo Project", path=str(project_root), launch_cmd="echo hi"))
    app = build_app(storage, EventBus())
    return TestClient(app), app.state.auth.local_token


def _rpc(client: TestClient, token: str, method: str, params: dict | None = None, suffix: str = ""):
    body: dict = {"jsonrpc": "2.0", "id": 1, "method": method}
    if params is not None:
        body["params"] = params
    return client.post(f"/mcp/{token}{suffix}", json=body)


def _tool_result_json(response) -> dict:
    assert response.status_code == 200, response.text
    result = response.json()["result"]
    assert result["isError"] is False, result
    return json.loads(result["content"][0]["text"])


def test_video_tools_are_split_between_read_and_write_connectors(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SYNAPSE_MCP_ALLOW_WRITES", "1")
    client, token = _harness(tmp_path)

    full_names = {t["name"] for t in _rpc(client, token, "tools/list").json()["result"]["tools"]}
    read_names = {
        t["name"] for t in _rpc(client, token, "tools/list", suffix="?mode=read").json()["result"]["tools"]
    }

    assert {
        "synapse_video_generation_status",
        "synapse_get_video_plan",
        "synapse_get_video_job",
        "synapse_list_project_videos",
        "synapse_get_video_asset",
        "synapse_audit_video_assets",
    } <= read_names
    assert {"synapse_create_video_plan", "synapse_start_video_render", "synapse_cancel_video_render"} <= full_names
    assert "synapse_start_video_render" not in read_names


def test_video_status_is_callable_without_provider_key(tmp_path: Path, monkeypatch) -> None:
    for key in ("GEMINI_API_KEY", "GOOGLE_API_KEY"):
        monkeypatch.delenv(key, raising=False)
    client, token = _harness(tmp_path)

    payload = _tool_result_json(
        _rpc(client, token, "tools/call", {"name": "synapse_video_generation_status", "arguments": {}})
    )
    assert payload["capability"] == "video_generation"
    assert payload["provider"] == "local"
    assert payload["requires_cloud_api_key"] is False
    assert payload["supports"]["max_video_seconds"] == 300
    assert payload["supports"]["native_audio"] is True


def test_create_video_plan_tool_calls_shared_service(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SYNAPSE_MCP_ALLOW_WRITES", "1")
    client, token = _harness(tmp_path)
    captured: dict = {}

    def fake_create(storage, **kwargs):
        captured["storage"] = storage
        captured.update(kwargs)
        return {"created": True, "plan_id": "plan123", "planned_duration_seconds": 16}

    monkeypatch.setattr(video_assets, "create_video_plan", fake_create)
    payload = _tool_result_json(
        _rpc(
            client,
            token,
            "tools/call",
            {
                "name": "synapse_create_video_plan",
                "arguments": {
                    "project_id": "demo-project",
                    "title": "Short film",
                    "brief": "One coherent protagonist journey.",
                    "character_bible": "Same person, same clothes, same voice.",
                    "shots": [
                        {"prompt": "Opening", "duration_seconds": 8, "continuity_group": "scene-a"},
                        {"prompt": "Continue", "duration_seconds": 8, "continuity_group": "scene-a"},
                    ],
                },
            },
        )
    )
    assert captured["storage"] is client.app.state.storage
    assert captured["character_bible"].startswith("Same person")
    assert len(captured["shots"]) == 2
    assert payload["plan_id"] == "plan123"


def test_start_video_render_tool_returns_detached_receipt(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SYNAPSE_MCP_ALLOW_WRITES", "1")
    client, token = _harness(tmp_path)
    captured: dict = {}

    def fake_start(storage, **kwargs):
        captured.update(kwargs)
        return {"started": True, "job_id": "job123", "status": "starting"}

    monkeypatch.setattr(video_assets, "start_video_render", fake_start)
    payload = _tool_result_json(
        _rpc(
            client,
            token,
            "tools/call",
            {
                "name": "synapse_start_video_render",
                "arguments": {
                    "project_id": "demo-project",
                    "plan_id": "plan123",
                    "relative_path": "public/video/story.mp4",
                },
            },
        )
    )
    assert captured["relative_path"] == "public/video/story.mp4"
    assert payload == {"started": True, "job_id": "job123", "status": "starting"}
