"""Tests for project-scoped image editing/reference-image support."""

from __future__ import annotations

import base64
import binascii
import json
import struct
import zlib
from pathlib import Path

import httpx
import pytest

from synapse_daemon import image_editing


def _fake_response(image_bytes: bytes = b"edited-image") -> httpx.Response:
    request = httpx.Request("POST", image_editing.OPENAI_EDITS_URL)
    return httpx.Response(
        200,
        json={"data": [{"b64_json": base64.b64encode(image_bytes).decode("ascii")}]},
        headers={"x-request-id": "req_edit_test"},
        request=request,
    )


def _write_image(root: Path, rel: str, data: bytes = b"source") -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def _png_bytes(width: int, height: int, *, alpha: bool) -> bytes:
    def chunk(kind: bytes, data: bytes) -> bytes:
        crc = binascii.crc32(kind + data) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", crc)

    color_type = 6 if alpha else 2
    pixel = bytes((255, 0, 0, 255)) if alpha else bytes((255, 255, 255))
    raw = (bytes((0,)) + pixel * width) * height
    ihdr = struct.pack(">IIBBBBB", width, height, 8, color_type, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )


def _write_png(root: Path, rel: str, width: int = 64, height: int = 64, *, alpha: bool = True) -> Path:
    return _write_image(root, rel, _png_bytes(width, height, alpha=alpha))


def test_edit_requires_input_image(tmp_path: Path) -> None:
    with pytest.raises(image_editing.ImageEditError, match="at least one"):
        image_editing.edit_image(
            project_root=tmp_path,
            prompt="Make it cleaner",
            input_paths=[],
            relative_path="out.png",
        )


