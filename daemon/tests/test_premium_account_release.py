"""Release account regressions without contacting real accounts."""
from pathlib import Path
from types import SimpleNamespace
import pytest
from synapse_daemon.profile import ProfileManager
from synapse_daemon.storage import Storage
from synapse_daemon.synapse_accounts_client import SynapseAccountsClient, AccountPayload, SessionPayload, SyncDocumentPayload, PublicConfigPayload

@pytest.mark.parametrize("endpoint", ["http://localhost:8788", "http://127.0.0.1:8788", "http://[::1]:8788"])
def test_retired_loopback_endpoint_migrates_unless_explicit(monkeypatch, endpoint):
    monkeypatch.setenv("SYNAPSE_ACCOUNTS_BASE_URL", endpoint)
    monkeypatch.delenv("SYNAPSE_ALLOW_LOCAL_ACCOUNTS", raising=False)
    assert SynapseAccountsClient().base_url.startswith("https://")
    monkeypatch.setenv("SYNAPSE_ALLOW_LOCAL_ACCOUNTS", "1")
    assert SynapseAccountsClient().base_url == endpoint

class Accounts:
    def __init__(self):
        self.document = {"schema": 2, "future_extension": {"keep": True}}
        self.saved = []
        self.revoked = []
    def public_config(self):
        return PublicConfigPayload(available_providers=["native"])
    def account(self):
        return AccountPayload(account_id="release-user", username="release-user", email="release@example.com", email_verified=True)
    def sign_in(self, **kwargs):
        return SessionPayload(access_token="test-access", refresh_token="test-refresh", expires_in=3600, account=self.account())
    def get_me(self, **kwargs):
        return self.account()
    def get_sync_document(self, **kwargs):
        return SyncDocumentPayload(document=self.document, updated_at="2026-10-12T00:00:00Z", revision="revision-1")
    def put_sync_document(self, *, access_token, document, expected_revision):
        assert expected_revision == "revision-1"
        self.saved.append(document)
        return SyncDocumentPayload(document=document, updated_at="2026-10-12T00:00:00Z", revision="revision-2")
    def revoke_relay_device(self, **kwargs):
        self.revoked.append(kwargs)
    def sign_out(self, **kwargs):
        pass

def manager_at(tmp_path):
    storage = Storage(tmp_path / "data")
    storage.open()
    storage.migrate()
    accounts = Accounts()
    return ProfileManager(storage, accounts_client=accounts), storage, accounts

def test_signin_publishes_machine_and_preserves_future_fields(tmp_path):
    manager, storage, accounts = manager_at(tmp_path)
    result = manager.sign_in_password(login="release-user", password="test-only")
    assert result.signed_in and result.sync_enabled
    assert accounts.saved
    assert accounts.saved[-1]["future_extension"] == {"keep": True}
    assert any(host["id"] == result.current_host.id for host in accounts.saved[-1]["hosts"])
    storage.close()

@pytest.mark.parametrize("cloud_available", [True, False])
def test_signout_removes_local_relay_credential_even_when_cloud_offline(tmp_path, cloud_available):
    manager, storage, accounts = manager_at(tmp_path)
    result = manager.sign_in_password(login="release-user", password="test-only")
    credential = storage.data_dir / "relay-device-credential.json"
    credential.write_text("test-credential")
    if not cloud_available:
        def offline(**kwargs):
            raise RuntimeError("offline")
        accounts.revoke_relay_device = offline
    assert not manager.sign_out().signed_in
    assert not credential.exists()
    if cloud_available:
        assert accounts.revoked[0]["device_id"] == result.current_host.id
    storage.close()
