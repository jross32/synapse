import pytest
from synapse_daemon.worker_scope_coordination import (
    ScopeConflict, WorkerScopeCoordinator, normalize_scope, overlaps,
)


def test_scope_overlap_and_path_validation():
    assert overlaps("daemon", "daemon/a.py")
    assert not overlaps("daemon/a", "daemon/ab")
    for bad in ("", "../main", "/root", "a//b", "a/./b", "C:/root", "a\\b"):
        with pytest.raises(ValueError):
            normalize_scope(bad)


def test_parallel_nonoverlap_conflict_and_release():
    coordinator = WorkerScopeCoordinator()
    first = coordinator.acquire("worker1", ["daemon/synapse_daemon"])
    second = coordinator.acquire("worker2", ["frontend/src"])
    with pytest.raises(ScopeConflict):
        coordinator.acquire("worker3", ["daemon/synapse_daemon/mcp_connector.py"])
    coordinator.assert_owner(first.token, "worker1", "daemon/synapse_daemon/x.py")
    with pytest.raises(ScopeConflict):
        coordinator.assert_owner(first.token, "worker2", "daemon/synapse_daemon/x.py")
    assert coordinator.release(first.token)
    third = coordinator.acquire("worker3", ["daemon/synapse_daemon/mcp_connector.py"])
    assert third.worker_id == "worker3"
    assert second.token != third.token


def test_expiry_fences_stale_worker_and_renewal():
    clock = [100.]
    coordinator = WorkerScopeCoordinator(clock=lambda: clock[0])
    first = coordinator.acquire("a", ["daemon"], ttl=5)
    clock[0] = 104
    coordinator.renew(first.token, ttl=5)
    clock[0] = 108
    coordinator.assert_owner(first.token, "a", "daemon/x.py")
    clock[0] = 109
    with pytest.raises(ScopeConflict):
        coordinator.assert_owner(first.token, "a", "daemon/x.py")
    with pytest.raises(ScopeConflict):
        coordinator.renew(first.token)
    coordinator.acquire("b", ["daemon"], ttl=10)
