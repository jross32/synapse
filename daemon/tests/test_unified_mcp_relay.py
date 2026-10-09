"""End-to-end account-wide MCP queue, device permissions and routing (no real user data)."""
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlsplit

from fastapi.testclient import TestClient
from synapse_accounts.app import create_app
from synapse_accounts.config import AccountsSettings


def _client(tmp_path, monkeypatch):
    monkeypatch.setenv("SYNAPSE_RELAY_SIGNING_KEY", "test-only-very-long-key-do-not-use-in-production-123456789abc")
    return TestClient(create_app(AccountsSettings(
        database_url=f"sqlite:///{(tmp_path / 'relay-test.sqlite').as_posix()}",
        public_base_url="https://accounts.example.test",
        access_token_ttl_seconds=900,
        refresh_token_ttl_seconds=3600,
        oauth_state_ttl_seconds=900,
        oauth_handoff_ttl_seconds=300,
        request_timeout_seconds=8,
        google_client_id=None,
        google_client_secret=None,
        github_client_id=None,
        github_client_secret=None,
    )))


def _owner(client, username):
    response = client.post("/v1/auth/signup", json={
        "username": username, "email": f"{username}@example.test",
        "password": "unique-long-fixture-passcode",
    })
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _hosts(client, owner, *names):
    response = client.put("/v1/sync/document", headers=owner, json={"document": {
        "hosts": [{"id": name, "name": name, "platform": "windows",
                   "last_seen_at": "2026-10-09T12:00:00Z",
                   "updated_at": "2026-10-09T12:00:00Z"} for name in names],
    }})
    assert response.status_code == 200, response.text


def _connector(client, owner):
    response = client.get("/v1/relay/connector", headers=owner)
    assert response.status_code == 200, response.text
    return urlsplit(response.json()["url"]).path


def _enroll(client, owner, name):
    response = client.post(f"/v1/relay/devices/{name}/enroll", headers=owner)
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['device_token']}"}


def _select(client, owner, device):
    result = client.put("/v1/relay/connector/selection", headers=owner, json={"device_id": device})
    assert result.status_code == 200, result.text

def _rpc(client, path, device, token_header, mode="full"):
    payload = {"jsonrpc": "2.0", "id": 7, "method": "tools/list"}
    with ThreadPoolExecutor(max_workers=2) as executor:
        pending = executor.submit(client.post, path + f"?device={device}" + ("&mode=read" if mode == "read" else ""), json=payload)
        claimed = client.get(f"/v1/relay/devices/{device}/jobs/next", headers=token_header)
        assert claimed.status_code == 200, claimed.text
        job = claimed.json()
        assert job["job_id"], job
        response = {"jsonrpc": "2.0", "id": 7, "result": {"tools": ["verified"]}}
        accepted = client.post(f"/v1/relay/devices/{device}/jobs/result",
                               headers=token_header, json={"job_id": job["job_id"], "response": response})
        assert accepted.status_code == 200, accepted.text
        result = pending.result(timeout=10)
        assert result.status_code == 200, result.text
        assert result.json() == response
        return job


def test_stable_link_two_machines_default_full_and_switch_off(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as client:
        owner = _owner(client, "owner")
        _hosts(client, owner, "desktop-a", "laptop-b")
        connector = _connector(client, owner)
        assert _connector(client, owner) == connector  # same link on every signed-in PC
        a = _enroll(client, owner, "desktop-a")
        b = _enroll(client, owner, "laptop-b")
        _select(client, owner, "desktop-a")
        first = _rpc(client, connector, "desktop-a", a)
        assert first["mode"] == "full"
        deny_writes = client.put("/v1/devices/laptop-b/access", headers=owner,
                                 json={"remote_write_enabled": False})
        assert deny_writes.status_code == 200
        _select(client, owner, "laptop-b")
        second = _rpc(client, connector, "laptop-b", b)
        assert second["mode"] == "read"
        # Explicit URL read-only mode pins full-capability devices too.
        _select(client, owner, "desktop-a")
        third = _rpc(client, connector, "desktop-a", a, mode="read")
        assert third["mode"] == "read"
        selection = client.put("/v1/relay/connector/selection", headers=owner,
                               json={"device_id": "desktop-a"})
        assert selection.status_code == 200
        assert client.get("/v1/relay/connector", headers=owner).json()["selected_device_id"] == "desktop-a"


def test_connector_rotation_rejects_old_secret_and_is_account_isolated(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as client:
        owner = _owner(client, "one")
        outsider = _owner(client, "two")
        _hosts(client, owner, "personal-pc")
        original_path = _connector(client, owner)
        assert client.post("/v1/relay/devices/personal-pc/enroll", headers=outsider).status_code == 404
        assert client.put("/v1/relay/connector/selection", headers=outsider,
                          json={"device_id": "personal-pc"}).status_code == 404
        replacement = client.post("/v1/relay/connector/rotate", headers=owner)
        assert replacement.status_code == 200
        assert urlsplit(replacement.json()["url"]).path != original_path
        rejected = client.post(original_path, json={"jsonrpc": "2.0", "method": "ping", "id": 1})
        assert rejected.status_code == 401


def test_revocation_stops_device_polling(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as client:
        owner = _owner(client, "revoker")
        _hosts(client, owner, "revoked-pc")
        secret = _enroll(client, owner, "revoked-pc")
        result = client.post("/v1/relay/devices/revoked-pc/revoke", headers=owner)
        assert result.status_code == 200
        polled = client.get("/v1/relay/devices/revoked-pc/jobs/next", headers=secret)
        assert polled.status_code == 401


def test_absent_account_secret_disables_public_connector(tmp_path, monkeypatch):
    monkeypatch.delenv("SYNAPSE_RELAY_SIGNING_KEY", raising=False)
    settings = AccountsSettings(
        database_url=f"sqlite:///{(tmp_path / 'no-key.sqlite').as_posix()}",
        public_base_url="https://accounts.example.test",
        access_token_ttl_seconds=900, refresh_token_ttl_seconds=3600,
        oauth_state_ttl_seconds=900, oauth_handoff_ttl_seconds=300,
        request_timeout_seconds=8, google_client_id=None, google_client_secret=None,
        github_client_id=None, github_client_secret=None,
    )
    with TestClient(create_app(settings)) as client:
        owner = _owner(client, "no-key")
        assert client.get("/v1/relay/connector", headers=owner).status_code == 503
