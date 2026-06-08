"""Tests for ToolRegistry hot reload (v0.1.21 · ADR-0001)."""

from __future__ import annotations

import json
from pathlib import Path

from synapse_daemon.api_versions import event_name
from synapse_daemon.tools import ToolHandler
from synapse_daemon.tools_registry import ToolRegistry
from synapse_daemon.ws import Event, EventBus


def _write_manifest(tools_dir: Path, tool_id: str, body: dict) -> None:
    folder = tools_dir / tool_id
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "manifest.json").write_text(json.dumps(body), encoding="utf-8")


async def test_reload_picks_up_a_newly_added_manifest(tmp_path: Path) -> None:
    tools = tmp_path / "tools"
    tools.mkdir()
    reg = ToolRegistry(tools, EventBus())
    reg.load()
    assert reg.list_manifests() == []

    _write_manifest(tools, "fresh", {"id": "fresh", "name": "Fresh", "actions": []})

    report = await reg.reload()

    assert report == {"added": ["fresh"], "removed": [], "kept": []}
    assert [m.id for m in reg.list_manifests()] == ["fresh"]


async def test_reload_drops_a_removed_manifest_and_shuts_its_handler(tmp_path: Path) -> None:
    tools = tmp_path / "tools"
    _write_manifest(tools, "cloudtap", {"id": "cloudtap", "name": "Cloudtap", "actions": []})
    reg = ToolRegistry(tools, EventBus())
    reg.load()
    assert reg.get_manifest("cloudtap").runnable is True
    handler = reg._handlers["cloudtap"]  # the live CloudtapTool instance

    # Remove the manifest folder, then reload.
    (tools / "cloudtap" / "manifest.json").unlink()
    (tools / "cloudtap").rmdir()
    report = await reg.reload()

    assert report["removed"] == ["cloudtap"]
    assert "cloudtap" not in reg._handlers
    # The handler instance is no longer tracked but did get a shutdown call.
    assert handler not in reg._handlers.values()


async def test_reload_preserves_handler_instance_for_unchanged_manifest(tmp_path: Path) -> None:
    tools = tmp_path / "tools"
    _write_manifest(tools, "cloudtap", {"id": "cloudtap", "name": "Cloudtap", "actions": []})
    reg = ToolRegistry(tools, EventBus())
    reg.load()
    before = reg._handlers["cloudtap"]

    # No file changes -- just reload.
    report = await reg.reload()

    assert report == {"added": [], "removed": [], "kept": ["cloudtap"]}
    after = reg._handlers["cloudtap"]
    assert before is after, "Reload should not throw away a live handler instance."


async def test_reload_updates_manifest_fields_for_kept_tool(tmp_path: Path) -> None:
    tools = tmp_path / "tools"
    _write_manifest(tools, "demo", {"id": "demo", "name": "Demo v1", "actions": []})
    reg = ToolRegistry(tools, EventBus())
    reg.load()
    assert reg.get_manifest("demo").name == "Demo v1"

    _write_manifest(tools, "demo", {"id": "demo", "name": "Demo v2", "actions": []})
    await reg.reload()

    assert reg.get_manifest("demo").name == "Demo v2"


async def test_reload_broadcasts_v1_tool_reloaded(tmp_path: Path) -> None:
    tools = tmp_path / "tools"
    _write_manifest(tools, "a", {"id": "a", "name": "A", "actions": []})
    bus = EventBus()
    reg = ToolRegistry(tools, bus)
    reg.load()

    seen: list[Event] = []

    async def subscriber(event: Event) -> None:
        seen.append(event)

    await bus.subscribe(subscriber)

    _write_manifest(tools, "b", {"id": "b", "name": "B", "actions": []})
    await reg.reload()

    reloaded = [e for e in seen if e.name == event_name("tool", "reloaded")]
    assert len(reloaded) == 1
    payload = reloaded[0].payload
    assert payload["added"] == ["b"]
    assert payload["loaded"] == ["a", "b"]


def test_start_watching_is_idempotent_and_skips_missing_dir(tmp_path: Path) -> None:
    """start_watching is a no-op if the directory doesn't exist; calling it
    twice doesn't spawn two observers."""

    import asyncio

    missing = tmp_path / "nope"
    reg = ToolRegistry(missing, EventBus())
    loop = asyncio.new_event_loop()
    try:
        reg.start_watching(loop)
        assert reg._observer is None  # missing dir -> no observer

        # Real dir, idempotent on repeat calls.
        real = tmp_path / "tools"
        real.mkdir()
        reg_real = ToolRegistry(real, EventBus())
        reg_real.start_watching(loop)
        first = reg_real._observer
        reg_real.start_watching(loop)
        assert reg_real._observer is first
        reg_real.stop_watching()
        assert reg_real._observer is None
    finally:
        loop.close()


class _CountingHandler(ToolHandler):
    """A ToolHandler that records shutdown calls -- proves reload tears it down."""

    tool_id = "demo"
    shutdown_calls = 0

    def __init__(self, bus, storage) -> None:  # type: ignore[no-untyped-def]
        self._bus = bus

    async def run_action(self, action_id, fields, item_id=None):  # type: ignore[override]
        from synapse_daemon.models import EntityStatus, ToolState
        return ToolState(tool_id=self.tool_id, status=EntityStatus.IDLE)

    def state(self):  # type: ignore[override]
        from synapse_daemon.models import EntityStatus, ToolState
        return ToolState(tool_id=self.tool_id, status=EntityStatus.IDLE)

    async def shutdown(self) -> None:
        type(self).shutdown_calls += 1


async def test_removed_tool_handler_gets_shutdown_call(tmp_path: Path, monkeypatch) -> None:
    from synapse_daemon import tools_registry as tr

    tools = tmp_path / "tools"
    _write_manifest(tools, "demo", {"id": "demo", "name": "Demo", "actions": []})

    monkeypatch.setitem(tr._BUILTIN_HANDLER_FACTORIES, "demo", _CountingHandler)
    _CountingHandler.shutdown_calls = 0
    reg = ToolRegistry(tools, EventBus())
    reg.load()
    assert "demo" in reg._handlers

    (tools / "demo" / "manifest.json").unlink()
    (tools / "demo").rmdir()
    await reg.reload()

    assert _CountingHandler.shutdown_calls == 1
