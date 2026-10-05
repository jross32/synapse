"""Tests for the generated-image provenance catalog and integrity audit."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from synapse_daemon import image_asset_catalog


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _write_manifest(root: Path, rows: list[object]) -> Path:
    manifest = root / ".synapse" / "image-assets.jsonl"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    lines = [row if isinstance(row, str) else json.dumps(row) for row in rows]
    manifest.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return manifest


def test_empty_catalog_when_manifest_missing(tmp_path: Path) -> None:
    result = image_asset_catalog.load_image_assets(tmp_path)
    assert result["record_count"] == 0
    assert result["records"] == []
    assert result["malformed_lines"] == 0


def test_catalog_verifies_hash_and_detects_tamper(tmp_path: Path) -> None:
    target = tmp_path / "public" / "hero.png"
    target.parent.mkdir(parents=True)
    original = b"original"
    target.write_bytes(original)
    _write_manifest(
        tmp_path,
        [{"kind": "generated_image", "path": "public/hero.png", "sha256": _sha(original)}],
    )

    first = image_asset_catalog.audit_image_assets(tmp_path)
    assert first["healthy"] is True

    target.write_bytes(b"tampered")
    second = image_asset_catalog.audit_image_assets(tmp_path)
    assert second["healthy"] is False
    assert second["modified_paths"] == ["public/hero.png"]


def test_catalog_detects_missing_file(tmp_path: Path) -> None:
    _write_manifest(
        tmp_path,
        [{"kind": "generated_image", "path": "public/missing.png", "sha256": "deadbeef"}],
    )
    result = image_asset_catalog.audit_image_assets(tmp_path)
    assert result["missing_paths"] == ["public/missing.png"]
    assert result["healthy"] is False


def test_catalog_skips_malformed_and_escaping_records(tmp_path: Path) -> None:
    _write_manifest(
        tmp_path,
        [
            "{not-json",
            {"path": "../escape.png", "sha256": "x"},
            {"path": "safe.png", "kind": "generated_image"},
        ],
    )
    (tmp_path / "safe.png").write_bytes(b"safe")

    result = image_asset_catalog.load_image_assets(tmp_path)
    assert result["record_count"] == 1
    assert result["malformed_lines"] == 2
    assert result["records"][0]["path"] == "safe.png"


def test_duplicate_paths_and_latest_record_lookup(tmp_path: Path) -> None:
    (tmp_path / "hero.png").write_bytes(b"new")
    _write_manifest(
        tmp_path,
        [
            {"path": "hero.png", "kind": "generated_image", "prompt": "old"},
            {"path": "hero.png", "kind": "edited_image", "prompt": "new"},
        ],
    )

    catalog = image_asset_catalog.load_image_assets(tmp_path)
    assert catalog["duplicate_paths"] == ["hero.png"]

    latest = image_asset_catalog.get_image_asset(tmp_path, "hero.png")
    assert latest is not None
    assert latest["kind"] == "edited_image"
    assert latest["prompt"] == "new"
