import pytest
from synapse_daemon.chatgpt_worker_checkpoints import WorkerCheckpointStore

URL = "https://chatgpt.com/g/g-p-project/c/12345"

def test_restart_recovers_durable_conversation(tmp_path):
    db = tmp_path / "worker.sqlite"
    first = WorkerCheckpointStore(db)
    first.record("item", "worker", "sent", conversation_url=URL)
    second = WorkerCheckpointStore(db)
    assert second.get("item")["conversation_url"] == URL
    assert second.pending_recovery() == ["item"]
    second.record("item", "worker", "needs_recovery")
    assert first.get("item")["state"] == "needs_recovery"

def test_completion_requires_real_evidence(tmp_path):
    store = WorkerCheckpointStore(tmp_path / "worker.sqlite")
    store.record("item", "worker", "observing", conversation_url=URL)
    with pytest.raises(ValueError):
        store.record("item", "worker", "verified", evidence={"commit": "abc"})
    store.record("item", "worker", "verified", evidence={
        "commit": "abc", "tests_passed": True, "completion_confirmed": True})
    assert store.pending_recovery() == []
    with pytest.raises(ValueError):
        store.record("item", "worker", "observing")

def test_prevents_worker_and_conversation_takeover(tmp_path):
    store = WorkerCheckpointStore(tmp_path / "worker.sqlite")
    store.record("item", "worker", "sent", conversation_url=URL)
    with pytest.raises(ValueError):
        store.record("item", "other", "sent")
    with pytest.raises(ValueError):
        store.record("item", "worker", "sent", conversation_url="https://chatgpt.com/c/another")
    with pytest.raises(ValueError):
        store.record("item", "worker", "sent", conversation_url="https://example.com/c/x")
