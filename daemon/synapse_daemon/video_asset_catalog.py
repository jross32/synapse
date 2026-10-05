"""Read-only catalog and integrity audit for Synapse-generated video assets."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

MANIFEST_RELATIVE_PATH = Path(".synapse") / "video-assets.jsonl"


class VideoAssetCatalogError(ValueError):
    """A safe, user-facing asset-catalog error."""


def _project_root(project_root: str | Path) -> Path:
    root = Path(project_root).expanduser().resolve()
    if not root.is_dir():
        raise VideoAssetCatalogError(f"registered project path does not exist: {root}")
    return root


def _safe_project_path(root: Path, relative_path: str) -> Path:
    raw = str(relative_path or "").strip()
    if not raw:
        raise VideoAssetCatalogError("asset path is missing")
    candidate = Path(raw)
    if candidate.is_absolute() or candidate.drive:
        raise VideoAssetCatalogError("asset path must be project-relative")
    target = (root / candidate).resolve()
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise VideoAssetCatalogError("asset path escapes the registered project") from exc
    return target


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_video_assets(
    project_root: str | Path,
    *,
    verify_hashes: bool = False,
) -> dict[str, Any]:
    """Load video provenance records and annotate current on-disk integrity."""

    root = _project_root(project_root)
    manifest = root / MANIFEST_RELATIVE_PATH
    if not manifest.exists():
        return {
            "manifest_path": str(manifest),
            "records": [],
            "record_count": 0,
            "malformed_lines": 0,
            "missing_files": 0,
            "modified_files": 0,
            "duplicate_paths": [],
        }

    records: list[dict[str, Any]] = []
    malformed = 0
    seen_paths: dict[str, int] = {}

    for line_number, raw_line in enumerate(
        manifest.read_text(encoding="utf-8", errors="replace").splitlines(),
        start=1,
    ):
        if not raw_line.strip():
            continue
        try:
            value = json.loads(raw_line)
            if not isinstance(value, dict):
                raise ValueError("record is not an object")
            rel = str(value.get("path") or "").strip()
            target = _safe_project_path(root, rel)
        except (json.JSONDecodeError, ValueError, VideoAssetCatalogError):
            malformed += 1
            continue

        record = dict(value)
        record["manifest_line"] = line_number
        record["exists"] = target.is_file()
        record["bytes_on_disk"] = target.stat().st_size if target.is_file() else None
        if target.is_file() and verify_hashes and value.get("sha256"):
            actual = _sha256(target)
            record["sha256_on_disk"] = actual
            record["sha256_matches"] = actual == str(value.get("sha256"))
        elif verify_hashes:
            record["sha256_on_disk"] = None
            record["sha256_matches"] = None

        records.append(record)
        seen_paths[rel] = seen_paths.get(rel, 0) + 1

    duplicates = sorted(path for path, count in seen_paths.items() if count > 1)
    missing = sum(1 for item in records if not item.get("exists"))
    modified = sum(1 for item in records if item.get("sha256_matches") is False)

    return {
        "manifest_path": str(manifest),
        "records": records,
        "record_count": len(records),
        "malformed_lines": malformed,
        "missing_files": missing,
        "modified_files": modified,
        "duplicate_paths": duplicates,
    }


def get_video_asset(
    project_root: str | Path,
    relative_path: str,
    *,
    verify_hash: bool = False,
) -> dict[str, Any] | None:
    """Return the newest manifest record for a project-relative video asset."""

    wanted = Path(str(relative_path or "").strip()).as_posix()
    catalog = load_video_assets(project_root, verify_hashes=verify_hash)
    for record in reversed(catalog["records"]):
        if Path(str(record.get("path") or "")).as_posix() == wanted:
            return record
    return None


def audit_video_assets(project_root: str | Path) -> dict[str, Any]:
    """Run a full integrity audit with hashes and concise issue lists."""

    catalog = load_video_assets(project_root, verify_hashes=True)
    missing = [item.get("path") for item in catalog["records"] if not item.get("exists")]
    modified = [
        item.get("path")
        for item in catalog["records"]
        if item.get("sha256_matches") is False
    ]
    healthy = catalog["malformed_lines"] == 0 and not missing and not modified
    return {
        "healthy": healthy,
        "record_count": catalog["record_count"],
        "malformed_lines": catalog["malformed_lines"],
        "missing_paths": missing,
        "modified_paths": modified,
        "duplicate_paths": catalog["duplicate_paths"],
        "manifest_path": catalog["manifest_path"],
    }
