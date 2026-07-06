"""Tests for the MCP-server marketplace + manager (ADR-0017 MW2)."""

from __future__ import annotations

import asyncio
import json
import socket
from pathlib import Path

from fastapi.testclient import TestClient

from synapse_daemon import mcp_servers as mcp
from synapse_daemon.app import build_app
from synapse_daemon.mcp_servers import (
    McpServer,
    McpServerManager,
    McpServerStatus,
    McpTransport,
    build_mcp_config,
)
from synapse_daemon.storage import Storage
from synapse_daemon.ws import EventBus


def _harness(tmp_path: Path) -> TestClient:
    storage = Storage(tmp_path / "data")
    storage.open()
    storage.migrate()
    app = build_app(storage, EventBus())
    return TestClient(app, headers={"X-Synapse-Token": app.state.auth.local_token})


def _server(**kw) -> McpServer:
    base = dict(
        id="x", name="X", transport=McpTransport.STDIO, created_at="t", updated_at="t",
    )
    base.update(kw)
    return McpServer(**base)


def _fake_web_scraper_repo(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    (path / "mcp-server.js").write_text("// fake web scraper mcp\n", encoding="utf-8")
    (path / "package.json").write_text(
        json.dumps({"name": "web-scraper-app", "scripts": {"mcp:http": "node mcp-server.js --http"}}),
        encoding="utf-8",
    )
    return path


# ── Catalog + CRUD via HTTP ──────────────────────────────────────────────────


def test_registry_lists_curated_servers(tmp_path: Path) -> None:
    client = _harness(tmp_path)
    res = client.get("/api/v1/mcp-servers/registry")
    assert res.status_code == 200, res.text
    by_id = {s["id"]: s for s in res.json()["servers"]}
    assert "filesystem" in by_id and by_id["filesystem"]["transport"] == "stdio"
    assert "web-scraper" in by_id and by_id["web-scraper"]["transport"] == "http"
    assert "custom-http" in by_id and by_id["custom-http"]["transport"] == "http"
    assert by_id["filesystem"]["installed"] is False


def test_install_from_catalog_then_status(tmp_path: Path) -> None:
    client = _harness(tmp_path)
    res = client.post("/api/v1/mcp-servers/install", json={"catalog_id": "filesystem"})
    assert res.status_code == 201, res.text
    assert res.json()["transport"] == "stdio"
    # registry now flags it installed
    reg = {s["id"]: s for s in client.get("/api/v1/mcp-servers/registry").json()["servers"]}
    assert reg["filesystem"]["installed"] is True
    # installed list shows it with a stdio-ready status
    installed = client.get("/api/v1/mcp-servers").json()["servers"]
    fs = next(s for s in installed if s["id"] == "filesystem")
    assert fs["status"] == "stdio_ready"


def test_install_web_scraper_catalog_bootstraps_autorun(tmp_path: Path, monkeypatch) -> None:
    storage = Storage(tmp_path / "data")
    storage.open()
    storage.migrate()
    app = build_app(storage, EventBus())
    client = TestClient(app, headers={"X-Synapse-Token": app.state.auth.local_token})
    checkout = _fake_web_scraper_repo(tmp_path / "checkout")
    monkeypatch.setattr(mcp, "ensure_web_scraper_checkout", lambda data_dir: checkout)

    res = client.post("/api/v1/mcp-servers/install", json={"catalog_id": "web-scraper"})
    assert res.status_code == 201, res.text
    payload = res.json()
    assert payload["id"] == "web-scraper"
    assert payload["autorun"] is True
    assert payload["enabled"] is True

    stored = mcp.get_server(storage.conn, "web-scraper")
    assert stored.launch_command in {"npm", "npm.cmd"}
    assert stored.launch_args[:2] == ["--prefix", str(checkout)]
    assert stored.launch_args[-2:] == ["run", "mcp:http"]


def test_install_duplicate_is_409(tmp_path: Path) -> None:
    client = _harness(tmp_path)
    client.post("/api/v1/mcp-servers/install", json={"catalog_id": "filesystem"})
    dup = client.post("/api/v1/mcp-servers/install", json={"catalog_id": "filesystem"})
    assert dup.status_code == 409


def test_install_custom_http_and_status_stopped(tmp_path: Path) -> None:
    client = _harness(tmp_path)
    res = client.post(
        "/api/v1/mcp-servers/install",
        json={"id": "scraper", "name": "Web Scraper", "transport": "http", "url": "http://127.0.0.1:59999/mcp"},
    )
    assert res.status_code == 201, res.text
    installed = client.get("/api/v1/mcp-servers").json()["servers"]
    s = next(x for x in installed if x["id"] == "scraper")
    assert s["status"] == "stopped"  # nothing listening on :59999


def test_custom_requires_id_and_name(tmp_path: Path) -> None:
    client = _harness(tmp_path)
    res = client.post("/api/v1/mcp-servers/install", json={"transport": "http", "url": "http://x"})
    assert res.status_code == 422


def test_ensure_bootstrap_web_scraper_creates_autorun_server(tmp_path: Path) -> None:
    storage = Storage(tmp_path / "data")
    storage.open()
    storage.migrate()
    checkout = _fake_web_scraper_repo(tmp_path / "wbscrper")

    with storage.transaction() as conn:
        server = mcp.ensure_bootstrap_web_scraper(conn, source_path=checkout)

    assert server is not None
    assert server.id == "web-scraper"
    assert server.autorun is True
    assert server.enabled is True
    assert server.url == "http://127.0.0.1:12345/mcp"


def test_patch_enable_autorun_and_delete(tmp_path: Path) -> None:
    client = _harness(tmp_path)
    client.post("/api/v1/mcp-servers/install", json={"catalog_id": "memory"})
    patched = client.patch("/api/v1/mcp-servers/memory", json={"autorun": True, "enabled": False})
    assert patched.status_code == 200
    assert patched.json()["autorun"] is True and patched.json()["enabled"] is False
    assert client.delete("/api/v1/mcp-servers/memory").status_code == 204
    reg = {s["id"]: s for s in client.get("/api/v1/mcp-servers/registry").json()["servers"]}
    assert reg["memory"]["installed"] is False


def test_unknown_catalog_id_is_404(tmp_path: Path) -> None:
    client = _harness(tmp_path)
    assert client.post("/api/v1/mcp-servers/install", json={"catalog_id": "nope"}).status_code == 404


def test_env_secrets_redacted_on_read_but_kept_for_the_ai(tmp_path: Path) -> None:
    storage = Storage(tmp_path / "data")
    storage.open()
    storage.migrate()
    app = build_app(storage, EventBus())
    client = TestClient(app, headers={"X-Synapse-Token": app.state.auth.local_token})

    client.post(
        "/api/v1/mcp-servers/install",
        json={"id": "gh", "name": "GitHub", "transport": "stdio", "command": "npx", "env": {"TOKEN": "supersecret"}},
    )
    # The API never round-trips the real secret.
    listed = next(s for s in client.get("/api/v1/mcp-servers").json()["servers"] if s["id"] == "gh")
    assert listed["env"]["TOKEN"] == "(set)"
    # Sending the placeholder back preserves the stored secret (no clobber)...
    client.patch("/api/v1/mcp-servers/gh", json={"env": {"TOKEN": "(set)"}})
    assert mcp.get_server(storage.conn, "gh").env["TOKEN"] == "supersecret"
    # ...a real new value updates it.
    client.patch("/api/v1/mcp-servers/gh", json={"env": {"TOKEN": "newsecret"}})
    assert mcp.get_server(storage.conn, "gh").env["TOKEN"] == "newsecret"
    # The config the AI actually receives keeps the real value.
    cfg = build_mcp_config(mcp.list_servers(storage.conn))["mcpServers"]
    assert cfg["gh"]["env"] == {"TOKEN": "newsecret"}


# ── Manager status + config (unit, deterministic) ────────────────────────────


def test_status_stdio_is_ready() -> None:
    mgr = McpServerManager()
    status, _ = asyncio.run(mgr.status(_server(transport=McpTransport.STDIO, command="npx")))
    assert status == McpServerStatus.STDIO_READY


def test_status_http_connected_when_listening() -> None:
    mgr = McpServerManager()

    async def run() -> McpServerStatus:
        server = await asyncio.start_server(lambda r, w: w.close(), "127.0.0.1", 0)
        port = server.sockets[0].getsockname()[1]
        try:
            s = _server(transport=McpTransport.HTTP, url=f"http://127.0.0.1:{port}/mcp")
            status, _ = await mgr.status(s)
            return status
        finally:
            server.close()
            await server.wait_closed()

    assert asyncio.run(run()) == McpServerStatus.CONNECTED


def test_status_http_stopped_when_nothing_listening() -> None:
    mgr = McpServerManager()
    # find a definitely-closed port
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    status, _ = asyncio.run(mgr.status(_server(transport=McpTransport.HTTP, url=f"http://127.0.0.1:{port}/mcp")))
    assert status == McpServerStatus.STOPPED


def test_build_mcp_config_filters_and_shapes() -> None:
    servers = [
        _server(id="fs", transport=McpTransport.STDIO, command="npx", args=["-y", "server-fs"], enabled=True),
        _server(id="off", transport=McpTransport.STDIO, command="npx", enabled=False),
        _server(id="http", transport=McpTransport.HTTP, url="http://127.0.0.1:9/mcp", enabled=True),
        _server(id="gh", transport=McpTransport.STDIO, command="npx", env={"TOKEN": "x"}, enabled=True),
    ]
    cfg = build_mcp_config(servers)["mcpServers"]
    assert set(cfg) == {"fs", "http", "gh"}  # disabled excluded
    assert cfg["fs"] == {"command": "npx", "args": ["-y", "server-fs"]}
    assert cfg["http"] == {"type": "http", "url": "http://127.0.0.1:9/mcp"}
    assert cfg["gh"]["env"] == {"TOKEN": "x"}
