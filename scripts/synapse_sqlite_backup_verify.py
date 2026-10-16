"""SQLite-consistent backup and isolated restore verification.

Requires explicit input/output paths. Never deletes or modifies source database.
Run from a trusted local environment only; backups may contain credentials.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import sqlite3
from pathlib import Path

def digest(path: Path) -> str:
    hash_ = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            hash_.update(chunk)
    return hash_.hexdigest()

def verified_sqlite_backup(source: Path, archive: Path, restored: Path) -> dict:
    source = source.resolve(strict=True)
    archive = archive.resolve(strict=False)
    restored = restored.resolve(strict=False)
    if not source.is_file() or source.is_symlink():
        raise ValueError("Source must be an existing regular SQLite file.")
    if len({str(source).casefold(), str(archive).casefold(), str(restored).casefold()}) != 3:
        raise ValueError("Paths must be distinct.")
    if archive.exists() or restored.exists():
        raise FileExistsError("Refusing to overwrite backup or restore.")
    if not archive.parent.is_dir() or not restored.parent.is_dir():
        raise ValueError("Backup and restore parent directories must already exist.")
    try:
        with sqlite3.connect(f"file:{source.as_posix()}?mode=ro", uri=True, timeout=15) as live:
            with sqlite3.connect(str(archive)) as backup:
                live.backup(backup)
                if backup.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise ValueError("Backup database integrity check failed.")
        with sqlite3.connect(f"file:{archive.as_posix()}?mode=ro", uri=True) as backup:
            if backup.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise ValueError("Backup database failed post-close integrity check.")
        # Only copy the consistent backup, never a locked live WAL database.
        import shutil
        with archive.open("rb") as src, restored.open("xb") as dest:
            shutil.copyfileobj(src, dest)
        if digest(archive) != digest(restored):
            raise ValueError("Restored database checksum mismatch.")
        with sqlite3.connect(f"file:{restored.as_posix()}?mode=ro", uri=True) as check:
            if check.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise ValueError("Restored database integrity check failed.")
        return {"status": "SQLITE_RESTORE_VERIFIED", "bytes": archive.stat().st_size,
                "archive_sha256": digest(archive), "restore_sha256": digest(restored),
                "source_preserved": True, "live_account_restore_proven": False}
    except BaseException:
        for candidate in (archive, restored):
            try:
                candidate.unlink(missing_ok=True)
            except OSError:
                pass
        raise

def main() -> None:
    parser=argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--restored", type=Path, required=True)
    args=parser.parse_args()
    print(json.dumps(verified_sqlite_backup(args.source,args.archive,args.restored),indent=2))

if __name__ == "__main__":
    main()

