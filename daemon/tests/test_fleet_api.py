"""Fleet API/MCP discovery contract with isolated scratch storage."""
from pathlib import Path

from fastapi.testclient import TestClient

from synapse_daemon.app import build_app
from synapse_daemon.mcp_connector import _tool_specs
from synapse_daemon.storage import Storage
from synapse_daemon.ws import EventBus


def test_fleet_mcp_tools_have_correct_capabilities():
    reads = {s["name"]: s for s in _tool_specs(False)}
    writes = {s["name"]: s for s in _tool_specs(True)}
    assert "synapse_fleet_status" in reads
    assert "synapse_fleet_start" not in reads
    for name in ("synapse_fleet_start", "synapse_fleet_status",
                 "synapse_fleet_nudge", "synapse_fleet_stop"):
        assert name in writes
        assert writes[name]["annotations"]["readOnlyHint"] == (name == "synapse_fleet_status")


def test_fleet_rest_openapi_and_ai_discovery(tmp_path: Path):
    storage = Storage(tmp_path / "data")
    storage.open()
    storage.migrate()
    app = build_app(storage, EventBus())
    with TestClient(app, headers={"X-Synapse-Token": app.state.auth.local_token}) as client:
        schema = client.get("/api/v1/openapi.json").json()
        paths = schema["paths"]
        expected = {
            "/api/v1/fleet/start": "post",
            "/api/v1/fleet/status": "get",
            "/api/v1/fleet/nudge": "post",
            "/api/v1/fleet/stop": "post",
        }
        for path, method in expected.items():
            assert method in paths[path]
        context = client.get("/api/v1/ai/context")
        assert context.status_code == 200, context.text[:500]
        advertised = {e["path"] for e in context.json()["endpoints_for_ai"]}
        assert set(expected).issubset(advertised)
        assert client.get("/api/v1/fleet/status").json() == []
