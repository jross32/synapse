"""Tests for the daemon-owned Profile hub routes."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from synapse_daemon.app import build_app
from synapse_daemon.profile import ProfileManager
from synapse_daemon.pty_sessions import PtySessionManager
from synapse_daemon.storage import Storage
from synapse_daemon.ws import EventBus


def _harness(tmp_path: Path):
    storage = Storage(tmp_path / "data")
    storage.open()
    storage.migrate()
    app = build_app(storage, EventBus())
    client = TestClient(app, headers={"X-Synapse-Token": app.state.auth.local_token})
    return client, storage, app


def test_profile_defaults_to_local_first_summary(tmp_path: Path) -> None:
    client, _, _ = _harness(tmp_path)
    with client as c:
        res = c.get("/api/v1/profile")
    assert res.status_code == 200
    body = res.json()
    assert body["signed_in"] is False
    assert body["config_ready"] is False
    assert body["sync_status"] == "config-required"
    assert body["current_host"]["name"]


def test_profile_config_patch_persists_supabase_settings(tmp_path: Path) -> None:
    client, _, _ = _harness(tmp_path)
    with client as c:
        res = c.patch(
            "/api/v1/profile",
            json={
                "supabase_url": "demo.supabase.co",
                "supabase_anon_key": "public-demo-key",
                "sync_enabled": False,
            },
        )
        again = c.get("/api/v1/profile")
    assert res.status_code == 200, res.text
    assert res.json()["config_ready"] is True
    assert res.json()["has_anon_key"] is True
    assert res.json()["sync_enabled"] is False
    assert again.json()["supabase_url"] == "https://demo.supabase.co"


def test_profile_favorites_round_trip_into_catalog_state(tmp_path: Path) -> None:
    client, _, _ = _harness(tmp_path)
    with client as c:
        res = c.post("/api/v1/profile/favorites/tool/cloudtap", json={"favorite": True})
        state = c.get("/api/v1/profile/catalog-state")
    assert res.status_code == 200, res.text
    assert res.json()["favorite"] is True
    items = {item["item_key"]: item for item in state.json()["items"]}
    assert items["tool:cloudtap"]["favorite"] is True
    assert "tool:cloudtap" in state.json()["favorite_keys"]


def test_marketplace_install_updates_profile_catalog_install_history(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, _, _ = _harness(tmp_path)
    with client as c:
        res = c.post("/api/v1/marketplace/install/open-synapse-docs?force=true")
        state = c.get("/api/v1/profile/catalog-state")
    assert res.status_code == 200, res.text
    items = {item["item_key"]: item for item in state.json()["items"]}
    assert items["tool:open-synapse-docs"]["last_installed_at"] is not None
    assert items["tool:open-synapse-docs"]["installed_here"] is True


def test_quick_action_launch_updates_profile_usage_history(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, _, _ = _harness(tmp_path)

    async def fake_spawn(self, *, argv, cwd, env=None, rows=24, cols=80, project_id=None):  # type: ignore[override]
        class _Session:
            session_id = "sid-profile-usage"
            pid = 42
            cwd_value = cwd
            argv_value = argv

            def summary(self):
                class _Summary:
                    session_id = "sid-profile-usage"
                    pid = 42
                    cwd = _Session.cwd_value
                    argv = _Session.argv_value

                return _Summary()

        return _Session()

    monkeypatch.setattr(PtySessionManager, "spawn", fake_spawn)

    with client as c:
        res = c.post("/api/v1/quick-actions/new-mcp-server/launch")
        state = c.get("/api/v1/profile/catalog-state")
    assert res.status_code == 200, res.text
    items = {item["item_key"]: item for item in state.json()["items"]}
    assert items["quick-action:new-mcp-server"]["use_count"] >= 1
    assert items["quick-action:new-mcp-server"]["used_before"] is True


def test_profile_sign_in_uses_mocked_supabase_session(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, _, app = _harness(tmp_path)

    def fake_supabase(self, *, path, anon_key, method, payload=None, access_token=None):
        if path == "/auth/v1/token?grant_type=password":
            return type("Resp", (), {
                "payload": {
                    "access_token": "access-token",
                    "refresh_token": "refresh-token",
                    "expires_in": 3600,
                    "user": {
                        "id": "user-123",
                        "email": "justin@example.com",
                        "app_metadata": {"provider": "github"},
                        "user_metadata": {"display_name": "Justin", "avatar_url": None},
                        "identities": [
                            {
                                "id": "identity-1",
                                "provider": "github",
                                "identity_data": {"email": "justin@example.com"},
                            }
                        ],
                    },
                }
            })()
        if path == "/auth/v1/user":
            return type("Resp", (), {
                "payload": {
                    "id": "user-123",
                    "email": "justin@example.com",
                    "app_metadata": {"provider": "github"},
                    "user_metadata": {"display_name": "Justin", "avatar_url": None},
                    "identities": [
                        {
                            "id": "identity-1",
                            "provider": "github",
                            "identity_data": {"email": "justin@example.com"},
                        }
                    ],
                }
            })()
        raise AssertionError(f"unexpected Supabase path: {path}")

    monkeypatch.setattr(ProfileManager, "_supabase_request", fake_supabase)

    with client as c:
        c.patch(
            "/api/v1/profile",
            json={
                "supabase_url": "https://demo.supabase.co",
                "supabase_anon_key": "public-demo-key",
            },
        )
        res = c.post(
            "/api/v1/profile/signin",
            json={"email": "justin@example.com", "password": "hunter42"},
        )
    assert res.status_code == 200, res.text
    assert res.json()["signed_in"] is True
    assert res.json()["provider"] == "github"
    assert res.json()["display_name"] == "Justin"
