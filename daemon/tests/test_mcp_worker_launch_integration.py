"""In-process MCP worker launch integration; never spawn a real worker."""
import json
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from synapse_daemon.app import build_app
from synapse_daemon.storage import Storage
from synapse_daemon.ws import EventBus
from synapse_daemon import boot_config


@pytest.fixture
def harness(tmp_path, monkeypatch):
    monkeypatch.delenv("SYNAPSE_MCP_ALLOW_WRITES", raising=False)
    storage = Storage(tmp_path / "data")
    storage.open()
    storage.migrate()
    cfg = boot_config.load(storage.data_dir)
    cfg.mcp_writes_enabled = True
    boot_config.save(storage.data_dir, cfg)
    app = build_app(storage, EventBus())
    app.state.bound_port = 9107
    return TestClient(app), app.state.auth.local_token


def call(client, token, suffix=""):
    return client.post(f"/mcp/{token}{suffix}", json={
        "jsonrpc": "2.0", "id": 1, "method": "tools/call",
        "params": {"name": "synapse_start_work_item",
                   "arguments": {"work_item_id": "b4df6f6b0e21"}},
    })


def test_mcp_launch_uses_actual_bound_port_without_exposing_token(harness):
    client, token = harness
    calls = []
    def fake_launch(work_item_id, *, local_token, port):
        calls.append((work_item_id, local_token, port))
        return {"work_item_id": work_item_id, "status": "running"}
    with patch("synapse_daemon.mcp_worker_launch.launch_existing_work_item",
               side_effect=fake_launch):
        response = call(client, token)
    assert response.status_code == 200
    assert response.headers["x-synapse-mcp-lane"] == "network"
    assert calls == [("b4df6f6b0e21", token, 9107)]
    assert token not in response.text
    content = json.loads(response.json()["result"]["content"][0]["text"])
    assert content["status"] == "running"


def test_readonly_mcp_cannot_spawn(harness):
    client, token = harness
    with patch("synapse_daemon.mcp_worker_launch.launch_existing_work_item") as fake:
        response = call(client, token, "?mode=read")
    assert response.json()["result"]["isError"] is True
    fake.assert_not_called()


def test_wrong_token_cannot_spawn(harness):
    client, _ = harness
    with patch("synapse_daemon.mcp_worker_launch.launch_existing_work_item") as fake:
        response = call(client, "invalid")
    assert response.status_code == 401
    fake.assert_not_called()
