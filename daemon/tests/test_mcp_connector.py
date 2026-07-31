"""Tests for the claude.ai MCP connector endpoint (ADR-0012)."""

from __future__ import annotations

from pathlib import Path

import pytest
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
    token = app.state.auth.local_token
    return TestClient(app), token


def _rpc(client: TestClient, token: str, method: str, params: dict | None = None, msg_id: int | None = 1):
    body: dict = {"jsonrpc": "2.0", "method": method}
    if msg_id is not None:
        body["id"] = msg_id
    if params is not None:
        body["params"] = params
    return client.post(f"/mcp/{token}", json=body)


def test_unauthorized_token_is_401(tmp_path: Path) -> None:
    client, _ = _harness(tmp_path)
    res = _rpc(client, "wrong-token", "initialize")
    assert res.status_code == 401
    assert res.json()["error"]["code"] == -32001


def test_initialize_handshake(tmp_path: Path) -> None:
    client, token = _harness(tmp_path)
    res = _rpc(client, token, "initialize", {"protocolVersion": "2025-06-18"})
    assert res.status_code == 200, res.text
    result = res.json()["result"]
    assert result["serverInfo"]["name"] == "synapse"
    assert "tools" in result["capabilities"]
    assert result["protocolVersion"] == "2025-06-18"


def test_initialized_notification_returns_202(tmp_path: Path) -> None:
    client, token = _harness(tmp_path)
    # A notification has no id.
    res = client.post(f"/mcp/{token}", json={"jsonrpc": "2.0", "method": "notifications/initialized"})
    assert res.status_code == 202


def test_ping(tmp_path: Path) -> None:
    client, token = _harness(tmp_path)
    res = _rpc(client, token, "ping")
    assert res.status_code == 200
    assert res.json()["result"] == {}


def test_tools_list_is_read_only_by_default(tmp_path: Path) -> None:
    client, token = _harness(tmp_path)
    res = _rpc(client, token, "tools/list")
    names = {t["name"] for t in res.json()["result"]["tools"]}
    assert "synapse_get_context" in names
    assert "synapse_list_projects" in names
    assert "synapse_get_project_records" in names
    # Writes are off by default -> the write tool is not advertised.
    assert "synapse_add_project_idea" not in names


def test_tools_call_list_projects(tmp_path: Path) -> None:
    client, token = _harness(tmp_path)
    res = _rpc(client, token, "tools/call", {"name": "synapse_list_projects", "arguments": {}})
    result = res.json()["result"]
    assert result["isError"] is False
    text = result["content"][0]["text"]
    assert "demo-project" in text


def test_tools_call_get_records(tmp_path: Path) -> None:
    client, token = _harness(tmp_path)
    res = _rpc(
        client, token, "tools/call",
        {"name": "synapse_get_project_records", "arguments": {"project_id": "demo-project"}},
    )
    result = res.json()["result"]
    assert result["isError"] is False
    assert '"adrs"' in result["content"][0]["text"]


def test_tools_call_unknown_project_is_tool_error(tmp_path: Path) -> None:
    client, token = _harness(tmp_path)
    res = _rpc(
        client, token, "tools/call",
        {"name": "synapse_get_project_records", "arguments": {"project_id": "nope"}},
    )
    result = res.json()["result"]
    assert result["isError"] is True


def test_unknown_method(tmp_path: Path) -> None:
    client, token = _harness(tmp_path)
    res = _rpc(client, token, "bogus/method")
    assert res.json()["error"]["code"] == -32601


def test_get_is_405(tmp_path: Path) -> None:
    client, token = _harness(tmp_path)
    assert client.get(f"/mcp/{token}").status_code == 405


def test_connector_info_authed(tmp_path: Path) -> None:
    client, token = _harness(tmp_path)
    res = client.get("/api/v1/mcp/connector", headers={"X-Synapse-Token": token})
    assert res.status_code == 200, res.text
    d = res.json()
    assert d["read_only"] is True
    assert d["mcp_path"] == f"/mcp/{token}"
    assert d["local_url"].endswith(f"/mcp/{token}")
    # No Cloudtap tunnel open in tests -> no connector URL yet.
    assert d["tunnel_open"] is False
    assert d["connector_url"] is None


def test_connector_info_requires_auth(tmp_path: Path) -> None:
    client, _ = _harness(tmp_path)
    res = client.get("/api/v1/mcp/connector")
    assert res.status_code in (401, 403)


