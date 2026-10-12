"""Read-only account-plan API tests: no payment credentials or UI required."""
from fastapi.testclient import TestClient

from synapse_accounts.app import create_app
from synapse_accounts.config import AccountsSettings


def test_catalog_is_not_sellable_and_subscription_requires_login(tmp_path):
    settings = AccountsSettings(database_url=f"sqlite:///{tmp_path / 'plans.sqlite'}",
                                public_base_url="http://localhost:8788")
    client = TestClient(create_app(settings))
    catalog = client.get("/v1/plans")
    assert catalog.status_code == 200
    assert [x["id"] for x in catalog.json()["plans"]] == [
        "free", "plus", "pro", "unlimited"
    ]
    assert catalog.json()["paid_checkout_enabled"] is False
    assert client.get("/v1/subscription").status_code == 401


def test_new_account_defaults_to_free(tmp_path):
    settings = AccountsSettings(database_url=f"sqlite:///{tmp_path / 'accounts.sqlite'}",
                                public_base_url="http://localhost:8788")
    client = TestClient(create_app(settings))
    response = client.post("/v1/auth/signup", json={
        "username": "tier_test",
        "email": "tier_test@example.org",
        "password": "test_secure_password_123",
    })
    assert response.status_code == 200
    token = response.json()["access_token"]
    result = client.get("/v1/subscription", headers={"Authorization": f"Bearer {token}"})
    assert result.status_code == 200
    assert result.json()["plan"] == "free"
    assert result.json()["billing_configured"] is False
