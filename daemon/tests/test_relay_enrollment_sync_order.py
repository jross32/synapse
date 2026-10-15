from types import SimpleNamespace
from unittest.mock import Mock
from synapse_daemon.outbound_mcp_relay import OutboundMcpRelay


def test_enrollment_publishes_host_before_credential_issue():
    events = []
    relay = object.__new__(OutboundMcpRelay)
    relay.manager = SimpleNamespace(
        list_hosts=lambda: events.append("local-host"),
        _sync_to_remote=lambda *, best_effort: events.append("cloud-sync"),
        _ensure_access_token=lambda: "account-access",
        _accounts=SimpleNamespace(enroll_relay_device=lambda **kwargs:
                                  (events.append("enroll") or {"device_token": "x" * 40})),
    )
    relay._save_credential = lambda *args: events.append("save")
    assert relay._enroll_once("account", "device") == "x" * 40
    assert events == ["local-host", "cloud-sync", "enroll", "save"]


def test_failed_sync_does_not_enroll_unregistered_device():
    relay = object.__new__(OutboundMcpRelay)
    enroll = Mock()
    def fail(*, best_effort):
        raise RuntimeError("cloud unavailable")
    relay.manager = SimpleNamespace(
        list_hosts=lambda: [], _sync_to_remote=fail,
        _accounts=SimpleNamespace(enroll_relay_device=enroll),
    )
    import pytest
    with pytest.raises(RuntimeError, match="cloud unavailable"):
        relay._enroll_once("account", "device")
    enroll.assert_not_called()
