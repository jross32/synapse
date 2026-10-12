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


def test_state_row_creation_is_race_safe(tmp_path: Path) -> None:
    # Regression: profile_state is a singleton (id=1). A duplicate creation -- from a
    # concurrent caller or a stale read snapshot that missed the row -- must NOT raise
    # "UNIQUE constraint failed: profile_state.id"; the fix uses INSERT OR IGNORE.
    storage = Storage(tmp_path / "data")
    storage.open()
    storage.migrate()
    manager = ProfileManager(storage, accounts_client=_UnreachableAccounts())
    row = manager._state_row()  # creates the singleton
    assert row is not None
    # A second singleton insert (what the racing path does) is a no-op, not an error.
    with storage.transaction() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO profile_state (id, sync_enabled, provider_identities_json, "
            "preferences_json, created_at, updated_at) VALUES (1, 0, '[]', '{}', '', '')"
        )
    assert storage.conn.execute("SELECT COUNT(*) FROM profile_state").fetchone()[0] == 1


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


class _FlakyAccounts:
    """Authenticates once, then the accounts server is unreachable on get_me.

    Mirrors the real freeze bug: a signed-in user whose remote accounts server
    (127.0.0.1:8788) is down. Every profile read used to re-hit get_me with a
    blocking urllib call, freezing the async event loop. The circuit breaker must
    stop re-trying the remote after the first failure.
    """

    def __init__(self) -> None:
        self.get_me_calls = 0

    def public_config(self):  # noqa: ANN201 - test double
        from synapse_daemon.synapse_accounts_client import PublicConfigPayload

        return PublicConfigPayload(available_providers=["native"])

    def sign_in(self, *, login: str, password: str) -> SessionPayload:
        return SessionPayload(
            access_token="access-token",
            refresh_token="refresh-token",
            expires_in=3600,
            account=AccountPayload(
                account_id="user-123",
                username="justin",
                email="justin@example.com",
                email_verified=True,
            ),
        )

    def get_me(self, *, access_token: str):  # noqa: ANN201 - test double
        self.get_me_calls += 1
        raise RuntimeError("connection refused")

    def get_sync_document(self, *, access_token: str):  # noqa: ANN201 - test double
        raise RuntimeError("connection refused")

    def put_sync_document(self, *, access_token: str, document):  # noqa: ANN201 - test double
        raise RuntimeError("connection refused")


def test_remote_circuit_breaker_stops_hammering_a_down_accounts_server(tmp_path: Path) -> None:
    storage = Storage(tmp_path / "data")
    storage.open()
    storage.migrate()
    accounts = _FlakyAccounts()
    manager = ProfileManager(storage, accounts_client=accounts)

    # Sign in so a user_id + fresh access token exist -> reads will attempt the remote.
    manager.sign_in_password(login="justin@example.com", password="hunter42")
    accounts.get_me_calls = 0  # ignore any calls during the sign-in flow
    manager._remote_cooldown_until = 0.0  # close the breaker (sign-in already tripped it)

    # First read attempts the remote (get_me), which fails and trips the breaker.
    manager.list_service_connections()
    # Second read within the cooldown window must serve local state WITHOUT re-hitting
    # the remote -- otherwise a down accounts server blocks the event loop on every poll.
    manager.list_service_connections()

    assert accounts.get_me_calls == 1, (
        "circuit breaker should stop re-calling the remote after the first failure; "
        f"got {accounts.get_me_calls} calls"
    )
    # And the app stays usable: the read still returns connections from local state.
    assert isinstance(manager.list_service_connections(), list)
    assert accounts.get_me_calls == 1  # still no new remote call


class _NoConfigAccounts:
    """Accounts server whose public_config probe always fails (server down)."""

    def __init__(self) -> None:
        self.public_config_calls = 0

    def public_config(self):  # noqa: ANN201 - test double
        self.public_config_calls += 1
        raise RuntimeError("connection refused")


def test_circuit_breaker_also_covers_public_config_probe(tmp_path: Path) -> None:
    # summary() probes the accounts server for available auth providers on every call.
    # When the server is down, that probe (a blocking urllib connect) must be skipped
    # after the first failure -- otherwise every /profile poll pays the full connect
    # timeout, which is what made the app feel frozen even when not signed in.
    storage = Storage(tmp_path / "data")
    storage.open()
    storage.migrate()
    accounts = _NoConfigAccounts()
    manager = ProfileManager(storage, accounts_client=accounts)

    manager.summary()  # probes public_config -> fails -> trips the breaker
    manager.summary()  # breaker open -> no re-probe
    manager.summary()

    assert accounts.public_config_calls == 1, (
        f"public_config should be probed once then short-circuited; got {accounts.public_config_calls}"
    )
    # The app stays usable local-first: still reports the native provider + unreachable backend.
    summary = manager.summary()
    assert "native" in summary.available_auth_providers
    assert summary.account_backend_reachable is False


