"""Account-backed MCP selection never uses local daemon tokens."""
from datetime import datetime, timedelta, timezone
import pytest
from synapse_daemon.account_device_gateway import select_account_device
from synapse_daemon.device_route_policy import DeviceTarget, DeviceRouteError

NOW = datetime(2026, 10, 13, 19, tzinfo=timezone.utc)

class FakeCloud:
    def __init__(self, *, returned=None):
        self.calls = []
        self.returned = returned
    def select_mcp_device(self, *, access_token, device_id):
        self.calls.append((access_token, device_id))
        return {"selected_device_id": device_id if self.returned is None else self.returned}

def host(device_id, *, account="alice", ready=True, capabilities=frozenset({"mcp"})):
    return DeviceTarget(device_id=device_id, account_id=account, display_name="Computer",
                        last_heartbeat=NOW - timedelta(seconds=5),
                        relay_connected=ready, enabled=True, capabilities=capabilities)

def choose(cloud, selector="desktop", devices=None, **kwargs):
    return select_account_device(
        client=cloud, account_id="alice", account_access_token="account-session-token",
        selector=selector, devices=devices if devices is not None else [host("laptop"), host("desktop")],
        operation="mcp.tools", now=NOW, **kwargs,
    )

def test_selected_desktop_confirmed_with_account_token():
    cloud = FakeCloud()
    selected = choose(cloud)
    assert selected.device_id == "desktop"
    assert selected.plan.device_ids == ("desktop",)
    assert cloud.calls == [("account-session-token", "desktop")]

def test_auto_selected_device_and_capability():
    cloud = FakeCloud()
    selected = choose(cloud, "auto", [host("laptop", capabilities=frozenset()),
                                      host("desktop")], required_capabilities={"mcp"})
    assert selected.device_id == "desktop"

@pytest.mark.parametrize("returned", ["laptop", "", False, 123])
def test_remote_confirmation_must_match_exact_device(returned):
    with pytest.raises(DeviceRouteError):
        choose(FakeCloud(returned=returned))

def test_cross_account_or_offline_never_calls_cloud():
    cloud = FakeCloud()
    for devices in ([host("desktop", account="bob")], [host("desktop", ready=False)]):
        with pytest.raises(DeviceRouteError):
            choose(cloud, devices=devices)
    assert cloud.calls == []

def test_device_scoped_approval_rejects_unapproved_target():
    cloud = FakeCloud()
    with pytest.raises(DeviceRouteError):
        choose(cloud, approved_device_ids={"laptop"})
    assert cloud.calls == []

def test_requires_account_session_and_does_not_use_local_token():
    cloud = FakeCloud()
    with pytest.raises(DeviceRouteError):
        select_account_device(client=cloud, account_id="alice", account_access_token="",
                              selector="desktop", devices=[host("desktop")],
                              operation="mcp.tools", now=NOW)
    assert cloud.calls == []

def test_cloud_api_does_not_claim_multi_target_support():
    with pytest.raises(DeviceRouteError):
        choose(FakeCloud(), selector="both",
               approved_device_ids={"desktop", "laptop"})


def test_auto_selects_project_affinity_and_creative_capabilities():
    cloud = FakeCloud()
    chosen = choose(
        cloud, "auto",
        [host("laptop", capabilities=frozenset({"mcp", "filesystem"})),
         host("desktop", capabilities=frozenset({"mcp", "filesystem", "gpu", "blender"}))],
        required_capabilities={"mcp"},
        preferred_capabilities={"gpu", "blender"},
        preferred_device_ids=["desktop"],
    )
    assert chosen.device_id == "desktop"
    assert cloud.calls[-1][1] == "desktop"


def test_explicit_device_never_redirects_to_preferred_one():
    cloud = FakeCloud()
    chosen = choose(cloud, "laptop", preferred_capabilities={"gpu"},
                    preferred_device_ids=["desktop"])
    assert chosen.device_id == "laptop"
