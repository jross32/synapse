"""REST + AI-discovery tests for Synapse image generation."""

from __future__ import annotations

import threading
from pathlib import Path

from fastapi.testclient import TestClient
from synapse_daemon import image_assets, image_editing, image_imports, image_uploads
from synapse_daemon.app import build_app
from synapse_daemon.projects import Project, create
from synapse_daemon.storage import Storage
from synapse_daemon.ws import EventBus


def _harness(tmp_path: Path) -> TestClient:
    project_root = tmp_path / "demo-project"
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
    app.state.bound_host = "127.0.0.1"
    app.state.bound_port = 7878
    return TestClient(app, headers={"X-Synapse-Token": app.state.auth.local_token})


def test_status_route_is_authenticated_and_reports_configuration(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    client = _harness(tmp_path)

    with client as c:
        response = c.get("/api/v1/image-generation/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["capability"] == "image_generation"
    assert payload["configured"] is False
    assert payload["provider"] == "openai"
    assert "OPENAI_API_KEY" in payload["reason"]

    response = TestClient(client.app).get("/api/v1/image-generation/status")
    assert response.status_code == 401


def test_generate_route_runs_shared_service_off_event_loop(
    tmp_path: Path, monkeypatch
) -> None:
    client = _harness(tmp_path)
    caller_thread = threading.get_ident()
    captured: dict = {}

    def fake_generate_project_image(storage, **kwargs):
        captured["thread_id"] = threading.get_ident()
        captured["storage"] = storage
        captured.update(kwargs)
        return {
            "project_id": kwargs["project_id"],
            "created": True,
            "project_relative_path": kwargs["relative_path"],
            "absolute_path": str(tmp_path / "demo-project" / kwargs["relative_path"]),
            "manifest_path": str(tmp_path / "demo-project" / ".synapse" / "image-assets.jsonl"),
            "provider": "openai",
            "model": "gpt-image-2",
            "size": kwargs["size"],
            "quality": kwargs["quality"],
            "format": kwargs["output_format"],
            "background": kwargs["background"],
            "bytes": 1234,
            "sha256": "a" * 64,
            "request_id": "req_route_test",
        }

    monkeypatch.setattr(image_assets, "generate_project_image", fake_generate_project_image)

    with client as c:
        response = c.post(
            "/api/v1/image-generation/generate",
            json={
                "project_id": "demo-project",
                "prompt": "A cinematic hero image for a polished application",
                "relative_path": "public/images/hero.webp",
                "size": "1536x1024",
                "quality": "high",
                "output_format": "webp",
            },
        )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["project_id"] == "demo-project"
    assert payload["project_relative_path"] == "public/images/hero.webp"
    assert payload["provider"] == "openai"
    assert captured["thread_id"] != caller_thread
    assert captured["storage"] is client.app.state.storage
    assert captured["audit_source"] == "auto"


def test_generate_route_returns_synapse_error_when_provider_not_configured(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    client = _harness(tmp_path)

    with client as c:
        response = c.post(
            "/api/v1/image-generation/generate",
            json={
                "project_id": "demo-project",
                "prompt": "A hero image",
                "relative_path": "public/images/hero.png",
            },
        )

    assert response.status_code == 503
    payload = response.json()
    assert payload["code"] == "image_generation.not_configured"
    assert payload["retryable"] is False
    assert "OPENAI_API_KEY" in payload["message"]


def test_image_generation_is_live_in_openapi_and_ai_context(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    client = _harness(tmp_path)

    openapi = TestClient(client.app).get("/api/v1/openapi.json")
    assert openapi.status_code == 200
    paths = openapi.json()["paths"]
    assert "/api/v1/image-generation/status" in paths
    assert "/api/v1/image-generation/generate" in paths

    with client as c:
        response = c.get("/api/v1/ai/context")
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["image_generation"]["configured"] is False
    assert payload["image_generation"]["provider"] == "openai"
    assert any(
        "/api/v1/image-generation/generate" in item["path"]
        and "generate/edit/import project-scoped images" in item["purpose"]
        for item in payload["endpoints_for_ai"]
    )

    unauthorized = TestClient(client.app).post(
        "/api/v1/image-generation/generate",
        json={
            "project_id": "demo-project",
            "prompt": "No auth",
            "relative_path": "public/images/nope.png",
        },
    )
    assert unauthorized.status_code == 401


def test_edit_and_catalog_routes_are_live(tmp_path: Path, monkeypatch) -> None:
    client = _harness(tmp_path)
    captured: dict = {}

    def fake_edit_project_image(storage, **kwargs):
        captured["storage"] = storage
        captured.update(kwargs)
        return {
            "project_id": kwargs["project_id"],
            "created": True,
            "kind": "edited_image",
            "project_relative_path": kwargs["relative_path"],
            "source_paths": list(kwargs["input_paths"]),
            "mask_path": kwargs["mask_path"],
            "manifest_path": str(tmp_path / "demo-project" / ".synapse" / "image-assets.jsonl"),
            "provider": "openai",
            "model": "gpt-image-2",
            "size": kwargs["size"],
            "quality": kwargs["quality"],
            "format": kwargs["output_format"],
            "background": kwargs["background"],
            "bytes": 4321,
            "sha256": "b" * 64,
            "request_id": "req_edit_route",
        }

    monkeypatch.setattr(image_editing, "edit_project_image", fake_edit_project_image)

    with client as c:
        response = c.post(
            "/api/v1/image-generation/edit",
            json={
                "project_id": "demo-project",
                "prompt": "Make this cleaner",
                "input_paths": ["public/source.png"],
                "relative_path": "public/edited.webp",
                "size": "1536x1024",
                "quality": "high",
                "output_format": "webp",
            },
        )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["project_id"] == "demo-project"
    assert payload["kind"] == "edited_image"
    assert captured["storage"] is client.app.state.storage
    assert captured["audit_source"] == "auto"

    project_root = tmp_path / "demo-project"
    target = project_root / "public" / "hero.png"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b"hero")
    import hashlib, json
    record = {
        "kind": "generated_image",
        "path": "public/hero.png",
        "sha256": hashlib.sha256(b"hero").hexdigest(),
        "bytes": 4,
    }
    manifest = project_root / ".synapse" / "image-assets.jsonl"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(json.dumps(record) + "\n", encoding="utf-8")

    with client as c:
        listed = c.get("/api/v1/image-generation/assets/demo-project?verify_hashes=true")
        got = c.get(
            "/api/v1/image-generation/asset/demo-project",
            params={"relative_path": "public/hero.png", "verify_hash": "true"},
        )
        audited = c.get("/api/v1/image-generation/assets/demo-project/audit")

    assert listed.status_code == 200, listed.text
    assert listed.json()["record_count"] == 1
    assert listed.json()["records"][0]["sha256_matches"] is True
    assert got.status_code == 200, got.text
    assert got.json()["asset"]["path"] == "public/hero.png"
    assert audited.status_code == 200, audited.text
    assert audited.json()["healthy"] is True


def test_openapi_and_ai_context_advertise_full_image_surface(tmp_path: Path) -> None:
    client = _harness(tmp_path)
    openapi = TestClient(client.app).get("/api/v1/openapi.json")
    assert openapi.status_code == 200
    paths = openapi.json()["paths"]
    assert "/api/v1/image-generation/edit" in paths
    assert "/api/v1/image-generation/assets/{project_id}" in paths
    assert "/api/v1/image-generation/asset/{project_id}" in paths
    assert "/api/v1/image-generation/assets/{project_id}/audit" in paths

    with client as c:
        response = c.get("/api/v1/ai/context")
    assert response.status_code == 200
    image_endpoint = next(
        item for item in response.json()["endpoints_for_ai"]
        if "image readiness" in item["purpose"]
    )
    assert "/api/v1/image-generation/edit" in image_endpoint["path"]
    assert "/api/v1/image-generation/import-file" in image_endpoint["path"]
    assert "/api/v1/image-generation/uploads/begin" in image_endpoint["path"]
    assert "/api/v1/image-generation/assets/{project_id}" in image_endpoint["path"]


def test_openai_credential_routes_store_encrypted_secret(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    client = _harness(tmp_path)
    plaintext = "sk-test-route-secret"

    with client as c:
        saved = c.put(
            "/api/v1/image-generation/credentials/openai",
            json={"api_key": plaintext},
        )
        status = c.get("/api/v1/image-generation/status")

    assert saved.status_code == 200, saved.text
    assert saved.json()["configured"] is True
    assert saved.json()["source"] == "synapse_secret"
    assert plaintext not in saved.text
    assert status.status_code == 200
    assert status.json()["configured"] is True
    assert status.json()["credential_source"] == "synapse_secret"
    assert plaintext not in status.text

    row = client.app.state.storage.conn.execute(
        "SELECT value_json FROM settings WHERE key = ?",
        ("image.openai_api_key",),
    ).fetchone()
    assert row is not None
    assert plaintext not in row["value_json"]

    with client as c:
        cleared = c.delete("/api/v1/image-generation/credentials/openai")
        after = c.get("/api/v1/image-generation/status")

    assert cleared.status_code == 200
    assert cleared.json()["stored_secret"] is False
    assert after.status_code == 200
    assert after.json()["configured"] is False


def test_import_file_route_is_live(tmp_path: Path, monkeypatch) -> None:
    client = _harness(tmp_path)
    source = tmp_path / "native-output.png"
    source.write_bytes(b"mocked-route-source")
    captured: dict = {}

    def fake_import(storage, **kwargs):
        captured["storage"] = storage
        captured.update(kwargs)
        return {
            "project_id": kwargs["project_id"],
            "created": True,
            "kind": "imported_image",
            "project_relative_path": kwargs["relative_path"],
            "absolute_path": str(tmp_path / "demo-project" / kwargs["relative_path"]),
            "manifest_path": str(tmp_path / "demo-project" / ".synapse" / "image-assets.jsonl"),
            "source_name": source.name,
            "origin": kwargs["origin"],
            "provider": kwargs["provider"],
            "model": kwargs["model"],
            "width": 1280,
            "height": 720,
            "has_alpha": True,
            "format": "png",
            "bytes": 456,
            "sha256": "d" * 64,
        }

    monkeypatch.setattr(image_imports, "import_project_image_file", fake_import)

    with client as c:
        response = c.post(
            "/api/v1/image-generation/import-file",
            json={
                "project_id": "demo-project",
                "source_path": str(source.resolve()),
                "relative_path": "public/images/native-output.png",
                "origin": "chatgpt_native",
                "provider": "openai-chatgpt",
                "model": "native-image",
                "prompt": "Kept in project provenance only",
            },
        )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["kind"] == "imported_image"
    assert payload["width"] == 1280
    assert payload["height"] == 720
    assert captured["storage"] is client.app.state.storage
    assert captured["audit_source"] == "auto"

    openapi = TestClient(client.app).get("/api/v1/openapi.json").json()["paths"]
    assert "/api/v1/image-generation/import-file" in openapi


def test_chunked_upload_routes_are_live(tmp_path: Path, monkeypatch) -> None:
    client = _harness(tmp_path)
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
            "absolute_path": str(tmp_path / "demo-project" / "public" / "native.png"),
            "manifest_path": str(tmp_path / "demo-project" / ".synapse" / "image-assets.jsonl"),
            "source_name": "native.png",
            "origin": "chatgpt_native",
            "provider": "openai-chatgpt",
            "model": "native-image",
            "width": 1,
            "height": 1,
            "has_alpha": True,
            "format": "png",
            "bytes": 3,
            "sha256": "e" * 64,
        }

    monkeypatch.setattr(image_uploads, "begin_image_upload", fake_begin)
    monkeypatch.setattr(image_uploads, "append_image_upload_chunk", fake_append)
    monkeypatch.setattr(image_uploads, "finish_image_upload", fake_finish)

    with client as c:
        begun = c.post(
            "/api/v1/image-generation/uploads/begin",
            json={
                "project_id": "demo-project",
                "relative_path": "public/native.png",
                "source_name": "native.png",
                "origin": "chatgpt_native",
            },
        )
        appended = c.post(
            f"/api/v1/image-generation/uploads/{'a' * 24}/append",
            json={"chunk_base64": "YWJj"},
        )
        finished = c.post(f"/api/v1/image-generation/uploads/{'a' * 24}/finish")

    assert begun.status_code == 200, begun.text
    assert appended.status_code == 200, appended.text
    assert finished.status_code == 200, finished.text
    assert finished.json()["completed"] is True
    assert [name for name, _ in calls] == ["begin", "append", "finish"]

    paths = TestClient(client.app).get("/api/v1/openapi.json").json()["paths"]
    assert "/api/v1/image-generation/uploads/begin" in paths
    assert "/api/v1/image-generation/uploads/{upload_id}/append" in paths
    assert "/api/v1/image-generation/uploads/{upload_id}/finish" in paths
