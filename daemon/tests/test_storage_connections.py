import pytest
from synapse_daemon.storage_connections import Connection, ConnectionRegistry


def identity(name):
    return {"account_id": name, "verified": True}


def test_connection_is_account_bound(tmp_path):
    registry = ConnectionRegistry(tmp_path / "connections.json")
    owner = identity("alice")
    other = identity("bob")
    item = Connection("alice", "google_drive", "drive-1", "pending")
    assert registry.upsert(owner, item)["status"] == "pending"
    assert len(registry.list_for_account(owner)) == 1
    assert registry.list_for_account(other) == []
    assert registry.get(other, "drive-1") is None
    with pytest.raises(PermissionError):
        registry.upsert(other, item)
    with pytest.raises(PermissionError):
        registry.upsert(other, Connection("bob", "icloud", "drive-1", "pending"))


def test_missing_identity_fails_closed(tmp_path):
    registry = ConnectionRegistry(tmp_path / "connections.json")
    for bad in (None, {}, {"account_id": "alice"}, {"account_id": "", "verified": True}):
        with pytest.raises(PermissionError):
            registry.list_for_account(bad)


def test_reopen_persists_metadata_not_secrets(tmp_path):
    path = tmp_path / "connections.json"
    registry = ConnectionRegistry(path)
    registry.upsert(identity("alice"), Connection("alice", "icloud", "icloud-1", "reauth_required"))
    assert ConnectionRegistry(path).get(identity("alice"), "icloud-1")["status"] == "reauth_required"
    assert "token" not in path.read_text()


def test_invalid_provider_rejected(tmp_path):
    registry = ConnectionRegistry(tmp_path / "connections.json")
    with pytest.raises(ValueError):
        registry.upsert(identity("alice"), Connection("alice", "unknown", "other", "connected"))
