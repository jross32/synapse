"""Account-isolated shared workspace metadata; never stores file bytes or secrets."""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from datetime import datetime, timezone


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class WorkspaceCatalog:
    def __init__(self, path: str | Path):
        self.path = str(path)
        with self._db() as db:
            db.execute("CREATE TABLE IF NOT EXISTS workspace_locations (account_id TEXT NOT NULL, project_id TEXT NOT NULL, device_id TEXT NOT NULL, project_path TEXT NOT NULL, revision TEXT NOT NULL DEFAULT '', last_seen TEXT NOT NULL, PRIMARY KEY(account_id, project_id, device_id))")
            db.execute("CREATE TABLE IF NOT EXISTS workspace_notes (account_id TEXT NOT NULL, project_id TEXT NOT NULL, note_key TEXT NOT NULL, content TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 1, updated_at TEXT NOT NULL, PRIMARY KEY(account_id, project_id, note_key))")

    @contextmanager
    def _db(self):
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

    def register(self, account_id: str, project_id: str, device_id: str, project_path: str, revision: str = '') -> None:
        if not all((account_id, project_id, device_id, project_path)):
            raise ValueError('Missing required project location field')
        with self._db() as db:
            db.execute('INSERT INTO workspace_locations VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(account_id,project_id,device_id) DO UPDATE SET project_path=excluded.project_path, revision=excluded.revision, last_seen=excluded.last_seen', (account_id, project_id, device_id, project_path, revision, _now()))

    def locations(self, account_id: str, project_id: str) -> list[dict]:
        with self._db() as db:
            return [dict(r) for r in db.execute('SELECT project_id,device_id,project_path,revision,last_seen FROM workspace_locations WHERE account_id=? AND project_id=? ORDER BY last_seen DESC', (account_id, project_id))]

    def set_note(self, account_id: str, project_id: str, key: str, content: str, expected_version: int | None = None) -> int:
        if not all((account_id, project_id, key)):
            raise ValueError('Missing required note identifier')
        with self._db() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT version FROM workspace_notes WHERE account_id=? AND project_id=? AND note_key=?', (account_id, project_id, key)).fetchone()
            old = row['version'] if row else 0
            if expected_version is not None and old != expected_version:
                raise ValueError('Memory version conflict')
            version = old + 1
            db.execute('INSERT INTO workspace_notes VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(account_id,project_id,note_key) DO UPDATE SET content=excluded.content,version=excluded.version,updated_at=excluded.updated_at', (account_id,project_id,key,content,version,_now()))
            return version

    def get_note(self, account_id: str, project_id: str, key: str) -> dict | None:
        with self._db() as db:
            row = db.execute('SELECT note_key,content,version,updated_at FROM workspace_notes WHERE account_id=? AND project_id=? AND note_key=?', (account_id,project_id,key)).fetchone()
            return dict(row) if row else None


def initialize_catalog(path: str | Path) -> None:
    WorkspaceCatalog(path)

