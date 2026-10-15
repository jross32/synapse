"""Per-device remote write setting requires account ownership and enrolled host."""
from pathlib import Path

from fastapi.testclient import TestClient
from synapse_accounts.app import create_app
from synapse_accounts.config import AccountsSettings


def _client(tmp_path: Path):
    cfg = AccountsSettings(
        database_url=f"sqlite:///{(tmp_path / 'devices.sqlite').as_posix()}",
        public_base_url="https://accounts.example.test", access_token_ttl_seconds=900,
        refresh_token_ttl_seconds=3600, oauth_state_ttl_seconds=900,
        oauth_handoff_ttl_seconds=300, request_timeout_seconds=8,
        google_client_id=None, google_client_secret=None,
        github_client_id=None, github_client_secret=None)
    return TestClient(create_app(cfg))


def _signup(client, email):
    res = client.post("/v1/auth/signup", json={"username": email.split("@")[0], "email": email,
                       "password": "sufficiently-long-password"})
    assert res.status_code == 200, res.text
    return {"Authorization": "Bearer " + res.json()["access_token"]}


def test_device_toggle_default_on_and_off_and_account_isolation(tmp_path):
    with _client(tmp_path) as client:
        owner = _signup(client, "first@example.com")
        other = _signup(client, "second@example.com")
        sync = client.put("/v1/sync/document", headers=owner, json={"document": {
            "hosts": [{"id": "desktop-one", "name": "Desktop", "updated_at": "2026-10-09T00:00:00Z"}]}})
        assert sync.status_code == 200
        devices = client.get("/v1/devices/access", headers=owner)
        assert devices.status_code == 200
        assert devices.json()["devices"] == [{"device_id": "desktop-one", "remote_write_enabled": True, "enrolled": True}]
        denied = client.put("/v1/devices/desktop-one/access", headers=other,
                            json={"remote_write_enabled": False})
        assert denied.status_code == 404
        turned_off = client.put("/v1/devices/desktop-one/access", headers=owner,
                                json={"remote_write_enabled": False})
        assert turned_off.status_code == 200
        assert turned_off.json()["remote_write_enabled"] is False
        assert client.get("/v1/devices/access", headers=owner).json()["devices"][0]["remote_write_enabled"] is False
        turned_on = client.put("/v1/devices/desktop-one/access", headers=owner,
                               json={"remote_write_enabled": True})
        assert turned_on.status_code == 200
        assert turned_on.json()["remote_write_enabled"] is True


def test_unenrolled_device_cannot_toggle_and_auth_is_required(tmp_path):
    with _client(tmp_path) as client:
        owner = _signup(client, "third@example.com")
        assert client.put("/v1/devices/nonexistent/access", headers=owner,
                          json={"remote_write_enabled": True}).status_code == 404
        assert client.get("/v1/devices/access").status_code == 401
