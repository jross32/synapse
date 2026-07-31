"""REST for the MCP-server marketplace + manager (ADR-0017, MW2)."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Request

from . import mcp_servers as mcp
from . import warden_marketplace as warden
from .api_versions import event_name
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

    def _sync_warden(conn, *, reason: str) -> warden.WardenRegistrySync | None:  # noqa: ANN001
        result = warden.sync_if_installed(conn, storage.data_dir)
        if result is not None:
            audit(
                conn,
                AuditRecord(
                    entity_type="mcp_server",
                    entity_id=warden.WARDEN_SERVER_ID,
                    action="registry_sync",
                    source=AuditSource.DESKTOP,
                    result="success",
                    details={
                        "reason": reason,
                        "indexed_stdio_servers": result.indexed_stdio_servers,
                        "skipped_http_servers": result.skipped_http_servers,
                        "skipped_conflicting_env_servers": result.skipped_conflicting_env_servers,
                    },
                ),
            )
        return result

    @router.get("/registry", response_model=McpCatalog)
    async def registry() -> McpCatalog:
        return _catalog()

    @router.get("", response_model=McpServerList)
    async def list_installed() -> McpServerList:
        return McpServerList(servers=await mcp.server_views(storage.conn, manager))

    @router.post("/install", response_model=None, status_code=201)
    async def install(payload: McpServerInstallRequest, request: Request) -> dict[str, Any]:
        if payload.catalog_id == warden.WARDEN_SERVER_ID:
            if storage.conn.execute(
                "SELECT id FROM mcp_servers WHERE id = ?", (warden.WARDEN_SERVER_ID,)
            ).fetchone() is not None:
                raise mcp.conflict("mcp_server", "Warden is already installed.")
            await _publish(
                request,
                "installing",
                {"server_id": warden.WARDEN_SERVER_ID, "version": warden.WARDEN_PINNED_VERSION},
            )
            release = await asyncio.to_thread(warden.install_pinned_warden, storage.data_dir)
            with storage.transaction() as conn:
                server = mcp.install_server(
                    conn,
                    warden.install_request_for(storage.data_dir, release),
                    McpCatalog(servers=[]),
                )
                synced = _sync_warden(conn, reason="warden_installed")
                audit(
                    conn,
                    AuditRecord(
                        entity_type="mcp_server",
                        entity_id=server.id,
                        action="install",
                        source=AuditSource.DESKTOP,
                        result="success",
                        details={
                            "transport": server.transport.value,
                            "source_url": release.source_url,
                            "version": release.version,
                            "commit": release.commit,
                            "verified": True,
                        },
                    ),
                )
            await _publish(
                request,
                "installed",
                {
                    "server_id": server.id,
                    "server": mcp.client_dump(server),
                    "warden_registry": synced.model_dump(mode="json") if synced else None,
                },
            )
            return mcp.client_dump(server)

        if payload.catalog_id == mcp.WEB_SCRAPER_SERVER_ID:
            if mcp.find_known_web_scraper_server(storage.conn) is not None:
                raise mcp.conflict(
                    "mcp_server",
                    "Web Scraper is already installed.",
                )
            install_root = mcp.ensure_web_scraper_checkout(storage.data_dir)
            with storage.transaction() as conn:
                server = mcp.ensure_bootstrap_web_scraper(conn, source_path=install_root)
                if server is None:
                    raise mcp.invalid(
                        "mcp_server",
                        "Could not finish installing the Web Scraper MCP.",
                    )
                audit(
                    conn,
                    AuditRecord(
                        entity_type="mcp_server",
                        entity_id=server.id,
                        action="install",
                        source=AuditSource.DESKTOP,
                        result="success",
                        details={"transport": server.transport.value, "bootstrap": "github"},
                    ),
                )
                _sync_warden(conn, reason="web_scraper_installed")
            await _publish(
                request,
                "installed",
                {"server_id": server.id, "server": mcp.client_dump(server)},
            )
            return mcp.client_dump(server)

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
            _sync_warden(conn, reason="mcp_server_installed")
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
            _sync_warden(conn, reason="mcp_server_updated")
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
            if server_id != warden.WARDEN_SERVER_ID:
                _sync_warden(conn, reason="mcp_server_uninstalled")
        await _publish(
            request,
            "uninstalled",
            {"server_id": server.id, "server": mcp.client_dump(server)},
        )

    @router.get("/warden/status", response_model=warden.WardenStatus)
    async def warden_status() -> warden.WardenStatus:
        return warden.status(storage.conn, storage.data_dir)

    @router.post("/warden/sync", response_model=warden.WardenRegistrySync)
    async def sync_warden(request: Request) -> warden.WardenRegistrySync:
        with storage.transaction() as conn:
            result = warden.sync_registry(conn, storage.data_dir)
            audit(
                conn,
                AuditRecord(
                    entity_type="mcp_server",
                    entity_id=warden.WARDEN_SERVER_ID,
                    action="registry_sync",
                    source=AuditSource.DESKTOP,
                    result="success",
                    details=result.model_dump(mode="json", exclude={"config_path"}),
                ),
            )
        await _publish(
            request,
            "warden_registry_synced",
            {"server_id": warden.WARDEN_SERVER_ID, "registry": result.model_dump(mode="json")},
        )
        return result

    @router.post("/warden/update", response_model=warden.WardenStatus)
    async def update_warden(request: Request) -> warden.WardenStatus:
        mcp.get_server(storage.conn, warden.WARDEN_SERVER_ID)
        release = await asyncio.to_thread(warden.install_pinned_warden, storage.data_dir)
        with storage.transaction() as conn:
            warden.activate_release(conn, storage.data_dir, release)
            synced = warden.sync_registry(conn, storage.data_dir)
            audit(
                conn,
                AuditRecord(
                    entity_type="mcp_server",
                    entity_id=warden.WARDEN_SERVER_ID,
                    action="update",
                    source=AuditSource.DESKTOP,
                    result="success",
                    details={"version": release.version, "commit": release.commit, "verified": True},
                ),
            )
        result = warden.status(storage.conn, storage.data_dir)
        await _publish(
            request,
            "warden_updated",
            {
                "server_id": warden.WARDEN_SERVER_ID,
                "version": release.version,
                "registry": synced.model_dump(mode="json"),
            },
        )
        return result

    @router.post("/warden/rollback", response_model=warden.WardenStatus)
    async def rollback_warden(request: Request) -> warden.WardenStatus:
        with storage.transaction() as conn:
            release = warden.rollback(conn, storage.data_dir)
            audit(
                conn,
                AuditRecord(
                    entity_type="mcp_server",
                    entity_id=warden.WARDEN_SERVER_ID,
                    action="rollback",
                    source=AuditSource.DESKTOP,
                    result="success",
                    details={"version": release.version, "commit": release.commit, "verified": True},
                ),
            )
        result = warden.status(storage.conn, storage.data_dir)
        await _publish(
            request,
            "warden_rolled_back",
            {"server_id": warden.WARDEN_SERVER_ID, "version": release.version},
        )
        return result

    return router
