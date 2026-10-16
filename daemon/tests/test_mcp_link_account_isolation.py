"""Every Synapse profile gets its own MCP link that only reaches its own computers.

Covers the case the owner cares about most: a second person signs into Synapse
(even on the same physical computer) and must get *their* MCP server, never the
owner's. The cloud half runs the real accounts service; the daemon half checks the
link handed to the profile UI is stamped with the account that owns it.
"""
from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from synapse_accounts.app import create_app
from synapse_accounts.config import AccountsSettings
from synapse_accounts.db import RelayDevice, RelayJob, session_scope
from synapse_daemon.errors import SynapseError
from synapse_daemon.profile import ProfileManager
from synapse_daemon.storage import Storage
from synapse_daemon.synapse_accounts_client import AccountPayload, PublicConfigPayload, SessionPayload

SHARED_PC = "shared-family-pc"


@pytest.fixture()
def cloud(tmp_path, monkeypatch):
    monkeypatch.setenv("SYNAPSE_RELAY_SIGNING_KEY", "test-only-very-long-key-do-not-use-in-production-isolation-01")
    app = create_app(AccountsSettings(
        database_url=f"sqlite:///{(tmp_path / 'isolation.sqlite').as_posix()}",
        public_base_url="https://accounts.example.test",
        access_token_ttl_seconds=900,
        refresh_token_ttl_seconds=3600,
        oauth_state_ttl_seconds=900,
        oauth_handoff_ttl_seconds=300,
        request_timeout_seconds=8,
        google_client_id=None,
        google_client_secret=None,
        github_client_id=None,
        github_client_secret=None,
    ))
    with TestClient(app) as client:
        yield client, app.state.accounts_service.session_factory


def _sign_up(client, username):
    response = client.post("/v1/auth/signup", json={
        "username": username, "email": f"{username}@example.test",
        "password": "unique-long-fixture-passcode",
    })
    assert response.status_code == 200, response.text
    body = response.json()
    return {"Authorization": f"Bearer {body['access_token']}"}, body["account"]["account_id"]


def _publish_hosts(client, owner, *host_ids):
    response = client.put("/v1/sync/document", headers=owner, json={"document": {"hosts": [
        {"id": host_id, "name": host_id, "platform": "windows",
         "last_seen_at": "2026-10-16T12:00:00Z", "updated_at": "2026-10-16T12:00:00Z"}
        for host_id in host_ids]}})
    assert response.status_code == 200, response.text


def _enroll(client, owner, host_id):
    response = client.post(f"/v1/relay/devices/{host_id}/enroll", headers=owner)
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['device_token']}"}


def _mark_online(factory, account_id, host_id):
    with session_scope(factory) as db:
        device = db.scalar(select(RelayDevice).where(
            RelayDevice.account_id == account_id, RelayDevice.device_id == host_id))
        device.last_seen_at = datetime.now(UTC)


def _link_path(client, owner):
    response = client.get("/v1/relay/connector", headers=owner)
    assert response.status_code == 200, response.text
    return urlsplit(response.json()["url"]).path


