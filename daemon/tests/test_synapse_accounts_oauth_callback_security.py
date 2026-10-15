"""Cross-device OAuth handoffs must not be redirected to attacker sites."""
from fastapi.testclient import TestClient

from synapse_accounts.app import create_app
from synapse_accounts.config import AccountsSettings


def _app(tmp_path):
    return create_app(AccountsSettings(
        database_url="sqlite:///" + (tmp_path / "oauth.sqlite").as_posix(),
        public_base_url="https://accounts.example.test",
        access_token_ttl_seconds=900, refresh_token_ttl_seconds=3600,
        oauth_state_ttl_seconds=900, oauth_handoff_ttl_seconds=300,
        request_timeout_seconds=8,
        google_client_id="example-client", google_client_secret="example-secret",
        github_client_id=None, github_client_secret=None))


def test_only_synapse_daemon_loopback_callbacks_allowed(tmp_path):
    with TestClient(_app(tmp_path)) as client:
        approved = client.post("/v1/oauth/start", json={
            "provider": "google", "mode": "signin",
            "callback_url": "http://127.0.0.1:7878/api/v1/profile/auth/callback"})
        assert approved.status_code == 200
        assert approved.json()["url"].startswith("https://accounts.google.com/")
        for bad_url in [
            "https://attacker.example/api/v1/profile/auth/callback",
            "http://127.0.0.1:9876/api/v1/profile/auth/callback",
            "http://localhost:7878/redirect",
            "http://localhost:7878/api/v1/profile/auth/callback?next=evil",
        ]:
            rejected = client.post("/v1/oauth/start", json={
                "provider": "google", "mode": "signin", "callback_url": bad_url})
            assert rejected.status_code == 400, bad_url
