"""Canonical REST surface for Synapse Video Studio.

Human clients and AI connectors call the same project-scoped planning/render services, so
provider credentials, path confinement, provenance, and long-form continuity limits cannot
drift between UI and MCP entry points.
"""

from __future__ import annotations

import asyncio
from typing import Any, Literal

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from . import projects as projects_module
from . import video_asset_catalog, video_assets, video_credentials
from .errors import SynapseError
from .storage import Storage


class VideoCredentialRequest(BaseModel):
    api_key: str = Field(min_length=1, max_length=4_096)


class VideoShotRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=12_000)
    duration_seconds: int = Field(default=8, ge=3, le=10)
    continuity_group: str | None = Field(default=None, max_length=120)
    dialogue: str | None = Field(default=None, max_length=4_000)
    audio_cues: str | None = Field(default=None, max_length=4_000)
    transition: str | None = Field(default=None, max_length=200)
    bridge_from_previous: bool = False


class CreateVideoPlanRequest(BaseModel):
    project_id: str = Field(min_length=1, max_length=200)
    title: str = Field(min_length=1, max_length=300)
    brief: str = Field(min_length=1, max_length=32_000)
    shots: list[VideoShotRequest] = Field(min_length=1)
    aspect_ratio: Literal["16:9", "9:16"] = "16:9"
    resolution: Literal["360p", "720p", "1080p", "4k"] = "720p"
    audio_mode: Literal["native", "silent"] = "native"
    story_bible: str = Field(default="", max_length=32_000)
    character_bible: str = Field(default="", max_length=32_000)
    style_bible: str = Field(default="", max_length=32_000)
    reference_paths: list[str] = Field(default_factory=list, max_length=14)


class StartVideoRenderRequest(BaseModel):
    project_id: str = Field(min_length=1, max_length=200)
    plan_id: str = Field(min_length=1, max_length=100)
    relative_path: str = Field(min_length=1, max_length=1_024)
    overwrite: bool = False


class CancelVideoRenderRequest(BaseModel):
    project_id: str = Field(min_length=1, max_length=200)
    job_id: str = Field(min_length=1, max_length=100)


def _as_video_error(exc: video_assets.VideoStudioError) -> SynapseError:
    return SynapseError(code=exc.code, message=str(exc), retryable=exc.retryable, status=exc.status)


def _as_credential_error(exc: video_credentials.VideoCredentialError) -> SynapseError:
    return SynapseError(
        code="video_credentials.invalid",
        message=str(exc),
        retryable=False,
        status=422,
    )


def build_video_generation_router(storage: Storage) -> APIRouter:
    router = APIRouter(prefix="/video-generation", tags=["video-generation"])

    @router.get("/status")
    async def status() -> dict[str, Any]:
        return video_assets.video_generation_status(storage)

    @router.put("/credentials/{provider}")
    async def set_credential(provider: Literal["google", "runway"], payload: VideoCredentialRequest) -> dict[str, Any]:
        try:
            result = await asyncio.to_thread(video_credentials.set_api_key, storage, provider, payload.api_key)
        except video_credentials.VideoCredentialError as exc:
            raise _as_credential_error(exc) from exc
        return {"provider": provider, **result}

    @router.delete("/credentials/{provider}")
    async def clear_credential(provider: Literal["google", "runway"]) -> dict[str, Any]:
        try:
            result = await asyncio.to_thread(video_credentials.clear_api_key, storage, provider)
        except video_credentials.VideoCredentialError as exc:
            raise _as_credential_error(exc) from exc
        return {"provider": provider, **result}

    @router.post("/plans")
    async def create_plan(payload: CreateVideoPlanRequest) -> dict[str, Any]:
        try:
            return await asyncio.to_thread(
                video_assets.create_video_plan,
                storage,
                project_id=payload.project_id,
                title=payload.title,
                brief=payload.brief,
                shots=[shot.model_dump(exclude_none=True) for shot in payload.shots],
                aspect_ratio=payload.aspect_ratio,
                resolution=payload.resolution,
                audio_mode=payload.audio_mode,
                story_bible=payload.story_bible,
                character_bible=payload.character_bible,
                style_bible=payload.style_bible,
                reference_paths=payload.reference_paths,
            )
        except video_assets.VideoStudioError as exc:
            raise _as_video_error(exc) from exc

    @router.get("/projects/{project_id}/plans/{plan_id}")
    async def get_plan(project_id: str, plan_id: str) -> dict[str, Any]:
        try:
            return await asyncio.to_thread(
                video_assets.get_video_plan,
                storage,
                project_id=project_id,
                plan_id=plan_id,
            )
        except video_assets.VideoStudioError as exc:
            raise _as_video_error(exc) from exc

    @router.post("/renders")
    async def start_render(payload: StartVideoRenderRequest) -> dict[str, Any]:
        try:
            return await asyncio.to_thread(
                video_assets.start_video_render,
                storage,
                project_id=payload.project_id,
                plan_id=payload.plan_id,
                relative_path=payload.relative_path,
                overwrite=payload.overwrite,
            )
        except video_assets.VideoStudioError as exc:
            raise _as_video_error(exc) from exc

    @router.get("/projects/{project_id}/renders/{job_id}")
    async def get_render(project_id: str, job_id: str) -> dict[str, Any]:
        try:
            return await asyncio.to_thread(
                video_assets.get_video_job,
                storage,
                project_id=project_id,
                job_id=job_id,
            )
        except video_assets.VideoStudioError as exc:
            raise _as_video_error(exc) from exc

    @router.post("/renders/cancel")
    async def cancel_render(payload: CancelVideoRenderRequest) -> dict[str, Any]:
        try:
            return await asyncio.to_thread(
                video_assets.cancel_video_render,
                storage,
                project_id=payload.project_id,
                job_id=payload.job_id,
            )
        except video_assets.VideoStudioError as exc:
            raise _as_video_error(exc) from exc

    @router.get("/projects/{project_id}/assets")
    async def list_assets(
        project_id: str,
        verify_hashes: bool = Query(default=False),
    ) -> dict[str, Any]:
        project = projects_module.get(storage.conn, project_id)
        return await asyncio.to_thread(
            video_asset_catalog.load_video_assets,
            project.path,
            verify_hashes=verify_hashes,
        )

    @router.get("/projects/{project_id}/assets/audit")
    async def audit_assets(project_id: str) -> dict[str, Any]:
        project = projects_module.get(storage.conn, project_id)
        return {"project_id": project_id, **await asyncio.to_thread(video_asset_catalog.audit_video_assets, project.path)}

    return router
