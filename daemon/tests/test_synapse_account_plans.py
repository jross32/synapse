from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from synapse_accounts.app import create_app
from synapse_accounts.config import load_settings
from synapse_accounts.db import Account, session_scope
from synapse_accounts.subscriptions import consume_usage, get_account_plan, set_plan_trusted, usage_snapshot


def app_for(tmp_path: Path):
    from dataclasses import replace
    return create_app(replace(load_settings(),
        database_url=f"sqlite:///{(tmp_path / 'plans.sqlite').as_posix()}",
        public_base_url="http://127.0.0.1:8788"))


def signup(client: TestClient, name: str):
    response = client.post("/v1/auth/signup", json={
        "username": name, "email": f"{name}@example.org",
        "password": "test_secure_password_123",
    })
    assert response.status_code == 200, response.text
    return response.json()


def headers(session):
    return {"Authorization": f"Bearer {session['access_token']}"}


def test_catalog_signup_plan_and_protected_routes(tmp_path):
    app = app_for(tmp_path)
    with TestClient(app) as client:
        plans = client.get("/v1/plans")
        assert plans.status_code == 200
        assert [p["id"] for p in plans.json()["plans"]] == ["free", "plus", "pro", "unlimited"]
        assert all(not p["available_for_purchase"] for p in plans.json()["plans"])
        assert client.get("/v1/subscription").status_code == 401
        assert client.get("/v1/subscription/usage").status_code == 401
        a = signup(client, "alice")
        assert client.get("/v1/subscription", headers=headers(a)).json()["plan"] == "free"
        assert client.get("/v1/subscription/usage", headers=headers(a)).json()["metrics"]["preview_actions"]["remaining"] == 3
        assert client.post("/v1/subscription/preview-usage", json={
            "metric": "preview_actions", "units": 1, "event_key": "x"
        }).status_code == 401


def test_usage_idempotency_limits_and_isolation(tmp_path):
    app = app_for(tmp_path)
    with TestClient(app) as client:
        a, b = signup(client, "alice"), signup(client, "bob")
        path = "/v1/subscription/preview-usage"
        payload = {"metric": "preview_actions", "units": 2, "event_key": "first"}
        first = client.post(path, json=payload, headers=headers(a))
        assert first.status_code == 200, first.text
        assert first.json()["usage"]["metrics"]["preview_actions"]["used"] == 2
        duplicate = client.post(path, json=payload, headers=headers(a))
        assert duplicate.status_code == 200
        assert duplicate.json()["duplicate"] is True
        assert client.post(path, json={**payload, "units": 1}, headers=headers(a)).status_code == 409
        assert client.post(path, json={**payload, "event_key": "over"}, headers=headers(a)).status_code == 429
        assert client.get("/v1/subscription/usage", headers=headers(b)).json()["metrics"]["preview_actions"]["used"] == 0
        assert client.post(path, json=payload, headers=headers(b)).status_code == 200
        assert client.get("/v1/subscription/usage", headers=headers(a)).json()["metrics"]["preview_actions"]["used"] == 2
        assert client.post(path, json={**payload, "metric": "other"}, headers=headers(a)).status_code == 422


def test_trusted_upgrades_downgrades_and_suspension(tmp_path):
    app = app_for(tmp_path)
    with TestClient(app) as client:
        a = signup(client, "alice")
        account_id = a["account"]["account_id"]
        factory = app.state.accounts_service.session_factory
        with session_scope(factory) as db:
            with pytest.raises(ValueError):
                set_plan_trusted(db, account_id=account_id, plan_id="pro",
                                 billing_status="active", provider=None)
            set_plan_trusted(db, account_id=account_id, plan_id="plus",
                             billing_status="active", provider="admin")
        assert client.get("/v1/subscription", headers=headers(a)).json()["plan"] == "plus"
        path = "/v1/subscription/preview-usage"
        assert client.post(path, json={"metric":"preview_actions","units":10,"event_key":"plus-1"}, headers=headers(a)).status_code == 200
        with session_scope(factory) as db:
            set_plan_trusted(db, account_id=account_id, plan_id="pro",
                             billing_status="trialing", provider="stripe")
        assert client.get("/v1/subscription", headers=headers(a)).json()["limits"]["preview_actions"] == 300
        with session_scope(factory) as db:
            set_plan_trusted(db, account_id=account_id, plan_id="pro",
                             billing_status="past_due", provider="stripe")
        assert client.get("/v1/subscription", headers=headers(a)).json()["plan"] == "free"
        assert client.post(path, json={"metric":"preview_actions","units":1,"event_key":"suspended"}, headers=headers(a)).status_code == 429
        with session_scope(factory) as db:
            set_plan_trusted(db, account_id=account_id, plan_id="unlimited",
                             billing_status="active", provider="admin")
        assert client.get("/v1/subscription", headers=headers(a)).json()["limits"]["preview_actions"] is None
        with session_scope(factory) as db:
            set_plan_trusted(db, account_id=account_id, plan_id="free",
                             billing_status="inactive")
        assert client.get("/v1/subscription", headers=headers(a)).json()["plan"] == "free"
        assert client.get("/v1/subscription/usage", headers=headers(a)).json()["metrics"]["preview_actions"]["used"] == 10


def test_no_public_upgrade_endpoint(tmp_path):
    with TestClient(app_for(tmp_path)) as client:
        a = signup(client, "alice")
        for path in ("/v1/subscription", "/v1/subscription/upgrade", "/v1/subscription/plan"):
            response = client.post(path, json={"plan": "unlimited"}, headers=headers(a))
            assert response.status_code in (404, 405)
        assert client.get("/v1/subscription", headers=headers(a)).json()["plan"] == "free"
