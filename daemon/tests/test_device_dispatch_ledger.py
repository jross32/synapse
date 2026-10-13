"""Durable two-device dispatch, isolation, retry and idempotency tests."""
import hashlib
import pytest
from synapse_daemon.device_route_policy import RoutePlan
from synapse_daemon.device_dispatch_ledger import DeviceDispatchLedger, DispatchConflict


def plan(account="alice", devices=("laptop", "desktop"), operation="files.copy"):
    return RoutePlan(account, "both", tuple(devices), frozenset({"filesystem"}), operation)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def test_dual_device_submission_and_receipts_survive_restart(tmp_path):
    path = tmp_path / "jobs.sqlite"
    ledger = DeviceDispatchLedger(path)
    first = ledger.submit(plan(), "unique-req", payload_digest=digest(b"payload"))
    assert [x["device_id"] for x in first] == ["desktop", "laptop"]
    assert {x["state"] for x in first} == {"queued"}
    lease = ledger.claim("alice", "unique-req", "laptop", now=1000)
    assert lease
    assert ledger.finish("alice", "unique-req", "laptop", success=True,
                         result_digest=digest(b"done"), lease_token=lease, now=1001)
    resumed = DeviceDispatchLedger(path)
    assert resumed.get("alice", "unique-req")[1]["state"] == "succeeded"
    assert resumed.submit(plan(), "unique-req", payload_digest=digest(b"payload"))[1]["attempts"] == 1


def test_cross_account_cannot_claim_or_read(tmp_path):
    ledger = DeviceDispatchLedger(tmp_path / "jobs.sqlite")
    ledger.submit(plan(), "r1", payload_digest=digest(b"x"))
    assert ledger.get("other", "r1") == ()
    assert not ledger.claim("other", "r1", "laptop")
    assert not ledger.finish("other", "r1", "laptop", success=True, result_digest=digest(b"no"), lease_token="x" * 32)


def test_same_request_id_cannot_change_targets_or_payload(tmp_path):
    ledger = DeviceDispatchLedger(tmp_path / "jobs.sqlite")
    ledger.submit(plan(), "r1", payload_digest=digest(b"x"))
    with pytest.raises(DispatchConflict):
        ledger.submit(plan(devices=("laptop",)), "r1", payload_digest=digest(b"x"))
    with pytest.raises(DispatchConflict):
        ledger.submit(plan(), "r1", payload_digest=digest(b"y"))


def test_claim_only_one_worker_per_active_lease_and_retry_after_expiration(tmp_path):
    ledger = DeviceDispatchLedger(tmp_path / "jobs.sqlite")
    ledger.submit(plan(devices=("desktop",)), "r", payload_digest=digest(b"x"))
    original = ledger.claim("alice", "r", "desktop", now=100, lease_seconds=30)
    assert original
    assert not ledger.claim("alice", "r", "desktop", now=129)
    renewal = ledger.claim("alice", "r", "desktop", now=131)
    assert renewal and renewal != original
    assert not ledger.finish("alice", "r", "desktop", success=True,
                             result_digest=digest(b"old"), lease_token=original, now=132)
    assert ledger.finish("alice", "r", "desktop", success=True,
                         result_digest=digest(b"new"), lease_token=renewal, now=132)
    assert ledger.get("alice", "r")[0]["attempts"] == 2


def test_receipt_is_idempotent_but_conflicting_final_result_fails(tmp_path):
    ledger = DeviceDispatchLedger(tmp_path / "jobs.sqlite")
    ledger.submit(plan(devices=("laptop",)), "r", payload_digest=digest(b"x"))
    assert not ledger.finish("alice", "r", "laptop", success=True, result_digest=digest(b"ok"), lease_token="x" * 32)
    lease = ledger.claim("alice", "r", "laptop")
    assert lease
    assert ledger.finish("alice", "r", "laptop", success=True, result_digest=digest(b"ok"), lease_token=lease)
    assert not ledger.finish("alice", "r", "laptop", success=True, result_digest=digest(b"ok"), lease_token=lease)
    with pytest.raises(DispatchConflict):
        ledger.finish("alice", "r", "laptop", success=False, result_digest=digest(b"error"), lease_token=lease)
    assert not ledger.claim("alice", "r", "laptop", now=999999999999)


def test_rejected_duplicate_targets_and_bad_digest(tmp_path):
    ledger = DeviceDispatchLedger(tmp_path / "jobs.sqlite")
    with pytest.raises(ValueError):
        ledger.submit(plan(devices=("laptop", "laptop")), "r", payload_digest=digest(b"x"))
    ledger.submit(plan(devices=("laptop",)), "r", payload_digest=digest(b"x"))
    lease = ledger.claim("alice", "r", "laptop")
    assert lease
    with pytest.raises(ValueError):
        ledger.finish("alice", "r", "laptop", success=True, result_digest="bad", lease_token=lease)
