"""REST for the MCP-server marketplace + manager (ADR-0017, MW2)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from . import mcp_servers as mcp
from .audit import AuditRecord, audit
from .mcp_servers import (
    McpCatalog,
    McpServerInstallRequest,
    McpServerList,
    McpServerManager,
    McpServerUpdate,
)
from .models import AuditSource
from .storage import Storage


def build_mcp_servers_router(storage: Storage, manager: McpServerManager) -> APIRouter:
    router = APIRouter(prefix="/mcp-servers", tags=["mcp-servers"])

    def _catalog() -> McpCatalog:
        installed = {s.id for s in mcp.list_servers(storage.conn)}
        return mcp.load_catalog(installed)

    @router.get("/registry", response_model=McpCatalog)
    async def registry() -> McpCatalog:
        return _catalog()

    @router.get("", response_model=McpServerList)
    async def list_installed() -> McpServerList:
        return McpServerList(servers=await mcp.server_views(storage.conn, manager))

    @router.post("/install", response_model=None, status_code=201)
    async def install(payload: McpServerInstallRequest) -> dict[str, Any]:
        with storage.transaction() as conn:
            server = mcp.install_server(conn, payload, _catalog())
            audit(
                conn,
                AuditRecord(
                    entity_type="mcp_server",
                    entity_id=server.id,
                    action="install",
                    source=AuditSource.DESKTOP,
                    result="success",
                    details={"transport": server.transport.value},
                ),
            )
        return mcp.client_dump(server)

    @router.patch("/{server_id}", response_model=None)
    async def update(server_id: str, payload: McpServerUpdate) -> dict[str, Any]:
        with storage.transaction() as conn:
            server = mcp.update_server(conn, server_id, payload)
        return mcp.client_dump(server)

    @router.post("/{server_id}/start", response_model=None)
    async def start(server_id: str) -> dict[str, Any]:
        server = mcp.get_server(storage.conn, server_id)
        started = manager.start(server)
        status, detail = await manager.status(server)
        return {"started": started, "status": status.value, "detail": detail}

    @router.post("/{server_id}/stop", response_model=None)
    async def stop(server_id: str) -> dict[str, Any]:
        mcp.get_server(storage.conn, server_id)  # 404 if missing
        return {"stopped": manager.stop(server_id)}

    @router.delete("/{server_id}", status_code=204, response_model=None)
    async def uninstall(server_id: str) -> None:
        manager.stop(server_id)
        with storage.transaction() as conn:
            mcp.delete_server(conn, server_id)

    return router
