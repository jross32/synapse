"""Durable, account-isolated per-device dispatch receipts.

A transport adapter must authenticate the actor and check remote authorization
before using this ledger. This module never executes queued operations.
"""
from __future__ import annotations

import hashlib
import json
import secrets
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

from .device_route_policy import RoutePlan

_STATES = frozenset({"queued", "running", "succeeded", "failed"})
_TERMINAL = frozenset({"succeeded", "failed"})


class DispatchConflict(ValueError):
    pass


class DeviceDispatchLedger:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._db() as db:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS dispatch_jobs(
              account_id TEXT NOT NULL, request_id TEXT NOT NULL,
              fingerprint TEXT NOT NULL, operation TEXT NOT NULL,
              device_id TEXT NOT NULL, state TEXT NOT NULL,
              attempts INTEGER NOT NULL DEFAULT 0,
              lease_deadline REAL, lease_token TEXT, result_digest TEXT,
              updated_at REAL NOT NULL,
              PRIMARY KEY(account_id,request_id,device_id)
            );
            CREATE INDEX IF NOT EXISTS dispatch_device_queue
              ON dispatch_jobs(account_id,device_id,state);
            """)

    @contextmanager
    def _db(self):
        db = sqlite3.connect(self.path, timeout=15, isolation_level=None)
        db.row_factory = sqlite3.Row
        try:
            db.execute("PRAGMA busy_timeout=15000")
            yield db
        finally:
            db.close()

    @staticmethod
    def _fingerprint(plan: RoutePlan, request_id: str, payload_digest: str) -> str:
        if not request_id or len(request_id) > 128 or not payload_digest:
            raise ValueError("Invalid dispatch request identity")
        body = json.dumps({
            "account": plan.account_id, "request": request_id,
            "operation": plan.operation, "selector": plan.selector,
            "devices": plan.device_ids,
            "required": sorted(plan.required_capabilities),
            "payload_digest": payload_digest,
        }, separators=(",", ":"), sort_keys=True)
        return hashlib.sha256(body.encode()).hexdigest()

    def submit(self, plan: RoutePlan, request_id: str, *, payload_digest: str) -> tuple[dict, ...]:
        if not plan.account_id or not plan.operation or not plan.device_ids:
            raise ValueError("Invalid device routing plan")
        if len(plan.device_ids) != len(set(plan.device_ids)):
            raise ValueError("Duplicated target device")
        fingerprint = self._fingerprint(plan, request_id, payload_digest)
        now = time.time()
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                old = list(db.execute(
                    "SELECT fingerprint FROM dispatch_jobs WHERE account_id=? AND request_id=?",
                    (plan.account_id, request_id)))
                if old and any(row["fingerprint"] != fingerprint for row in old):
                    raise DispatchConflict("Request ID already used for different operation or targets")
                for device_id in plan.device_ids:
                    db.execute("""INSERT OR IGNORE INTO dispatch_jobs
                        (account_id,request_id,fingerprint,operation,device_id,state,updated_at)
                        VALUES(?,?,?,?,?,'queued',?)""",
                        (plan.account_id, request_id, fingerprint, plan.operation, device_id, now))
                rows = self._read(db, plan.account_id, request_id)
                if len(rows) != len(plan.device_ids):
                    raise DispatchConflict("Partial or inconsistent existing dispatch request")
                db.execute("COMMIT")
                return rows
            except Exception:
                db.execute("ROLLBACK")
                raise

    @staticmethod
    def _read(db, account_id: str, request_id: str) -> tuple[dict, ...]:
        return tuple(dict(row) for row in db.execute(
            """SELECT account_id,request_id,operation,device_id,state,attempts,
                      lease_deadline,result_digest,updated_at
               FROM dispatch_jobs WHERE account_id=? AND request_id=?
               ORDER BY device_id""", (account_id, request_id)))

    def get(self, account_id: str, request_id: str) -> tuple[dict, ...]:
        with self._db() as db:
            return self._read(db, account_id, request_id)

    def claim(self, account_id: str, request_id: str, device_id: str, *, lease_seconds: int = 120,
              now: float | None = None) -> str | None:
        if not 1 <= lease_seconds <= 3600:
            raise ValueError("Invalid lease duration")
        at = time.time() if now is None else now
        lease_token = secrets.token_urlsafe(24)
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                changed = db.execute(
                    """UPDATE dispatch_jobs SET state='running', attempts=attempts+1,
                        lease_deadline=?,lease_token=?,updated_at=?
                       WHERE account_id=? AND request_id=? AND device_id=?
                         AND (state='queued' OR (state='running' AND lease_deadline<?))""",
                    (at + lease_seconds, lease_token, at, account_id, request_id, device_id, at)).rowcount
                db.execute("COMMIT")
                return lease_token if changed == 1 else None
            except Exception:
                db.execute("ROLLBACK")
                raise

    def finish(self, account_id: str, request_id: str, device_id: str, *,
               success: bool, result_digest: str, lease_token: str, now: float | None = None) -> bool:
        if not lease_token or len(lease_token) < 24:
            raise ValueError("Valid claim lease token required")
        if not isinstance(result_digest, str) or len(result_digest) != 64 or any(
            c not in "0123456789abcdef" for c in result_digest
        ):
            raise ValueError("Valid lowercase SHA256 result digest required")
        at = time.time() if now is None else now
        status = "succeeded" if success else "failed"
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                row = db.execute("""SELECT state,result_digest FROM dispatch_jobs
                    WHERE account_id=? AND request_id=? AND device_id=?""",
                    (account_id, request_id, device_id)).fetchone()
                if row and row["state"] in _TERMINAL:
                    if row["state"] != status or row["result_digest"] != result_digest:
                        raise DispatchConflict("Conflicting final result")
                    db.execute("COMMIT")
                    return False
                changed = db.execute("""UPDATE dispatch_jobs SET state=?,result_digest=?,
                    lease_deadline=NULL,updated_at=?
                    WHERE account_id=? AND request_id=? AND device_id=? AND state='running'
                      AND lease_token=? AND lease_deadline>=?""",
                    (status, result_digest, at, account_id, request_id, device_id, lease_token, at)).rowcount
                db.execute("COMMIT")
                return changed == 1
            except Exception:
                db.execute("ROLLBACK")
                raise
