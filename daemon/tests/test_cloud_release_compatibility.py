"""Compatibility gates for a rolling cloud/desktop update (no live accounts)."""
from __future__ import annotations

import json
from types import SimpleNamespace

from sqlalchemy import select, update
from sqlalchemy.sql.dml import Update

from daemon.tests.test_synapse_accounts_service import _client
from synapse_accounts.db import Account, SyncDocument, session_scope


def test_legacy_write_preserves_new_cloud_fields_and_other_hosts(tmp_path):
    with _client(tmp_path) as client:
        signup = client.post("/v1/auth/signup", json={
            "username": "legacy", "email": "legacy@example.invalid", "password": "test-password-123"
        })
        headers = {"Authorization": f"Bearer {signup.json()['access_token']}"}
        initial = client.get("/v1/sync/document", headers=headers).json()
        document = {
            "schema": 3, "future_section": {"cloud": "keep"},
            "preferences": {"theme": "dark", "future_setting": True, "updated_at": "2026-10-12"},
            "hosts": [
                {"id": "desktop", "updated_at": "2026-10-12", "future_host_field": True},
                {"id": "laptop", "updated_at": "2026-10-11", "future_host_field": "keep"}
            ],
        }
        newer = client.put("/v1/sync/document", headers=headers,
                          json={"document": document, "expected_revision": initial["revision"]})
        assert newer.status_code == 200
        legacy = client.put("/v1/sync/document", headers=headers, json={"document": {
            "preferences": {"theme": "light", "updated_at": "2026-10-13"},
            "hosts": [{"id": "laptop", "name": "Laptop", "updated_at": "2026-10-13"}],
            "untrusted_unknown": "drop",
        }})
        assert legacy.status_code == 200
        saved = legacy.json()["document"]
        assert saved["schema"] == 3
        assert saved["future_section"] == {"cloud": "keep"}
        assert saved["preferences"]["future_setting"] is True
        assert saved["preferences"]["theme"] == "light"
        assert "untrusted_unknown" not in saved
        hosts = {h["id"]: h for h in saved["hosts"]}
        assert set(hosts) == {"desktop", "laptop"}
        assert hosts["laptop"]["future_host_field"] == "keep"
        stale = client.put("/v1/sync/document", headers=headers,
                           json={"document": {}, "expected_revision": newer.json()["revision"]})
        assert stale.status_code == 409
        assert client.app.version == "0.2.219"


def test_legacy_atomic_retry_reads_concurrent_document(tmp_path, monkeypatch):
    with _client(tmp_path) as client:
        signup = client.post("/v1/auth/signup", json={
            "username": "atomic", "email": "atomic@example.invalid", "password": "test-password-123"
        }).json()
        service = client.app.state.accounts_service
        with session_scope(service.session_factory) as db:
            account = db.get(Account, signup["account"]["account_id"])
            service.get_sync_document(db, account)
        with session_scope(service.session_factory) as db:
            account = db.get(Account, signup["account"]["account_id"])
            real_execute = db.execute
            raced = False

            def execute(statement, *args, **kwargs):
                nonlocal raced
                if isinstance(statement, Update) and statement.table.name == "synced_profile_documents" and not raced:
                    raced = True
                    real_execute(update(SyncDocument).where(SyncDocument.account_id == account.id).values(
                        document_json=json.dumps({"future_section": {"concurrent": True},
                                                  "hosts": [{"id": "desktop"}]})))
                    return SimpleNamespace(rowcount=0)
                return real_execute(statement, *args, **kwargs)

            monkeypatch.setattr(db, "execute", execute)
            saved = service.put_sync_document(db, account, {"hosts": [{"id": "laptop"}]}, None)
            assert raced
            assert saved.document["future_section"] == {"concurrent": True}
            assert {h["id"] for h in saved.document["hosts"]} == {"desktop", "laptop"}


def test_additive_subscription_schema_preserves_existing_accounts(tmp_path):
    from sqlalchemy import create_engine, inspect
    from synapse_accounts.db import Base, build_session_factory
    from synapse_accounts import subscriptions  # registers additive tables

    url = "sqlite:///" + (tmp_path / "existing.sqlite").as_posix()
    engine = create_engine(url)
    subscription_tables = {"account_plans", "subscription_usage_counters", "subscription_usage_events"}
    Base.metadata.create_all(engine, tables=[
        table for table in Base.metadata.sorted_tables if table.name not in subscription_tables
    ])
    from sqlalchemy.orm import sessionmaker
    with session_scope(sessionmaker(bind=engine)) as db:
        db.add(Account(id="existing", username="Existing", username_normalized="existing",
                       email="existing@example.invalid", email_normalized="existing@example.invalid",
                       password_hash="preserved-password"))
    factory = build_session_factory(url)
    with session_scope(factory) as db:
        assert db.get(Account, "existing").password_hash == "preserved-password"
    assert subscription_tables <= set(inspect(factory.kw["bind"]).get_table_names())
    # A second startup must also preserve the existing account.
    with session_scope(build_session_factory(url)) as db:
        assert db.get(Account, "existing").username == "Existing"


