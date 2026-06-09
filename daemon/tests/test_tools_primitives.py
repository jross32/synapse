"""Tests for declarative tool primitives (v0.1.22 · ADR-0001 step 2)."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from synapse_daemon.errors import SynapseError
from synapse_daemon.models import EntityStatus
from synapse_daemon.tools_primitives import (
    PRIMITIVES,
    is_known_primitive,
    run_primitive,
    substitute,
)
from synapse_daemon.tools_registry import ToolRegistry
from synapse_daemon.ws import EventBus


# ── helpers ────────────────────────────────────────────────────────────────


def _write_manifest(tools_dir: Path, tool_id: str, body: dict) -> None:
    folder = tools_dir / tool_id
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "manifest.json").write_text(json.dumps(body), encoding="utf-8")


# ── catalogue ──────────────────────────────────────────────────────────────


def test_known_primitives_are_published() -> None:
    # pty.spawn added in v0.1.25 (ADR-0002 Phase A).
    assert PRIMITIVES == frozenset({"url.open", "process.spawn", "pty.spawn"})
    assert is_known_primitive("url.open")
    assert is_known_primitive("pty.spawn")
    assert not is_known_primitive("filesystem.delete")


# ── field substitution ────────────────────────────────────────────────────


def test_substitute_replaces_placeholders() -> None:
    assert substitute("hello {name}", {"name": "world"}) == "hello world"
    assert (
        substitute("/api/{kind}/{id}", {"kind": "tools", "id": "x"})
        == "/api/tools/x"
    )


def test_substitute_treats_missing_fields_as_empty() -> None:
    assert substitute("port-{port}", {}) == "port-"


def test_substitute_stringifies_non_strings() -> None:
    assert substitute("port={port}", {"port": 12345}) == "port=12345"


def test_substitute_leaves_non_placeholders_alone() -> None:
    # JSON-ish payload should not be touched.
    assert substitute("{not a field}", {}) == "{not a field}"


# ── url.open ──────────────────────────────────────────────────────────────


async def test_url_open_opens_browser_and_returns_launched() -> None:
    with patch("webbrowser.open", return_value=True) as opener:
        state = await run_primitive(
            "url.open",
            {"url": "https://localhost:{port}/dash"},
            {"port": 7878},
            EventBus(),
            "demo",
        )

    opener.assert_called_once_with("https://localhost:7878/dash")
    assert state.status == EntityStatus.LAUNCHED
    assert state.result["url"] == "https://localhost:7878/dash"
    assert state.last_error is None


async def test_url_open_rejects_non_http_schemes() -> None:
    state = await run_primitive(
        "url.open",
        {"url": "file:///etc/passwd"},
        {},
        EventBus(),
        "demo",
    )
    assert state.status == EntityStatus.ERROR
    assert state.last_error.code == "primitive.bad_url"


async def test_url_open_requires_url_param() -> None:
    state = await run_primitive("url.open", {}, {}, EventBus(), "demo")
    assert state.last_error.code == "primitive.bad_params"


async def test_url_open_surfaces_browser_open_failure() -> None:
    with patch("webbrowser.open", return_value=False):
        state = await run_primitive(
            "url.open",
            {"url": "https://example.com"},
            {},
            EventBus(),
            "demo",
        )
    assert state.last_error.code == "primitive.open_failed"


# ── process.spawn ─────────────────────────────────────────────────────────


async def test_process_spawn_runs_subprocess_and_captures_output() -> None:
    state = await run_primitive(
        "process.spawn",
        {"argv": [sys.executable, "-c", "print('hello {name}')"]},
        {"name": "synapse"},
        EventBus(),
        "demo",
    )
    assert state.status == EntityStatus.LAUNCHED, state.last_error
    assert state.result["exit_code"] == 0
    assert "hello synapse" in state.result["output"]


async def test_process_spawn_returns_error_on_nonzero_exit() -> None:
    state = await run_primitive(
        "process.spawn",
        {"argv": [sys.executable, "-c", "import sys; sys.exit(3)"]},
        {},
        EventBus(),
        "demo",
    )
    assert state.status == EntityStatus.ERROR
    assert state.last_error.code == "primitive.exit_nonzero"
    assert state.result["exit_code"] == 3


async def test_process_spawn_requires_argv_list() -> None:
    state = await run_primitive("process.spawn", {}, {}, EventBus(), "demo")
    assert state.last_error.code == "primitive.bad_params"


async def test_process_spawn_handles_missing_binary() -> None:
    state = await run_primitive(
        "process.spawn",
        {"argv": ["this-binary-definitely-does-not-exist-1234"]},
        {},
        EventBus(),
        "demo",
    )
    assert state.last_error.code == "primitive.spawn_failed"


async def test_process_spawn_enforces_timeout() -> None:
    state = await run_primitive(
        "process.spawn",
        {
            "argv": [sys.executable, "-c", "import time; time.sleep(5)"],
            "timeout": 0.3,
        },
        {},
        EventBus(),
        "demo",
    )
    assert state.last_error.code == "primitive.timeout"


async def test_unknown_primitive_errors() -> None:
    state = await run_primitive("filesystem.delete", {}, {}, EventBus(), "demo")
    assert state.last_error.code == "primitive.unknown"


# ── integration with ToolRegistry ─────────────────────────────────────────


def test_manifest_with_primitive_action_is_runnable_without_handler(tmp_path: Path) -> None:
    """A declarative manifest -- no handler in _BUILTIN_HANDLER_FACTORIES --
    is still marked runnable so its action buttons stay live in the UI."""

    tools = tmp_path / "tools"
    _write_manifest(
        tools,
        "open-docs",
        {
            "id": "open-docs",
            "name": "Open docs",
            "actions": [
                {
                    "id": "go",
                    "label": "Open",
                    "primitive": "url.open",
                    "params": {"url": "https://example.com"},
                }
            ],
        },
    )
    reg = ToolRegistry(tools, EventBus())
    reg.load()
    assert reg.get_manifest("open-docs").runnable is True


async def test_registry_dispatches_to_primitive(tmp_path: Path) -> None:
    tools = tmp_path / "tools"
    _write_manifest(
        tools,
        "open-docs",
        {
            "id": "open-docs",
            "name": "Open docs",
            "actions": [
                {
                    "id": "go",
                    "label": "Open",
                    "primitive": "url.open",
                    "params": {"url": "https://example.com/{slug}"},
                }
            ],
        },
    )
    reg = ToolRegistry(tools, EventBus())
    reg.load()

    with patch("webbrowser.open", return_value=True) as opener:
        state = await reg.run_action("open-docs", "go", {"slug": "docs"})

    opener.assert_called_once_with("https://example.com/docs")
    assert state.status == EntityStatus.LAUNCHED


async def test_registry_rejects_action_with_unknown_primitive(tmp_path: Path) -> None:
    tools = tmp_path / "tools"
    _write_manifest(
        tools,
        "bad",
        {
            "id": "bad",
            "name": "Bad",
            "actions": [{"id": "go", "label": "Go", "primitive": "filesystem.delete"}],
        },
    )
    reg = ToolRegistry(tools, EventBus())
    reg.load()
    with pytest.raises(SynapseError) as exc:
        await reg.run_action("bad", "go", {})
    assert exc.value.status == 422
