"""SQLite-backed, cross-process repository scope leases."""
from __future__ import annotations
import sqlite3
import time
import uuid
from pathlib import Path
from .worker_scope_coordination import ScopeConflict, normalize_scope, overlaps

class DurableScopeLeases:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._db() as db:
            db.execute("CREATE TABLE IF NOT EXISTS leases (token TEXT, repo TEXT, worker TEXT, scope TEXT, expires REAL)")
            db.execute("CREATE INDEX IF NOT EXISTS leases_repo ON leases(repo)")

    def _db(self):
        return sqlite3.connect(self.path, timeout=20, isolation_level=None)

    def acquire(self, repo: str, worker: str, scopes: list[str], ttl: float = 300) -> str:
        if not repo or not worker or not scopes or ttl <= 0:
            raise ValueError("repo, worker, scopes and positive ttl required")
        scopes = sorted({normalize_scope(s) for s in scopes})
        token = uuid.uuid4().hex
        now = time.time()
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("DELETE FROM leases WHERE expires <= ?", (now,))
            for (existing,) in db.execute("SELECT scope FROM leases WHERE repo = ?", (repo,)):
                if any(overlaps(existing, scope) for scope in scopes):
                    raise ScopeConflict("overlapping scope already assigned")
            db.executemany("INSERT INTO leases VALUES (?,?,?,?,?)",
                           [(token, repo, worker, scope, now + ttl) for scope in scopes])
            db.commit()
        return token

    def renew(self, token: str, worker: str, ttl: float = 300) -> bool:
        if ttl <= 0:
            raise ValueError("positive ttl required")
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("DELETE FROM leases WHERE expires <= ?", (time.time(),))
            result = db.execute("UPDATE leases SET expires=? WHERE token=? AND worker=?",
                                (time.time() + ttl, token, worker))
            db.commit()
            return result.rowcount > 0

    def release(self, token: str, worker: str) -> bool:
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            result = db.execute("DELETE FROM leases WHERE token=? AND worker=?", (token, worker))
            db.commit()
            return result.rowcount > 0
