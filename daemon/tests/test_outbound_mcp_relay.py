"""Host relay worker receives authenticated cloud jobs without cloud learning local credentials."""
from types import SimpleNamespace
from unittest.mock import Mock

from synapse_daemon.outbound_mcp_relay import OutboundMcpRelay


class Cloud:
    def __init__(self, *, write_enabled=True, incoming_mode="full"):
        self.write_enabled = write_enabled
        self.incoming_mode = incoming_mode
        self.finished = []

    def relay_agent_poll(self, **kwargs):
        assert kwargs["device_token"] == "device-secret"
        return {"job_id": "job-1", "request": {"jsonrpc": "2.0", "id": 2,
                                               "method": "tools/call", "params": {"name": "synapse_run_command"}},
                "mode": self.incoming_mode}

    def relay_agent_access(self, **kwargs):
        assert kwargs["device_id"] == "device-1"
        return {"remote_write_enabled": self.write_enabled}

    def relay_agent_finish(self, **kwargs):
        self.finished.append(kwargs)


class Manager:
    def __init__(self, tmp_path, cloud):
        self._storage = SimpleNamespace(data_dir=tmp_path)
        self._accounts = cloud
        self.user_id = "account-1"

    def _state_row(self):
        return {"user_id": self.user_id, "current_host_id": "device-1"}


def _agent(tmp_path, *, write_enabled=True, incoming_mode="full"):
    cloud = Cloud(write_enabled=write_enabled, incoming_mode=incoming_mode)
    agent = OutboundMcpRelay(Manager(tmp_path, cloud), "local-daemon-secret")
    agent._read_saved_credential = lambda *_: "device-secret"
    agent._invoke_local_mcp = Mock(return_value={"jsonrpc": "2.0", "id": 2, "result": "ok"})
    return agent, cloud


def test_default_full_write_for_enrolled_device(tmp_path):
    agent, cloud = _agent(tmp_path)
    agent._run_one_cycle()
    agent._invoke_local_mcp.assert_called_once()
    assert agent._invoke_local_mcp.call_args.args[1] == "full"
    assert cloud.finished[0]["job_id"] == "job-1"


def test_disabling_device_write_pins_local_mcp_to_read_only(tmp_path):
    agent, cloud = _agent(tmp_path, write_enabled=False)
    agent._run_one_cycle()
    assert agent._invoke_local_mcp.call_args.args[1] == "read"
    assert cloud.finished[0]["response"]["result"] == "ok"


def test_explicit_read_only_link_stays_read_only_even_when_device_has_write_permission(tmp_path):
    agent, _cloud = _agent(tmp_path, write_enabled=True, incoming_mode="read")
    agent._run_one_cycle()
    assert agent._invoke_local_mcp.call_args.args[1] == "read"


def test_signout_between_poll_and_dispatch_blocks_command(tmp_path):
    agent, cloud = _agent(tmp_path)
    original_access = cloud.relay_agent_access

    def signout_during_access(**kwargs):
        result = original_access(**kwargs)
        agent.manager.user_id = None
        return result

    cloud.relay_agent_access = signout_during_access
    agent._run_one_cycle()
    agent._invoke_local_mcp.assert_not_called()
    assert cloud.finished[0]["response"]["error"]["code"] == -32001


def test_client_token_never_passed_to_cloud_request(tmp_path):
    agent, cloud = _agent(tmp_path)
    agent._run_one_cycle()
    assert "local-daemon-secret" not in str(cloud.finished)
    assert "local-daemon-secret" not in str(cloud.__dict__)
