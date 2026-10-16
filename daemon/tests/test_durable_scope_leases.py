import pytest
from synapse_daemon.durable_scope_leases import DurableScopeLeases
from synapse_daemon.worker_scope_coordination import ScopeConflict

def test_independent_connections_respect_scope_ownership(tmp_path):
    path = tmp_path / "leases.sqlite"
    first = DurableScopeLeases(path)
    second = DurableScopeLeases(path)
    a = first.acquire("repo", "alice", ["daemon"])
    with pytest.raises(ScopeConflict):
        second.acquire("repo", "bob", ["daemon/module.py"])
    b = second.acquire("repo", "bob", ["frontend"])
    assert first.renew(a, "alice")
    assert not first.renew(a, "bob")
    assert second.release(a, "alice")
    assert first.acquire("repo", "charlie", ["daemon/module.py"])
    assert second.release(b, "bob")

def test_invalid_scopes_and_isolated_repos(tmp_path):
    coordinator = DurableScopeLeases(tmp_path / "leases.sqlite")
    with pytest.raises(ValueError):
        coordinator.acquire("repo", "worker", ["../escape"])
    coordinator.acquire("repo-a", "worker", ["daemon"])
    coordinator.acquire("repo-b", "worker", ["daemon"])
