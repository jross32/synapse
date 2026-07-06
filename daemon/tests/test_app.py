"""Contracts #4, #5, #7 — FastAPI app endpoints."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from synapse_daemon import __version__
from synapse_daemon.app import build_app
from synapse_daemon.errors import SynapseError
from synapse_daemon.storage import Storage
from synapse_daemon.time_utils import to_iso, utc_now
from synapse_daemon.ws import Event, EventBus


def _build(tmp_path: Path, *, raise_server_exceptions: bool = True):
    """Spin up Storage + EventBus + FastAPI app + TestClient."""

    storage = Storage(tmp_path / "data")
    storage.open()
    storage.migrate()
    bus = EventBus()
    app = build_app(storage, bus)
    client = TestClient(app, raise_server_exceptions=raise_server_exceptions)
    return client, app, storage, bus


def _seed_event(bus: EventBus, *, name: str, payload: dict) -> Event:
    """Synchronously inject an event into the bus's ring buffer.

    Used in tests so we don't have to bridge sync test code to the async
    bus.publish() API. Equivalent to publish() minus the subscriber fan-out.
    """

    event = Event(
        id=bus._next_id,
        name=name,
        payload=payload,
        timestamp_utc=to_iso(utc_now()),
    )
    bus._next_id += 1
    bus._buffer.append(event)
    return event


@pytest.fixture
def harness(tmp_path: Path):
    client, app, storage, bus = _build(tmp_path)
    try:
        with client:
            yield client, app, storage, bus
    finally:
        storage.close()


def test_health_returns_contract_shape(harness) -> None:
    c, *_ = harness
    res = c.get("/api/v1/health")
    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is True
    assert body["version"] == __version__
    # Contracts #1–#28 honoured by this daemon build.
    assert body["contracts"] == list(range(1, 29))
    assert "started_at" in body


def test_health_path_is_versioned(harness) -> None:
    c, *_ = harness
    # Unversioned URL must 404 — Contract #7.
    assert c.get("/health").status_code == 404


def test_synapse_error_renders_envelope(harness) -> None:
    c, app, *_ = harness

    @app.get("/api/v1/_boom")
    async def boom() -> None:
        raise SynapseError(
            code="project.not_found",
            message="Project 'x' is missing.",
            status=404,
            retryable=False,
        )

    res = c.get("/api/v1/_boom")
    assert res.status_code == 404
    body = res.json()
    assert body == {
        "code": "project.not_found",
        "message": "Project 'x' is missing.",
        "details": None,
        "retryable": False,
    }


def test_fallback_handler_hides_internals(tmp_path: Path) -> None:
    # Use a non-raising TestClient so the fallback handler actually runs.
    client, app, storage, _ = _build(tmp_path, raise_server_exceptions=False)
    try:
        @app.get("/api/v1/_kaboom")
        async def kaboom() -> None:
            raise RuntimeError("internal detail user must not see")

        with client as c:
            res = c.get("/api/v1/_kaboom")
            assert res.status_code == 500
            body = res.json()
            assert body["code"] == "server.internal"
            assert "internal detail" not in body["message"]
    finally:
        storage.close()


def test_cors_allows_vite_dev_origin(harness) -> None:
    c, *_ = harness
    res = c.options(
        "/api/v1/health",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
        },
    )
    # FastAPI's CORS middleware returns 200 on preflight when origin matches.
    assert res.status_code in (200, 204)
    assert res.headers.get("access-control-allow-origin") == "http://localhost:5173"


def test_websocket_replay_handshake(harness) -> None:
    c, app, storage, bus = harness

    first = _seed_event(bus, name="v1.tick", payload={"i": 1})
    second = _seed_event(bus, name="v1.tick", payload={"i": 2})

    token = app.state.auth.local_token
    with c.websocket_connect("/api/v1/ws") as ws:
        ws.send_json({"type": "resume", "since": 0, "token": token})
        message = ws.receive_json()
        assert message["type"] == "replay"
        replayed_ids = [e["id"] for e in message["events"]]
        assert replayed_ids[-2:] == [first.id, second.id]
        assert message["last_event_id"] == second.id


def test_websocket_replay_window_exceeded(harness) -> None:
    c, app, storage, bus = harness

    _seed_event(bus, name="v1.first", payload={})
    _seed_event(bus, name="v1.second", payload={})
    # Force the buffer's oldest entry to fall off so since=1 is past the window.
    bus._buffer.popleft()
    assert bus.buffer_min_id == 2

    with c.websocket_connect("/api/v1/ws") as ws:
        ws.send_json({"type": "resume", "since": 1, "token": app.state.auth.local_token})
        first = ws.receive_json()
        # Either an error event or a replay envelope marking the window loss.
        assert first.get("type") == "error" or "replay_window_exceeded" in json.dumps(first)


def test_websocket_ping_pong(harness) -> None:
    c, app, *_ = harness
    with c.websocket_connect("/api/v1/ws") as ws:
        # Skip the initial replay envelope.
        ws.send_json({"type": "resume", "since": 0, "token": app.state.auth.local_token})
        _ = ws.receive_json()

        ws.send_json({"type": "ping"})
        reply = ws.receive_json()
        assert reply == {"type": "pong"}


def test_websocket_accepts_slightly_delayed_resume_frame(harness) -> None:
    c, app, *_ = harness
    with c.websocket_connect("/api/v1/ws") as ws:
        time.sleep(1.0)
        ws.send_json({"type": "resume", "since": 0, "token": app.state.auth.local_token})
        message = ws.receive_json()
        assert message["type"] == "replay"


def test_mobile_ui_is_served_without_a_token(harness) -> None:
    """The phone Web UI is open-to-load — a device pairs after the page renders."""

    c, *_ = harness
    res = c.get("/mobile/")  # no X-Synapse-Token
    assert res.status_code == 200
    assert "text/html" in res.headers["content-type"]
    assert "Synapse" in res.text


def test_root_redirects_to_mobile_shell(harness) -> None:
    """A bare daemon URL should open the web shell instead of a JSON 404."""

    c, *_ = harness
    res = c.get("/", follow_redirects=False)
    assert res.status_code == 307
    assert res.headers["location"] == "/mobile"

    head = c.head("/", follow_redirects=False)
    assert head.status_code == 307
    assert head.headers["location"] == "/mobile"
