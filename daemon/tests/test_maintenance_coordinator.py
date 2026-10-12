import pytest
from synapse_daemon.maintenance_coordinator import MaintenanceCoordinator, MaintenanceError


def test_maintenance_waits_for_all_workers_and_survives_recreation(tmp_path):
    now = [100.0]
    a = MaintenanceCoordinator(tmp_path, clock=lambda: now[0])
    d = a.prepare([{"id": "worker-1", "capability": "checkpoint"},
                   {"id": "worker-2", "capability": "drain"}])
    assert d["status"] == "preparing"
    with pytest.raises(MaintenanceError):
        a.require_ready(d["id"])
    a.acknowledge(d["id"], "worker-1", "paused", "checkpoint:abc")
    with pytest.raises(MaintenanceError):
        a.acknowledge(d["id"], "worker-1", "paused", "checkpoint:duplicate")
    b = MaintenanceCoordinator(tmp_path, clock=lambda: now[0])
    assert b.inspect()["workers"]["worker-1"]["checkpoint"] == "checkpoint:abc"
    b.acknowledge(d["id"], "worker-2", "drained")
    assert a.require_ready(d["id"])["status"] == "ready"


def test_maintenance_postpones_instead_of_killing(tmp_path):
    now = [100.0]
    a = MaintenanceCoordinator(tmp_path, clock=lambda: now[0])
    d = a.prepare([{"id": "busy", "capability": "drain"}], grace_seconds=5)
    now[0] = 106.0
    assert a.inspect()["status"] == "postponed"
    with pytest.raises(MaintenanceError):
        a.require_ready(d["id"])
    assert a.cancel(d["id"])["status"] == "cancelled"


def test_unsafe_and_non_pausable_workers_block_restart(tmp_path):
    a = MaintenanceCoordinator(tmp_path)
    d = a.prepare([{"id": "external", "capability": "non_pausable"}])
    with pytest.raises(MaintenanceError):
        a.acknowledge(d["id"], "external", "paused", "fake")
    assert a.acknowledge(d["id"], "external", "unsafe")["status"] == "postponed"


def test_invalid_checkpoints_and_duplicate_roster(tmp_path):
    a = MaintenanceCoordinator(tmp_path)
    with pytest.raises(MaintenanceError):
        a.prepare([{"id": "same", "capability": "drain"}, {"id": "same", "capability": "drain"}])
    d = a.prepare([{"id": "id", "capability": "checkpoint"}])
    with pytest.raises(MaintenanceError):
        a.acknowledge(d["id"], "id", "paused")
    with pytest.raises(MaintenanceError):
        a.prepare([])


def test_commit_is_one_shot_and_durable(tmp_path):
    a = MaintenanceCoordinator(tmp_path)
    d = a.prepare([{"id": "w", "capability": "drain"}])
    a.acknowledge(d["id"], "w", "drained")
    committed = a.commit_ready(d["id"])
    assert committed["status"] == "committed"
    assert MaintenanceCoordinator(tmp_path).inspect()["status"] == "committed"
    with pytest.raises(MaintenanceError):
        a.commit_ready(d["id"])
