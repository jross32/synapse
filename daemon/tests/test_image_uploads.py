"""Tests for chunked image transfer from AI runtimes into Synapse."""

from __future__ import annotations

import base64
import hashlib
import json
import struct
import zlib
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from synapse_daemon import image_uploads
from synapse_daemon.projects import Project, create
from synapse_daemon.storage import Storage


def _png_bytes(width: int = 4, height: int = 2) -> bytes:
    signature = b"\x89PNG\r\n\x1a\n"
    ihdr_data = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    ihdr = (
        struct.pack(">I", len(ihdr_data))
        + b"IHDR"
        + ihdr_data
        + struct.pack(">I", zlib.crc32(b"IHDR" + ihdr_data) & 0xFFFFFFFF)
    )
    raw = b"".join(b"\x00" + b"\x00\x00\x00\x00" * width for _ in range(height))
    idat_data = zlib.compress(raw)
    idat = (
        struct.pack(">I", len(idat_data))
        + b"IDAT"
        + idat_data
        + struct.pack(">I", zlib.crc32(b"IDAT" + idat_data) & 0xFFFFFFFF)
    )
    iend = struct.pack(">I", 0) + b"IEND" + struct.pack(">I", zlib.crc32(b"IEND") & 0xFFFFFFFF)
    return signature + ihdr + idat + iend


def _storage_with_project(tmp_path: Path) -> tuple[Storage, Path]:
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
    return storage, project_root


def test_chunked_upload_finishes_into_project_and_cleans_staging(tmp_path: Path) -> None:
    storage, project_root = _storage_with_project(tmp_path)
    payload = _png_bytes()
    digest = hashlib.sha256(payload).hexdigest()
    prompt = "private native generation prompt"

    begun = image_uploads.begin_image_upload(
        storage,
        project_id="demo",
        relative_path="public/images/native.png",
        source_name="chatgpt-native.png",
        origin="chatgpt_native",
        provider="openai-chatgpt",
        model="native-image",
        prompt=prompt,
        expected_sha256=digest,
    )
    upload_id = begun["upload_id"]

    meta_path = Path(storage.data_dir) / "image-upload-staging" / f"{upload_id}.json"
    meta_text = meta_path.read_text(encoding="utf-8")
    assert prompt not in meta_text
    assert "prompt_ciphertext_b64" in meta_text

    split = len(payload) // 2
    first = image_uploads.append_image_upload_chunk(
        storage,
        upload_id=upload_id,
        chunk_base64=base64.b64encode(payload[:split]).decode("ascii"),
    )
    second = image_uploads.append_image_upload_chunk(
        storage,
        upload_id=upload_id,
        chunk_base64=base64.b64encode(payload[split:]).decode("ascii"),
    )
    assert first["chunk_count"] == 1
    assert second["chunk_count"] == 2
    assert second["bytes_received"] == len(payload)

    result = image_uploads.finish_image_upload(storage, upload_id=upload_id)

    assert result["completed"] is True
    assert result["kind"] == "imported_image"
    assert result["width"] == 4
    assert result["height"] == 2
    assert result["sha256"] == digest
    assert (project_root / "public" / "images" / "native.png").read_bytes() == payload
    assert not meta_path.exists()
    staging = Path(storage.data_dir) / "image-upload-staging"
    assert not any(path.name.startswith(upload_id) for path in staging.iterdir())

    manifest_text = (project_root / ".synapse" / "image-assets.jsonl").read_text(encoding="utf-8")
    assert prompt in manifest_text
    assert "chatgpt_native" in manifest_text

    row = storage.conn.execute(
        "SELECT details_json FROM audit_log ORDER BY id DESC LIMIT 1"
    ).fetchone()
    assert row is not None
    assert prompt not in row["details_json"]
    assert "image-upload-staging" not in row["details_json"]


def test_finish_rejects_hash_mismatch_and_keeps_session_for_retry(tmp_path: Path) -> None:
    storage, project_root = _storage_with_project(tmp_path)
    payload = _png_bytes()
    begun = image_uploads.begin_image_upload(
        storage,
        project_id="demo",
        relative_path="public/native.png",
        expected_sha256="0" * 64,
    )
    upload_id = begun["upload_id"]
    image_uploads.append_image_upload_chunk(
        storage,
        upload_id=upload_id,
        chunk_base64=base64.b64encode(payload).decode("ascii"),
    )

    with pytest.raises(image_uploads.ImageUploadError, match="SHA-256"):
        image_uploads.finish_image_upload(storage, upload_id=upload_id)

    assert not (project_root / "public" / "native.png").exists()
    assert (Path(storage.data_dir) / "image-upload-staging" / f"{upload_id}.json").exists()


