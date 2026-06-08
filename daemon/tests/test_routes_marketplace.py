"""Tests for the marketplace registry route (v0.1.23 · ADR-0001 step 3)."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from synapse_daemon.app import build_app
from synapse_daemon.routes_marketplace import _cache
from synapse_daemon.storage import Storage
from synapse_daemon.tools_registry import ToolRegistry
from synapse_daemon.ws import EventBus


def _harness(tmp_path: Path, *, registry_url: str | None = None, monkeypatch=None):
    storage = Storage(tmp_path / "data")
    storage.open()
    storage.migrate()
    bus = EventBus()

    tools_dir = tmp_path / "tools"
    tools_dir.mkdir(exist_ok=True)
    registry = ToolRegistry(tools_dir, bus, storage)
    registry.load()

    app = build_app(storage, bus, tool_registry=registry)
    client = TestClient(app, headers={"X-Synapse-Token": app.state.auth.local_token})

    if monkeypatch is not None:
        if registry_url is None:
            monkeypatch.delenv("SYNAPSE_TOOL_REGISTRY_URL", raising=False)
        else:
            monkeypatch.setenv("SYNAPSE_TOOL_REGISTRY_URL", registry_url)
    _cache.clear()
    return client, registry, tools_dir


def _seed_installed(tools_dir: Path, tool_id: str) -> None:
    folder = tools_dir / tool_id
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "manifest.json").write_text(
        json.dumps({"id": tool_id, "name": tool_id.title(), "actions": []}),
        encoding="utf-8",
    )


def test_marketplace_returns_bundled_sample(tmp_path: Path, monkeypatch) -> None:
    client, _, _ = _harness(tmp_path, monkeypatch=monkeypatch)
    with client as c:
        res = c.get("/api/v1/marketplace")
        assert res.status_code == 200
        body = res.json()
        assert body["source"]["kind"] == "file"
        tools = body["registry"]["tools"]
        assert len(tools) >= 1
        # Cloudtap is in the sample registry and required.
        ids = {t["id"] for t in tools}
        assert "cloudtap" in ids


def test_marketplace_marks_installed_ids(tmp_path: Path, monkeypatch) -> None:
    client, registry, tools_dir = _harness(tmp_path, monkeypatch=monkeypatch)
    _seed_installed(tools_dir, "cloudtap")
    registry.load()
    with client as c:
        body = c.get("/api/v1/marketplace").json()
    assert "cloudtap" in body["installed_ids"]


def test_marketplace_caches_within_ttl(tmp_path: Path, monkeypatch) -> None:
    client, _, _ = _harness(tmp_path, monkeypatch=monkeypatch)
    with client as c:
        first = c.get("/api/v1/marketplace").json()
        second = c.get("/api/v1/marketplace").json()
    assert first["cached"] is False
    assert second["cached"] is True


def test_marketplace_refresh_query_busts_cache(tmp_path: Path, monkeypatch) -> None:
    client, _, _ = _harness(tmp_path, monkeypatch=monkeypatch)
    with client as c:
        c.get("/api/v1/marketplace")
        busted = c.get("/api/v1/marketplace?refresh=true").json()
    assert busted["cached"] is False


def test_marketplace_validates_malformed_entries(tmp_path: Path, monkeypatch) -> None:
    """A tool entry missing an id or name is silently dropped, not fatal."""

    from synapse_daemon.routes_marketplace import _validate_index

    out = _validate_index({
        "version": 1,
        "tools": [
            {"id": "good", "name": "Good"},
            {"id": "missing-name"},                          # dropped
            {"name": "missing-id"},                          # dropped
            "not a dict",                                    # dropped
            {"id": "second", "name": "Second", "extra": 1},  # kept, extras through
        ],
    })
    assert [t["id"] for t in out["tools"]] == ["good", "second"]


def test_marketplace_route_requires_auth(tmp_path: Path) -> None:
    storage = Storage(tmp_path / "data")
    storage.open()
    storage.migrate()
    app = build_app(storage, EventBus())
    unauthed = TestClient(app)
    assert unauthed.get("/api/v1/marketplace").status_code == 401
