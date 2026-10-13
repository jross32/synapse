"""Cloud MCP device discovery and selection through one connector."""
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent))
from concurrent.futures import ThreadPoolExecutor

from test_unified_mcp_relay import _client, _connector, _enroll, _hosts, _owner


def _call(client, path, name, args=None, *, read=False):
    suffix = "?mode=read" if read else ""
    response = client.post(path + suffix, json={
        "jsonrpc": "2.0", "id": 21, "method": "tools/call",
        "params": {"name": name, "arguments": args or {}},
    })
    return response


def test_account_lists_own_enrolled_devices_and_offline_state(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as client:
        owner = _owner(client, "owner")
        _hosts(client, owner, "laptop", "desktop")
        path = _connector(client, owner)
        _enroll(client, owner, "laptop")
        listed = _call(client, path, "synapse_account_list_devices")
        assert listed.status_code == 200
        parsed = json.loads(listed.json()["result"]["content"][0]["text"])
        assert [d["device_id"] for d in parsed["devices"]] == ["desktop", "laptop"]
        assert not parsed["devices"][0]["enrolled"]
        assert parsed["devices"][1]["enrolled"]
        assert not parsed["devices"][1]["online"]


def test_selection_requires_heartbeat_and_account_membership(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as client:
        owner = _owner(client, "owner")
        other = _owner(client, "other")
        _hosts(client, owner, "laptop")
        _hosts(client, other, "otherdevice")
        path = _connector(client, owner)
        device_token = _enroll(client, owner, "laptop")
        assert _call(client, path, "synapse_account_select_device", {"device_id": "laptop"}).status_code == 503
        assert _call(client, path, "synapse_account_select_device", {"device_id": "otherdevice"}).status_code == 404
        assert _call(client, path, "synapse_account_select_device", {"device_id": "laptop"}, read=True).status_code == 403
        # Device heartbeat arrives through its own credential.
        poll = client.get("/v1/relay/devices/laptop/jobs/next", headers=device_token)
        assert poll.status_code == 200
        selected = _call(client, path, "synapse_account_select_device", {"device_id": "laptop"})
        assert selected.status_code == 200, selected.text
        assert json.loads(selected.json()["result"]["content"][0]["text"])["selected_device_id"] == "laptop"


def test_bad_account_tool_arguments_fail_closed(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as client:
        owner = _owner(client, "owner")
        path = _connector(client, owner)
        assert _call(client, path, "synapse_account_list_devices", {"leak": True}).status_code == 400
        assert _call(client, path, "synapse_account_select_device", {"device_id": "x", "unexpected": True}).status_code == 422


def test_account_tool_listing_augmented_without_removing_device_tools(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as client:
        owner = _owner(client, "owner")
        _hosts(client, owner, "desktop")
        path = _connector(client, owner)
        token = _enroll(client, owner, "desktop")
        from test_unified_mcp_relay import _select
        _select(client, owner, "desktop")
        with ThreadPoolExecutor(max_workers=2) as pool:
            future = pool.submit(client.post, path, json={
                "jsonrpc": "2.0", "id": 15, "method": "tools/list"})
            job = client.get("/v1/relay/devices/desktop/jobs/next", headers=token).json()
            assert job["job_id"]
            reply = {"jsonrpc": "2.0", "id": 15, "result": {"tools": [
                {"name": "synapse_get_context", "inputSchema": {"type": "object"}}]}}
            finish = client.post("/v1/relay/devices/desktop/jobs/result", headers=token, json={
                "job_id": job["job_id"], "response": reply})
            assert finish.status_code == 200
            result = future.result(timeout=10)
        assert result.status_code == 200
        names = {x["name"] for x in result.json()["result"]["tools"]}
        assert {"synapse_get_context", "synapse_account_list_devices", "synapse_account_select_device"} <= names


def test_explicit_remote_call_targets_device_without_changing_default(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as client:
        owner = _owner(client, "owner")
        _hosts(client, owner, "laptop", "desktop")
        path = _connector(client, owner)
        laptop = _enroll(client, owner, "laptop")
        desktop = _enroll(client, owner, "desktop")
        from test_unified_mcp_relay import _select
        _select(client, owner, "laptop")
        # Establish an authenticated heartbeat for the destination device.
        assert client.get("/v1/relay/devices/desktop/jobs/next", headers=desktop).status_code == 200
        payload = {"jsonrpc": "2.0", "id": 41, "method": "tools/call",
                   "params": {"name": "synapse_account_call_device",
                              "arguments": {"device_id": "desktop", "tool": "synapse_get_context", "arguments": {}}}}
        with ThreadPoolExecutor(max_workers=2) as pool:
            submitted = pool.submit(client.post, path, json=payload)
            polled = client.get("/v1/relay/devices/desktop/jobs/next", headers=desktop)
            assert polled.status_code == 200
            job = polled.json()
            assert job["request"]["params"]["name"] == "synapse_get_context"
            assert job["mode"] == "full"
            reply = {"jsonrpc": "2.0", "id": 41,
                     "result": {"content": [{"type": "text", "text": "device desktop"}]}}
            assert client.post("/v1/relay/devices/desktop/jobs/result",
                               headers=desktop, json={"job_id": job["job_id"], "response": reply}).status_code == 200
            completed = submitted.result(timeout=10)
        assert completed.status_code == 200
        assert completed.json() == reply
        assert client.get("/v1/relay/connector", headers=owner).json()["selected_device_id"] == "laptop"


def test_explicit_call_rejects_cross_account_and_untrusted_fields(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as client:
        owner = _owner(client, "owner")
        outsider = _owner(client, "outsider")
        _hosts(client, owner, "laptop")
        _hosts(client, outsider, "other")
        path = _connector(client, owner)
        _enroll(client, owner, "laptop")
        denied = _call(client, path, "synapse_account_call_device",
                       {"device_id": "other", "tool": "synapse_get_context"})
        assert denied.status_code == 404
        nested = _call(client, path, "synapse_account_call_device",
                       {"device_id": "laptop", "tool": "synapse_account_select_device"})
        assert nested.status_code == 422
        invalid = _call(client, path, "synapse_account_call_device",
                        {"device_id": "laptop", "tool": "synapse_get_context",
                         "arguments": {}, "extra": "unexpected"})
        assert invalid.status_code == 422


def test_account_tool_discovery_when_all_devices_offline(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as client:
        owner = _owner(client, "owner")
        path = _connector(client, owner)
        full = client.post(path, json={"jsonrpc": "2.0", "id": 5, "method": "tools/list"})
        assert full.status_code == 200
        names = {tool["name"] for tool in full.json()["result"]["tools"]}
        assert {"synapse_account_list_devices", "synapse_account_select_device",
                "synapse_account_call_device"} <= names
        readonly = client.post(path + "?mode=read", json={
            "jsonrpc": "2.0", "id": 5, "method": "tools/list"})
        assert readonly.status_code == 200
        assert [t["name"] for t in readonly.json()["result"]["tools"]] == ["synapse_account_list_devices"]


def test_one_connector_independently_dispatches_to_two_devices(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as client:
        owner = _owner(client, "owner")
        _hosts(client, owner, "laptop", "desktop")
        path = _connector(client, owner)
        creds = {"laptop": _enroll(client, owner, "laptop"),
                 "desktop": _enroll(client, owner, "desktop")}
        from test_unified_mcp_relay import _select
        _select(client, owner, "laptop")
        with ThreadPoolExecutor(max_workers=2) as pool:
            checkins = [pool.submit(client.get,
                f"/v1/relay/devices/{device}/jobs/next", headers=creds[device])
                for device in ("laptop", "desktop")]
            for checkin in checkins:
                assert checkin.result(timeout=25).status_code == 200
        requests = {
            device: {"jsonrpc": "2.0", "id": i,
                     "method": "tools/call", "params": {
                         "name": "synapse_account_call_device",
                         "arguments": {"device_id": device, "tool": "synapse_get_context"}}}
            for i, device in enumerate(("laptop", "desktop"), 1)
        }
        with ThreadPoolExecutor(max_workers=2) as pool:
            pending = {device: pool.submit(client.post, path, json=requests[device])
                       for device in ("laptop", "desktop")}
            for device in ("desktop", "laptop"):
                polled = client.get(f"/v1/relay/devices/{device}/jobs/next", headers=creds[device])
                assert polled.status_code == 200
                job = polled.json()
                assert job["job_id"] and job["request"]["params"]["name"] == "synapse_get_context"
                assert job["mode"] == "full"
                response = {"jsonrpc": "2.0", "id": requests[device]["id"],
                            "result": {"content": [{"type": "text", "text": device}]}}
                done = client.post(f"/v1/relay/devices/{device}/jobs/result", headers=creds[device],
                                   json={"job_id": job["job_id"], "response": response})
                assert done.status_code == 200
            for device in ("laptop", "desktop"):
                result = pending[device].result(timeout=15)
                assert result.status_code == 200, result.text
                assert result.json()["result"]["content"][0]["text"] == device
        assert client.get("/v1/relay/connector", headers=owner).json()["selected_device_id"] == "laptop"
