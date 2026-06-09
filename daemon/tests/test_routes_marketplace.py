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


# ── install / uninstall (v0.1.24) ──────────────────────────────────────────


def test_install_writes_manifest_and_makes_it_runnable(
    tmp_path: Path, monkeypatch
) -> None:
    client, registry, tools_dir = _harness(tmp_path, monkeypatch=monkeypatch)
    with client as c:
        res = c.post("/api/v1/marketplace/install/open-synapse-docs")
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["installed"] == "open-synapse-docs"
        assert body["reload"]["added"] == ["open-synapse-docs"]

    # File landed in tools/<id>/manifest.json.
    target = tools_dir / "open-synapse-docs" / "manifest.json"
    assert target.exists()

    # Registry now has it AND marks it runnable (declarative + primitive
    # action means the daemon can execute it without a Python handler).
    assert "open-synapse-docs" in {m.id for m in registry.list_manifests()}
    assert registry.get_manifest("open-synapse-docs").runnable is True


def test_install_refuses_to_clobber_without_force(
    tmp_path: Path, monkeypatch
) -> None:
    client, _, _ = _harness(tmp_path, monkeypatch=monkeypatch)
    with client as c:
        c.post("/api/v1/marketplace/install/open-synapse-docs")
        again = c.post("/api/v1/marketplace/install/open-synapse-docs")
        assert again.status_code == 409
        forced = c.post("/api/v1/marketplace/install/open-synapse-docs?force=true")
        assert forced.status_code == 200


def test_install_rejects_unknown_tool(tmp_path: Path, monkeypatch) -> None:
    client, _, _ = _harness(tmp_path, monkeypatch=monkeypatch)
    with client as c:
        res = c.post("/api/v1/marketplace/install/never-heard-of-it")
        assert res.status_code == 404


def test_install_rejects_manifest_with_mismatched_id(
    tmp_path: Path, monkeypatch
) -> None:
    """A registry entry pointing at a manifest whose own ``id`` differs is
    refused -- the registry id is the trust anchor for "this tool is what it
    claims to be"."""

    client, registry, tools_dir = _harness(tmp_path, monkeypatch=monkeypatch)
    # Monkey-patch the cached index to inject a malicious manifest_inline.
    from synapse_daemon.routes_marketplace import _cache, _load_from_file, _resolve_source

    _cache.clear()
    _, location = _resolve_source()
    index = _load_from_file(location)
    for entry in index["tools"]:
        if entry["id"] == "git-status":
            entry["manifest_inline"] = {"id": "definitely-not-git-status", "name": "Sneaky", "actions": []}
            break
    _cache.set(location, index)

    with client as c:
        res = c.post("/api/v1/marketplace/install/git-status")
        assert res.status_code == 422
        assert "does not match" in res.json()["message"]


def test_uninstall_removes_manifest_and_folder(tmp_path: Path, monkeypatch) -> None:
    client, registry, tools_dir = _harness(tmp_path, monkeypatch=monkeypatch)
    with client as c:
        c.post("/api/v1/marketplace/install/open-synapse-docs")
        target = tools_dir / "open-synapse-docs"
        assert target.exists()

        res = c.delete("/api/v1/marketplace/install/open-synapse-docs")
        assert res.status_code == 200
        body = res.json()
        assert body["uninstalled"] == "open-synapse-docs"
        assert body["reload"]["removed"] == ["open-synapse-docs"]

    # Folder should be gone (only contained the manifest).
    assert not target.exists()
    assert "open-synapse-docs" not in {m.id for m in registry.list_manifests()}


def test_uninstall_unknown_returns_404(tmp_path: Path, monkeypatch) -> None:
    client, _, _ = _harness(tmp_path, monkeypatch=monkeypatch)
    with client as c:
        res = c.delete("/api/v1/marketplace/install/not-installed")
        assert res.status_code == 404
