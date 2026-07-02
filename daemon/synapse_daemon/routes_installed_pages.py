"""Installed dedicated pages + curated proxy routes."""

from __future__ import annotations

from typing import Any

import httpx
from fastapi import APIRouter

from .errors import SynapseError
from .installed_pages import InstalledPageList, WebScraperOverview, get_web_scraper_overview, list_installed_pages
from .storage import Storage

_PROXY_TIMEOUT_SECONDS = 20.0


def build_installed_pages_router(storage: Storage) -> APIRouter:
    router = APIRouter(prefix="/installed-pages", tags=["installed-pages"])

    async def _scraper_overview() -> WebScraperOverview:
        overview = await get_web_scraper_overview(storage.conn)
        if overview is None:
            raise SynapseError(
                code="installed_page.not_found",
                message="Web Scraper is not installed or no longer eligible for a dedicated page.",
                status=404,
            )
        return overview

    async def _connected_scraper_base_url() -> str:
        overview = await _scraper_overview()
        if overview.status != "connected" or not overview.base_url:
            raise SynapseError(
                code="web_scraper.offline",
                message="Web Scraper is installed, but it is not connected right now.",
                details={"status": overview.status, "detail": overview.detail},
                retryable=True,
                status=503,
            )
        return overview.base_url.rstrip("/")

    async def _proxy_json(
        method: str,
        path: str,
        *,
        body: dict[str, Any] | None = None,
    ) -> Any:
        base_url = await _connected_scraper_base_url()
        url = f"{base_url}{path}"
        try:
            async with httpx.AsyncClient(timeout=_PROXY_TIMEOUT_SECONDS) as client:
                response = await client.request(method, url, json=body)
                response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            message = f"Web Scraper rejected the request ({exc.response.status_code})."
            details: dict[str, Any] = {"status_code": exc.response.status_code, "url": url}
            try:
                payload = exc.response.json()
                if isinstance(payload, dict):
                    details["upstream"] = payload
                    if isinstance(payload.get("detail"), str):
                        message = payload["detail"]
                else:
                    details["upstream"] = payload
            except ValueError:
                if exc.response.text:
                    details["upstream_text"] = exc.response.text[:500]
            raise SynapseError(
                code="web_scraper.proxy_failed",
                message=message,
                details=details,
                retryable=exc.response.status_code >= 500,
                status=502,
            ) from exc
        except httpx.HTTPError as exc:
            raise SynapseError(
                code="web_scraper.unreachable",
                message="Could not reach the installed Web Scraper server.",
                details={"url": url},
                retryable=True,
                status=502,
            ) from exc
        try:
            return response.json()
        except ValueError as exc:
            raise SynapseError(
                code="web_scraper.invalid_response",
                message="Web Scraper responded, but not with JSON.",
                details={"url": url},
                status=502,
            ) from exc

    @router.get("", response_model=InstalledPageList)
    async def installed_pages() -> InstalledPageList:
        return InstalledPageList(pages=await list_installed_pages(storage.conn))

    @router.get("/web-scraper", response_model=WebScraperOverview)
    async def web_scraper_overview() -> WebScraperOverview:
        return await _scraper_overview()

    @router.get("/web-scraper/saves", response_model=None)
    async def web_scraper_saves() -> Any:
        return await _proxy_json("GET", "/api/saves")

    @router.get("/web-scraper/schedules", response_model=None)
    async def web_scraper_schedules() -> Any:
        return await _proxy_json("GET", "/api/schedules")

    @router.get("/web-scraper/active", response_model=None)
    async def web_scraper_active() -> Any:
        return await _proxy_json("GET", "/api/active")

    @router.post("/web-scraper/scrape-url", response_model=None)
    async def web_scraper_scrape_url(payload: dict[str, Any]) -> Any:
        return await _proxy_json("POST", "/api/scrape_url", body=payload)

    return router

