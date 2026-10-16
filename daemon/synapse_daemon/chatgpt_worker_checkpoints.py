"""Durable checkpoints for browser-driven ChatGPT work items.

Never infer completion from a page being loaded or a response being visible.
Only a validated work-item result with test and commit evidence may complete.
"""
from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from urllib.parse import urlparse


class WorkerCheckpointStore:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS chatgpt_worker_checkpoints (
                work_item TEXT PRIMARY KEY, worker TEXT NOT NULL,
                state TEXT NOT NULL, conversation_url TEXT NOT NULL DEFAULT '',
                evidence TEXT NOT NULL DEFAULT '{}', updated REAL NOT NULL
            )""")

    def _connect(self):
        return sqlite3.connect(self.path, timeout=20)

    def record(self, work_item: str, worker: str, state: str,
               *, conversation_url: str = "", evidence: dict | None = None) -> None:
        if not work_item or not worker:
            raise ValueError("work item and worker required")
        if state not in {"assigned", "sent", "observing", "needs_recovery", "verified", "failed"}:
            raise ValueError("invalid worker state")
        if conversation_url:
            parsed = urlparse(conversation_url)
            if parsed.scheme != "https" or parsed.hostname != "chatgpt.com" or "/c/" not in parsed.path:
                raise ValueError("durable ChatGPT conversation URL required")
        evidence = evidence or {}
        if state == "verified" and not (
            evidence.get("commit") and evidence.get("tests_passed") is True
            and evidence.get("completion_confirmed") is True
        ):
            raise ValueError("cannot verify without commit, passing tests, and completion evidence")
        with self._connect() as db:
            existing = db.execute("SELECT worker, state, conversation_url FROM chatgpt_worker_checkpoints WHERE work_item=?",
                                  (work_item,)).fetchone()
            if existing and existing[0] != worker:
                raise ValueError("work item already belongs to another worker")
            if existing and existing[1] == "verified" and state != "verified":
                raise ValueError("verified work cannot regress")
            if existing and existing[2] and conversation_url and existing[2] != conversation_url:
                raise ValueError("conversation URL changed; explicit reconciliation required")
            url = conversation_url or (existing[2] if existing else "")
            db.execute("""INSERT INTO chatgpt_worker_checkpoints VALUES (?,?,?,?,?,?)
                ON CONFLICT(work_item) DO UPDATE SET state=excluded.state,
                conversation_url=excluded.conversation_url, evidence=excluded.evidence,
                updated=excluded.updated""",
                (work_item, worker, state, url, json.dumps(evidence), time.time()))

    def get(self, work_item: str) -> dict | None:
        with self._connect() as db:
            row = db.execute("SELECT worker,state,conversation_url,evidence,updated FROM chatgpt_worker_checkpoints WHERE work_item=?",
                             (work_item,)).fetchone()
        return None if row is None else dict(worker=row[0], state=row[1],
                                              conversation_url=row[2], evidence=json.loads(row[3]), updated=row[4])

    def pending_recovery(self) -> list[str]:
        with self._connect() as db:
            return [row[0] for row in db.execute(
                "SELECT work_item FROM chatgpt_worker_checkpoints WHERE state IN ('sent','observing','needs_recovery')")]
