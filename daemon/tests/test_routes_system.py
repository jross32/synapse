"""Tests for the system-level routes (v0.1.35)."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from synapse_daemon import boot_config
from synapse_daemon.app import build_app
from synapse_daemon.models import EntityStatus, ToolItem, ToolState
from synapse_daemon.storage import Storage
from synapse_daemon.ws import EventBus


def _harness(tmp_path: Path):
    storage = Storage(tmp_path / "data")
    storage.open()
    storage.migrate()
    app = build_app(storage, EventBus())
    app.state.bound_host = "127.0.0.1"
    app.state.bound_port = 7878
    app.state.data_dir = storage.data_dir
    client = TestClient(app, headers={"X-Synapse-Token": app.state.auth.local_token})
    return client, storage


def test_network_status_returns_loopback_by_default(tmp_path: Path) -> None:
    client, _ = _harness(tmp_path)
    with client as c:
        res = c.get("/api/v1/system/network")
    assert res.status_code == 200
    body = res.json()
    assert body["bind_lan_persisted"] is False
    assert body["bound_host"] == "127.0.0.1"
    assert body["bound_port"] == 7878
    assert body["loopback_url"] == "http://localhost:7878/mobile"
    # Loopback bind => mobile_urls is empty (no LAN exposure yet).
    assert body["mobile_urls"] == []
    # We're consistent: not bound to LAN and persisted=False => no restart needed.
    assert body["restart_required"] is False


def test_patch_network_persists_bind_lan_and_signals_restart(tmp_path: Path) -> None:
    client, storage = _harness(tmp_path)
    with client as c:
        res = c.patch("/api/v1/system/network", json={"bind_lan": True})
    assert res.status_code == 200
    body = res.json()
    assert body["bind_lan_persisted"] is True
    # Live bind hasn't changed yet -- the daemon still listens on loopback.
    assert body["bound_host"] == "127.0.0.1"
    # And the response tells the user that.
    assert body["restart_required"] is True
    # The file on disk reflects it so a real restart would honour it.
    cfg = boot_config.load(storage.data_dir)
    assert cfg.bind_lan is True


def test_patch_network_writes_audit_row(tmp_path: Path) -> None:
    client, storage = _harness(tmp_path)
    with client as c:
        c.patch("/api/v1/system/network", json={"bind_lan": True})
        audit_res = c.get("/api/v1/audit?limit=10").json()
    actions = [r["action"] for r in audit_res["entries"]]
    assert "network.bind_lan.set" in actions


def test_get_network_after_toggle_reflects_persisted(tmp_path: Path) -> None:
    client, _ = _harness(tmp_path)
    with client as c:
        c.patch("/api/v1/system/network", json={"bind_lan": True})
        body = c.get("/api/v1/system/network").json()
    assert body["bind_lan_persisted"] is True
    assert body["bound_host"] == "127.0.0.1"
    assert body["restart_required"] is True


def test_get_network_requires_auth(tmp_path: Path) -> None:
    storage = Storage(tmp_path / "data")
    storage.open()
    storage.migrate()
    app = build_app(storage, EventBus())
    app.state.bound_host = "127.0.0.1"
    app.state.bound_port = 7878
    unauthed = TestClient(app)
    res = unauthed.get("/api/v1/system/network")
    assert res.status_code == 401


def test_remote_access_reports_pairing_code_and_inactive_wan(tmp_path: Path) -> None:
    client, _ = _harness(tmp_path)
    with client as c:
        code = c.post("/api/v1/pair/code").json()
        res = c.get("/api/v1/remote-access")
    assert res.status_code == 200
    body = res.json()
    assert body["computer_name"]
    assert body["pairing_code"]["active"] is True
    assert body["pairing_code"]["code"] == code["code"]
    assert body["wan"]["verification"]["status"] == "inactive"


def test_remote_access_reports_verified_wan_when_daemon_tunnel_matches_port(
    tmp_path: Path, monkeypatch
) -> None:
    client, storage = _harness(tmp_path)
    app = client.app

    async def _fake_verify(public_url: str):
        from synapse_daemon.routes_system import RemoteAccessWanVerification

        return RemoteAccessWanVerification(
            status="ready",
            checked_at="2026-06-20T00:00:00+00:00",
            health_url=f"{public_url}/api/v1/health",
            mobile_url=f"{public_url}/mobile",
            health_ok=True,
            mobile_ok=True,
        )

    monkeypatch.setattr("synapse_daemon.routes_system._verify_public_tunnel", _fake_verify)

    def _fake_state(_tool_id: str):
        return ToolState(
            tool_id="cloudtap",
            status=EntityStatus.LAUNCHED,
            items=[
                ToolItem(
                    id="t1",
                    label="Synapse",
                    status=EntityStatus.LAUNCHED,
                    result={
                        "local_port": 7878,
                        "public_url": "https://demo-tunnel.trycloudflare.com",
                    },
                )
            ],
        )

    monkeypatch.setattr(app.state.tool_registry, "get_state", _fake_state)
    with client as c:
        res = c.get("/api/v1/remote-access")
    assert res.status_code == 200
    body = res.json()
    assert body["wan"]["active"] is True
    assert body["wan"]["public_url"] == "https://demo-tunnel.trycloudflare.com"
    assert body["wan"]["verification"]["status"] == "ready"


def test_remote_access_reports_wrong_port_when_cloudtap_points_elsewhere(
    tmp_path: Path, monkeypatch
) -> None:
    client, _ = _harness(tmp_path)
    app = client.app

    def _fake_state(_tool_id: str):
        return ToolState(
            tool_id="cloudtap",
            status=EntityStatus.LAUNCHED,
            items=[
                ToolItem(
                    id="t1",
                    label="Other app",
                    status=EntityStatus.LAUNCHED,
                    result={
                        "local_port": 9999,
                        "public_url": "https://other.trycloudflare.com",
                    },
                )
            ],
        )

    monkeypatch.setattr(app.state.tool_registry, "get_state", _fake_state)
    with client as c:
        res = c.get("/api/v1/remote-access")
    assert res.status_code == 200
    body = res.json()
    assert body["wan"]["verification"]["status"] == "error"
    assert body["wan"]["verification"]["failure_code"] == "cloudtap.wrong_port"
