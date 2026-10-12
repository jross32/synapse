"""A successful login must recover from a previous account outage immediately."""
import time
import pytest
from .test_premium_account_release import manager_at

@pytest.mark.parametrize("method", ["password", "oauth", "signup"])
def test_successful_login_resumes_sync_after_previous_outage(tmp_path, method):
    manager, storage, accounts = manager_at(tmp_path)
    manager._remote_cooldown_until = time.monotonic() + 60
    manager._account_backend_reachable = False
    # The fake service is reachable now; account authentication proves recovery.
    accounts.exchange_oauth = accounts.sign_in
    accounts.sign_up = accounts.sign_in
    try:
        if method == "password":
            summary = manager.sign_in_password(login="release-user", password="test-only")
        elif method == "oauth":
            summary = manager.complete_oauth(handoff="test-handoff")
        else:
            summary, _ = manager.sign_up_password(username="release-user", email="release@example.com", password="test-only")
        assert summary.signed_in
        assert accounts.saved, "Successful authentication must publish this machine immediately"
        assert any(host["id"] == summary.current_host.id for host in accounts.saved[-1]["hosts"])
        assert summary.account_backend_reachable
    finally:
        storage.close()

