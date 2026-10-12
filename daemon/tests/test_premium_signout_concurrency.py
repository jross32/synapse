"""Sign-out must remain final when previous account work completes late."""
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from datetime import timedelta
import threading
import pytest
from .test_premium_account_release import manager_at
from synapse_daemon.time_utils import to_iso, utc_now

@pytest.mark.parametrize("operation", ["refresh", "push", "token-renewal"])
def test_signout_waits_for_inflight_account_work_then_clears_identity(tmp_path, operation):
    manager, storage, accounts = manager_at(tmp_path)
    manager.sign_in_password(login="release-user", password="test-only")
    credential = storage.data_dir / "relay-device-credential.json"
    credential.write_text("test-only-encrypted-placeholder")
    reached, release, logout_started = threading.Event(), threading.Event(), threading.Event()
    def pause(original):
        def delayed(**kwargs):
            reached.set()
            assert release.wait(5), "Test operation was not released"
            return original(**kwargs)
        return delayed
    if operation == "refresh":
        accounts.get_me = pause(accounts.get_me)
        invoke = lambda: manager._refresh_from_remote(best_effort=True)
    elif operation == "push":
        accounts.put_sync_document = pause(accounts.put_sync_document)
        invoke = lambda: manager._sync_to_remote(best_effort=True)
    else:
        with storage.transaction() as conn:
            conn.execute("UPDATE profile_state SET access_token_expires_at=? WHERE id=1",
                         (to_iso(utc_now()-timedelta(seconds=1)),))
        accounts.refresh = pause(accounts.sign_in)
        invoke = manager._ensure_access_token
    def logout():
        logout_started.set()
        return manager.sign_out()
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            inflight = pool.submit(invoke)
            assert reached.wait(5)
            signing_out = pool.submit(logout)
            assert logout_started.wait(5)
            try:
                with pytest.raises(TimeoutError):
                    signing_out.result(timeout=0.1)
            finally:
                release.set()
            inflight.result(timeout=5)
            assert not signing_out.result(timeout=5).signed_in
        writes_after_logout = len(accounts.saved)
        manager._refresh_from_remote(best_effort=True)
        manager._sync_to_remote(best_effort=True)
        assert len(accounts.saved) == writes_after_logout
        assert not manager.summary(refresh_remote=False).signed_in
        assert not credential.exists()
        row = manager._state_row()
        assert row["access_token_cipher"] is None
        assert row["refresh_token_cipher"] is None
    finally:
        release.set()
        storage.close()
