from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient
from synapse_daemon.app import build_app
from synapse_daemon.projects import Project, create
from synapse_daemon.storage import Storage
from synapse_daemon.ws import EventBus


def _harness(tmp_path: Path) -> tuple[TestClient, str, Path]:
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
    return TestClient(app), app.state.auth.local_token, storage.db_path


def _rpc(client: TestClient, token: str, method: str, params: dict | None = None):
    body: dict = {"jsonrpc": "2.0", "id": 1, "method": method}
    if params is not None:
        body["params"] = params
    return client.post(f"/mcp/{token}", json=body)


def _tool_json(response) -> dict:
    result = response.json()["result"]
    assert result["isError"] is False, result
    return json.loads(result["content"][0]["text"])


def test_trace_tools_are_advertised_on_correct_surfaces(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SYNAPSE_MCP_ALLOW_WRITES", "1")
    client, token, _db_path = _harness(tmp_path)

    full = _rpc(client, token, "tools/list").json()["result"]["tools"]
    full_names = {tool["name"] for tool in full}
    assert "synapse_trace_recent" in full_names
    assert "synapse_trace_analyze" in full_names
    assert "synapse_trace_record" in full_names

    read = _rpc(client, token, "tools/list", None)
    assert read.status_code == 200

    read_only = client.post(
        f"/mcp/{token}?mode=read",
        json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
    ).json()["result"]["tools"]
    read_names = {tool["name"] for tool in read_only}
    assert "synapse_trace_recent" in read_names
    assert "synapse_trace_analyze" in read_names
    assert "synapse_trace_record" not in read_names


def test_mcp_tool_call_automatically_writes_safe_trace_receipt(tmp_path: Path) -> None:
    client, token, db_path = _harness(tmp_path)

    response = _rpc(
        client,
        token,
        "tools/call",
        {
            "name": "synapse_get_project_records",
            "arguments": {"project_id": "demo-project", "token": "must-not-be-stored"},
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["result"]["isError"] is False

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        """
        SELECT action, status, project_id, details_json
        FROM trace_events
        WHERE category = 'tool'
        ORDER BY occurred_at DESC
        LIMIT 1
        """
    ).fetchone()
    assert row is not None
    assert row["action"] == "synapse_get_project_records"
    assert row["status"] == "success"
    assert row["project_id"] == "demo-project"
    assert "must-not-be-stored" not in row["details_json"]
    assert "[REDACTED]" in row["details_json"]


def test_trace_record_and_analysis_tools_work(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SYNAPSE_MCP_ALLOW_WRITES", "1")
    client, token, _db_path = _harness(tmp_path)

    recorded = _tool_json(
        _rpc(
            client,
            token,
            "tools/call",
            {
                "name": "synapse_trace_record",
                "arguments": {
                    "summary": "Explicit verification receipt",
                    "project_id": "demo-project",
                    "details": {"password": "redact-me", "safe": "yes"},
                },
            },
        )
    )
    assert recorded["recorded"] is True

    recent = _tool_json(
        _rpc(
            client,
            token,
            "tools/call",
            {
                "name": "synapse_trace_recent",
                "arguments": {"limit": 20, "project_id": "demo-project"},
            },
        )
    )
    assert any(item["summary"] == "Explicit verification receipt" for item in recent["items"])

    analysis = _tool_json(
        _rpc(
            client,
            token,
            "tools/call",
            {"name": "synapse_trace_analyze", "arguments": {"window_hours": 24}},
        )
    )
    assert analysis["totals"]["events"] >= 1