def test_local_cli_detection_is_cached(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Local CLI/service detection shells out (`where claude`, `gh auth status`, …). It must be cached
    # across profile reads so /profile/service-connections isn't ~1.5s every poll -- but an explicit
    # connect/verify must bypass the cache for a fresh probe.
    import synapse_daemon.profile as profile_mod

    storage = Storage(tmp_path / "data")
    storage.open()
    storage.migrate()
    manager = ProfileManager(storage, accounts_client=_UnreachableAccounts())

    calls = {"n": 0}

    def counting_resolve(cmd: str):  # noqa: ANN202 - test stub
        calls["n"] += 1
        return None  # nothing on PATH -> deterministic + no real subprocess

    monkeypatch.setattr(profile_mod, "resolve_command", counting_resolve)

    manager.list_service_connections()
    first = calls["n"]
    assert first > 0, "first read should actually probe the local CLIs"

    manager.list_service_connections()
    assert calls["n"] == first, "second read within the TTL must hit the detection cache (no re-probe)"

    manager.verify_service(provider="claude-code")
    assert calls["n"] > first, "an explicit verify must bypass the cache and re-probe"


def test_mcp_connection_check_reports_unconfigured_when_signed_out(tmp_path: Path) -> None:
    client, _, _ = _harness(tmp_path)
    with client as c:
        res = c.post("/api/v1/profile/mcp-connections/check")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["local"] == {"ok": False, "status": None, "ms": None, "server_version": None, "error": "not configured"}
    assert body["remote"]["error"] == "not configured"
    assert body["checked_at"]


def test_probe_mcp_reads_server_version(monkeypatch: pytest.MonkeyPatch) -> None:
    import io
    import json as _json

    from synapse_daemon import routes_profile

    class FakeResponse(io.BytesIO):
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    payload = _json.dumps({"jsonrpc": "2.0", "id": 1, "result": {"serverInfo": {"name": "synapse", "version": "0.1.209"}}})
    seen = {}

    def fake_urlopen(req, timeout):
        seen["method"] = req.get_method()
        seen["body"] = _json.loads(req.data)
        return FakeResponse(payload.encode())

    monkeypatch.setattr(routes_profile.urllib.request, "urlopen", fake_urlopen)
    result = routes_profile._probe_mcp("https://synapse.example.com/mcp/secret-token-value-123456")
    assert result["ok"] is True
    assert result["server_version"] == "0.1.209"
    assert seen["method"] == "POST"
    assert seen["body"]["method"] == "initialize"


def test_probe_mcp_never_leaks_token_on_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    import urllib.error

    from synapse_daemon import routes_profile

    token = "secret-token-value-123456"

    def fake_urlopen(req, timeout):
        raise urllib.error.URLError(TimeoutError(f"timed out reaching {req.full_url}"))

    monkeypatch.setattr(routes_profile.urllib.request, "urlopen", fake_urlopen)
    result = routes_profile._probe_mcp(f"https://synapse.example.com/mcp/{token}")
    assert result["ok"] is False
    assert result["error"] == "timed out"
    assert token not in repr(result)


class _StubAccounts:
    def __init__(self, fail: bool = False) -> None:
        self.calls: list[tuple[str, object]] = []
        self.fail = fail

    def create_mcp_connector(self, *, access_token: str) -> dict:
        self.calls.append(("read", access_token))
        if self.fail:
            from synapse_daemon.errors import SynapseError

            raise SynapseError(code="profile.remote_unreachable", message="Could not reach https://x/mcp/secret", status=422)
        return {"url": "https://accounts.example/mcp/" + "A" * 43, "selected_device_id": "host-1"}

    def rotate_mcp_connector(self, *, access_token: str) -> dict:
        self.calls.append(("rotate", access_token))
        return {"url": "https://accounts.example/mcp/" + "B" * 43, "selected_device_id": "host-1"}

    def select_mcp_device(self, *, access_token: str, device_id: str) -> dict:
        self.calls.append(("select", device_id))
        return {"selected_device_id": device_id}


class _StubManager:
    def __init__(self, accounts: _StubAccounts, signed_in: bool = True) -> None:
        self._accounts = accounts
        self._signed_in = signed_in

    def summary(self, refresh_remote: bool = False):
        from types import SimpleNamespace

        return SimpleNamespace(signed_in=self._signed_in)

    def _state_row(self) -> dict:
        return {"current_host_id": "host-1"}

    def _ensure_access_token(self) -> str:
        return "access"


def test_account_connector_reads_selects_and_rotates() -> None:
    from synapse_daemon.routes_profile import _account_connector

    accounts = _StubAccounts()
    manager = _StubManager(accounts)
    read = _account_connector(manager)
    assert read["url"].endswith("A" * 43)
    assert read["selected_device_id"] == read["this_device_id"] == "host-1"
    assert read["error"] is None

    _account_connector(manager, "select")
    assert ("select", "host-1") in accounts.calls

    rotated = _account_connector(manager, "rotate")
    assert rotated["url"].endswith("B" * 43)


def test_account_connector_requires_sign_in_and_hides_errors() -> None:
    from synapse_daemon.routes_profile import _account_connector

    signed_out = _account_connector(_StubManager(_StubAccounts(), signed_in=False))
    assert signed_out["url"] is None and "Sign in" in signed_out["error"]

    failed = _account_connector(_StubManager(_StubAccounts(fail=True)))
    assert failed["url"] is None
    assert failed["error"] == "Couldn't reach Synapse accounts (unreachable)."
    assert "secret" not in repr(failed)
