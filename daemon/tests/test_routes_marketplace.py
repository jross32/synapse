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

_DISCOVER_CATEGORIES = {
    "ai-assistants",
    "workflows",
    "editors",
    "remote",
    "dev-tools",
    "system",
    "data",
}


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


def test_marketplace_bundled_handlers_load_with_valid_shape(
    tmp_path: Path, monkeypatch
) -> None:
    """Every tool in the bundled sample must round-trip through the
    registry's manifest validator. Catches a malformed JSON edit before
    it reaches Tools -> Browse in the UI."""

    client, _, _ = _harness(tmp_path, monkeypatch=monkeypatch)
    with client as c:
        body = c.get("/api/v1/marketplace").json()
    tools = body["registry"]["tools"]
    # The 5 declarative tools shipped 2026-06-16 must remain present
    # until they're explicitly removed in a separate commit. Add to
    # this set when you bundle a new tool.
    must_include = {
        "cloudtap",
        "claude",
        "codex",
        "copilot",
        "fast-money",
        "open-folder",
        "open-vscode-insiders",
        "open-cursor",
        "open-zed",
        "tail-log",
        "npm-install",
        "pip-install-dev",
        "docker-compose-up",
        "git-log-recent",
    }
    seen = {t["id"] for t in tools}
    missing = must_include - seen
    assert not missing, f"bundled tools missing from registry: {missing}"
    for t in tools:
        category = t.get("category")
        assert category in _DISCOVER_CATEGORIES, (
            f"{t['id']}: invalid category {category!r}"
        )
        tags = t.get("tags")
        assert isinstance(tags, list) and tags, f"{t['id']}: missing tags"
        assert isinstance(t.get("featured"), bool), f"{t['id']}: featured must be bool"
        assert isinstance(t.get("sort_rank"), int), f"{t['id']}: sort_rank must be int"
        # Every declarative entry needs a `manifest_inline` or `manifest_url`
        # the install route can use.
        if t.get("tier") != "declarative":
            continue
        has_inline = isinstance(t.get("manifest_inline"), dict)
        has_url = isinstance(t.get("manifest_url"), str) and t["manifest_url"]
        assert has_inline or has_url, (
            f"declarative tool {t['id']} has neither manifest_inline nor manifest_url"
        )
        if has_inline:
            inline = t["manifest_inline"]
            assert inline.get("id") == t["id"], (
                f"{t['id']}: inline manifest id mismatch"
            )
            assert inline.get("actions"), f"{t['id']}: no actions"
            for action in inline["actions"]:
                assert action.get("primitive") in {
                    "url.open",
                    "process.spawn",
                    "pty.spawn",
                }, f"{t['id']}: unknown primitive {action.get('primitive')!r}"


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
