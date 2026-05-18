"""Tests for the tool plugin REST endpoints (Milestone F · v0.1.9)."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient
from synapse_daemon.app import build_app
from synapse_daemon.storage import Storage
from synapse_daemon.tools_registry import ToolRegistry
from synapse_daemon.ws import EventBus

_CLOUDTAP_MANIFEST = {
    "id": "cloudtap",
    "name": "Cloudtap",
    "icon": "cloud",
    "description": "One-tap Cloudflare tunnel.",
    "version": "0.1.0",
    "fields": [{"key": "port", "type": "number", "label": "Local port", "required": True}],
    "actions": [
        {"id": "tunnel", "label": "Open tunnel", "primary": True,
         "available_in": ["idle", "stopped", "error"]},
        {"id": "stop", "label": "Close tunnel", "available_in": ["launching", "launched"]},
    ],
}


def _harness(tmp_path: Path):
    storage = Storage(tmp_path / "data")
    storage.open()
    storage.migrate()
    bus = EventBus()

    tools_dir = tmp_path / "tools"
    (tools_dir / "cloudtap").mkdir(parents=True)
    (tools_dir / "cloudtap" / "manifest.json").write_text(
        json.dumps(_CLOUDTAP_MANIFEST), encoding="utf-8"
    )

    registry = ToolRegistry(tools_dir, bus)
    registry.load()
    app = build_app(storage, bus, tool_registry=registry)
    return TestClient(app), storage


def test_list_tools_returns_cloudtap(tmp_path: Path) -> None:
    client, _ = _harness(tmp_path)
    with client as c:
        res = c.get("/api/v1/tools")
        assert res.status_code == 200
        tools = res.json()["tools"]
        assert len(tools) == 1
        entry = tools[0]
        assert entry["manifest"]["id"] == "cloudtap"
        assert entry["manifest"]["runnable"] is True
        assert entry["state"]["status"] == "idle"
        # available_in round-trips so the UI can disable buttons by state.
        actions = {a["id"]: a for a in entry["manifest"]["actions"]}
        assert actions["tunnel"]["available_in"] == ["idle", "stopped", "error"]


def test_get_one_tool(tmp_path: Path) -> None:
    client, _ = _harness(tmp_path)
    with client as c:
        res = c.get("/api/v1/tools/cloudtap")
        assert res.status_code == 200
        assert res.json()["manifest"]["name"] == "Cloudtap"


def test_get_unknown_tool_is_404(tmp_path: Path) -> None:
    client, _ = _harness(tmp_path)
    with client as c:
        res = c.get("/api/v1/tools/ghost")
        assert res.status_code == 404
        assert res.json()["code"] == "tool.not_found"


def test_unknown_action_is_422(tmp_path: Path) -> None:
    client, _ = _harness(tmp_path)
    with client as c:
        res = c.post("/api/v1/tools/cloudtap/actions/teleport")
        assert res.status_code == 422
        assert res.json()["code"] == "tool.invalid"


def test_bad_port_returns_error_state_not_500(tmp_path: Path) -> None:
    """A handler-level failure is a 200 with an error state, not an HTTP 500."""

    client, storage = _harness(tmp_path)
    with client as c:
        res = c.post(
            "/api/v1/tools/cloudtap/actions/tunnel",
            json={"fields": {"port": "abc"}},
        )
        assert res.status_code == 200
        state = res.json()["state"]
        assert state["status"] == "error"
        assert state["last_error"]["code"] == "cloudtap.bad_port"

    # The action was audited (Contract #11).
    row = storage.conn.execute(
        "SELECT result, action FROM audit_log WHERE entity_type = 'tool'"
    ).fetchone()
    assert row is not None
    assert row["action"] == "action.tunnel"
    assert row["result"] == "error"
