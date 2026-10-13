"""Local-token remains inside the server; the MCP client never receives it."""
import io
import json
import urllib.error
from unittest.mock import patch

import pytest
from synapse_daemon.mcp_worker_launch import WorkerLaunchError, launch_existing_work_item


class Response:
    status = 200
    def __enter__(self): return self
    def __exit__(self, *args): return False
    def read(self, size=-1): return b'{"status":"running","work_item_id":"b4df6f6b0e21"}'


def test_launch_calls_localhost_with_auth_header_and_receipt():
    captured = {}
    def urlopen(req, timeout):
        captured.update(url=req.full_url, token=req.get_header("X-synapse-token"),
                        method=req.get_method(), timeout=timeout)
        return Response()
    with patch("urllib.request.urlopen", side_effect=urlopen):
        result = launch_existing_work_item("b4df6f6b0e21", local_token="private-secret", port=7878)
    assert captured == {"url": "http://127.0.0.1:7878/api/v1/agent-work-items/b4df6f6b0e21/launch",
                        "token": "private-secret", "method": "POST", "timeout": 25}
    assert "private-secret" not in json.dumps(result)
    assert result["status"] == "running"


@pytest.mark.parametrize("work_item", ["", "../hack", "work/id", "a", "abc?query=1"])
def test_rejects_injected_or_invalid_work_item_ids(work_item):
    with pytest.raises(WorkerLaunchError):
        launch_existing_work_item(work_item, local_token="secret")


def test_requires_internal_token():
    with pytest.raises(WorkerLaunchError):
        launch_existing_work_item("b4df6f6b0e21", local_token="")


def test_http_failure_redacts_server_body_and_token():
    err = urllib.error.HTTPError("http://127.0.0.1", 403, "secret-body", {}, io.BytesIO(b"private details"))
    with patch("urllib.request.urlopen", side_effect=err):
        with pytest.raises(WorkerLaunchError, match="HTTP 403") as caught:
            launch_existing_work_item("b4df6f6b0e21", local_token="private-secret")
    assert "private-secret" not in str(caught.value)
    assert "private details" not in str(caught.value)
