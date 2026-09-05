from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from synapse_daemon.mcp_chatgpt_compat import (
    ABOUT_RESOURCE_URI,
    ChatGPTMcpCompatMiddleware,
)


def _client() -> TestClient:
    app = FastAPI()

    @app.post("/mcp/{token}")
    async def core_mcp_fallback(token: str) -> dict[str, object]:
        return {"fallback": True, "token": token}

    app.add_middleware(
        ChatGPTMcpCompatMiddleware,
        token="secret-token",
        version="9.9.9-test",
    )
    return TestClient(app)


def test_initialize_advertises_tools_and_resources() -> None:
    client = _client()
    response = client.post(
        "/mcp/secret-token",
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {"protocolVersion": "2025-06-18"},
        },
    )

    assert response.status_code == 200
    result = response.json()["result"]
    assert result["protocolVersion"] == "2025-06-18"
    assert result["capabilities"]["tools"] == {"listChanged": False}
    assert result["capabilities"]["resources"] == {
        "subscribe": False,
        "listChanged": False,
    }
    assert result["serverInfo"] == {"name": "synapse", "version": "9.9.9-test"}


def test_resource_is_listed_and_readable() -> None:
    client = _client()

    listed = client.post(
        "/mcp/secret-token",
        json={"jsonrpc": "2.0", "id": 2, "method": "resources/list", "params": {}},
    )
    assert listed.status_code == 200
    resources = listed.json()["result"]["resources"]
    assert [resource["uri"] for resource in resources] == [ABOUT_RESOURCE_URI]
    assert resources[0]["mimeType"] == "text/plain"

    read = client.post(
        "/mcp/secret-token",
        json={
            "jsonrpc": "2.0",
            "id": 3,
            "method": "resources/read",
            "params": {"uri": ABOUT_RESOURCE_URI},
        },
    )
    assert read.status_code == 200
    content = read.json()["result"]["contents"][0]
    assert content["uri"] == ABOUT_RESOURCE_URI
    assert content["mimeType"] == "text/plain"
    assert "Synapse daemon 9.9.9-test" in content["text"]


def test_unknown_resource_returns_mcp_resource_not_found() -> None:
    client = _client()
    response = client.post(
        "/mcp/secret-token",
        json={
            "jsonrpc": "2.0",
            "id": 4,
            "method": "resources/read",
            "params": {"uri": "synapse://missing"},
        },
    )

    assert response.status_code == 200
    assert response.json()["error"]["code"] == -32002


def test_wrong_path_token_is_rejected_for_compat_methods() -> None:
    client = _client()
    response = client.post(
        "/mcp/not-the-token",
        json={"jsonrpc": "2.0", "id": 5, "method": "resources/list", "params": {}},
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == -32001


def test_tool_calls_still_flow_to_the_core_mcp_router() -> None:
    client = _client()
    response = client.post(
        "/mcp/secret-token",
        json={"jsonrpc": "2.0", "id": 6, "method": "tools/list", "params": {}},
    )

    assert response.status_code == 200
    assert response.json() == {"fallback": True, "token": "secret-token"}
