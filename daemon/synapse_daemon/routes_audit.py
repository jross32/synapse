"""REST routes for the audit log (Contract #11 · v0.1.17).

  GET /api/v1/audit?limit=100&offset=0
      -> the most recent ``limit`` audit_log rows, newest first.

All under ``/api/v1`` — mounted by :func:`synapse_daemon.app.build_app`.
Token-guarded like every other data route.
"""

from __future__ import annotations

import json

from fastapi import APIRouter

from .storage import Storage


def build_audit_router(storage: Storage) -> APIRouter:
    router = APIRouter(prefix="/audit", tags=["audit"])

    @router.get("", response_model=None)
    async def list_entries(limit: int = 100, offset: int = 0) -> dict:
        capped_limit = max(1, min(limit, 1000))
        capped_offset = max(0, offset)

        cursor = storage.conn.execute(
            "SELECT id, timestamp_utc, entity_type, entity_id, action, source, "
            "result, error_code, details_json "
            "FROM audit_log ORDER BY id DESC LIMIT ? OFFSET ?",
            (capped_limit, capped_offset),
        )
        entries: list[dict] = []
        for row in cursor.fetchall():
            details_json = row["details_json"]
            entries.append(
                {
                    "id": row["id"],
                    "timestamp_utc": row["timestamp_utc"],
                    "entity_type": row["entity_type"],
                    "entity_id": row["entity_id"],
                    "action": row["action"],
                    "source": row["source"],
                    "result": row["result"],
                    "error_code": row["error_code"],
                    "details": json.loads(details_json) if details_json else None,
                }
            )

        total = storage.conn.execute("SELECT COUNT(*) AS c FROM audit_log").fetchone()["c"]
        return {
            "entries": entries,
            "total": total,
            "limit": capped_limit,
            "offset": capped_offset,
        }

    return router
