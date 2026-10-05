"""Tests for importing already-generated local images into Synapse projects."""

from __future__ import annotations

import json
import struct
import zlib
from pathlib import Path

import pytest

from synapse_daemon import image_imports
from synapse_daemon.projects import Project, create
from synapse_daemon.storage import Storage


def _png_bytes(width: int = 2, height: int = 3) -> bytes:
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


def test_import_copies_valid_image_and_records_safe_manifest(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    source_dir = tmp_path / "private-source-dir"
    source_dir.mkdir()
    source = source_dir / "native-output.png"
    source.write_bytes(_png_bytes())

    result = image_imports.import_image_file(
        project_root=project,
        source_path=source,
        relative_path="public/images/native-output.png",
        origin="chatgpt_native",
        provider="openai-chatgpt",
        model="native-image",
        prompt="A project-specific proof image",
    )

    target = project / "public" / "images" / "native-output.png"
    assert target.read_bytes() == source.read_bytes()
    assert result["width"] == 2
    assert result["height"] == 3
    assert result["has_alpha"] is True
    assert result["format"] == "png"
    assert result["source_name"] == "native-output.png"

    manifest_text = (project / ".synapse" / "image-assets.jsonl").read_text(encoding="utf-8")
    record = json.loads(manifest_text)
    assert record["kind"] == "imported_image"
    assert record["origin"] == "chatgpt_native"
    assert record["prompt"] == "A project-specific proof image"
    assert str(source_dir) not in manifest_text


def test_import_rejects_fake_image_before_copy(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    source = tmp_path / "fake.png"
    source.write_bytes(b"not-a-png")

    with pytest.raises(image_imports.ImageImportError, match="invalid PNG"):
        image_imports.import_image_file(
            project_root=project,
            source_path=source,
            relative_path="public/fake.png",
        )
    assert not (project / "public" / "fake.png").exists()


def test_import_enforces_output_extension_and_overwrite_guard(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    source = tmp_path / "source.png"
    source.write_bytes(_png_bytes())

    with pytest.raises(image_imports.ImageImportError, match="extension"):
        image_imports.import_image_file(
            project_root=project,
            source_path=source,
            relative_path="public/source.jpg",
        )

    image_imports.import_image_file(
        project_root=project,
        source_path=source,
        relative_path="public/source.png",
    )
    with pytest.raises(image_imports.ImageImportError, match="overwrite"):
        image_imports.import_image_file(
            project_root=project,
            source_path=source,
            relative_path="public/source.png",
        )


def test_project_import_audits_without_absolute_source_or_prompt(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    source_dir = tmp_path / "private-source-dir"
    source_dir.mkdir()
    source = source_dir / "native-output.png"
    source.write_bytes(_png_bytes())

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

    prompt = "confidential test-only native generation prompt"
    result = image_imports.import_project_image_file(
        storage,
        project_id="demo",
        source_path=source,
        relative_path="public/native-output.png",
        origin="chatgpt_native",
        provider="openai-chatgpt",
        model="native-image",
        prompt=prompt,
    )

    assert result["project_id"] == "demo"
    row = storage.conn.execute(
        "SELECT action, details_json FROM audit_log ORDER BY id DESC LIMIT 1"
    ).fetchone()
    assert row is not None
    assert row["action"] == "import"
    assert prompt not in row["details_json"]
    assert str(source_dir) not in row["details_json"]
    details = json.loads(row["details_json"])
    assert details["source_name"] == "native-output.png"
    assert details["origin"] == "chatgpt_native"
