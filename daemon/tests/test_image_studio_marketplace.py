"""Marketplace lifecycle proof for Synapse Image Studio."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from synapse_daemon.app import build_app
from synapse_daemon.routes_marketplace import _cache
from synapse_daemon.storage import Storage
from synapse_daemon.tools_registry import ToolRegistry
from synapse_daemon.ws import EventBus


def _harness(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("SYNAPSE_TOOL_REGISTRY_URL", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    _cache.clear()

    storage = Storage(tmp_path / "data")
    storage.open()
    storage.migrate()
    bus = EventBus()
    tools_dir = tmp_path / "tools"
    tools_dir.mkdir()
    registry = ToolRegistry(tools_dir, bus, storage)
    registry.load()
    app = build_app(storage, bus, tool_registry=registry)
    client = TestClient(app, headers={"X-Synapse-Token": app.state.auth.local_token})
    return client, registry, tools_dir


def test_image_studio_install_uninstall_reinstall(tmp_path: Path, monkeypatch) -> None:
    client, registry, tools_dir = _harness(tmp_path, monkeypatch)

    with client as c:
        installed = c.post("/api/v1/marketplace/install/synapse-image-studio")

    assert installed.status_code == 200, installed.text
    assert installed.json()["installed"] == "synapse-image-studio"
    manifest_path = tools_dir / "synapse-image-studio" / "manifest.json"
    assert manifest_path.exists()

    manifest = registry.get_manifest("synapse-image-studio")
    assert manifest.runnable is True
    assert manifest.publisher == "The WhatIf Company"
    assert manifest.verified is True
    assert manifest.bundled is True
    assert manifest.install_default is True

    with client as c:
        tool = c.get("/api/v1/tools/synapse-image-studio")
    assert tool.status_code == 200, tool.text
    body = tool.json()
    assert body["manifest"]["publisher"] == "The WhatIf Company"
    assert body["state"]["result"]["installed"] is True
    assert body["state"]["result"]["configured"] is False

    with client as c:
        removed = c.delete("/api/v1/marketplace/install/synapse-image-studio")
    assert removed.status_code == 200, removed.text
    assert not manifest_path.exists()
    assert "synapse-image-studio" not in {m.id for m in registry.list_manifests()}

    with client as c:
        reinstalled = c.post("/api/v1/marketplace/install/synapse-image-studio")
    assert reinstalled.status_code == 200, reinstalled.text
    assert registry.get_manifest("synapse-image-studio").runnable is True
