"""Auditable Railway deployment decisions; deliberately never deploys resources."""
from __future__ import annotations

import json
import os
import re
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

STATUSES = {"proposed", "approved", "rejected", "deployed", "review_due", "retired"}
DECISIONS = {"keep", "optimize", "move_local", "retire", "undecided"}
_ID = re.compile(r"^[0-9a-f]{32}$")


def _db(data_dir: Path) -> sqlite3.Connection:
    db = data_dir / "railway-costs" / "decision-journal.sqlite3"
    db.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db, timeout=10)
    conn.execute("PRAGMA busy_timeout=10000")
    conn.execute("""CREATE TABLE IF NOT EXISTS cloud_decisions (
       id TEXT PRIMARY KEY, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
       project TEXT NOT NULL, workload TEXT NOT NULL, reason TEXT NOT NULL,
       placement TEXT NOT NULL, max_estimate_usd REAL, status TEXT NOT NULL,
       review_decision TEXT NOT NULL, reviewer_note TEXT NOT NULL DEFAULT ''
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS decision_events (
       event_id INTEGER PRIMARY KEY AUTOINCREMENT, decision_id TEXT NOT NULL,
       created_at TEXT NOT NULL, from_status TEXT, to_status TEXT NOT NULL,
       note TEXT NOT NULL, actor TEXT NOT NULL
    )""")
    return conn


def _clock() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_proposal(data_dir: Path, *, project: str, workload: str, reason: str,
                    placement: str, max_estimate_usd: float | None = None,
                    actor: str = "owner") -> dict:
    if placement not in {"local", "railway", "hybrid"}:
        raise ValueError("Invalid placement")
    if any(not isinstance(s, str) or not s.strip() or len(s) > 1500
           for s in (project, workload, reason, actor)):
        raise ValueError("Missing/invalid field")
    if max_estimate_usd is not None and (
        isinstance(max_estimate_usd, bool) or not isinstance(max_estimate_usd, (int, float))
        or not 0 <= max_estimate_usd < 1e7):
        raise ValueError("Invalid projected cost")
    import math
    if max_estimate_usd is not None and not math.isfinite(max_estimate_usd):
        raise ValueError("Invalid projected cost")
    ident = uuid.uuid4().hex
    now = _clock()
    with _db(data_dir) as conn:
        conn.execute("INSERT INTO cloud_decisions (id,created_at,updated_at,project,workload,reason,placement,max_estimate_usd,status,review_decision) VALUES (?,?,?,?,?,?,?,?,?,?)",
                     (ident, now, now, project.strip(), workload.strip(), reason.strip(),
                      placement, max_estimate_usd, "proposed", "undecided"))
        conn.execute("INSERT INTO decision_events (decision_id,created_at,from_status,to_status,note,actor) VALUES (?,?,?,?,?,?)",
                     (ident, now, None, "proposed", "Created; no Railway deployment performed", actor.strip()))
    return get_decision(data_dir, ident)


def get_decision(data_dir: Path, ident: str) -> dict:
    if not _ID.fullmatch(ident):
        raise ValueError("Invalid id")
    conn = _db(data_dir)
    try:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM cloud_decisions WHERE id=?", (ident,)).fetchone()
        if not row:
            raise KeyError("Decision not found")
        record = dict(row)
        record["events"] = [dict(r) for r in conn.execute(
            "SELECT created_at, from_status, to_status, note, actor FROM decision_events WHERE decision_id=? ORDER BY event_id",
            (ident,))]
        return record
    finally:
        conn.close()


def list_decisions(data_dir: Path, limit: int = 100) -> list[dict]:
    if not isinstance(limit, int) or not 1 <= limit <= 500:
        raise ValueError("Invalid limit")
    conn = _db(data_dir)
    try:
        conn.row_factory = sqlite3.Row
        return [dict(r) for r in conn.execute("SELECT * FROM cloud_decisions ORDER BY created_at DESC LIMIT ?", (limit,))]
    finally:
        conn.close()


def change_status(data_dir: Path, ident: str, status: str, *, actor: str,
                  note: str = "", decision: str = "undecided") -> dict:
    if not _ID.fullmatch(ident) or status not in STATUSES or decision not in DECISIONS:
        raise ValueError("Invalid transition input")
    if not actor.strip() or len(actor) > 150 or len(note) > 4000:
        raise ValueError("Invalid actor/note")
    transitions = {
        "proposed": {"approved", "rejected"},
        "approved": {"deployed", "rejected"},
        "deployed": {"review_due", "retired"},
        "review_due": {"deployed", "retired"},
        "rejected": set(),
        "retired": set(),
    }
    now = _clock()
    conn = _db(data_dir)
    try:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("SELECT status FROM cloud_decisions WHERE id=?", (ident,)).fetchone()
        if row is None:
            raise KeyError("Decision not found")
        if status not in transitions[row[0]]:
            raise ValueError("Invalid transition")
        conn.execute("UPDATE cloud_decisions SET status=?, updated_at=?, review_decision=?, reviewer_note=? WHERE id=?",
                     (status, now, decision, note, ident))
        conn.execute("INSERT INTO decision_events (decision_id,created_at,from_status,to_status,note,actor) VALUES (?,?,?,?,?,?)",
                     (ident, now, row[0], status, note, actor))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    return get_decision(data_dir, ident)
