"""Safe, local-first inventory and migration planning for Synapse.

No cloud credentials, network access, or destructive operations in this module.
All sizes and plans are read-only and advisory.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import os
import shutil
from typing import Iterable

DEFAULT_EXCLUSIONS = frozenset({
    ".git", "node_modules", ".venv", "venv", "__pycache__", ".next",
    "chrome-profile", "browser-profiles", "playwright-profile",
})
PROTECTED_SUFFIXES = frozenset({".db", ".sqlite", ".sqlite3", ".env", ".key", ".pem"})


@dataclass(frozen=True)
class Inventory:
    root: str
    bytes_total: int
    file_count: int
    directory_count: int
    skipped_links: int
    skipped_errors: int
    excluded_directories: int

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ArchiveCandidate:
    path: str
    size_bytes: int
    reason: str

    def to_dict(self) -> dict:
        return asdict(self)


def disk_capacity(path: str | Path) -> dict:
    """Read volume free/used/total without touching files."""
    p = Path(path).resolve(strict=True)
    usage = shutil.disk_usage(p)
    return {"total": usage.total, "used": usage.used, "free": usage.free}


def scan_tree(root: str | Path, excluded: Iterable[str] = DEFAULT_EXCLUSIONS) -> Inventory:
    """Read-only scan. Never follows directory symlinks or Windows junctions."""
    base = Path(root).resolve(strict=True)
    if not base.is_dir():
        raise NotADirectoryError(str(base))
    excluded_lower = {n.lower() for n in excluded}
    total = files = dirs = links = errors = excluded_dirs = 0
    pending = [base]
    while pending:
        current = pending.pop()
        try:
            with os.scandir(current) as entries:
                for item in entries:
                    try:
                        if item.is_symlink() or (hasattr(item, "is_junction") and item.is_junction()):
                            links += 1
                            continue
                        if item.is_dir(follow_symlinks=False):
                            if item.name.lower() in excluded_lower:
                                excluded_dirs += 1
                            else:
                                dirs += 1
                                pending.append(Path(item.path))
                        elif item.is_file(follow_symlinks=False):
                            total += item.stat(follow_symlinks=False).st_size
                            files += 1
                    except OSError:
                        errors += 1
        except OSError:
            errors += 1
    return Inventory(str(base), total, files, dirs, links, errors, excluded_dirs)


def propose_archives(root: str | Path, min_size_bytes: int = 10 * 1024 * 1024,
                     excluded: Iterable[str] = DEFAULT_EXCLUSIONS,
                     limit: int = 100) -> list[ArchiveCandidate]:
    """Recommend only standalone archive/media artifacts; never live source or secrets."""
    if min_size_bytes < 0 or not 1 <= limit <= 10000:
        raise ValueError("Invalid archive parameters")
    base = Path(root).resolve(strict=True)
    if not base.is_dir():
        raise NotADirectoryError(str(base))
    excluded_lower = {s.lower() for s in excluded}
    allowed = {".zip", ".7z", ".tar", ".gz", ".mp4", ".mov", ".webm", ".mkv"}
    candidates = []
    pending = [base]
    while pending:
        folder = pending.pop()
        try:
            with os.scandir(folder) as entries:
                for entry in entries:
                    try:
                        if entry.is_symlink() or (hasattr(entry, "is_junction") and entry.is_junction()):
                            continue
                        if entry.is_dir(follow_symlinks=False):
                            if entry.name.lower() not in excluded_lower:
                                pending.append(Path(entry.path))
                        elif entry.is_file(follow_symlinks=False):
                            p = Path(entry.path)
                            if p.suffix.lower() in allowed and p.suffix.lower() not in PROTECTED_SUFFIXES:
                                size = entry.stat(follow_symlinks=False).st_size
                                if size >= min_size_bytes:
                                    candidates.append(ArchiveCandidate(str(p), size, "archive_or_media"))
                    except OSError:
                        continue
        except OSError:
            continue
    candidates.sort(key=lambda c: (-c.size_bytes, c.path))
    return candidates[:limit]


def migration_preview(root: str | Path, provider: str = "google_drive",
                      min_size_bytes: int = 10 * 1024 * 1024) -> dict:
    """Preview only; migration/deletion intentionally not implemented."""
    if provider not in {"google_drive", "icloud"}:
        raise ValueError("Unsupported storage provider")
    inventory = scan_tree(root)
    candidates = propose_archives(root, min_size_bytes=min_size_bytes)
    return {
        "mode": "dry_run", "provider": provider,
        "inventory": inventory.to_dict(),
        "candidates": [c.to_dict() for c in candidates],
        "potential_reclaim_bytes": sum(c.size_bytes for c in candidates),
        "cloud_upload_performed": False,
        "local_files_removed": False,
        "requires_explicit_approval": True,
    }
