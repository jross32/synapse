"""Cloud account sync must preserve both computers and never accept secrets."""
from synapse_accounts.sync_merge import merge_documents


def _host(key, stamp):
    return {"id": key, "name": key, "platform": "windows", "updated_at": stamp, "current_host": True}


def test_two_devices_are_preserved_when_each_pushes_its_local_snapshot():
    first = merge_documents({}, {"hosts": [_host("desktop-a", "2026-10-09T10:00:00Z")]})
    second = merge_documents(first, {"hosts": [_host("laptop-b", "2026-10-09T11:00:00Z")]})
    assert {h["id"] for h in second["hosts"]} == {"desktop-a", "laptop-b"}
    assert all(not h["current_host"] for h in second["hosts"])


def test_stale_host_update_cannot_erase_newer_name():
    recent = merge_documents({}, {"hosts": [_host("a", "2026-10-09T12:00:00Z")]})
    old = {"hosts": [{"id": "a", "name": "old", "updated_at": "2026-10-09T10:00:00Z"}]}
    result = merge_documents(recent, old)
    assert result["hosts"][0]["name"] == "a"


def test_new_favorite_and_service_connection_survive_device_push():
    first = {"catalog_preferences": [{"item_key": "tool-one", "updated_at": "2026-10-09T01:00:00Z"}],
             "service_connections": [{"id": "service-one", "updated_at": "2026-10-09T01:00:00Z"}]}
    second = {"catalog_preferences": [{"item_key": "tool-two", "updated_at": "2026-10-09T02:00:00Z"}]}
    result = merge_documents(first, second)
    assert {x["item_key"] for x in result["catalog_preferences"]} == {"tool-one", "tool-two"}
    assert len(result["service_connections"]) == 1


def test_preferences_choose_newer_timestamp():
    old = {"preferences": {"theme": "light", "updated_at": "2026-10-09T00:00:00Z"}}
    new = {"preferences": {"theme": "dark", "updated_at": "2026-10-09T01:00:00Z"}}
    assert merge_documents(old, new)["preferences"]["theme"] == "dark"
    assert merge_documents(new, old)["preferences"]["theme"] == "dark"


def test_secrets_and_unknown_top_level_fields_never_sync():
    result = merge_documents({}, {"access_token": "secret", "auth": {"private": True},
                                  "password": "secret", "hosts": [_host("a", "1")]})
    assert "access_token" not in result and "auth" not in result and "password" not in result


def test_malformed_collections_are_skipped():
    result = merge_documents({"hosts": "not-an-array"},
                             {"hosts": [None, {"id": ""}, _host("valid", "now")]})
    assert len(result["hosts"]) == 1 and result["hosts"][0]["id"] == "valid"
