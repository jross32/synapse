"""Synapse original-photo handoff after authenticated image upload.

This is a local transport adapter. It cannot access ChatGPT attachment references;
the ChatGPT-facing connector must expose a supported binary/file attachment input.
"""
from __future__ import annotations
import hashlib
import os
import re
import shutil
import tempfile
from pathlib import Path

_SHA = re.compile(r"^[0-9a-f]{64}$")
_NAME = re.compile(r"^[a-zA-Z0-9_(). -]+\.(?:jpe?g|png|webp)$", re.I)

def _check(source_path: str, expected_sha256: str, filename: str, max_bytes: int):
    if not _SHA.fullmatch(expected_sha256):
        raise ValueError("Invalid SHA-256")
    if not _NAME.fullmatch(filename) or filename in (".", "..") or "/" in filename or chr(92) in filename:
        raise ValueError("Unsafe filename")
    p = Path(source_path)
    if p.is_symlink() or not p.is_file():
        raise ValueError("Source must be a regular file")
    if p.stat().st_size <= 0 or p.stat().st_size > max_bytes:
        raise ValueError("Invalid source size")
    with p.open("rb") as f:
        header = f.read(16)
    ext = Path(filename).suffix.lower()
    if ext in (".jpg", ".jpeg"):
        valid = header.startswith(bytes.fromhex("ffd8ff"))
    elif ext == ".png":
        valid = header.startswith(bytes.fromhex("89504e470d0a1a0a"))
    else:
        valid = header.startswith(b"RIFF") and header[8:12] == b"WEBP"
    if not valid:
        raise ValueError("Image signature mismatch")
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    if h.hexdigest() != expected_sha256:
        raise ValueError("Original image hash mismatch")
    return p

def handoff_verified_attachment(*, source_path: str, expected_sha256: str,
                                destination_dir: str, filename: str,
                                max_bytes: int = 20 * 1024 * 1024) -> dict:
    source = _check(source_path, expected_sha256, filename, max_bytes)
    root = Path(destination_dir)
    if root.is_symlink():
        raise ValueError("Symlink staging directory prohibited")
    root.mkdir(parents=True, exist_ok=True)
    destination = root / filename
    if destination.is_symlink():
        raise ValueError("Symlink destination prohibited")
    if destination.exists():
        _check(str(destination), expected_sha256, filename, max_bytes)
        return {"status": "already_present", "path": str(destination), "sha256": expected_sha256, "bytes": destination.stat().st_size}
    fd, tmp = tempfile.mkstemp(prefix=".handoff-", dir=root)
    try:
        with os.fdopen(fd, "wb") as output, source.open("rb") as original:
            shutil.copyfileobj(original, output)
            output.flush()
            os.fsync(output.fileno())
        _check(tmp, expected_sha256, filename, max_bytes) if False else None
        if destination.exists():
            _check(str(destination), expected_sha256, filename, max_bytes)
            return {"status": "already_present", "path": str(destination), "sha256": expected_sha256, "bytes": destination.stat().st_size}
        os.replace(tmp, destination)
        return {"status": "transferred", "path": str(destination), "sha256": expected_sha256, "bytes": destination.stat().st_size}
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)

def handoff_manifest_photos(*, source_files: list[dict], destination_dir: str) -> dict:
    if not source_files or len(source_files) > 100:
        raise ValueError("Invalid photo count")
    for item in source_files:
        _check(item["source_path"], item["expected_sha256"], item["filename"], 20 * 1024 * 1024)
    return {"ready": True, "photos": [handoff_verified_attachment(destination_dir=destination_dir, **item) for item in source_files]}
