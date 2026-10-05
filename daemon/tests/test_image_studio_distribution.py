"""Distribution/product tests for first-party Synapse Image Studio."""

from __future__ import annotations

import json
from pathlib import Path

from synapse_daemon.storage import Storage
from synapse_daemon.tools.image_studio import ImageStudioTool
from synapse_daemon.ws import EventBus

REPO = Path(__file__).resolve().parents[2]


def _storage(tmp_path: Path) -> Storage:
    storage = Storage(tmp_path / "data")
    storage.open()
    storage.migrate()
    return storage


def test_image_studio_handler_reports_live_readiness(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    storage = _storage(tmp_path)
    tool = ImageStudioTool(EventBus(), storage)

    state = tool.state()

    assert state.tool_id == "synapse-image-studio"
    assert state.status.value == "idle"
    assert state.result["installed"] is True
    assert state.result["configured"] is False
    assert state.result["generation"] is True
    assert state.result["editing"] is True
    assert state.result["importing"] is True
    assert state.result["chunked_upload"] is True
    assert state.result["native_bridge_ready"] is True
    assert "Native image import/chunked transfer are ready now" in (state.message or "")
    assert "Add an OpenAI image credential" in (state.message or "")


async def test_image_studio_check_action_uses_nonsecret_status(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "do-not-leak-this")
    storage = _storage(tmp_path)
    tool = ImageStudioTool(EventBus(), storage)

    state = await tool.run_action("check", {})

    dumped = json.dumps(state.model_dump(mode="json"))
    assert state.status.value == "launched"
    assert state.result["configured"] is True
    assert state.result["credential_source"] == "environment"
    assert "do-not-leak-this" not in dumped


def test_bundled_marketplace_marks_image_studio_first_party_default() -> None:
    payload = json.loads((REPO / "docs" / "marketplace-sample.json").read_text(encoding="utf-8"))
    entry = next(item for item in payload["tools"] if item["id"] == "synapse-image-studio")

    assert entry["publisher"] == "The WhatIf Company"
    assert entry["verified"] is True
    assert entry["bundled"] is True
    assert entry["install_default"] is True
    assert entry["tier"] == "handler"
    assert {"import", "upload", "provenance"} <= set(entry["tags"])
    assert "chunked AI transfer" in entry["description"]
    manifest = entry["manifest_inline"]
    assert manifest["publisher"] == "The WhatIf Company"
    assert manifest["verified"] is True
    assert manifest["install_default"] is True


def test_windows_installer_prompts_default_on_and_bootstraps_choice() -> None:
    installer = (REPO / "installer" / "installer.nsh").read_text(encoding="utf-8")

    assert "Synapse Image Studio" in installer
    assert "The WhatIf Company" in installer
    assert "StrCpy $BundleImageStudioState 1" in installer
    assert "bootstrap-optional-tools.json" in installer
    assert "install_tool_ids" in installer
    assert "uninstall_tool_ids" in installer
    assert installer.count("synapse-image-studio") >= 2


def test_packaged_tools_defer_image_studio_to_installer_bootstrap() -> None:
    package = json.loads((REPO / "package.json").read_text(encoding="utf-8"))
    tools_resource = next(
        item for item in package["build"]["extraResources"] if item.get("from") == "tools"
    )
    assert "!synapse-image-studio/**" in tools_resource["filter"]

    main = (REPO / "electron" / "main.ts").read_text(encoding="utf-8")
    assert "applyBootstrapOptionalTools" in main
    assert "/marketplace/install/" in main
    assert "await applyBootstrapOptionalTools();" in main


def test_image_api_docs_cover_native_bridge() -> None:
    docs = (REPO / "docs" / "api-finds.md").read_text(encoding="utf-8")
    assert "/image-generation/import-file" in docs
    assert "/image-generation/uploads/begin" in docs
    assert "/image-generation/uploads/{upload_id}/append" in docs
    assert "/image-generation/uploads/{upload_id}/finish" in docs
    assert "synapse_begin_image_upload" in docs
    assert "synapse_append_image_upload" in docs
    assert "synapse_finish_image_upload" in docs
    assert "Upload prompts are encrypted while staged" in docs
