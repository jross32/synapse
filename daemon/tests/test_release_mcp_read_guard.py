"""Read connector rejects writes before validating arguments or changing state."""
import pytest
from tests.test_mcp_connector import _harness, _rpc

@pytest.mark.parametrize("name", [
    "synapse_set_project_chat_url", "synapse_add_project_idea",
    "synapse_create_active_task", "synapse_capture_note",
    "synapse_run_command", "synapse_write_file",
    "unknown_legacy_write_tool",
])
def test_read_guard_precedes_dispatch(tmp_path, monkeypatch, name):
    monkeypatch.setenv("SYNAPSE_MCP_ALLOW_WRITES", "1")
    client, token = _harness(tmp_path)
    response = _rpc(client, token, "tools/call", {"name": name, "arguments": {}}, url_suffix="?mode=read")
    assert response.status_code == 200
    result = response.json()["result"]
    assert result["isError"] is True
    assert "read-only connector URL" in result["content"][0]["text"]
