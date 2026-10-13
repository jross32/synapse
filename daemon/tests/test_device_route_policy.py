"""Safety contracts for account-scoped multi-device target selection."""
from datetime import datetime, timedelta, timezone

import pytest

from synapse_daemon.device_route_policy import DeviceRouteError, DeviceTarget, plan_devices


NOW = datetime(2026, 10, 13, 17, 30, tzinfo=timezone.utc)


def device(name, account="alice", **kwargs):
    values = dict(
        device_id=name, account_id=account, display_name="SAME HOSTNAME",
        last_heartbeat=NOW - timedelta(seconds=10), relay_connected=True,
        enabled=True, revoked=False, capabilities=frozenset({"mcp", "filesystem"}),
        priority=0,
    )
    values.update(kwargs)
    return DeviceTarget(**values)


def route(selector, devices, **kwargs):
    return plan_devices(account_id="alice", selector=selector, devices=devices,
                        operation="files.read", now=NOW, **kwargs)


def test_explicit_id_routes_to_target_without_hostname_guessing():
    result = route("desktop-id", [device("laptop-id"), device("desktop-id")])
    assert result.device_ids == ("desktop-id",)
    with pytest.raises(DeviceRouteError):
        route("SAME HOSTNAME", [device("laptop-id"), device("desktop-id")])


def test_cross_account_target_refused_even_when_online():
    with pytest.raises(DeviceRouteError):
        route("desktop-id", [device("desktop-id", "someone-else")])


@pytest.mark.parametrize("override", [
    {"relay_connected": False}, {"enabled": False}, {"revoked": True},
    {"last_heartbeat": NOW - timedelta(seconds=91)},
    {"last_heartbeat": NOW + timedelta(seconds=1)},
    {"last_heartbeat": None},
])
def test_explicit_target_never_falls_back_when_unavailable(override):
    with pytest.raises(DeviceRouteError):
        route("desktop-id", [device("desktop-id", **override), device("laptop-id")])


def test_capability_must_exist_on_target():
    with pytest.raises(DeviceRouteError):
        route("desktop-id", [device("desktop-id", capabilities=frozenset({"mcp"}))],
              required_capabilities={"filesystem"})


def test_auto_prefers_priority_with_stable_tiebreak():
    result = route("auto", [device("z", priority=2), device("a", priority=2),
                            device("q", priority=0)])
    assert result.device_ids == ("a",)


def test_both_needs_opt_in_and_approval_for_every_device():
    fleet = [device("laptop"), device("desktop")]
    with pytest.raises(DeviceRouteError):
        route("both", fleet)
    with pytest.raises(DeviceRouteError):
        route("both", fleet, allow_multiple=True)
    with pytest.raises(DeviceRouteError):
        route("both", fleet, allow_multiple=True, approved_device_ids=["laptop"])
    result = route("both", fleet, allow_multiple=True, approved_device_ids=["laptop", "desktop"])
    assert result.device_ids == ("desktop", "laptop")


def test_both_does_not_include_unreachable_or_other_account():
    fleet = [device("laptop"), device("desktop", relay_connected=False),
             device("intruder", account="other")]
    with pytest.raises(DeviceRouteError):
        route("both", fleet, allow_multiple=True)


def test_duplicate_device_identity_rejected():
    with pytest.raises(DeviceRouteError):
        route("auto", [device("dup"), device("dup")])


def test_stale_and_naive_time_do_not_authorize():
    with pytest.raises(DeviceRouteError):
        route("laptop", [device("laptop", last_heartbeat=NOW.replace(tzinfo=None))])


def test_empty_operation_and_account_fail_closed():
    with pytest.raises(DeviceRouteError):
        plan_devices(account_id="", selector="auto", devices=[device("laptop")],
                     operation="execute", now=NOW)
    with pytest.raises(DeviceRouteError):
        plan_devices(account_id="alice", selector="auto", devices=[device("laptop")],
                     operation="", now=NOW)


def test_both_never_fans_out_to_a_third_device():
    fleet = [device('laptop'), device('desktop'), device('workstation')]
    result = route('both', fleet, allow_multiple=True, approved_device_ids=['laptop', 'desktop'])
    assert result.device_ids == ('desktop', 'laptop')
    with pytest.raises(DeviceRouteError):
        route('both', fleet, allow_multiple=True, approved_device_ids=['laptop', 'desktop', 'workstation'])
