"""Tests for the system-level routes (v0.1.35)."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

from fastapi.testclient import TestClient

from synapse_daemon import boot_config
from synapse_daemon.app import build_app
from synapse_daemon.models import EntityStatus, ToolItem, ToolState
from synapse_daemon.time_utils import utc_now
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


def test_network_status_reports_wan_auto_start_on_by_default(tmp_path: Path) -> None:
    client, _ = _harness(tmp_path)
    with client as c:
        body = c.get("/api/v1/system/network").json()
    assert body["wan_auto_start"] is True


def test_patch_wan_auto_start_persists_without_touching_bind_lan(tmp_path: Path) -> None:
    client, storage = _harness(tmp_path)
    with client as c:
        # Toggle ONLY wan_auto_start -- bind_lan must be left untouched.
        res = c.patch("/api/v1/system/network", json={"wan_auto_start": False})
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["wan_auto_start"] is False
        assert body["bind_lan_persisted"] is False  # unchanged
        # Persisted to disk + reflected on GET.
        assert boot_config.load(storage.data_dir).wan_auto_start is False
        assert c.get("/api/v1/system/network").json()["wan_auto_start"] is False
        # Audited under its own action key.
        actions = [r["action"] for r in c.get("/api/v1/audit?limit=10").json()["entries"]]
        assert "network.wan_auto_start.set" in actions


def test_patch_network_both_knobs_at_once(tmp_path: Path) -> None:
    client, storage = _harness(tmp_path)
    with client as c:
        res = c.patch("/api/v1/system/network", json={"bind_lan": True, "wan_auto_start": False})
        assert res.status_code == 200, res.text
        body = res.json()
    cfg = boot_config.load(storage.data_dir)
    assert cfg.bind_lan is True
    assert cfg.wan_auto_start is False
    # Flipping bind_lan on a loopback daemon signals a restart is needed.
    assert body["restart_required"] is True


def test_remote_access_network_carries_wan_auto_start(tmp_path: Path) -> None:
    # PhoneAccessPanel reads the WAN auto-start toggle from the /remote-access aggregate's
    # `network` object -- so RemoteAccessNetwork must carry the field (default on).
    client, _ = _harness(tmp_path)
    with client as c:
        body = c.get("/api/v1/remote-access").json()
    assert body["network"]["wan_auto_start"] is True


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


def test_restart_operation_tracks_stages_and_error_catalog(tmp_path: Path) -> None:
    client, _storage = _harness(tmp_path)
    operation_id = "restart-test-001"
    with client as c:
        empty = c.get("/api/v1/system/restart")
        assert empty.status_code == 200
        assert empty.json()["operation"] is None
        assert "SYN-BOOT-102" in empty.json()["error_catalog"]

        requested = c.post(
            "/api/v1/system/restart",
            json={"operation_id": operation_id, "source": "tray"},
        )
        assert requested.status_code == 202, requested.text
        assert requested.json()["operation"]["status"] == "requested"

        progress = c.post(
            f"/api/v1/system/restart/{operation_id}/stage",
            json={
                "stage": "request",
                "state": "success",
                "detail": "Restart accepted from tray.",
                "source": "tray",
            },
        )
        assert progress.status_code == 200, progress.text
        assert progress.json()["operation"]["status"] == "restarting"
        request_stage = progress.json()["operation"]["stages"][0]
        assert request_stage["stage"] == "request"
        assert request_stage["state"] == "success"

        failed = c.post(
            f"/api/v1/system/restart/{operation_id}/stage",
            json={
                "stage": "daemon",
                "state": "error",
                "detail": "Daemon health timed out.",
                "error_code": "SYN-BOOT-102",
                "error_message": "No health response after 15 seconds.",
            },
        )
        assert failed.status_code == 200, failed.text
        assert failed.json()["operation"]["status"] == "error"
        daemon_stage = failed.json()["operation"]["stages"][3]
        assert daemon_stage["error_code"] == "SYN-BOOT-102"


def test_restart_request_refuses_a_second_live_operation(tmp_path: Path) -> None:
    client, _storage = _harness(tmp_path)
    with client as c:
        first = c.post(
            "/api/v1/system/restart",
            json={"operation_id": "restart-first", "source": "desktop"},
        )
        assert first.status_code == 202
        duplicate = c.post(
            "/api/v1/system/restart",
            json={"operation_id": "restart-second", "source": "desktop"},
        )
    assert duplicate.status_code == 409
    assert duplicate.json()["code"] == "system_restart.conflict"
    assert duplicate.json()["details"]["diagnostic_code"] == "SYN-RST-001"


def test_restart_stage_requires_known_operation(tmp_path: Path) -> None:
    client, _storage = _harness(tmp_path)
    with client as c:
        missing = c.post(
            "/api/v1/system/restart/missing-operation/stage",
            json={
                "stage": "daemon",
                "state": "success",
                "detail": "Healthy.",
            },
        )
    assert missing.status_code == 404


def test_stale_restart_gets_a_stable_diagnostic_code(tmp_path: Path) -> None:
    client, storage = _harness(tmp_path)
    with client as c:
        requested = c.post(
            "/api/v1/system/restart",
            json={"operation_id": "restart-stale", "source": "auto"},
        )
        assert requested.status_code == 202
        storage.conn.execute(
            "UPDATE audit_log SET timestamp_utc = ? WHERE entity_type = 'system_restart'",
            ("2026-01-01T00:00:00+00:00",),
        )
        storage.conn.commit()
        status = c.get("/api/v1/system/restart")

    assert status.status_code == 200
    operation = status.json()["operation"]
    assert operation["status"] == "error"
    assert operation["stages"][0]["state"] == "error"
    assert operation["stages"][0]["error_code"] == "SYN-BOOT-301"


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


def test_remote_access_marks_fresh_cloudtap_probe_failures_as_warming(
    tmp_path: Path, monkeypatch
) -> None:
    client, _ = _harness(tmp_path)
    app = client.app

    async def _fake_verify(public_url: str):
        from synapse_daemon.routes_system import RemoteAccessWanVerification

        return RemoteAccessWanVerification(
            status="error",
            checked_at="2026-06-22T00:00:00+00:00",
            health_url=f"{public_url}/api/v1/health",
            mobile_url=f"{public_url}/mobile",
            health_ok=False,
            mobile_ok=False,
            failure_code="unreachable",
            failure_message=f"Could not reach {public_url}/api/v1/health: getaddrinfo failed",
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
                        "public_url": "https://warming.trycloudflare.com",
                    },
                    created_at=utc_now() - timedelta(seconds=15),
                )
            ],
        )

    monkeypatch.setattr(app.state.tool_registry, "get_state", _fake_state)
    with client as c:
        res = c.get("/api/v1/remote-access")
    assert res.status_code == 200
    body = res.json()
    assert body["wan"]["verification"]["status"] == "warming"
    assert "warming up" in body["wan"]["verification"]["failure_message"]
