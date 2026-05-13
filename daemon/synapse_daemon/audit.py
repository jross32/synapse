"""Audit log helpers (Contract #11).

Every state-changing daemon action writes a row to ``audit_log``. UI surface:
``Settings → Audit``. Rows are never auto-deleted; manual export/truncate only.

For v0.1.1 this module defines the in-memory ``AuditRecord`` shape and a
``audit()`` function that takes a DB connection. Wiring into actual SQLite
storage lands in Milestone B together with ``synapse_daemon.storage``.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Protocol

from pydantic import BaseModel, Field

from .models import AuditSource


class AuditRecord(BaseModel):
    """One row of ``audit_log``."""

    timestamp_utc: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    entity_type: str
    entity_id: str | None = None
    action: str  # 'launch', 'stop', 'rename', 'delete', etc.
    source: AuditSource = AuditSource.AUTO
    result: str = "success"  # 'success' | 'error'
    error_code: str | None = None
    details: dict[str, Any] | None = None


class _DBExecutor(Protocol):
    """Minimal DB shim — accepts any object with an ``execute(sql, params)`` method."""

    def execute(self, sql: str, params: tuple[Any, ...]) -> Any: ...


_INSERT_SQL = (
    "INSERT INTO audit_log "
    "(timestamp_utc, entity_type, entity_id, action, source, result, error_code, details_json) "
    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
)


def audit(db: _DBExecutor, record: AuditRecord) -> None:
    """Persist an audit record. Caller commits.

    Synchronous on purpose: audit must be cheap and inline with the action it
    records. Daemon writes to SQLite in WAL mode so this is non-blocking.
    """

    db.execute(
        _INSERT_SQL,
        (
            record.timestamp_utc.isoformat(),
            record.entity_type,
            record.entity_id,
            record.action,
            record.source.value,
            record.result,
            record.error_code,
            json.dumps(record.details) if record.details else None,
        ),
    )
