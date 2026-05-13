"""Contract #11 — audit log helper."""

from __future__ import annotations

from typing import Any

from synapse_daemon.audit import AuditRecord, audit
from synapse_daemon.models import AuditSource


class _DbSpy:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[Any, ...]]] = []

    def execute(self, sql: str, params: tuple[Any, ...]) -> Any:
        self.calls.append((sql, params))


def test_audit_writes_one_row() -> None:
    db = _DbSpy()
    rec = AuditRecord(
        entity_type="project",
        entity_id="wbscrper",
        action="launch",
        source=AuditSource.DESKTOP,
        result="success",
    )
    audit(db, rec)
    assert len(db.calls) == 1
    sql, params = db.calls[0]
    assert sql.startswith("INSERT INTO audit_log")
    assert params[1] == "project"
    assert params[2] == "wbscrper"
    assert params[3] == "launch"
    assert params[4] == "desktop"
    assert params[5] == "success"
    assert params[6] is None  # no error_code
    assert params[7] is None  # no details_json


def test_audit_serialises_details_as_json() -> None:
    db = _DbSpy()
    rec = AuditRecord(
        entity_type="tool",
        entity_id="cloudtap",
        action="tunnel",
        source=AuditSource.MOBILE,
        result="error",
        error_code="tunnel.cloudflared_missing",
        details={"attempted_port": 12345},
    )
    audit(db, rec)
    sql, params = db.calls[0]
    assert params[6] == "tunnel.cloudflared_missing"
    assert params[7] is not None
    assert '"attempted_port": 12345' in params[7]
