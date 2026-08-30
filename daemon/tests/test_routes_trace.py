from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from synapse_daemon.app import build_app
from synapse_daemon.storage import Storage
from synapse_daemon.ws import EventBus


def _harness(tmp_path: Path):
    storage = Storage(tmp_path / "data")
    storage.open()
    storage.migrate()
    app = build_app(storage, EventBus())
    app.state.bound_host = "127.0.0.1"
    app.state.bound_port = 7878
    client = TestClient(app, headers={"X-Synapse-Token": app.state.auth.local_token})
    return client, storage, app


def test_trace_routes_record_list_and_analyze(tmp_path: Path) -> None:
    client, _storage, _app = _harness(tmp_path)

    with client as c:
        created = c.post(
            "/api/v1/trace/events",
            json={
                "source": "operator",
                "category": "note",
                "action": "verify",
                "status": "info",
                "summary": "Trace route proof",
                "details": {"password": "do-not-store", "safe": "ok"},
            },
        )
        assert created.status_code == 201, created.text

        listed = c.get("/api/v1/trace/events?sync_runtime=false")
        assert listed.status_code == 200, listed.text
        items = listed.json()["items"]
        assert items[0]["summary"] == "Trace route proof"
        assert items[0]["details"]["password"] == "[REDACTED]"
        assert items[0]["details"]["safe"] == "ok"

        analyzed = c.get("/api/v1/trace/analysis?sync_runtime=false&window_hours=24")
        assert analyzed.status_code == 200, analyzed.text
        assert analyzed.json()["totals"]["events"] >= 1


def test_trace_routes_require_auth(tmp_path: Path) -> None:
    _client, _storage, app = _harness(tmp_path)
    unauthed = TestClient(app)

    assert unauthed.get("/api/v1/trace/events?sync_runtime=false").status_code == 401
    assert unauthed.get("/api/v1/trace/analysis?sync_runtime=false").status_code == 401
    assert (
        unauthed.post(
            "/api/v1/trace/events",
            json={"summary": "nope"},
        ).status_code
        == 401
    )
