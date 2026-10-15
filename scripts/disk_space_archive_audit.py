"""Read-only storage triage for the owner's Synapse development laptop.

This module NEVER deletes or moves source files. Archive candidates are
limited to direct files in the user's Downloads directory; directories,
symlinks, active app files, keys, and working trees are excluded.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path

INSTALLERS = {".exe", ".msi", ".msix", ".apk", ".xapk", ".zip"}
MIN_BYTES = 25 * 1024 * 1024
FAT32_MAX = 4 * 1024**3 - 1


def scan_downloads(downloads: Path, usb: Path) -> dict:
    """Classify top-level download installers without opening any contents."""
    downloads = downloads.resolve(strict=True)
    usb = usb.resolve(strict=True)
    if downloads == usb or downloads in usb.parents:
        raise ValueError("Destination must not be inside Downloads.")
    candidates = []
    for file in downloads.iterdir():
        if file.is_symlink() or not file.is_file() or file.suffix.lower() not in INSTALLERS:
            continue
        try:
            stat = file.stat()
        except OSError:
            continue
        if stat.st_size < MIN_BYTES:
            continue
        candidates.append({
            "name": file.name,
            "source": str(file),
            "bytes": stat.st_size,
            "size_mib": round(stat.st_size / 1024**2, 1),
            "usb_fat32_compatible": stat.st_size <= FAT32_MAX,
            "classification": "archive_candidate_only",
            "action": "copy_and_verify_before_considering_removal",
        })
    candidates.sort(key=lambda x: x["bytes"], reverse=True)
    return {
        "source_directory": str(downloads),
        "destination_directory": str(usb),
        "candidates": candidates,
        "potential_bytes": sum(c["bytes"] for c in candidates),
        "warning": "No files were copied, moved, or deleted. Do not move active project/data directories.",
    }


def copy_verified(source: Path, destination_dir: Path, downloads: Path) -> dict:
    """Optional non-destructive copy only, with checksum verification.

    Never removes source; callers must independently decide any deletion.
    Refuses destination overwrite and symlink sources.
    """
    downloads = downloads.resolve(strict=True)
    if source.is_symlink() or not source.is_file():
        raise ValueError("Source must be a regular non-symlink file.")
    source = source.resolve(strict=True)
    if source.parent != downloads or source.suffix.lower() not in INSTALLERS:
        raise ValueError("Only direct installer archives in Downloads are permitted.")
    if source.stat().st_size < MIN_BYTES or source.stat().st_size > FAT32_MAX:
        raise ValueError("Source is too small or exceeds FAT32 file limit.")
    destination_dir = destination_dir.resolve(strict=True)
    if destination_dir == downloads or downloads in destination_dir.parents:
        raise ValueError("Invalid destination.")
    destination = destination_dir / source.name
    if destination.exists() or destination.is_symlink():
        raise FileExistsError("Destination already exists; refusing overwrite.")
    source_hash = hashlib.sha256()
    copied = 0
    try:
        with source.open("rb") as incoming, destination.open("xb") as outgoing:
            while block := incoming.read(1024 * 1024):
                source_hash.update(block)
                outgoing.write(block)
                copied += len(block)
        destination_hash = hashlib.sha256()
        with destination.open("rb") as verified:
            while block := verified.read(1024 * 1024):
                destination_hash.update(block)
        if source_hash.digest() != destination_hash.digest() or copied != source.stat().st_size:
            raise IOError("Archive checksum or size verification failed.")
    except BaseException:
        try:
            destination.unlink(missing_ok=True)
        except OSError:
            pass
        raise
    return {
        "source": str(source),
        "destination": str(destination),
        "size_bytes": copied,
        "sha256": source_hash.hexdigest(),
        "source_preserved": True,
        "copy_verified": True,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--downloads", type=Path, default=Path.home() / "Downloads")
    parser.add_argument("--usb", type=Path, default=Path("D:/"))
    parser.add_argument("--copy", type=Path, help="Explicitly copy exactly one safe source; never delete.")
    args = parser.parse_args()
    result = (copy_verified(args.copy, args.usb, args.downloads)
              if args.copy is not None else scan_downloads(args.downloads, args.usb))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
