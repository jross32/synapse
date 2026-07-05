"""Installed dedicated pages + curated proxy routes."""

from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any

import httpx
from fastapi import APIRouter
from pydantic import BaseModel, Field

from . import benchmarks
from . import files_storage
from . import projects as projects_module
from .audit import AuditRecord, audit
from .errors import SynapseError
from .installed_pages import InstalledPageList, WebScraperOverview, get_web_scraper_overview, list_installed_pages
from .models import AuditSource
from .storage import Storage

_PROXY_TIMEOUT_SECONDS = 20.0
_HARVEST_ACTIONS: tuple[dict[str, str], ...] = (
    {"id": "capture", "label": "Capture", "description": "Capture a reference URL with a screenshot-first pass."},
    {"id": "research_url", "label": "Summarize", "description": "Summarize the reference page and navigate it for the stated goal."},
    {"id": "to_markdown", "label": "Reference brief", "description": "Turn a page into a reusable Markdown brief for a project."},
    {"id": "extract_styles", "label": "Extract styles", "description": "Pull colors, type, spacing, and notable styling cues."},
    {"id": "extract_structure", "label": "Extract structure", "description": "Pull layout, sections, and content hierarchy notes."},
    {"id": "generate_react", "label": "Generate React", "description": "Generate a reusable React component candidate from the page."},
    {"id": "generate_css", "label": "Generate CSS", "description": "Generate CSS or tokens aligned with the reference."},
    {"id": "infer_schema", "label": "Infer schema", "description": "Infer typed data contracts from the page."},
)
_HARVEST_ACTION_IDS = {item["id"] for item in _HARVEST_ACTIONS}


class HarvestArtifactInput(BaseModel):
    name: str
    kind: str = "artifact"
    mime: str = "text/plain"
    content: str | dict[str, Any] | list[Any]
    metadata: dict[str, Any] = Field(default_factory=dict)


class SaveHarvestArtifactsRequest(BaseModel):
    project_id: str
    reference_urls: list[str] = Field(default_factory=list)
    provenance_mode: str = "inspiration-only"
    originality_notes: str = ""
    benchmark_attempt_id: str | None = None
    artifacts: list[HarvestArtifactInput] = Field(default_factory=list)


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

    @router.get("/web-scraper/harvest-capabilities", response_model=None)
    async def web_scraper_harvest_capabilities() -> dict[str, Any]:
        return {
            "actions": list(_HARVEST_ACTIONS),
            "adaptation_modes": [
                {"id": "inspiration-only", "label": "Inspiration only"},
                {"id": "licensed-close-copy", "label": "Licensed close-copy"},
                {"id": "regenerated-original-output", "label": "Regenerated original output"},
            ],
        }

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

    @router.post("/web-scraper/actions/{action}", response_model=None)
    async def web_scraper_action(action: str, payload: dict[str, Any] | None = None) -> Any:
        normalized = action.strip().lower()
        if normalized not in _HARVEST_ACTION_IDS:
            raise SynapseError(
                code="web_scraper.unsupported_action",
                message=f"Unsupported design-harvest action: {action}",
                details={"allowed_actions": sorted(_HARVEST_ACTION_IDS)},
                status=422,
            )
        return await _proxy_json("POST", f"/api/{normalized}", body=payload or {})

    @router.post("/web-scraper/save-artifacts", response_model=None)
    async def web_scraper_save_artifacts(payload: SaveHarvestArtifactsRequest) -> dict[str, Any]:
        if not payload.artifacts:
            raise SynapseError(
                code="web_scraper.no_artifacts",
                message="At least one artifact is required to save a harvest result.",
                status=422,
            )
        project = projects_module.get(storage.conn, payload.project_id)
        saved_rows: list[dict[str, Any]] = []
        with storage.transaction() as conn:
            if payload.benchmark_attempt_id:
                benchmarks.get_attempt(conn, payload.benchmark_attempt_id)
            manifest = {
                "reference_urls": payload.reference_urls,
                "provenance_mode": payload.provenance_mode,
                "originality_notes": payload.originality_notes,
                "artifact_names": [artifact.name for artifact in payload.artifacts],
            }
            manifest_row = files_storage.save_generated_file(
                conn,
                storage.data_dir,
                project_id=project.id,
                original_name="design-harvest-manifest.json",
                content=json.dumps(manifest, indent=2).encode("utf-8"),
                mime="application/json",
                source_session="web-scraper-harvest",
            )
            saved_rows.append(asdict(manifest_row))
            for artifact in payload.artifacts:
                content = artifact.content
                if isinstance(content, str):
                    bytes_payload = content.encode("utf-8")
                else:
                    bytes_payload = json.dumps(content, indent=2).encode("utf-8")
                row = files_storage.save_generated_file(
                    conn,
                    storage.data_dir,
                    project_id=project.id,
                    original_name=artifact.name,
                    content=bytes_payload,
                    mime=artifact.mime,
                    source_session="web-scraper-harvest",
                )
                saved_rows.append(asdict(row))
                if payload.benchmark_attempt_id:
                    benchmarks.add_artifact(
                        conn,
                        payload.benchmark_attempt_id,
                        kind=artifact.kind,
                        label=artifact.name,
                        path=str(files_storage.final_dir_for(storage.data_dir, row.project_id) / row.on_disk_name),
                        mime=artifact.mime,
                        metadata={
                            **artifact.metadata,
                            "reference_urls": payload.reference_urls,
                            "provenance_mode": payload.provenance_mode,
                        },
                    )
            audit(
                conn,
                AuditRecord(
                    entity_type="project",
                    entity_id=project.id,
                    action="web_scraper.harvest_save",
                    source=AuditSource.DESKTOP,
                    result="success",
                    details={
                        "artifact_count": len(payload.artifacts),
                        "benchmark_attempt_id": payload.benchmark_attempt_id,
                        "provenance_mode": payload.provenance_mode,
                        "reference_urls": payload.reference_urls,
                    },
                ),
            )
        return {
            "project_id": project.id,
            "saved": saved_rows,
            "provenance_mode": payload.provenance_mode,
        }

    return router
