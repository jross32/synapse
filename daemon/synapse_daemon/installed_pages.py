"""Curated dedicated pages that can appear in Synapse.

The first pass is intentionally small and opinionated: we surface a dedicated
page for the owner's Web Scraper when an installed MCP server looks like that
integration. Visibility is user-controlled in the renderer; this module only
answers "is this page available?" and "what state is it in right now?".
"""

from __future__ import annotations

from enum import Enum
from typing import Any
from urllib.parse import urlparse

import httpx
from pydantic import BaseModel, Field

from . import mcp_servers as mcp

_SCRAPER_TIMEOUT_SECONDS = 3.0
_KNOWN_WEB_SCRAPER_IDS = {"web-scraper", "wbscrper"}


class InstalledPageStatus(str, Enum):
    CONNECTED = "connected"
    AVAILABLE = "available"
    OFFLINE = "offline"
    ERROR = "error"


class InstalledPageView(BaseModel):
    id: str
    label: str
    description: str
    icon: str = "globe"
    route_kind: str = "dedicated-page"
    source_kind: str = "mcp-server"
    source_id: str
    default_visible: bool = False
    status: InstalledPageStatus = InstalledPageStatus.AVAILABLE
    detail: str | None = None


class InstalledPageList(BaseModel):
    pages: list[InstalledPageView] = Field(default_factory=list)


class WebScraperOverview(BaseModel):
    id: str = "web-scraper"
    label: str = "Web Scraper"
    status: InstalledPageStatus
    detail: str | None = None
    source_id: str
    source_url: str | None = None
    base_url: str | None = None
    docs_url: str | None = None
    ui_url: str | None = None
    tool_count: int | None = None
    prompt_count: int | None = None


def _base_url_from_mcp_url(url: str | None) -> str | None:
    if not url:
        return None
    trimmed = url.rstrip("/")
    if trimmed.endswith("/mcp"):
        trimmed = trimmed[: -len("/mcp")]
    return trimmed


def _web_scraper_base_url(server: mcp.McpServer) -> str | None:
    configured = server.env.get("SCRAPER_URL")
    if isinstance(configured, str) and configured.startswith(("http://", "https://")):
        return configured.rstrip("/")
    parsed = urlparse(server.url or "")
    if server.id in _KNOWN_WEB_SCRAPER_IDS and parsed.port == mcp.WEB_SCRAPER_MCP_PORT:
        return mcp.WEB_SCRAPER_APP_BASE_URL
    return _base_url_from_mcp_url(server.url)


def _count_from_meta(meta: dict[str, Any], *keys: str) -> int | None:
    for key in keys:
        value = meta.get(key)
        if isinstance(value, int):
            return value
    server_info = meta.get("server_info")
    if isinstance(server_info, dict):
        for key in keys:
            value = server_info.get(key)
            if isinstance(value, int):
                return value
    return None


def _is_web_scraper_meta(meta: dict[str, Any]) -> bool:
    server = meta.get("server")
    if isinstance(server, dict) and server.get("name") == "web-scraper":
        return True
    server_info = meta.get("server_info")
    if isinstance(server_info, dict) and server_info.get("name") == "web-scraper":
        return True
    return False


async def _fetch_meta(base_url: str) -> tuple[dict[str, Any] | None, str | None]:
    url = f"{base_url.rstrip('/')}/api/mcp-meta"
    try:
        async with httpx.AsyncClient(timeout=_SCRAPER_TIMEOUT_SECONDS) as client:
            response = await client.get(url)
            response.raise_for_status()
            payload = response.json()
    except httpx.HTTPError as exc:
        return None, f"Could not reach {urlparse(base_url).netloc}."
    except ValueError:
        return None, "The endpoint responded, but not with JSON."
    if not isinstance(payload, dict):
        return None, "The endpoint responded, but not with the expected metadata."
    return payload, None


async def _overview_for_server(server: mcp.McpServer) -> WebScraperOverview:
    base_url = _web_scraper_base_url(server)
    if not base_url:
        return WebScraperOverview(
            status=InstalledPageStatus.AVAILABLE,
            detail="Install is present, but no HTTP URL is configured yet.",
            source_id=server.id,
            source_url=server.url,
            base_url=base_url,
        )
    meta, error = await _fetch_meta(base_url)
    if meta is None:
        return WebScraperOverview(
            status=InstalledPageStatus.OFFLINE,
            detail=error or "The scraper is installed, but currently offline.",
            source_id=server.id,
            source_url=server.url,
            base_url=base_url,
            docs_url=f"{base_url}/docs",
            ui_url=base_url,
        )
    if not _is_web_scraper_meta(meta):
        return WebScraperOverview(
            status=InstalledPageStatus.ERROR,
            detail="Connected, but this endpoint does not fingerprint as Web Scraper.",
            source_id=server.id,
            source_url=server.url,
            base_url=base_url,
            docs_url=f"{base_url}/docs",
            ui_url=base_url,
        )
    return WebScraperOverview(
        status=InstalledPageStatus.CONNECTED,
        detail=None,
        source_id=server.id,
        source_url=server.url,
        base_url=base_url,
        docs_url=f"{base_url}/docs",
        ui_url=base_url,
        tool_count=_count_from_meta(meta, "tools_count", "tool_count"),
        prompt_count=_count_from_meta(meta, "prompts_count", "prompt_count"),
    )


def _rank_overview(server: mcp.McpServer, overview: WebScraperOverview) -> tuple[int, int, str]:
    status_rank = {
        InstalledPageStatus.CONNECTED: 0,
        InstalledPageStatus.AVAILABLE: 1,
        InstalledPageStatus.OFFLINE: 2,
        InstalledPageStatus.ERROR: 3,
    }[overview.status]
    known_rank = 0 if server.id in _KNOWN_WEB_SCRAPER_IDS else 1
    return (status_rank, known_rank, server.id)


async def get_web_scraper_overview(conn) -> WebScraperOverview | None:  # noqa: ANN001
    candidates: list[tuple[tuple[int, int, str], WebScraperOverview]] = []
    for server in mcp.list_servers(conn):
        if server.transport != mcp.McpTransport.HTTP:
            continue
        overview = await _overview_for_server(server)
        # Visibility is driven by install state, not runtime state:
        # - known ids stay eligible while offline / unavailable
        # - an endpoint that answers but fingerprints as something else is not
        #   eligible and should disappear from Installed Pages
        is_known = server.id in _KNOWN_WEB_SCRAPER_IDS
        if overview.status == InstalledPageStatus.ERROR:
            if not is_known:
                continue
            # A known-id server that answers with the wrong fingerprint is not
            # the scraper anymore, so treat it as ineligible.
            continue
        if is_known or overview.status == InstalledPageStatus.CONNECTED:
            candidates.append((_rank_overview(server, overview), overview))
    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0])
    return candidates[0][1]


async def list_installed_pages(conn) -> list[InstalledPageView]:  # noqa: ANN001
    overview = await get_web_scraper_overview(conn)
    if overview is None:
        return []
    return [
        InstalledPageView(
            id="web-scraper",
            label="Web Scraper",
            description="A dedicated browser + scraping workspace for your installed Web Scraper MCP server.",
            icon="globe",
            route_kind="dedicated-page",
            source_kind="mcp-server",
            source_id=overview.source_id,
            default_visible=False,
            status=overview.status,
            detail=overview.detail,
        )
    ]


__all__ = [
    "InstalledPageList",
    "InstalledPageStatus",
    "InstalledPageView",
    "WebScraperOverview",
    "get_web_scraper_overview",
    "list_installed_pages",
]
