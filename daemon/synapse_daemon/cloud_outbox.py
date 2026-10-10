"""Local durable synchronization outbox for a Railway-backed Synapse control plane.

Only acknowledged events are removed. Local workers never execute remotely supplied
commands from this queue. This is a persistence primitive, not a cloud connection.
"""
from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS cloud_outbox (
  event_id TEXT PRIMARY KEY,
  event_type TEXT NOT NULL,
  payload TEXT NOT NULL,
  created_at REAL NOT NULL,
  available_at REAL NOT NULL,
  leased_until REAL,
  attempts INTEGER NOT NULL DEFAULT 0,
  acknowledged_at REAL
);
CREATE INDEX IF NOT EXISTS idx_cloud_outbox_ready
 ON cloud_outbox(acknowledged_at, available_at, leased_until);
"""

class DurableOutbox:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._db() as db:
            db.executescript(SCHEMA)

    def _db(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path, timeout=15)
        db.execute("PRAGMA busy_timeout=15000")
        db.execute("PRAGMA journal_mode=WAL")
        return db

    def enqueue(self, event_id: str, event_type: str, payload: dict[str, Any], *, now: float | None = None) -> bool:
        if not event_id or len(event_id) > 160 or not event_type or len(event_type) > 100:
            raise ValueError("event identity and type required")
        moment = time.time() if now is None else now
        data = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        if len(data.encode("utf-8")) > 128_000:
            raise ValueError("Event too large")
        with self._db() as db:
            result = db.execute(
                "INSERT OR IGNORE INTO cloud_outbox "
                "(event_id,event_type,payload,created_at,available_at) VALUES (?,?,?,?,?)",
                (event_id, event_type, data, moment, moment))
            return result.rowcount == 1

    def lease(self, *, limit: int = 20, duration: float = 60, now: float | None = None) -> list[dict[str, Any]]:
        if not 1 <= limit <= 100 or not 1 <= duration <= 3600:
            raise ValueError("Invalid lease request")
        moment = time.time() if now is None else now
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            rows = db.execute(
                "SELECT event_id,event_type,payload,attempts FROM cloud_outbox "
                "WHERE acknowledged_at IS NULL AND available_at <= ? "
                "AND (leased_until IS NULL OR leased_until <= ?) "
                "ORDER BY created_at,event_id LIMIT ?",
                (moment, moment, limit)).fetchall()
            for row in rows:
                db.execute(
                    "UPDATE cloud_outbox SET leased_until=?, attempts=attempts+1 WHERE event_id=?",
                    (moment + duration, row[0]))
        return [{"event_id": r[0], "event_type": r[1], "payload": json.loads(r[2]),
                 "attempts": r[3] + 1} for r in rows]

    def acknowledge(self, event_id: str, *, now: float | None = None) -> bool:
        moment = time.time() if now is None else now
        with self._db() as db:
            result = db.execute(
                "UPDATE cloud_outbox SET acknowledged_at=?, leased_until=NULL "
                "WHERE event_id=? AND acknowledged_at IS NULL", (moment, event_id))
            return result.rowcount == 1

    def defer(self, event_id: str, *, delay: float, now: float | None = None) -> bool:
        if delay < 0 or delay > 86400:
            raise ValueError("Invalid retry delay")
        moment = time.time() if now is None else now
        with self._db() as db:
            result = db.execute(
                "UPDATE cloud_outbox SET leased_until=NULL, available_at=? "
                "WHERE event_id=? AND acknowledged_at IS NULL",
                (moment + delay, event_id))
            return result.rowcount == 1

    def stats(self) -> dict[str, int]:
        with self._db() as db:
            pending, acked = db.execute(
                "SELECT COUNT(*) FILTER (WHERE acknowledged_at IS NULL), "
                "COUNT(*) FILTER (WHERE acknowledged_at IS NOT NULL) FROM cloud_outbox").fetchone()
        return {"pending": pending, "acknowledged": acked}

    def prune(self, *, before: float) -> int:
        with self._db() as db:
            result = db.execute(
                "DELETE FROM cloud_outbox WHERE acknowledged_at IS NOT NULL AND acknowledged_at<?",
                (before,))
            return result.rowcount
