"""Tests for the audit-log REST endpoint (Contract #11 · v0.1.17)."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from synapse_daemon.app import build_app
from synapse_daemon.audit import AuditRecord, audit
from synapse_daemon.models import AuditSource
from synapse_daemon.storage import Storage
from synapse_daemon.ws import EventBus


def _harness(tmp_path: Path):
    storage = Storage(tmp_path / "data")
    storage.open()
    storage.migrate()
    app = build_app(storage, EventBus())
    client = TestClient(app, headers={"X-Synapse-Token": app.state.auth.local_token})
    return client, storage


def _seed(storage: Storage, count: int) -> None:
    for i in range(count):
        with storage.transaction() as conn:
            audit(
                conn,
                AuditRecord(
                    entity_type="project",
                    entity_id=f"p{i}",
                    action="launch",
                    source=AuditSource.DESKTOP,
                    result="success",
                    details={"i": i},
                ),
            )


def test_list_returns_empty_initially(tmp_path: Path) -> None:
    client, _ = _harness(tmp_path)
    with client as c:
        res = c.get("/api/v1/audit")
        assert res.status_code == 200
        body = res.json()
        assert body["entries"] == []
        assert body["total"] == 0


def test_list_returns_newest_first(tmp_path: Path) -> None:
    client, storage = _harness(tmp_path)
    _seed(storage, 5)
    with client as c:
        body = c.get("/api/v1/audit").json()
        assert body["total"] == 5
        ids = [e["entity_id"] for e in body["entries"]]
        # Newest-first ordering: the LAST seeded row (p4) appears first.
        assert ids == ["p4", "p3", "p2", "p1", "p0"]
        # details_json round-trips back to a dict
        assert body["entries"][0]["details"] == {"i": 4}


def test_limit_and_offset_paginate(tmp_path: Path) -> None:
    client, storage = _harness(tmp_path)
    _seed(storage, 25)
    with client as c:
        page1 = c.get("/api/v1/audit?limit=10").json()
        page2 = c.get("/api/v1/audit?limit=10&offset=10").json()
    assert page1["total"] == 25
    assert len(page1["entries"]) == 10
    assert len(page2["entries"]) == 10
    # No overlap between pages.
    ids1 = {e["id"] for e in page1["entries"]}
    ids2 = {e["id"] for e in page2["entries"]}
    assert ids1.isdisjoint(ids2)


def test_audit_requires_auth(tmp_path: Path) -> None:
    storage = Storage(tmp_path / "data")
    storage.open()
    storage.migrate()
    app = build_app(storage, EventBus())
    unauthed = TestClient(app)  # no token header
    res = unauthed.get("/api/v1/audit")
    assert res.status_code == 401