def test_writes_opt_in_exposes_add_idea(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SYNAPSE_MCP_ALLOW_WRITES", "1")
    client, token = _harness(tmp_path)
    names = {t["name"] for t in _rpc(client, token, "tools/list").json()["result"]["tools"]}
    assert "synapse_add_project_idea" in names

    res = _rpc(
        client, token, "tools/call",
        {"name": "synapse_add_project_idea", "arguments": {"project_id": "demo-project", "title": "Use Redis"}},
    )
    result = res.json()["result"]
    assert result["isError"] is False
    assert "Use Redis" in result["content"][0]["text"]


def test_drive_tools_hidden_when_writes_off(tmp_path: Path) -> None:
    # Default = read-only: drive tools are neither advertised nor callable (ADR-0027).
    client, token = _harness(tmp_path)
    names = {t["name"] for t in _rpc(client, token, "tools/list").json()["result"]["tools"]}
    for tool in ("synapse_create_squad", "synapse_add_work_item", "synapse_capture_note"):
        assert tool not in names
    res = _rpc(
        client, token, "tools/call",
        {"name": "synapse_create_squad", "arguments": {"project_id": "demo-project", "name": "X"}},
    )
    assert res.json()["result"]["isError"] is True  # writes disabled -> tool error


def test_drive_create_squad_then_add_work_item(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import json

    monkeypatch.setenv("SYNAPSE_MCP_ALLOW_WRITES", "1")
    client, token = _harness(tmp_path)
    names = {t["name"] for t in _rpc(client, token, "tools/list").json()["result"]["tools"]}
    assert {"synapse_create_squad", "synapse_add_work_item", "synapse_capture_note"} <= names

    res = _rpc(
        client, token, "tools/call",
        {"name": "synapse_create_squad", "arguments": {"project_id": "demo-project", "name": "Drive test"}},
    )
    result = res.json()["result"]
    assert result["isError"] is False, result
    squad = json.loads(result["content"][0]["text"])
    assert squad["project_id"] == "demo-project"

    res2 = _rpc(
        client, token, "tools/call",
        {"name": "synapse_add_work_item",
         "arguments": {"squad_id": squad["id"], "title": "do the thing", "assigned_role_id": "implementer"}},
    )
    r2 = res2.json()["result"]
    assert r2["isError"] is False, r2
    work_item = json.loads(r2["content"][0]["text"])
    assert work_item["title"] == "do the thing"
    assert work_item["squad_id"] == squad["id"]


def test_drive_create_squad_unknown_project_is_tool_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SYNAPSE_MCP_ALLOW_WRITES", "1")
    client, token = _harness(tmp_path)
    res = _rpc(
        client, token, "tools/call",
        {"name": "synapse_create_squad", "arguments": {"project_id": "nope", "name": "X"}},
    )
    assert res.json()["result"]["isError"] is True


def test_drive_capture_note(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SYNAPSE_MCP_ALLOW_WRITES", "1")
    client, token = _harness(tmp_path)
    res = _rpc(
        client, token, "tools/call",
        {"name": "synapse_capture_note",
         "arguments": {"project_id": "demo-project", "content": "remember the /orders 500", "destination": "ai_context"}},
    )
    assert res.json()["result"]["isError"] is False, res.text


# -- AI activity read tools (ADR-0028 Phase 6) --------------------------------

def test_activity_read_tools_are_always_available(tmp_path: Path) -> None:
    # These are READ tools -- available without SYNAPSE_MCP_ALLOW_WRITES.
    client, token = _harness(tmp_path)
    names = {t["name"] for t in _rpc(client, token, "tools/list").json()["result"]["tools"]}
    assert {"synapse_list_sessions", "synapse_recent_activity"} <= names


def test_list_sessions_returns_numbered_sessions(tmp_path: Path) -> None:
    import json

    client, token = _harness(tmp_path)
    with client as c:
        c.post("/api/v1/coordination/sessions", json={"runtime_id": "claude", "agent_label": "Claude"},
               headers={"X-Synapse-Token": token})
        res = _rpc(c, token, "tools/call", {"name": "synapse_list_sessions", "arguments": {}})
        result = res.json()["result"]
        assert result["isError"] is False, result
        sessions = json.loads(result["content"][0]["text"])
        assert sessions and sessions[0]["seq"] == 1
        assert sessions[0]["runtime_id"] == "claude"
        # The connection grade an AI can read about itself.
        assert sessions[0]["connection_level"] in {"green", "yellow", "red"}
        assert sessions[0]["connection_code"]


def test_recent_activity_returns_the_feed(tmp_path: Path) -> None:
    import json

    client, token = _harness(tmp_path)
    with client as c:
        c.post("/api/v1/coordination/sessions", json={"runtime_id": "codex"},
               headers={"X-Synapse-Token": token})
        res = _rpc(c, token, "tools/call", {"name": "synapse_recent_activity", "arguments": {}})
        rows = json.loads(res.json()["result"]["content"][0]["text"])
        assert any(r["kind"] == "session.connected" for r in rows), rows
