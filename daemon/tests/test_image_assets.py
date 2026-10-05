"""Tests for Synapse's project-scoped image generation capability."""

from __future__ import annotations

import base64
import json
from pathlib import Path

import httpx
import pytest
from synapse_daemon import image_assets
from synapse_daemon.projects import Project, create
from synapse_daemon.storage import Storage


def _fake_response(image_bytes: bytes = b"fake-png-bytes") -> httpx.Response:
    request = httpx.Request("POST", image_assets.OPENAI_GENERATIONS_URL)
    return httpx.Response(
        200,
        json={"data": [{"b64_json": base64.b64encode(image_bytes).decode("ascii")}]},
        headers={"x-request-id": "req_test_image"},
        request=request,
    )


def test_status_reports_missing_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("SYNAPSE_IMAGE_PROVIDER", raising=False)
    monkeypatch.delenv("SYNAPSE_OPENAI_IMAGE_MODEL", raising=False)

    status = image_assets.image_generation_status()

    assert status["configured"] is False
    assert status["provider"] == "openai"
    assert status["model"] == "gpt-image-2.5-sunburst"
    assert "OPENAI_API_KEY" in status["reason"]


def test_status_reports_configured_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    status = image_assets.image_generation_status()

    assert status["configured"] is True
    assert status["reason"] is None
    assert status["supports"]["project_scoped_output"] is True
    assert status["supports"]["asset_manifest"] is True
    assert status["supports"]["editing"] is True


def test_generate_rejects_path_escape(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    with pytest.raises(image_assets.ImageGenerationError, match="escapes"):
        image_assets.generate_image(
            project_root=tmp_path,
            prompt="A useful project hero image",
            relative_path="../outside.png",
        )


def test_generate_requires_key_before_network(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    def fail_if_called(*args, **kwargs):
        raise AssertionError("network should not be called without a configured provider key")

    monkeypatch.setattr(image_assets.httpx, "post", fail_if_called)

    with pytest.raises(image_assets.ImageGenerationError, match="OPENAI_API_KEY"):
        image_assets.generate_image(
            project_root=tmp_path,
            prompt="A useful project hero image",
            relative_path="public/images/hero.png",
        )


def test_generate_writes_asset_and_manifest(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    image_bytes = b"generated-image-content"

    seen: dict[str, object] = {}

    def fake_post(url, *, headers, json, timeout):
        seen.update({"url": url, "headers": headers, "json": json, "timeout": timeout})
        return _fake_response(image_bytes)

    monkeypatch.setattr(image_assets.httpx, "post", fake_post)

    result = image_assets.generate_image(
        project_root=tmp_path,
        prompt="A premium gaming PC hero image on a dark studio background",
        relative_path="public/images/hero.webp",
        size="1536x1024",
        quality="max",
        output_format="webp",
    )

    target = tmp_path / "public" / "images" / "hero.webp"
    assert target.read_bytes() == image_bytes
    assert result["project_relative_path"] == "public/images/hero.webp"
    assert result["provider"] == "openai"
    assert result["model"] == "gpt-image-2.5-sunburst"
    assert result["request_id"] == "req_test_image"
    assert seen["url"] == image_assets.OPENAI_GENERATIONS_URL
    assert seen["json"] == {
        "model": "gpt-image-2.5-sunburst",
        "prompt": "A premium gaming PC hero image on a dark studio background",
        "size": "1536x1024",
        "quality": "max",
        "output_format": "webp",
        "background": "auto",
    }

    manifest = tmp_path / ".synapse" / "image-assets.jsonl"
    record = json.loads(manifest.read_text(encoding="utf-8").strip())
    assert record["path"] == "public/images/hero.webp"
    assert record["provider"] == "openai"
    assert record["model"] == "gpt-image-2.5-sunburst"
    assert record["request_id"] == "req_test_image"
    assert record["sha256"] == result["sha256"]


def test_generate_refuses_overwrite_by_default(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    target = tmp_path / "public" / "images" / "hero.png"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"keep-me")

    def fail_if_called(*args, **kwargs):
        raise AssertionError("network should not be called when output already exists")

    monkeypatch.setattr(image_assets.httpx, "post", fail_if_called)

    with pytest.raises(image_assets.ImageGenerationError, match="refusing to overwrite"):
        image_assets.generate_image(
            project_root=tmp_path,
            prompt="A replacement hero",
            relative_path="public/images/hero.png",
        )

    assert target.read_bytes() == b"keep-me"


@pytest.mark.parametrize(
    ("size", "message"),
    [
        ("1000x1000", "multiples of 16"),
        ("4096x1024", "3840"),
        ("3200x800", "3:1"),
        ("640x640", "pixel count"),
    ],
)
def test_size_validation_matches_provider_constraints(size: str, message: str) -> None:
    with pytest.raises(image_assets.ImageGenerationError, match=message):
        image_assets._validate_size(size)


def test_generate_project_image_resolves_project_and_audits_without_prompt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(image_assets.httpx, "post", lambda *args, **kwargs: _fake_response(b"asset"))

    project_root = tmp_path / "project"
    project_root.mkdir()
    storage = Storage(tmp_path / "data")
    storage.open()
    storage.migrate()
    with storage.transaction() as conn:
        create(
            conn,
            Project(
                id="demo",
                name="Demo",
                path=str(project_root),
                launch_cmd="echo hi",
            ),
        )

    prompt = "A confidential-looking but test-only image prompt"
    result = image_assets.generate_project_image(
        storage,
        project_id="demo",
        prompt=prompt,
        relative_path="public/images/hero.png",
    )

    assert result["project_id"] == "demo"
    assert (project_root / "public" / "images" / "hero.png").read_bytes() == b"asset"

    row = storage.conn.execute(
        "SELECT entity_type, entity_id, action, source, details_json "
        "FROM audit_log ORDER BY id DESC LIMIT 1"
    ).fetchone()
    assert row["entity_type"] == "image_asset"
    assert row["action"] == "generate"
    assert row["source"] == "auto"
    details = json.loads(row["details_json"])
    assert details["project_id"] == "demo"
    assert details["project_relative_path"] == "public/images/hero.png"
    assert prompt not in row["details_json"]

