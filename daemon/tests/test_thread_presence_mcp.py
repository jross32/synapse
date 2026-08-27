from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from synapse_daemon.app import build_app
from synapse_daemon.projects import Project, create
from synapse_daemon.storage import Storage
from synapse_daemon.ws import EventBus


def _harness(tmp_path: Path) -> tuple[TestClient, str]:
    storage = Storage(tmp_path / "data")
    storage.open()
    storage.migrate()
    with storage.transaction() as conn:
        create(
            conn,
            Project(
                id="demo-project",
                name="Demo Project",
                path=str(tmp_path),
                launch_cmd="echo hi",
            ),
        )
    app = build_app(storage, EventBus())
    return TestClient(app), app.state.auth.local_token


def _rpc(client: TestClient, token: str, name: str, arguments: dict):
    return client.post(
        f"/mcp/{token}",
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        },
    )


def _tool_json(response) -> dict:
    result = response.json()["result"]
    assert result["isError"] is False, result
    return json.loads(result["content"][0]["text"])


def test_context_advertises_thread_tracking_protocol(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SYNAPSE_MCP_ALLOW_WRITES", "1")
    client, token = _harness(tmp_path)
    body = _tool_json(_rpc(client, token, "synapse_get_context", {}))
    assert body["thread_tracking"]["enabled"] is True
    assert body["thread_tracking"]["bootstrap_required_for_project_work"] is True
    assert "begin turn" in body["thread_tracking"]["protocol"]


def test_mcp_thread_lifecycle_and_group_decision(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SYNAPSE_MCP_ALLOW_WRITES", "1")
    client, token = _harness(tmp_path)

    inspect = _tool_json(
        _rpc(
            client,
            token,
            "synapse_thread_bootstrap",
            {
                "project_id": "demo-project",
                "external_thread_key": "chat-1",
                "runtime_id": "chatgpt",
                "title": "Build dashboard",
            },
        )
    )
    assert inspect["needs_group_decision"] is True
    assert inspect["thread"] is None

    created = _tool_json(
        _rpc(
            client,
            token,
            "synapse_thread_bootstrap",
            {
                "project_id": "demo-project",
                "external_thread_key": "chat-1",
                "runtime_id": "chatgpt",
                "title": "Build dashboard",
                "create_group_name": "Dashboard build",
                "create_group_description": "Build and verify the dashboard",
            },
        )
    )
    thread_id = created["thread"]["id"]

    turn = _tool_json(
        _rpc(
            client,
            token,
            "synapse_thread_begin_turn",
            {
                "thread_id": thread_id,
                "prompt_label": "Implement dashboard",
                "current_task": "coding dashboard",
            },
        )
    )
    assert turn["status"] == "active"

    hb = _tool_json(
        _rpc(
            client,
            token,
            "synapse_thread_heartbeat",
            {"thread_id": thread_id, "status": "active", "current_task": "testing"},
        )
    )
    assert hb["display_status"] == "active"
    assert hb["current_task"] == "testing"

    finished = _tool_json(
        _rpc(
            client,
            token,
            "synapse_thread_finish_turn",
            {
                "thread_id": thread_id,
                "turn_id": turn["id"],
                "duration_seconds": 123,
                "duration_source": "ui_display",
                "summary_md": "Dashboard finished.",
            },
        )
    )
    assert finished["thread"]["total_work_seconds"] == 123
    assert finished["thread"]["turn_count"] == 1
    assert finished["thread"]["display_status"] == "idle"


def test_read_only_connector_does_not_advertise_thread_write_tools(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SYNAPSE_MCP_ALLOW_WRITES", "1")
    client, token = _harness(tmp_path)
    res = client.post(
        f"/mcp/{token}?mode=read",
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
    )
    names = {item["name"] for item in res.json()["result"]["tools"]}
    assert "synapse_thread_bootstrap" not in names
    assert "synapse_thread_begin_turn" not in names
    assert "synapse_thread_finish_turn" not in names
