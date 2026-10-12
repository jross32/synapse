"""Relay session checks happen after queuing, without blocking running work."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import Mock
import threading
import httpx
from fastapi import FastAPI
from .test_premium_account_release import manager_at
from synapse_daemon import mcp_connector
from synapse_daemon.time_utils import to_iso, utc_now

def test_queued_relay_job_rejected_after_logout_normal_mcp_unchanged(tmp_path, monkeypatch):
    manager, storage, accounts = manager_at(tmp_path)
    manager.sign_in_password(login="release-user", password="test-only")
    stamp = manager.relay_dispatch_stamp()
    app = FastAPI()
    app.state.profile_manager = manager
    app.include_router(mcp_connector.build_mcp_router(storage, SimpleNamespace(), SimpleNamespace(local_token="test-local-only")))
    executor = mcp_connector.McpDispatchExecutor(name="qa-relay", max_workers=1, max_queue=2)
    monkeypatch.setattr(mcp_connector, "_mcp_dispatch_executor", lambda message: ("qa-relay", executor))
    release, reached = threading.Event(), threading.Event()
    def occupy():
        reached.set()
        assert release.wait(8)
    async def scenario():
        blocker = asyncio.create_task(executor.run(occupy, label="qa-existing-work"))
        assert await asyncio.to_thread(reached.wait, 5)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            message = {"jsonrpc":"2.0","id":1,"method":"ping"}
            queued = asyncio.create_task(client.post("/mcp/test-local-only", json=message, headers={"X-Synapse-Relay-Session":stamp}))
            for _ in range(500):
                if executor.snapshot()["queued"] == 1:
                    break
                await asyncio.sleep(0.005)
            assert executor.snapshot()["queued"] == 1
            await asyncio.to_thread(manager.sign_out)
            release.set()
            await blocker
            assert (await queued).json()["error"]["code"] == -32001
            # New requests with the previous epoch fail; ordinary local MCP works.
            assert (await client.post("/mcp/test-local-only", json=message, headers={"X-Synapse-Relay-Session":stamp})).json()["error"]["code"] == -32001
            assert (await client.post("/mcp/test-local-only", json=message)).json()["result"] == {}
            await asyncio.to_thread(manager.sign_in_password, login="release-user", password="test-only")
            new_stamp = manager.relay_dispatch_stamp()
            assert new_stamp != stamp
            assert (await client.post("/mcp/test-local-only", json=message, headers={"X-Synapse-Relay-Session":stamp})).json()["error"]["code"] == -32001
            assert (await client.post("/mcp/test-local-only", json=message, headers={"X-Synapse-Relay-Session":new_stamp})).json()["result"] == {}
            write = {"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"synapse_write_file","arguments":{"path":str(tmp_path/"must-not-exist"),"content":"no"}}}
            response = await client.post("/mcp/test-local-only?mode=read",json=write,headers={"X-Synapse-Relay-Session":new_stamp})
            assert response.json()["result"]["isError"]
            assert not (tmp_path/"must-not-exist").exists()
    try:
        asyncio.run(scenario())
    finally:
        release.set()
        executor.shutdown()
        storage.close()

def test_logout_intent_blocks_admission_before_waiting_for_network_mutex(tmp_path):
    manager, storage, _ = manager_at(tmp_path)
    manager.sign_in_password(login="release-user", password="test-only")
    stamp = manager.relay_dispatch_stamp()
    held, release, intent = threading.Event(), threading.Event(), threading.Event()
    original = manager._invalidate_relay_dispatch
    def invalidate():
        original()
        intent.set()
    manager._invalidate_relay_dispatch = invalidate
    def network_work():
        with manager._account_operation_lock:
            held.set()
            assert release.wait(5)
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            work = pool.submit(network_work)
            assert held.wait(5)
            logout = pool.submit(manager.sign_out)
            assert intent.wait(5)
            assert manager._state_row()["user_id"] is not None
            assert not manager.admit_relay_dispatch(stamp)
            assert not logout.done()
            release.set()
            work.result(timeout=5)
            assert not logout.result(timeout=5).signed_in
    finally:
        release.set()
        storage.close()

def test_logout_clears_local_identity_before_cloud_cleanup_and_never_renews(tmp_path):
    manager, storage, accounts = manager_at(tmp_path)
    manager.sign_in_password(login="release-user",password="test-only")
    credential = storage.data_dir/"relay-device-credential.json"
    credential.write_text("test-only")
    with storage.transaction() as conn:
        conn.execute("UPDATE profile_state SET access_token_expires_at=? WHERE id=1",(to_iso(utc_now()-timedelta(seconds=1)),))
    accounts.refresh = Mock(side_effect=AssertionError("Logout must not renew tokens"))
    revoked, release = threading.Event(), threading.Event()
    def revoke(**kwargs):
        revoked.set()
        assert release.wait(5)
    accounts.revoke_relay_device = revoke
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            logout = pool.submit(manager.sign_out)
            assert revoked.wait(5)
            assert manager._state_row()["user_id"] is None
            assert not credential.exists()
            assert manager.relay_dispatch_stamp() is None
            release.set()
            assert not logout.result(timeout=5).signed_in
        accounts.refresh.assert_not_called()
    finally:
        release.set()
        storage.close()


def test_competing_reauth_cannot_reopen_admission_before_pending_logout_clears_identity(tmp_path):
    manager, storage, _ = manager_at(tmp_path)
    try:
        manager.sign_in_password(login="release-user", password="test-only")
        manager._invalidate_relay_dispatch()
        manager._begin_relay_session()
        assert manager._state_row()["user_id"] is not None
        assert manager.relay_dispatch_stamp() is None
        manager.sign_out()
        manager.sign_in_password(login="release-user", password="test-only")
        assert manager.relay_dispatch_stamp() is not None
    finally:
        storage.close()


def test_successful_account_switch_fences_jobs_captured_while_login_pending(tmp_path):
    from synapse_daemon.synapse_accounts_client import AccountPayload
    manager, storage, accounts = manager_at(tmp_path)
    try:
        manager.sign_in_password(login="release-user", password="test-only")
        manager._begin_relay_session()
        stamp_during_login = manager.relay_dispatch_stamp()
        accounts.account = lambda: AccountPayload(account_id="replacement-user", username="replacement-user", email="replacement@example.com", email_verified=True)
        session = accounts.sign_in()
        manager._store_session_payload(session, establish_relay_session=True)
        assert not manager.admit_relay_dispatch(stamp_during_login)
        stamp_after_login = manager.relay_dispatch_stamp()
        assert stamp_after_login and manager.admit_relay_dispatch(stamp_after_login)
        # Normal same-account token renewal does not invalidate queued jobs.
        manager._store_session_payload(session)
        assert manager.relay_dispatch_stamp() == stamp_after_login
    finally:
        storage.close()
