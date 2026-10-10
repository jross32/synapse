from synapse_daemon.synapse_accounts_client import SynapseAccountsClient


def test_default_uses_cloud(monkeypatch):
    monkeypatch.delenv("SYNAPSE_ACCOUNTS_BASE_URL", raising=False)
    assert SynapseAccountsClient().base_url.startswith("https://accounts-api-production")


def test_old_loopback_override_recovers_cloud(monkeypatch):
    monkeypatch.setenv("SYNAPSE_ACCOUNTS_BASE_URL", "http://127.0.0.1:8788")
    monkeypatch.delenv("SYNAPSE_ALLOW_LOCAL_ACCOUNTS", raising=False)
    assert SynapseAccountsClient().base_url.startswith("https://accounts-api-production")


def test_developer_explicit_local_override(monkeypatch):
    monkeypatch.setenv("SYNAPSE_ACCOUNTS_BASE_URL", "http://localhost:8788")
    monkeypatch.setenv("SYNAPSE_ALLOW_LOCAL_ACCOUNTS", "1")
    assert SynapseAccountsClient().base_url == "http://localhost:8788"


def test_custom_https_endpoint_respected(monkeypatch):
    monkeypatch.setenv("SYNAPSE_ACCOUNTS_BASE_URL", "https://accounts.example.test/")
    assert SynapseAccountsClient().base_url == "https://accounts.example.test"