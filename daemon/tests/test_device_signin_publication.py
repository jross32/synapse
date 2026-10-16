"""Regression: account sign-in publishes machine identity and presence is throttled."""
from pathlib import Path
from unittest.mock import patch

from synapse_daemon.profile import ProfileManager
from synapse_daemon.storage import Storage
from synapse_daemon.synapse_accounts_client import AccountPayload, SessionPayload


class Accounts:
    def sign_in(self, *, login, password):
        return SessionPayload(
            access_token="access", refresh_token="refresh", expires_in=900,
            account=AccountPayload(account_id="acct", username="test", email="test@example.com",
                                   email_verified=True),
        )

    def public_config(self):
        from synapse_daemon.synapse_accounts_client import PublicConfigPayload
        return PublicConfigPayload(available_providers=["native"])


def harness(tmp_path):
    storage = Storage(tmp_path / "data")
    storage.open()
    storage.migrate()
    return storage, ProfileManager(storage, accounts_client=Accounts())


def test_sign_in_publishes_local_host_after_pull(tmp_path: Path):
    storage, manager = harness(tmp_path)
    order = []
    with patch.object(manager, "_refresh_from_remote", side_effect=lambda **_: order.append("pull")), \
         patch.object(manager, "ensure_current_host", wraps=manager.ensure_current_host) as ensure, \
         patch.object(manager, "_sync_to_remote", side_effect=lambda **_: order.append("push")):
        manager.sign_in_password(login="test", password="pass")
    assert ensure.call_count >= 1
    assert order == ["pull", "push"]
    assert storage.conn.execute("SELECT COUNT(*) FROM profile_hosts").fetchone()[0] == 1
    assert storage.conn.execute("SELECT user_id FROM profile_state").fetchone()[0] == "acct"


def test_host_listing_throttles_account_presence_sync(tmp_path: Path):
    storage, manager = harness(tmp_path)
    manager._store_session_payload(Accounts().sign_in(login="test", password="pass"))
    with patch.object(manager, "_sync_to_remote") as publish:
        first = manager.list_hosts()
        second = manager.list_hosts()
    assert len(first) == len(second) == 1
    assert publish.call_count == 1
