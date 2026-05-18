"""Tests for the tool plugin registry (Milestone F · v0.1.9)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from synapse_daemon.errors import SynapseError
from synapse_daemon.tools_registry import ToolRegistry
from synapse_daemon.ws import EventBus


def _write_manifest(tools_dir: Path, tool_id: str, body: dict) -> None:
    folder = tools_dir / tool_id
    folder.mkdir(parents=True)
    (folder / "manifest.json").write_text(json.dumps(body), encoding="utf-8")


def _registry(tools_dir: Path) -> ToolRegistry:
    return ToolRegistry(tools_dir, EventBus())


def test_missing_tools_dir_loads_nothing(tmp_path: Path) -> None:
    reg = _registry(tmp_path / "does-not-exist")
    assert reg.load() == []
    assert reg.list_manifests() == []


def test_loads_a_valid_manifest(tmp_path: Path) -> None:
    tools = tmp_path / "tools"
    _write_manifest(
        tools,
        "demo",
        {
            "id": "demo",
            "name": "Demo Tool",
            "description": "A demo.",
            "fields": [{"key": "x", "type": "text", "label": "X"}],
            "actions": [{"id": "go", "label": "Go"}],
        },
    )
    reg = _registry(tools)
    assert reg.load() == ["demo"]

    manifest = reg.get_manifest("demo")
    assert manifest.name == "Demo Tool"
    assert manifest.fields[0].key == "x"
    # No built-in handler for 'demo' -> listed but not runnable.
    assert manifest.runnable is False


def test_cloudtap_manifest_binds_a_handler(tmp_path: Path) -> None:
    tools = tmp_path / "tools"
    _write_manifest(
        tools,
        "cloudtap",
        {
            "id": "cloudtap",
            "name": "Cloudtap",
            "actions": [{"id": "tunnel", "label": "Open"}],
        },
    )
    reg = _registry(tools)
    reg.load()
    assert reg.get_manifest("cloudtap").runnable is True


def test_malformed_manifest_is_skipped_not_fatal(tmp_path: Path) -> None:
    tools = tmp_path / "tools"
    # One good, one broken JSON, one missing required fields.
    _write_manifest(tools, "good", {"id": "good", "name": "Good"})
    (tools / "bad-json").mkdir()
    (tools / "bad-json" / "manifest.json").write_text("{ not json", encoding="utf-8")
    _write_manifest(tools, "no-id", {"name": "Nameless"})

    reg = _registry(tools)
    loaded = reg.load()
    assert loaded == ["good"]  # the two broken ones are skipped, not fatal


def test_get_manifest_unknown_raises_not_found(tmp_path: Path) -> None:
    reg = _registry(tmp_path / "tools")
    reg.load()
    with pytest.raises(SynapseError) as exc:
        reg.get_manifest("nope")
    assert exc.value.status == 404


async def test_run_action_unknown_tool_raises_not_found(tmp_path: Path) -> None:
    reg = _registry(tmp_path / "tools")
    reg.load()
    with pytest.raises(SynapseError) as exc:
        await reg.run_action("nope", "go", {})
    assert exc.value.status == 404


async def test_run_action_unknown_action_raises_invalid(tmp_path: Path) -> None:
    tools = tmp_path / "tools"
    _write_manifest(
        tools,
        "cloudtap",
        {"id": "cloudtap", "name": "Cloudtap", "actions": [{"id": "tunnel", "label": "Open"}]},
    )
    reg = _registry(tools)
    reg.load()
    with pytest.raises(SynapseError) as exc:
        await reg.run_action("cloudtap", "nonexistent", {})
    assert exc.value.status == 422


async def test_run_action_on_handlerless_tool_raises_conflict(tmp_path: Path) -> None:
    tools = tmp_path / "tools"
    _write_manifest(
        tools,
        "demo",
        {"id": "demo", "name": "Demo", "actions": [{"id": "go", "label": "Go"}]},
    )
    reg = _registry(tools)
    reg.load()
    with pytest.raises(SynapseError) as exc:
        await reg.run_action("demo", "go", {})
    assert exc.value.status == 409


def test_duplicate_tool_id_keeps_first(tmp_path: Path) -> None:
    tools = tmp_path / "tools"
    _write_manifest(tools, "a-first", {"id": "dup", "name": "First"})
    _write_manifest(tools, "b-second", {"id": "dup", "name": "Second"})
    reg = _registry(tools)
    assert reg.load() == ["dup"]
    # sorted glob -> 'a-first' wins.
    assert reg.get_manifest("dup").name == "First"