def test_append_rejects_invalid_base64_without_changing_count(tmp_path: Path) -> None:
    storage, _ = _storage_with_project(tmp_path)
    begun = image_uploads.begin_image_upload(
        storage,
        project_id="demo",
        relative_path="public/native.png",
    )
    upload_id = begun["upload_id"]

    with pytest.raises(image_uploads.ImageUploadError, match="valid base64"):
        image_uploads.append_image_upload_chunk(
            storage,
            upload_id=upload_id,
            chunk_base64="not!!base64",
        )

    meta = json.loads(
        (Path(storage.data_dir) / "image-upload-staging" / f"{upload_id}.json").read_text(
            encoding="utf-8"
        )
    )
    assert meta["bytes_received"] == 0
    assert meta["chunk_count"] == 0


def test_expired_upload_is_removed(tmp_path: Path) -> None:
    storage, _ = _storage_with_project(tmp_path)
    begun = image_uploads.begin_image_upload(
        storage,
        project_id="demo",
        relative_path="public/native.png",
    )
    upload_id = begun["upload_id"]
    meta_path = Path(storage.data_dir) / "image-upload-staging" / f"{upload_id}.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta["created_at"] = (datetime.now(UTC) - timedelta(hours=3)).isoformat()
    meta_path.write_text(json.dumps(meta), encoding="utf-8")

    with pytest.raises(image_uploads.ImageUploadError, match="expired"):
        image_uploads.append_image_upload_chunk(
            storage,
            upload_id=upload_id,
            chunk_base64=base64.b64encode(b"x").decode("ascii"),
        )

    assert not meta_path.exists()
    assert not any(
        path.name.startswith(upload_id)
        for path in (Path(storage.data_dir) / "image-upload-staging").iterdir()
    )


def test_indexed_chunk_retry_is_idempotent_and_status_is_safe(tmp_path: Path) -> None:
    storage, _ = _storage_with_project(tmp_path)
    payload = _png_bytes()
    prompt = "do not expose this staged prompt"
    begun = image_uploads.begin_image_upload(
        storage,
        project_id="demo",
        relative_path="public/retry.png",
        prompt=prompt,
    )
    upload_id = begun["upload_id"]
    chunk = payload[: len(payload) // 2]
    encoded = base64.b64encode(chunk).decode("ascii")

    first = image_uploads.append_image_upload_chunk(
        storage,
        upload_id=upload_id,
        chunk_base64=encoded,
        chunk_index=0,
    )
    retry = image_uploads.append_image_upload_chunk(
        storage,
        upload_id=upload_id,
        chunk_base64=encoded,
        chunk_index=0,
    )
    status = image_uploads.image_upload_status(storage, upload_id=upload_id)

    assert first["duplicate"] is False
    assert first["chunk_count"] == 1
    assert first["next_chunk_index"] == 1
    assert retry["duplicate"] is True
    assert retry["chunk_count"] == 1
    assert retry["bytes_received"] == len(chunk)
    assert status["bytes_received"] == len(chunk)
    assert status["chunk_count"] == 1
    assert status["next_chunk_index"] == 1
    dumped = json.dumps(status)
    assert prompt not in dumped
    assert "prompt_ciphertext" not in dumped
    assert "staging_filename" not in dumped


def test_out_of_order_chunk_rejected_and_cancel_cleans_staging(tmp_path: Path) -> None:
    storage, _ = _storage_with_project(tmp_path)
    begun = image_uploads.begin_image_upload(
        storage,
        project_id="demo",
        relative_path="public/cancel.png",
    )
    upload_id = begun["upload_id"]
    encoded = base64.b64encode(b"abc").decode("ascii")

    with pytest.raises(image_uploads.ImageUploadError) as exc_info:
        image_uploads.append_image_upload_chunk(
            storage,
            upload_id=upload_id,
            chunk_base64=encoded,
            chunk_index=1,
        )
    assert exc_info.value.code == "image_upload.chunk_out_of_order"
    assert exc_info.value.status == 409

    image_uploads.append_image_upload_chunk(
        storage,
        upload_id=upload_id,
        chunk_base64=encoded,
        chunk_index=0,
    )
    staging = Path(storage.data_dir) / "image-upload-staging"
    assert any(path.name.startswith(upload_id) for path in staging.iterdir())

    result = image_uploads.cancel_image_upload(storage, upload_id=upload_id)
    assert result == {"upload_id": upload_id, "cancelled": True}
    assert not any(path.name.startswith(upload_id) for path in staging.iterdir())

    with pytest.raises(image_uploads.ImageUploadError) as missing:
        image_uploads.image_upload_status(storage, upload_id=upload_id)
    assert missing.value.code == "image_upload.not_found"
