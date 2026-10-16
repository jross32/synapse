"""Daemon-owned adapter to the registered Playwright MCP server.

The same persistent stdio session must be used for every browser action. The
shared tab adapter serializes select+action. No Chrome profile is launched here.
"""
from __future__ import annotations
import asyncio
from typing import Any
from . import mcp_servers, mcp_connector


def build_playwright_call(storage):
    async def call(name: str, arguments: dict[str, Any]) -> Any:
        with storage.transaction() as conn:
            servers = {server.id: server for server in mcp_servers.list_servers(conn)}
        server = servers.get("playwright")
        if server is None:
            raise RuntimeError("Registered playwright MCP server is missing")
        if server.transport == "http":
            speak = mcp_connector._http_mcp
        elif server.transport == "stdio":
            speak = mcp_connector._persistent_stdio_mcp
        else:
            raise RuntimeError("Playwright MCP transport is unsupported")
        return await asyncio.to_thread(
            speak, server, "tools/call", {"name": name, "arguments": arguments}, 40
        )
    return call
