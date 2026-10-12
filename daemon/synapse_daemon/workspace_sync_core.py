"""Local-first workspace synchronization primitives.

No implicit network access or executable file deployment. Transport adapters
must authenticate both devices and explicitly authorize project/path access.
"""
from __future__ import annotations

import hashlib
import os
import sqlite3
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any


class SyncConflict(Exception):
    pass


def safe_relative_path(path: str) -> str:
    if not isinstance(path, str) or not path or "\\" in path or "\x00" in path:
        raise ValueError("Invalid relative path")
    normalized = PurePosixPath(path)
    if normalized.is_absolute() or any(part in ("..", ".") for part in path.split("/")) or ":" in path:
        raise ValueError("Unsafe relative path")
    if path.startswith("/") or "//" in path or ".git" in normalized.parts:
        raise ValueError("Unsafe relative path")
    return str(normalized)


def checksum(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@dataclass(frozen=True)
class FileManifest:
    path: str
    digest: str
    size: int
    version: int = 1

    def to_dict(self) -> dict[str, Any]:
        return {"path": self.path, "digest": self.digest, "size": self.size, "version": self.version}


def file_manifest(root: Path, relative: str) -> FileManifest:
    safe_relative_path(relative)
    base = root.resolve(strict=True)
    path = (base / relative).resolve(strict=True)
    if base not in path.parents or not path.is_file() or path.is_symlink():
        raise ValueError("File outside project or not regular")
    data = path.read_bytes()
    return FileManifest(path=relative, digest=checksum(data), size=len(data))


def atomic_write_verified(root: Path, relative: str, data: bytes, *,
                          expected_digest: str | None, advertised_digest: str) -> str:
    """Writes only if the local file still matches its observed revision."""
    relative = safe_relative_path(relative)
    base = root.resolve(strict=True)
    target = base / relative
    parent = target.parent.resolve(strict=True)
    if parent != base and base not in parent.parents:
        raise ValueError("Write escapes project")
    if target.is_symlink():
        raise ValueError("Symlinks are not valid sync targets")
    current = checksum(target.read_bytes()) if target.exists() else None
    if current != expected_digest:
        raise SyncConflict("Local file changed since sync planning")
    if checksum(data) != advertised_digest:
        raise ValueError("Transfer checksum mismatch")
    fd, temp = tempfile.mkstemp(prefix=".synapse-sync-", dir=parent)
    try:
        with os.fdopen(fd, "wb") as out:
            out.write(data)
            out.flush()
            os.fsync(out.fileno())
        # Race-safe promotion requires an external per-path lock held by caller.
        last = checksum(target.read_bytes()) if target.exists() else None
        if last != expected_digest:
            raise SyncConflict("Local file changed while staging")
        os.replace(temp, target)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)
    return advertised_digest


class Outbox:
    """Durable retry queue. Successful delivery must be explicitly acknowledged."""

    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        with self._db() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS sync_outbox (
                id INTEGER PRIMARY KEY AUTOINCREMENT, project_id TEXT NOT NULL,
                device_id TEXT NOT NULL, relative_path TEXT NOT NULL,
                digest TEXT NOT NULL, base_digest TEXT, created_at REAL NOT NULL,
                attempts INTEGER NOT NULL DEFAULT 0, next_attempt REAL NOT NULL DEFAULT 0
            )""")

    def _db(self):
        import contextlib
        @contextlib.contextmanager
        def conn():
            db = sqlite3.connect(self.path, timeout=15)
            db.row_factory = sqlite3.Row
            try:
                yield db
                db.commit()
            except Exception:
                db.rollback()
                raise
            finally:
                db.close()
        return conn()

    def enqueue(self, project_id: str, device_id: str, relative_path: str,
                digest: str, base_digest: str | None = None) -> int:
        rel = safe_relative_path(relative_path)
        if not project_id or not device_id or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest.lower()):
            raise ValueError("Invalid queue item")
        with self._db() as db:
            row = db.execute("""INSERT INTO sync_outbox
                (project_id,device_id,relative_path,digest,base_digest,created_at)
                VALUES(?,?,?,?,?,?)""",
                (project_id,device_id,rel,digest,base_digest,time.time()))
            return int(row.lastrowid)

    def pending(self, now: float | None = None, limit: int = 100) -> list[dict]:
        at = time.time() if now is None else now
        with self._db() as db:
            return [dict(row) for row in db.execute(
                "SELECT * FROM sync_outbox WHERE next_attempt<=? ORDER BY id LIMIT ?",
                (at, min(max(1,limit),500)))]

    def failed_attempt(self, item_id: int, now: float | None = None) -> None:
        at = time.time() if now is None else now
        with self._db() as db:
            db.execute("""UPDATE sync_outbox SET attempts=attempts+1,
                next_attempt=? + min(3600, 5 * (1 << min(attempts, 10)))
                WHERE id=?""", (at, item_id))

    def acknowledge(self, item_id: int, digest: str) -> bool:
        with self._db() as db:
            result = db.execute(
                "DELETE FROM sync_outbox WHERE id=? AND digest=?", (item_id, digest))
            return result.rowcount == 1
