"""Connector-level proof for Synapse image generation tools."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient
from synapse_daemon import image_assets, image_editing, image_imports, image_uploads
from synapse_daemon.app import build_app
from synapse_daemon.projects import Project, create
from synapse_daemon.storage import Storage
from synapse_daemon.ws import EventBus


def _harness(tmp_path: Path) -> tuple[TestClient, str]:
    project_root = tmp_path / "project"
    project_root.mkdir()
    storage = Storage(tmp_path / "data")
    storage.open()
    storage.migrate()
    with storage.transaction() as conn:
        create(
            conn,
            Project(
                id="demo-project",
                name="Demo Project",
                path=str(project_root),
                launch_cmd="echo hi",
            ),
        )
    app = build_app(storage, EventBus())
    return TestClient(app), app.state.auth.local_token


def _rpc(client: TestClient, token: str, method: str, params: dict | None = None, suffix: str = ""):
    body: dict = {"jsonrpc": "2.0", "id": 1, "method": method}
    if params is not None:
        body["params"] = params
    return client.post(f"/mcp/{token}{suffix}", json=body)


def _tool_result_json(response) -> dict:
    assert response.status_code == 200, response.text
    result = response.json()["result"]
    assert result["isError"] is False, result
    return json.loads(result["content"][0]["text"])


def test_image_status_is_read_only_but_generation_is_write_only(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("SYNAPSE_MCP_ALLOW_WRITES", "1")
    client, token = _harness(tmp_path)

    full = _rpc(client, token, "tools/list").json()["result"]["tools"]
    full_names = {tool["name"] for tool in full}
    assert "synapse_image_generation_status" in full_names
    assert "synapse_generate_image" in full_names

    read = _rpc(client, token, "tools/list", suffix="?mode=read").json()["result"]["tools"]
    read_names = {tool["name"] for tool in read}
    assert "synapse_image_generation_status" in read_names
    assert "synapse_generate_image" not in read_names


def test_image_status_call_does_not_need_provider_key(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    client, token = _harness(tmp_path)

    payload = _tool_result_json(
        _rpc(
            client,
            token,
            "tools/call",
            {"name": "synapse_image_generation_status", "arguments": {}},
        )
    )

    assert payload["capability"] == "image_generation"
    assert payload["configured"] is False
    assert payload["provider"] == "openai"


def test_generate_tool_resolves_registered_project_root(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("SYNAPSE_MCP_ALLOW_WRITES", "1")
    client, token = _harness(tmp_path)
    captured: dict = {}

    def fake_generate_project_image(storage, **kwargs):
        captured["storage"] = storage
        captured.update(kwargs)
        return {
            "created": True,
            "project_relative_path": kwargs["relative_path"],
            "provider": "openai",
            "model": "gpt-image-2",
        }

    monkeypatch.setattr(image_assets, "generate_project_image", fake_generate_project_image)

    payload = _tool_result_json(
        _rpc(
            client,
            token,
            "tools/call",
            {
                "name": "synapse_generate_image",
                "arguments": {
                    "project_id": "demo-project",
                    "prompt": "A polished app hero image",
                    "relative_path": "public/images/hero.webp",
                    "size": "1536x1024",
                    "quality": "high",
                    "output_format": "webp",
                },
            },
        )
    )

    assert captured["storage"] is client.app.state.storage
    assert captured["relative_path"] == "public/images/hero.webp"
    assert captured["prompt"] == "A polished app hero image"
    assert captured["size"] == "1536x1024"
    assert captured["quality"] == "high"
    assert captured["output_format"] == "webp"
    assert payload["created"] is True
    assert payload["project_relative_path"] == "public/images/hero.webp"


def test_read_only_connector_rejects_direct_generate_call(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SYNAPSE_MCP_ALLOW_WRITES", "1")
    client, token = _harness(tmp_path)

    response = _rpc(
        client,
        token,
        "tools/call",
        {
            "name": "synapse_generate_image",
            "arguments": {
                "project_id": "demo-project",
                "prompt": "Should not run",
                "relative_path": "public/images/nope.png",
            },
        },
        suffix="?mode=read",
    )
    result = response.json()["result"]
    assert result["isError"] is True
    assert "read-only connector URL" in result["content"][0]["text"]


def test_catalog_tools_are_available_on_read_only_connector(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SYNAPSE_MCP_ALLOW_WRITES", "1")
    client, token = _harness(tmp_path)

    read = _rpc(client, token, "tools/list", suffix="?mode=read").json()["result"]["tools"]
    read_names = {tool["name"] for tool in read}
    assert {
        "synapse_image_generation_status",
        "synapse_list_project_images",
        "synapse_get_image_asset",
        "synapse_audit_image_assets",
    } <= read_names
    assert "synapse_edit_image" not in read_names


def test_catalog_tools_read_project_manifest(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SYNAPSE_MCP_ALLOW_WRITES", "1")
    client, token = _harness(tmp_path)
    project_root = tmp_path / "project"
    target = project_root / "public" / "hero.png"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b"hero")
    import hashlib
    record = {
        "kind": "generated_image",
        "path": "public/hero.png",
        "sha256": hashlib.sha256(b"hero").hexdigest(),
        "bytes": 4,
    }
    manifest = project_root / ".synapse" / "image-assets.jsonl"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(json.dumps(record) + "\n", encoding="utf-8")

    listed = _tool_result_json(
        _rpc(
            client,
            token,
            "tools/call",
            {
                "name": "synapse_list_project_images",
                "arguments": {"project_id": "demo-project", "verify_hashes": True},
            },
        )
    )
    assert listed["record_count"] == 1
    assert listed["records"][0]["path"] == "public/hero.png"
    assert listed["records"][0]["sha256_matches"] is True

    got = _tool_result_json(
        _rpc(
            client,
            token,
            "tools/call",
            {
                "name": "synapse_get_image_asset",
                "arguments": {
                    "project_id": "demo-project",
                    "relative_path": "public/hero.png",
                    "verify_hash": True,
                },
            },
        )
    )
    assert got["project_id"] == "demo-project"
    assert got["asset"]["path"] == "public/hero.png"
    assert got["asset"]["sha256_matches"] is True

    audited = _tool_result_json(
        _rpc(
            client,
            token,
            "tools/call",
            {
                "name": "synapse_audit_image_assets",
                "arguments": {"project_id": "demo-project"},
            },
        )
    )
    assert audited["project_id"] == "demo-project"
    assert audited["healthy"] is True


def test_edit_tool_resolves_registered_project_root(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SYNAPSE_MCP_ALLOW_WRITES", "1")
    client, token = _harness(tmp_path)
    captured: dict = {}

    def fake_edit_image(storage, **kwargs):
        captured["storage"] = storage
        captured.update(kwargs)
        return {
            "created": True,
            "kind": "edited_image",
            "project_relative_path": kwargs["relative_path"],
            "provider": "openai",
            "model": "gpt-image-2",
        }

    monkeypatch.setattr(image_editing, "edit_project_image", fake_edit_image)

    payload = _tool_result_json(
        _rpc(
            client,
            token,
            "tools/call",
            {
                "name": "synapse_edit_image",
                "arguments": {
                    "project_id": "demo-project",
                    "prompt": "Make the hero cleaner",
                    "input_paths": ["public/source.png"],
                    "relative_path": "public/edited.webp",
                    "size": "1536x1024",
                    "quality": "high",
                    "output_format": "webp",
                },
            },
        )
    )

    assert captured["project_id"] == "demo-project"
    assert captured["input_paths"] == ["public/source.png"]
    assert captured["relative_path"] == "public/edited.webp"
    assert captured["quality"] == "high"
    assert payload["created"] is True
    assert payload["kind"] == "edited_image"


def test_read_only_connector_rejects_direct_edit_call(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SYNAPSE_MCP_ALLOW_WRITES", "1")
    client, token = _harness(tmp_path)

    response = _rpc(
        client,
        token,
        "tools/call",
        {
            "name": "synapse_edit_image",
            "arguments": {
                "project_id": "demo-project",
                "prompt": "Should not run",
                "input_paths": ["public/source.png"],
                "relative_path": "public/nope.png",
            },
        },
        suffix="?mode=read",
    )
    result = response.json()["result"]
    assert result["isError"] is True
    assert "read-only connector URL" in result["content"][0]["text"]


def test_import_image_file_tool_uses_registered_project(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SYNAPSE_MCP_ALLOW_WRITES", "1")
    client, token = _harness(tmp_path)
    captured: dict = {}
    source = tmp_path / "native-output.png"
    source.write_bytes(b"placeholder-for-mocked-import")

    def fake_import(storage, **kwargs):
        captured["storage"] = storage
        captured.update(kwargs)
        return {
            "project_id": kwargs["project_id"],
            "created": True,
            "kind": "imported_image",
            "project_relative_path": kwargs["relative_path"],
            "source_name": source.name,
            "origin": kwargs["origin"],
            "provider": kwargs["provider"],
            "model": kwargs["model"],
            "width": 640,
            "height": 360,
            "format": "png",
            "bytes": 123,
            "sha256": "c" * 64,
        }

    monkeypatch.setattr(image_imports, "import_project_image_file", fake_import)

    payload = _tool_result_json(
        _rpc(
            client,
            token,
            "tools/call",
            {
                "name": "synapse_import_image_file",
                "arguments": {
                    "project_id": "demo-project",
                    "source_path": str(source.resolve()),
                    "relative_path": "public/images/native-output.png",
                    "origin": "chatgpt_native",
                    "provider": "openai-chatgpt",
                    "model": "native-image",
                    "prompt": "A private prompt kept project-local",
                },
            },
        )
    )

    assert captured["storage"] is client.app.state.storage
    assert captured["project_id"] == "demo-project"
    assert captured["source_path"] == str(source.resolve())
    assert captured["relative_path"] == "public/images/native-output.png"
    assert captured["origin"] == "chatgpt_native"
    assert captured["audit_source"] == "auto"
    assert payload["kind"] == "imported_image"


def test_import_tool_is_hidden_and_rejected_on_read_only_connector(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("SYNAPSE_MCP_ALLOW_WRITES", "1")
    client, token = _harness(tmp_path)

    read = _rpc(client, token, "tools/list", suffix="?mode=read").json()["result"]["tools"]
    assert "synapse_import_image_file" not in {tool["name"] for tool in read}

    source = tmp_path / "source.png"
    source.write_bytes(b"not-reached")
    response = _rpc(
        client,
        token,
        "tools/call",
        {
            "name": "synapse_import_image_file",
            "arguments": {
                "project_id": "demo-project",
                "source_path": str(source.resolve()),
                "relative_path": "public/source.png",
            },
        },
        suffix="?mode=read",
    )
    result = response.json()["result"]
    assert result["isError"] is True
    assert "read-only connector URL" in result["content"][0]["text"]


def test_chunked_upload_tools_call_shared_service(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SYNAPSE_MCP_ALLOW_WRITES", "1")
    client, token = _harness(tmp_path)
    calls: list[tuple[str, dict]] = []

    def fake_begin(storage, **kwargs):
        calls.append(("begin", kwargs))
        return {
            "upload_id": "a" * 24,
            "project_id": kwargs["project_id"],
            "relative_path": kwargs["relative_path"],
            "source_name": kwargs["source_name"] or "native.png",
            "max_chunk_bytes": 786432,
            "max_image_bytes": 50 * 1024 * 1024,
            "expires_in_seconds": 7200,
            "bytes_received": 0,
            "chunk_count": 0,
        }

    def fake_append(storage, **kwargs):
        calls.append(("append", kwargs))
        return {
            "upload_id": kwargs["upload_id"],
            "bytes_received": 3,
            "chunk_count": 1,
        }

    def fake_finish(storage, **kwargs):
        calls.append(("finish", kwargs))
        return {
            "upload_id": kwargs["upload_id"],
            "completed": True,
            "project_id": "demo-project",
            "created": True,
            "kind": "imported_image",
            "project_relative_path": "public/native.png",
            "source_name": "native.png",
            "origin": "chatgpt_native",
            "provider": "openai-chatgpt",
            "model": "native-image",
            "width": 1,
            "height": 1,
            "format": "png",
            "bytes": 3,
            "sha256": "e" * 64,
        }

    monkeypatch.setattr(image_uploads, "begin_image_upload", fake_begin)
    monkeypatch.setattr(image_uploads, "append_image_upload_chunk", fake_append)
    monkeypatch.setattr(image_uploads, "finish_image_upload", fake_finish)

    begun = _tool_result_json(
        _rpc(
            client,
            token,
            "tools/call",
            {
                "name": "synapse_begin_image_upload",
                "arguments": {
                    "project_id": "demo-project",
                    "relative_path": "public/native.png",
                    "source_name": "native.png",
                    "origin": "chatgpt_native",
                    "provider": "openai-chatgpt",
                    "model": "native-image",
                    "prompt": "private project-local prompt",
                    "expected_sha256": "f" * 64,
                },
            },
        )
    )
    assert begun["upload_id"] == "a" * 24

    appended = _tool_result_json(
        _rpc(
            client,
            token,
            "tools/call",
            {
                "name": "synapse_append_image_upload",
                "arguments": {
                    "upload_id": "a" * 24,
                    "chunk_base64": "YWJj",
                },
            },
        )
    )
    assert appended["chunk_count"] == 1

    finished = _tool_result_json(
        _rpc(
            client,
            token,
            "tools/call",
            {
                "name": "synapse_finish_image_upload",
                "arguments": {"upload_id": "a" * 24},
            },
        )
    )
    assert finished["completed"] is True
    assert finished["kind"] == "imported_image"

    assert [name for name, _ in calls] == ["begin", "append", "finish"]
    assert calls[0][1]["project_id"] == "demo-project"
    assert calls[0][1]["origin"] == "chatgpt_native"
    assert calls[2][1]["audit_source"] == "auto"


def test_chunked_upload_tools_hidden_on_read_only_connector(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("SYNAPSE_MCP_ALLOW_WRITES", "1")
    client, token = _harness(tmp_path)

    read = _rpc(client, token, "tools/list", suffix="?mode=read").json()["result"]["tools"]
    read_names = {tool["name"] for tool in read}
    assert "synapse_begin_image_upload" not in read_names
    assert "synapse_append_image_upload" not in read_names
    assert "synapse_finish_image_upload" not in read_names