def test_edit_rejects_input_path_escape(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    with pytest.raises(image_editing.ImageEditError, match="escapes"):
        image_editing.edit_image(
            project_root=tmp_path,
            prompt="Edit it",
            input_paths=["../outside.png"],
            relative_path="out.png",
        )


def test_edit_requires_key_before_network(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write_image(tmp_path, "assets/source.png")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    def fail_if_called(*args, **kwargs):
        raise AssertionError("network must not be called without a provider key")

    monkeypatch.setattr(image_editing.httpx, "post", fail_if_called)

    with pytest.raises(image_editing.ImageEditError, match="OPENAI_API_KEY"):
        image_editing.edit_image(
            project_root=tmp_path,
            prompt="Edit it",
            input_paths=["assets/source.png"],
            relative_path="assets/out.png",
        )


def test_edit_sends_repeated_reference_fields_and_records_provenance(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    _write_image(tmp_path, "refs/a.png", b"a")
    _write_image(tmp_path, "refs/b.webp", b"b")
    seen: dict[str, object] = {}

    def fake_post(url, *, headers, data, files, timeout):
        seen.update(
            {"url": url, "headers": headers, "data": data, "files": files, "timeout": timeout}
        )
        return _fake_response(b"final-edit")

    monkeypatch.setattr(image_editing.httpx, "post", fake_post)

    result = image_editing.edit_image(
        project_root=tmp_path,
        prompt="Combine these into one clean product composition",
        input_paths=["refs/a.png", "refs/b.webp"],
        relative_path="public/composite.webp",
        size="1536x1024",
        quality="max",
        output_format="webp",
    )

    fields = seen["files"]
    assert [name for name, _ in fields] == ["image[]", "image[]"]
    assert seen["url"] == image_editing.OPENAI_EDITS_URL
    assert seen["data"]["model"] == "gpt-image-2.5-sunburst"
    assert "input_fidelity" not in seen["data"]
    assert result["source_paths"] == ["refs/a.png", "refs/b.webp"]
    assert (tmp_path / "public/composite.webp").read_bytes() == b"final-edit"

    manifest = tmp_path / ".synapse" / "image-assets.jsonl"
    record = json.loads(manifest.read_text(encoding="utf-8").strip())
    assert record["kind"] == "edited_image"
    assert record["source_paths"] == ["refs/a.png", "refs/b.webp"]
    assert record["request_id"] == "req_edit_test"


def test_mask_applies_as_separate_multipart_field(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    _write_png(tmp_path, "refs/source.png", alpha=True)
    _write_png(tmp_path, "refs/mask.png", alpha=True)
    seen: dict[str, object] = {}

    def fake_post(url, *, headers, data, files, timeout):
        seen["files"] = files
        return _fake_response()

    monkeypatch.setattr(image_editing.httpx, "post", fake_post)

    result = image_editing.edit_image(
        project_root=tmp_path,
        prompt="Replace only the masked area",
        input_paths=["refs/source.png"],
        mask_path="refs/mask.png",
        relative_path="out.png",
    )

    assert [name for name, _ in seen["files"]] == ["image[]", "mask"]
    assert result["mask_path"] == "refs/mask.png"


def test_mask_format_must_match_first_input(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    _write_image(tmp_path, "refs/source.png")
    _write_image(tmp_path, "refs/mask.webp")

    with pytest.raises(image_editing.ImageEditError, match="same file format"):
        image_editing.edit_image(
            project_root=tmp_path,
            prompt="Edit masked area",
            input_paths=["refs/source.png"],
            mask_path="refs/mask.webp",
            relative_path="out.png",
        )


def test_mask_dimensions_must_match_before_provider_call(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    _write_png(tmp_path, "refs/source.png", 64, 64, alpha=True)
    _write_png(tmp_path, "refs/mask.png", 32, 64, alpha=True)

    def fail_if_called(*args, **kwargs):
        raise AssertionError("provider must not be called for an invalid mask")

    monkeypatch.setattr(image_editing.httpx, "post", fail_if_called)
    with pytest.raises(image_editing.ImageEditError, match="same pixel dimensions"):
        image_editing.edit_image(
            project_root=tmp_path,
            prompt="Edit masked area",
            input_paths=["refs/source.png"],
            mask_path="refs/mask.png",
            relative_path="out.png",
        )


def test_mask_requires_alpha_before_provider_call(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    _write_png(tmp_path, "refs/source.png", 64, 64, alpha=True)
    _write_png(tmp_path, "refs/mask.png", 64, 64, alpha=False)

    def fail_if_called(*args, **kwargs):
        raise AssertionError("provider must not be called for an invalid mask")

    monkeypatch.setattr(image_editing.httpx, "post", fail_if_called)
    with pytest.raises(image_editing.ImageEditError, match="alpha channel"):
        image_editing.edit_image(
            project_root=tmp_path,
            prompt="Edit masked area",
            input_paths=["refs/source.png"],
            mask_path="refs/mask.png",
            relative_path="out.png",
        )


@pytest.mark.parametrize(
    ("status_code", "expected_code", "expected_status", "retryable"),
    [
        (429, "image_edit.rate_limited", 429, True),
        (503, "image_edit.provider_unavailable", 502, True),
        (401, "image_edit.provider_auth_failed", 503, False),
        (422, "image_edit.provider_rejected", 422, False),
    ],
)
def test_edit_classifies_provider_failures(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    status_code: int,
    expected_code: str,
    expected_status: int,
    retryable: bool,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    _write_image(tmp_path, "refs/source.png")

    def fake_post(*args, **kwargs):
        return httpx.Response(
            status_code,
            json={"error": {"code": "provider_code", "message": "provider message"}},
            request=httpx.Request("POST", image_editing.OPENAI_EDITS_URL),
        )

    monkeypatch.setattr(image_editing.httpx, "post", fake_post)
    with pytest.raises(image_editing.ImageEditError) as caught:
        image_editing.edit_image(
            project_root=tmp_path,
            prompt="Edit it",
            input_paths=["refs/source.png"],
            relative_path="out.png",
        )

    assert caught.value.code == expected_code
    assert caught.value.status == expected_status
    assert caught.value.retryable is retryable
