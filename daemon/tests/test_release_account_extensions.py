"""Release integration of cloud account extensions with isolated SQLite only."""
from tests.test_unified_mcp_relay import _client, _owner, _hosts, _enroll
from synapse_accounts.db import session_scope
from synapse_accounts.subscriptions import set_plan_trusted

def test_extension_schema_routes_and_workspace_isolation(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as client:
        owner = _owner(client, "extensions")
        other = _owner(client, "outsider")
        paths = client.app.openapi()["paths"]
        for path in ["/v1/relay/connector", "/v1/devices/access", "/v1/subscription",
                     "/v1/workspace/projects/{project_id}/notes/{key}"]:
            assert path in paths
        _hosts(client, owner, "laptop")
        _enroll(client, owner, "laptop")
        location = "/v1/workspace/projects/example/locations"
        assert client.put(location, headers=other, json={"device_id": "laptop", "path": "C:/example"}).status_code == 403
        assert client.put(location, headers=owner, json={"device_id": "laptop", "path": "C:/example"}).status_code == 200
        assert client.get(location, headers=other).json()["locations"] == []
        note = "/v1/workspace/projects/example/notes/progress"
        assert client.put(note, headers=owner, json={"content": "first", "expected_version": 0}).status_code == 200
        assert client.put(note, headers=owner, json={"content": "stale", "expected_version": 0}).status_code == 409
        assert client.put(note, headers=owner, json={"content": "second", "expected_version": 1}).json()["version"] == 2
        assert client.get(note, headers=other).status_code == 404

def test_subscription_preview_idempotency_and_trusted_plan_transition(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as client:
        owner = _owner(client, "metering")
        other = _owner(client, "isolated")
        initial = client.get("/v1/subscription", headers=owner).json()
        assert initial["plan"] == "free"
        assert client.get("/v1/plans").json()["paid_checkout_enabled"] is False
        path = "/v1/subscription/preview-usage"
        event = {"metric": "preview_actions", "units": 3, "event_key": "action-one"}
        assert client.post(path, headers=owner, json=event).status_code == 200
        assert client.post(path, headers=owner, json=event).json()["duplicate"] is True
        assert client.post(path, headers=owner, json={**event, "event_key": "action-two"}).status_code == 429
        assert client.get("/v1/subscription/usage", headers=other).json()["metrics"]["preview_actions"]["used"] == 0
        with session_scope(client.app.state.accounts_service.session_factory) as db:
            set_plan_trusted(db, account_id=initial["account_id"], plan_id="pro", billing_status="active", provider="admin")
        assert client.get("/v1/subscription", headers=owner).json()["plan"] == "pro"
        assert client.post(path, headers=owner, json={**event, "event_key": "action-two"}).status_code == 200
        with session_scope(client.app.state.accounts_service.session_factory) as db:
            set_plan_trusted(db, account_id=initial["account_id"], plan_id="pro", billing_status="canceled", provider="admin")
        assert client.get("/v1/subscription", headers=owner).json()["plan"] == "free"
        assert client.put("/v1/subscription", headers=owner, json={"plan": "unlimited"}).status_code == 405
