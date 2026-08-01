"""Contract #21 — search tokeniser + helpers."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from synapse_daemon import mcp_servers
from synapse_daemon.routes_search import build_search_router
from synapse_daemon.search import build_search_tokens, tokenise
from synapse_daemon.storage import Storage
from synapse_daemon.tools_registry import ToolRegistry
from synapse_daemon.ws import EventBus


def test_tokenise_strips_punctuation_and_lowers() -> None:
    assert tokenise("Web-Scraper v2 (alpha)") == ["web", "scraper", "v2", "alpha"]


def test_tokenise_handles_empty() -> None:
    assert tokenise("") == []
    assert tokenise("   ") == []


def test_build_search_tokens_dedups_and_sorts() -> None:
    tokens = build_search_tokens("Web-Scraper", "Web Scraper", tags=["scraping", "tools"])
    assert tokens == sorted(set(tokens))
    assert "scraper" in tokens
    assert "web" in tokens
    assert "scraping" in tokens
    assert "tools" in tokens


def test_build_search_tokens_ignores_none() -> None:
    tokens = build_search_tokens(None, "Cloudtap", None, tags=[])
    assert tokens == ["cloudtap"]


def test_universal_search_finds_installed_mcp_server(tmp_path) -> None:
    storage = Storage(tmp_path / "data")
    storage.open()
    storage.migrate()
    with storage.transaction() as conn:
        mcp_servers.install_server(
            conn,
            mcp_servers.McpServerInstallRequest(
                id="reflex",
                name="Reflex",
                description="AI computer control for Windows",
                transport=mcp_servers.McpTransport.STDIO,
                command="node",
                args=["mcp-server.js"],
            ),
            mcp_servers.McpCatalog(servers=[]),
        )
    registry = ToolRegistry(tmp_path / "tools", EventBus(), storage)
    registry.load()
    app = FastAPI()
    app.include_router(build_search_router(storage, registry), prefix="/api/v1")
    response = TestClient(app).get("/api/v1/search?q=reflex")
    assert response.status_code == 200
    body = response.json()
    assert body["query"] == "reflex"
    assert body["hits"][0]["entity_id"] == "mcp:reflex"
    assert body["hits"][0]["badge"] == "MCP server"