def _tool(client, path, name, arguments=None):
    return client.post(path, json={"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                                   "params": {"name": name, "arguments": arguments or {}}})


def test_each_profile_gets_its_own_link_and_only_its_own_computers(cloud):
    client, factory = cloud
    justin, justin_id = _sign_up(client, "justin")
    guest, guest_id = _sign_up(client, "guest")
    # Both people have signed into Synapse on the same physical computer, which
    # therefore appears (with the same stable machine id) in both accounts.
    _publish_hosts(client, justin, SHARED_PC, "justin-laptop")
    _publish_hosts(client, guest, SHARED_PC)

    justin_link = _link_path(client, justin)
    guest_link = _link_path(client, guest)
    assert justin_link != guest_link
    assert _link_path(client, justin) == justin_link  # stable per account

    _enroll(client, justin, SHARED_PC)
    _enroll(client, justin, "justin-laptop")
    _enroll(client, guest, SHARED_PC)
    for account_id, host_id in ((justin_id, SHARED_PC), (justin_id, "justin-laptop"), (guest_id, SHARED_PC)):
        _mark_online(factory, account_id, host_id)

    listed = _tool(client, guest_link, "synapse_account_list_devices")
    assert listed.status_code == 200, listed.text
    guest_devices = json.loads(listed.json()["result"]["content"][0]["text"])["devices"]
    assert [d["device_id"] for d in guest_devices] == [SHARED_PC]

    # The guest's link can neither target nor select the owner's laptop.
    assert _tool(client, guest_link, "synapse_account_call_device",
                 {"device_id": "justin-laptop", "tool": "synapse_get_context"}).status_code == 404
    assert _tool(client, guest_link, "synapse_account_select_device",
                 {"device_id": "justin-laptop"}).status_code == 404
    assert client.put("/v1/relay/connector/selection", headers=guest,
                      json={"device_id": "justin-laptop"}).status_code == 404

    justin_listed = _tool(client, justin_link, "synapse_account_list_devices")
    justin_devices = json.loads(justin_listed.json()["result"]["content"][0]["text"])["devices"]
    assert sorted(d["device_id"] for d in justin_devices) == ["justin-laptop", SHARED_PC]


def test_shared_computer_only_runs_jobs_for_the_account_that_sent_them(cloud):
    client, factory = cloud
    justin, justin_id = _sign_up(client, "justin2")
    guest, guest_id = _sign_up(client, "guest2")
    _publish_hosts(client, justin, SHARED_PC)
    _publish_hosts(client, guest, SHARED_PC)
    guest_link = _link_path(client, guest)
    justin_device = _enroll(client, justin, SHARED_PC)
    guest_device = _enroll(client, guest, SHARED_PC)
    _mark_online(factory, guest_id, SHARED_PC)

    payload = {"jsonrpc": "2.0", "id": 9, "method": "tools/call",
               "params": {"name": "synapse_get_context", "arguments": {}}}
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(client.post, guest_link, json=payload)
        # The job is queued under the guest's account only.
        jobs: list = []
        for _ in range(40):
            time.sleep(0.25)
            with session_scope(factory) as db:
                jobs = list(db.scalars(select(RelayJob)))
            if jobs:
                break
        assert [job.account_id for job in jobs] == [guest_id], (
            pending.result(timeout=60).text if pending.done() else "request still pending")

        # The owner's Synapse on that computer (owner credential) cannot see it ...
        with session_scope(factory) as db:
            owner_row = db.scalar(select(RelayDevice).where(
                RelayDevice.account_id == justin_id, RelayDevice.device_id == SHARED_PC))
            from synapse_accounts.relay import claim_job
            assert claim_job(db, owner_row) is None
        # ... while the guest's own Synapse session claims and answers it.
        claimed = client.get(f"/v1/relay/devices/{SHARED_PC}/jobs/next", headers=guest_device).json()
        assert claimed["job_id"]
        answer = {"jsonrpc": "2.0", "id": 9, "result": {"owner": "guest"}}
        assert client.post(f"/v1/relay/devices/{SHARED_PC}/jobs/result", headers=guest_device,
                           json={"job_id": claimed["job_id"], "response": answer}).status_code == 200
        assert pending.result(timeout=20).json() == answer

    # The owner's device credential cannot submit results for the guest's jobs either.
    assert client.post(f"/v1/relay/devices/{SHARED_PC}/jobs/result", headers=justin_device,
                       json={"job_id": claimed["job_id"], "response": answer}).status_code == 404


class _FakeAccounts:
    """Accounts double: signs in a chosen account and serves that account's link."""

    def __init__(self) -> None:
        self.account = ("acct-justin", "justin")
        self.on_fetch = None

    def public_config(self):  # noqa: ANN201 - test double
        return PublicConfigPayload(available_providers=["native"])

    def sign_in(self, *, login: str, password: str) -> SessionPayload:
        account_id, username = self.account
        return SessionPayload(
            access_token=f"access-{account_id}", refresh_token=f"refresh-{account_id}", expires_in=3600,
            account=AccountPayload(account_id=account_id, username=username,
                                   email=f"{username}@example.test", email_verified=True))

    def create_mcp_connector(self, *, access_token: str):  # noqa: ANN201 - test double
        if self.on_fetch:
            self.on_fetch()
        owner = access_token.removeprefix("access-")
        return {"url": f"https://accounts.example.test/mcp/link-for-{owner}", "rotated": False,
                "selected_device_id": None, "note": ""}

    def __getattr__(self, name):  # remote sync calls are irrelevant here
        def unavailable(*args, **kwargs):
            raise RuntimeError("offline in test")
        return unavailable


def _manager(tmp_path: Path, accounts: _FakeAccounts) -> ProfileManager:
    storage = Storage(tmp_path / "data")
    storage.open()
    storage.migrate()
    return ProfileManager(storage, accounts_client=accounts)


def test_profile_link_is_stamped_with_the_signed_in_account(tmp_path):
    accounts = _FakeAccounts()
    manager = _manager(tmp_path, accounts)
    manager.sign_in_password(login="justin", password="fixture-password")
    link = manager.get_account_mcp_link()
    assert link["account_id"] == "acct-justin"
    assert link["username"] == "justin"
    assert link["url"].endswith("link-for-acct-justin")

    manager.sign_out()
    accounts.account = ("acct-guest", "guest")
    manager.sign_in_password(login="guest", password="fixture-password")
    guest_link = manager.get_account_mcp_link()
    assert guest_link["account_id"] == "acct-guest"
    assert guest_link["url"].endswith("link-for-acct-guest")


def test_profile_link_refused_when_account_switches_mid_request(tmp_path):
    accounts = _FakeAccounts()
    manager = _manager(tmp_path, accounts)
    manager.sign_in_password(login="justin", password="fixture-password")

    def switch_account() -> None:
        accounts.on_fetch = None
        manager.sign_out()
        accounts.account = ("acct-guest", "guest")
        manager.sign_in_password(login="guest", password="fixture-password")

    accounts.on_fetch = switch_account
    with pytest.raises(SynapseError):
        manager.get_account_mcp_link()


def test_signed_out_profile_has_no_link(tmp_path):
    manager = _manager(tmp_path, _FakeAccounts())
    with pytest.raises(SynapseError):
        manager.get_account_mcp_link()
