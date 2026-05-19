"""Tests for device auth + pairing (Milestone H · v0.1.11)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from synapse_daemon.app import build_app
from synapse_daemon.auth import AuthManager, ensure_local_token
from synapse_daemon.errors import SynapseError
from synapse_daemon.storage import Storage
from synapse_daemon.ws import EventBus


def _storage(tmp_path: Path, sub: str = "data") -> Storage:
    s = Storage(tmp_path / sub)
    s.open()
    s.migrate()
    return s


def _app(tmp_path: Path):
    storage = _storage(tmp_path)
    app = build_app(storage, EventBus())
    return app, storage


# ── local token ──────────────────────────────────────────────────────────


def test_ensure_local_token_is_stable(tmp_path: Path) -> None:
    data = tmp_path / "data"
    data.mkdir()
    first = ensure_local_token(data)
    second = ensure_local_token(data)
    assert first == second  # persisted, not regenerated
    assert len(first) > 20


def test_verify_accepts_local_token_only(tmp_path: Path) -> None:
    auth = AuthManager(_storage(tmp_path), "the-local-token")
    assert auth.verify("the-local-token") is True
    assert auth.verify("not-the-token") is False
    assert auth.verify(None) is False
    assert auth.verify("") is False


# ── pairing lifecycle ────────────────────────────────────────────────────


def test_redeem_creates_a_working_device_token(tmp_path: Path) -> None:
    auth = AuthManager(_storage(tmp_path), "local")
    code = auth.issue_code()["code"]
    result = auth.redeem(code, "Justin's iPhone")
    assert result["device"]["name"] == "Justin's iPhone"
    # The minted token authenticates.
    assert auth.verify(result["token"]) is True


def test_redeem_wrong_code_is_rejected(tmp_path: Path) -> None:
    auth = AuthManager(_storage(tmp_path), "local")
    auth.issue_code()
    with pytest.raises(SynapseError) as exc:
        auth.redeem("000000", "Phone")
    assert exc.value.status == 422


def test_redeem_without_a_live_code_is_rejected(tmp_path: Path) -> None:
    auth = AuthManager(_storage(tmp_path), "local")
    with pytest.raises(SynapseError):
        auth.redeem("123456", "Phone")


def test_pairing_code_is_single_use(tmp_path: Path) -> None:
    auth = AuthManager(_storage(tmp_path), "local")
    code = auth.issue_code()["code"]
    auth.redeem(code, "First")
    # The same code cannot be redeemed twice.
    with pytest.raises(SynapseError):
        auth.redeem(code, "Second")


def test_revoke_kills_the_device_token(tmp_path: Path) -> None:
    auth = AuthManager(_storage(tmp_path), "local")
    result = auth.redeem(auth.issue_code()["code"], "Phone")
    device_id = result["device"]["id"]
    assert auth.verify(result["token"]) is True

    auth.revoke(device_id)
    assert auth.verify(result["token"]) is False
    assert auth.list_devices() == []


# ── REST surface ─────────────────────────────────────────────────────────


def test_protected_route_401s_without_a_token(tmp_path: Path) -> None:
    app, _ = _app(tmp_path)
    client = TestClient(app)  # 'testclient' host, no token
    res = client.get("/api/v1/projects")
    assert res.status_code == 401
    assert res.json()["code"] == "auth.unauthorized"


def test_health_stays_open(tmp_path: Path) -> None:
    app, _ = _app(tmp_path)
    assert TestClient(app).get("/api/v1/health").status_code == 200


def test_local_token_endpoint_serves_trusted_local(tmp_path: Path) -> None:
    app, _ = _app(tmp_path)
    client = TestClient(app, client=("127.0.0.1", 5555))
    res = client.get("/api/v1/auth/local-token")
    assert res.status_code == 200
    assert res.json()["token"] == app.state.auth.local_token


def test_local_token_endpoint_refused_through_a_proxy(tmp_path: Path) -> None:
    """A tunnelled request is loopback but carries proxy headers — refuse it."""

    app, _ = _app(tmp_path)
    client = TestClient(app, client=("127.0.0.1", 5555))
    res = client.get("/api/v1/auth/local-token", headers={"X-Forwarded-For": "8.8.8.8"})
    assert res.status_code == 403


def test_local_token_endpoint_refused_off_machine(tmp_path: Path) -> None:
    app, _ = _app(tmp_path)
    client = TestClient(app, client=("203.0.113.9", 40000))
    assert client.get("/api/v1/auth/local-token").status_code == 403


def test_pair_code_endpoint_requires_auth(tmp_path: Path) -> None:
    app, _ = _app(tmp_path)
    assert TestClient(app).post("/api/v1/pair/code").status_code == 401


def test_full_pairing_flow_over_rest(tmp_path: Path) -> None:
    app, _ = _app(tmp_path)
    local = app.state.auth.local_token
    desktop = TestClient(app, headers={"X-Synapse-Token": local})

    # Desktop mints a code.
    code = desktop.post("/api/v1/pair/code").json()["code"]

    # A phone with no token redeems it -> gets its own device token.
    phone = TestClient(app)
    paired = phone.post(
        "/api/v1/pair", json={"code": code, "device_name": "Pixel"}
    )
    assert paired.status_code == 200
    device_token = paired.json()["token"]

    # The device token now authenticates a protected route.
    phone_authed = TestClient(app, headers={"X-Synapse-Token": device_token})
    assert phone_authed.get("/api/v1/projects").status_code == 200

    # It shows up in the device list...
    devices = desktop.get("/api/v1/pair/devices").json()["devices"]
    assert [d["name"] for d in devices] == ["Pixel"]

    # ...and revoking it locks the phone back out.
    device_id = devices[0]["id"]
    assert desktop.delete(f"/api/v1/pair/devices/{device_id}").status_code == 204
    assert phone_authed.get("/api/v1/projects").status_code == 401
