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
    return client, app


def test_watchdog_snapshot_route_is_mounted_and_authenticated(tmp_path: Path, monkeypatch) -> None:
    from synapse_daemon import routes_watchdogs

    expected = {
        "generated_at_epoch": 1.0,
        "counts": {
            "total": 1,
            "healthy": 1,
            "armed": 0,
            "warning": 0,
            "stopped": 0,
            "console_risk": 0,
        },
        "items": [{"id": "guard", "name": "Guard", "health": "healthy"}],
    }
    monkeypatch.setattr(routes_watchdogs, "snapshot_watchdogs", lambda _data_dir, force=False: expected)

    client, app = _harness(tmp_path)
    with client as c:
        response = c.get("/api/v1/system/watchdogs?force=true")
        assert response.status_code == 200
        assert response.json() == expected

    unauthenticated = TestClient(app)
    response = unauthenticated.get("/api/v1/system/watchdogs")
    assert response.status_code == 401


def test_watchdog_log_route_returns_not_found_for_unknown_id(tmp_path: Path, monkeypatch) -> None:
    from synapse_daemon import routes_watchdogs

    def missing(_data_dir: Path, _watchdog_id: str, _lines: int):
        raise KeyError("missing")

    monkeypatch.setattr(routes_watchdogs, "watchdog_log", missing)

    client, _app = _harness(tmp_path)
    with client as c:
        response = c.get("/api/v1/system/watchdogs/missing/log")
    assert response.status_code == 404
    assert response.json()["code"] == "watchdog.not_found"
