"""REST for the MCP-server marketplace + manager (ADR-0017, MW2)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from .api_versions import event_name
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

    async def _publish(request: Request, reason: str, payload: dict[str, Any]) -> None:
        await request.app.state.bus.publish(
            event_name("mcp_server", "updated"),
            {"reason": reason, **payload},
        )

    @router.get("/registry", response_model=McpCatalog)
    async def registry() -> McpCatalog:
        return _catalog()

    @router.get("", response_model=McpServerList)
    async def list_installed() -> McpServerList:
        return McpServerList(servers=await mcp.server_views(storage.conn, manager))

    @router.post("/install", response_model=None, status_code=201)
    async def install(payload: McpServerInstallRequest, request: Request) -> dict[str, Any]:
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
        await _publish(
            request,
            "installed",
            {"server_id": server.id, "server": mcp.client_dump(server)},
        )
        return mcp.client_dump(server)

    @router.patch("/{server_id}", response_model=None)
    async def update(server_id: str, payload: McpServerUpdate, request: Request) -> dict[str, Any]:
        with storage.transaction() as conn:
            server = mcp.update_server(conn, server_id, payload)
        await _publish(
            request,
            "updated",
            {"server_id": server.id, "server": mcp.client_dump(server)},
        )
        return mcp.client_dump(server)

    @router.post("/{server_id}/start", response_model=None)
    async def start(server_id: str, request: Request) -> dict[str, Any]:
        server = mcp.get_server(storage.conn, server_id)
        started = manager.start(server)
        status, detail = await manager.status(server)
        await _publish(
            request,
            "started",
            {
                "server_id": server.id,
                "started": started,
                "status": status.value,
                "detail": detail,
            },
        )
        return {"started": started, "status": status.value, "detail": detail}

    @router.post("/{server_id}/stop", response_model=None)
    async def stop(server_id: str, request: Request) -> dict[str, Any]:
        mcp.get_server(storage.conn, server_id)  # 404 if missing
        stopped = manager.stop(server_id)
        await _publish(
            request,
            "stopped",
            {"server_id": server_id, "stopped": stopped},
        )
        return {"stopped": stopped}

    @router.delete("/{server_id}", status_code=204, response_model=None)
    async def uninstall(server_id: str, request: Request) -> None:
        manager.stop(server_id)
        with storage.transaction() as conn:
            server = mcp.get_server(conn, server_id)
            mcp.delete_server(conn, server_id)
        await _publish(
            request,
            "uninstalled",
            {"server_id": server.id, "server": mcp.client_dump(server)},
        )

    return router
