"""Tests for the daemon-owned Profile hub routes."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from synapse_daemon.app import build_app
from synapse_daemon.profile import ProfileManager
from synapse_daemon.pty_sessions import PtySessionManager
from synapse_daemon.storage import Storage
from synapse_daemon.synapse_accounts_client import (
    AccountPayload,
    LinkedIdentityPayload,
    SessionPayload,
)
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
    assert body["sync_status"] == "local-only"
    assert body["sync_backend"] == "local-only"
    assert body["available_auth_providers"][0] == "native"
    assert body["current_host"]["name"]


class _UnreachableAccounts:
    """Stand-in for a Synapse Accounts client with no backend running."""

    def public_config(self):  # noqa: ANN201 - test double
        raise RuntimeError("connection refused")


class _ReachableAccounts:
    def public_config(self):  # noqa: ANN201 - test double
        from synapse_daemon.synapse_accounts_client import PublicConfigPayload

        return PublicConfigPayload(available_providers=["native", "google"])


def test_summary_flags_unreachable_accounts_backend(tmp_path: Path) -> None:
    storage = Storage(tmp_path / "data")
    storage.open()
    storage.migrate()
    manager = ProfileManager(storage, accounts_client=_UnreachableAccounts())
    summary = manager.summary()
    # Sign-in must be flagged off, but the app stays fully usable local-first.
    assert summary.account_backend_reachable is False
    assert summary.signed_in is False
    assert "native" in summary.available_auth_providers


def test_summary_flags_reachable_accounts_backend(tmp_path: Path) -> None:
    storage = Storage(tmp_path / "data")
    storage.open()
    storage.migrate()
    manager = ProfileManager(storage, accounts_client=_ReachableAccounts())
    summary = manager.summary()
    assert summary.account_backend_reachable is True
    assert "google" in summary.available_auth_providers


def test_profile_config_patch_persists_local_sync_setting(tmp_path: Path) -> None:
    client, _, _ = _harness(tmp_path)
    with client as c:
        res = c.patch(
            "/api/v1/profile",
            json={
                "sync_enabled": False,
            },
        )
        again = c.get("/api/v1/profile")
    assert res.status_code == 200, res.text
    assert res.json()["sync_enabled"] is False
    assert again.json()["sync_enabled"] is False


def test_profile_preferences_patch_round_trips(tmp_path: Path) -> None:
    client, _, _ = _harness(tmp_path)
    with client as c:
        res = c.patch(
            "/api/v1/profile/preferences",
            json={
                "theme": "hacker",
                "sessions_quick_actions_collapsed": False,
                "discover_recent_keys": ["tool:cloudtap"],
            },
        )
        again = c.get("/api/v1/profile/preferences")
    assert res.status_code == 200, res.text
    assert res.json()["theme"] == "hacker"
    assert res.json()["sessions_quick_actions_collapsed"] is False
    assert again.json()["discover_recent_keys"] == ["tool:cloudtap"]


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


def test_profile_sign_in_uses_mocked_accounts_session(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, _, app = _harness(tmp_path)

    def fake_sign_in(*, login: str, password: str) -> SessionPayload:
        assert login == "justin@example.com"
        assert password == "hunter42"
        return SessionPayload(
            access_token="access-token",
            refresh_token="refresh-token",
            expires_in=3600,
            account=AccountPayload(
                account_id="user-123",
                username="justin",
                email="justin@example.com",
                email_verified=True,
                email_verified_at="2026-06-21T00:00:00+00:00",
                display_name="Justin",
                avatar_url=None,
                account_provider="google",
                linked_identities=[
                    LinkedIdentityPayload(
                        provider="google",
                        email="justin@example.com",
                        identity_id="identity-1",
                    )
                ],
            ),
        )

    monkeypatch.setattr(app.state.profile_manager._accounts, "sign_in", fake_sign_in)

    with client as c:
        res = c.post(
            "/api/v1/profile/signin",
            json={"login": "justin@example.com", "password": "hunter42"},
        )
    assert res.status_code == 200, res.text
    assert res.json()["signed_in"] is True
    assert res.json()["account_provider"] == "google"
    assert res.json()["display_name"] == "Justin"
