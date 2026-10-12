"""A late relay enrollment must not recreate credentials after sign-out."""
from concurrent.futures import ThreadPoolExecutor, TimeoutError
import threading
from unittest.mock import Mock
import pytest
from .test_premium_account_release import manager_at
from synapse_daemon.outbound_mcp_relay import OutboundMcpRelay

def test_late_enrollment_is_revoked_and_deleted_before_logout_completes(tmp_path):
    manager, storage, accounts = manager_at(tmp_path)
    summary = manager.sign_in_password(login="release-user", password="test-only")
    identity = (summary.user_id, summary.current_host.id)
    agent = OutboundMcpRelay(manager, "test-local-only")
    reached, release, logout_started = threading.Event(), threading.Event(), threading.Event()
    def enroll(**kwargs):
        reached.set()
        assert release.wait(5)
        return {"device_token": "test-enrollment-credential-that-is-long-enough"}
    accounts.enroll_relay_device = enroll
    def logout():
        logout_started.set()
        return manager.sign_out()
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            enrolling = pool.submit(agent._enroll_once, *identity)
            assert reached.wait(5)
            signing_out = pool.submit(logout)
            assert logout_started.wait(5)
            try:
                with pytest.raises(TimeoutError):
                    signing_out.result(timeout=0.1)
            finally:
                release.set()
            enrolling.result(timeout=5)
            assert not signing_out.result(timeout=5).signed_in
        assert not (storage.data_dir / "relay-device-credential.json").exists()
        assert accounts.revoked[-1]["device_id"] == identity[1]
        assert agent._identity() is None
        accounts.enroll_relay_device = Mock()
        with pytest.raises(RuntimeError, match="session changed"):
            agent._enroll_once(*identity)
        accounts.enroll_relay_device.assert_not_called()
    finally:
        release.set()
        storage.close()
