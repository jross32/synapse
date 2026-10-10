import pytest
from synapse_daemon.storage_quotas import Quota, enforce_all


def test_reserved_capacity_counts_towards_limit():
    q = Quota(limit_bytes=100, used_bytes=60, reserved_bytes=30)
    assert q.available_bytes == 10
    enforce_all(10, q)
    with pytest.raises(OverflowError):
        enforce_all(11, q)


def test_project_and_account_both_must_have_space():
    project = Quota(1000, 200)
    account = Quota(400, 350)
    provider = Quota(10000, 0)
    enforce_all(50, project, account, provider)
    with pytest.raises(OverflowError):
        enforce_all(51, project, account, provider)


def test_invalid_quota_and_negative_reservation():
    with pytest.raises(ValueError):
        Quota(1, -1)
    with pytest.raises(ValueError):
        enforce_all(-1, Quota(10, 0))
    with pytest.raises(ValueError):
        enforce_all(1)
    assert Quota(100, 101).summary()["over_quota"] is True
