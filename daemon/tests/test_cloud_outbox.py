from __future__ import annotations

from synapse_daemon.cloud_outbox import DurableOutbox

def test_durable_reconnect_and_ack(tmp_path):
    path = tmp_path / "queue.sqlite"
    q = DurableOutbox(path)
    assert q.enqueue("a", "heartbeat", {"device": "pc"}, now=100)
    assert not q.enqueue("a", "heartbeat", {"device": "other"}, now=101)
    assert q.stats() == {"pending": 1, "acknowledged": 0}
    assert q.lease(now=101, duration=30)[0]["payload"]["device"] == "pc"
    assert q.lease(now=110) == []
    q2 = DurableOutbox(path)
    assert q2.lease(now=132)[0]["attempts"] == 2
    assert q2.acknowledge("a", now=133)
    assert not q2.acknowledge("a", now=134)
    assert q2.lease(now=200) == []
    assert q2.stats() == {"pending": 0, "acknowledged": 1}
    assert q2.prune(before=134) == 1

def test_defer_recovery(tmp_path):
    q = DurableOutbox(tmp_path / "queue.sqlite")
    q.enqueue("x", "checkpoint", {"step": 5}, now=10)
    q.lease(now=11)
    assert q.defer("x", delay=25, now=12)
    assert q.lease(now=36) == []
    assert q.lease(now=37)[0]["payload"] == {"step": 5}

def test_reject_invalid_and_duplicate(tmp_path):
    import pytest
    q = DurableOutbox(tmp_path / "queue.sqlite")
    with pytest.raises(ValueError):
        q.enqueue("", "heartbeat", {}, now=0)
    with pytest.raises(ValueError):
        q.enqueue("a", "heartbeat", {"oversized": "x" * 128001}, now=0)
    with pytest.raises(ValueError):
        q.lease(limit=0)
    with pytest.raises(ValueError):
        q.defer("missing", delay=-1)
