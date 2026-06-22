"""Tests for the PTY REST endpoints (v0.1.25 · ADR-0002 Phase A)."""

from __future__ import annotations

import base64
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from synapse_daemon.app import build_app
from synapse_daemon.pty_sessions import PtySession, PtySessionManager
from synapse_daemon.storage import Storage
from synapse_daemon.ws import EventBus

posix_only = pytest.mark.skipif(
    sys.platform == "win32", reason="POSIX PTY only here"
)


def _harness(tmp_path: Path):
    storage = Storage(tmp_path / "data")
    storage.open()
    storage.migrate()
    app = build_app(storage, EventBus())
    client = TestClient(app, headers={"X-Synapse-Token": app.state.auth.local_token})
    return client


@posix_only
def test_post_pty_spawns_session(tmp_path: Path) -> None:
    client = _harness(tmp_path)
    with client as c:
        res = c.post("/api/v1/pty", json={"argv": ["/bin/cat"]})
        assert res.status_code == 201
        body = res.json()
        assert body["argv"][0] == "/bin/cat"
        session_id = body["session_id"]

        # Listed.
        listed = c.get("/api/v1/pty").json()
        assert any(s["session_id"] == session_id for s in listed["sessions"])

        # Input via base64.
        payload = base64.b64encode(b"hello\n").decode()
        wrote = c.post(f"/api/v1/pty/{session_id}/input", json={"data": payload})
        assert wrote.status_code == 200
        assert wrote.json()["bytes"] == 6

        # Resize.
        rs = c.post(f"/api/v1/pty/{session_id}/resize", json={"rows": 50, "cols": 132})
        assert rs.status_code == 200
        assert rs.json()["rows"] == 50

        # Close.
        deleted = c.delete(f"/api/v1/pty/{session_id}")
        assert deleted.status_code == 204


@posix_only
def test_input_requires_data_or_text(tmp_path: Path) -> None:
    client = _harness(tmp_path)
    with client as c:
        body = c.post("/api/v1/pty", json={"argv": ["/bin/cat"]}).json()
        sid = body["session_id"]
        bad = c.post(f"/api/v1/pty/{sid}/input", json={})
        assert bad.status_code == 422
        c.delete(f"/api/v1/pty/{sid}")


def test_post_pty_rejects_unknown_command(tmp_path: Path) -> None:
    client = _harness(tmp_path)
    with client as c:
        res = c.post("/api/v1/pty", json={"argv": ["zzz-does-not-exist-9999"]})
        assert res.status_code == 422
        assert "not found" in res.json()["message"].lower()


def test_get_unknown_session_is_404(tmp_path: Path) -> None:
    client = _harness(tmp_path)
    with client as c:
        assert c.get("/api/v1/pty/nope").status_code == 404


def test_probe_returns_true_for_python(tmp_path: Path) -> None:
    """Python is always on PATH in test environments -- a stable positive case."""

    client = _harness(tmp_path)
    with client as c:
        res = c.get("/api/v1/pty/probe", params={"cmd": sys.executable})
        assert res.status_code == 200
        body = res.json()
        assert body["available"] is True
        assert body["resolved"] is not None


def test_probe_returns_false_for_nonsense(tmp_path: Path) -> None:
    client = _harness(tmp_path)
    with client as c:
        res = c.get("/api/v1/pty/probe", params={"cmd": "zzz-not-real-9999"})
        assert res.status_code == 200
        body = res.json()
        assert body["available"] is False
        assert body["resolved"] is None


def test_probe_uses_runtime_resolution_fallback(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    client = _harness(tmp_path)
    monkeypatch.setattr(
        "synapse_daemon.routes_pty.resolve_command",
        lambda cmd: r"C:\Runtime\codex.exe" if cmd == "codex" else None,
    )
    with client as c:
        res = c.get("/api/v1/pty/probe", params={"cmd": "codex"})
        assert res.status_code == 200
        body = res.json()
        assert body["available"] is True
        assert body["resolved"] == r"C:\Runtime\codex.exe"


@pytest.mark.asyncio
async def test_manager_spawn_uses_runtime_resolution_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    bus = EventBus()
    manager = PtySessionManager(bus)

    async def fake_start(self: PtySession) -> None:
        return None

    monkeypatch.setattr(
        "synapse_daemon.pty_sessions.resolve_command",
        lambda cmd: r"C:\Runtime\codex.exe" if cmd == "codex" else None,
    )
    monkeypatch.setattr(PtySession, "start", fake_start)

    session = await manager.spawn(["codex"])
    assert session.argv[0] == r"C:\Runtime\codex.exe"


def test_pty_requires_auth(tmp_path: Path) -> None:
    storage = Storage(tmp_path / "data")
    storage.open()
    storage.migrate()
    app = build_app(storage, EventBus())
    unauthed = TestClient(app)
    assert unauthed.get("/api/v1/pty").status_code == 401
