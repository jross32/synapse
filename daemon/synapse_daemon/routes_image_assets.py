"""Canonical REST surface for project-scoped image assets.

Human clients and AI connectors share the same provider-neutral generation/edit services and
project-local provenance catalog, so path confinement and audit behavior cannot drift.
"""

from __future__ import annotations

import asyncio
from typing import Any, Literal

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from . import image_asset_catalog, image_assets, image_credentials, image_editing, image_imports, image_uploads
from . import projects as projects_module
from .errors import SynapseError
from .storage import Storage


class ImageGenerationSupports(BaseModel):
    generation: bool
    editing: bool
    importing: bool
    chunked_upload: bool
    formats: list[str]
    quality: list[str]
    background: list[str]
    project_scoped_output: bool
    asset_manifest: bool


class ImageGenerationStatusResponse(BaseModel):
    capability: str
    configured: bool
    provider: str
    model: str | None = None
    credential: str | None = None
    credential_source: str | None = None
    supports: ImageGenerationSupports | None = None
    reason: str | None = None
    supported_providers: list[str] | None = None


class OpenAIImageCredentialRequest(BaseModel):
    api_key: str = Field(min_length=1, max_length=4_096)


class GenerateImageRequest(BaseModel):
    project_id: str = Field(min_length=1, max_length=200)
    prompt: str = Field(min_length=1, max_length=32_000)
    relative_path: str = Field(
        min_length=1,
        max_length=1_024,
        description="Project-relative output path, for example public/images/hero.webp.",
    )
    size: str = Field(default="auto", max_length=32)
    quality: Literal["auto", "low", "medium", "high"] = "auto"
    output_format: Literal["png", "jpeg", "webp"] = "png"
    background: Literal["auto", "opaque", "transparent"] = "auto"
    overwrite: bool = False


class GenerateImageResponse(BaseModel):
    project_id: str
    created: bool
    project_relative_path: str
    absolute_path: str
    manifest_path: str
    provider: str
    model: str
    size: str
    quality: str
    format: str
    background: str
    bytes: int
    sha256: str
    request_id: str | None = None


class EditImageRequest(BaseModel):
    project_id: str = Field(min_length=1, max_length=200)
    prompt: str = Field(min_length=1, max_length=32_000)
    input_paths: list[str] = Field(min_length=1)
    relative_path: str = Field(min_length=1, max_length=1_024)
    mask_path: str | None = Field(default=None, max_length=1_024)
    size: str = Field(default="auto", max_length=32)
    quality: Literal["auto", "low", "medium", "high"] = "auto"
    output_format: Literal["png", "jpeg", "webp"] = "png"
    background: Literal["auto", "opaque", "transparent"] = "auto"
    overwrite: bool = False


class EditImageResponse(BaseModel):
    project_id: str
    created: bool
    kind: str
    project_relative_path: str
    source_paths: list[str]
    mask_path: str | None = None
    manifest_path: str
    provider: str
    model: str
    size: str
    quality: str
    format: str
    background: str
    bytes: int
    sha256: str
    request_id: str | None = None


class BeginImageUploadRequest(BaseModel):
    project_id: str = Field(min_length=1, max_length=200)
    relative_path: str = Field(min_length=1, max_length=1_024)
    source_name: str | None = Field(default=None, max_length=255)
    origin: str = Field(default="ai_native_upload", max_length=200)
    provider: str | None = Field(default=None, max_length=200)
    model: str | None = Field(default=None, max_length=200)
    prompt: str | None = Field(default=None, max_length=32_000)
    overwrite: bool = False
    expected_sha256: str | None = Field(default=None, max_length=64)


class AppendImageUploadRequest(BaseModel):
    chunk_base64: str = Field(min_length=1, max_length=1_100_000)


class ImportImageFileRequest(BaseModel):
    project_id: str = Field(min_length=1, max_length=200)
    source_path: str = Field(min_length=1, max_length=4_096)
    relative_path: str = Field(min_length=1, max_length=1_024)
    origin: str = Field(default="local_file", max_length=200)
    provider: str | None = Field(default=None, max_length=200)
    model: str | None = Field(default=None, max_length=200)
    prompt: str | None = Field(default=None, max_length=32_000)
    overwrite: bool = False


class ImportImageFileResponse(BaseModel):
    project_id: str
    created: bool
    kind: str
    project_relative_path: str
    absolute_path: str
    manifest_path: str
    source_name: str
    origin: str
    provider: str | None = None
    model: str | None = None
    width: int
    height: int
    has_alpha: bool
    format: str
    bytes: int
    sha256: str


def _as_import_synapse_error(exc: image_imports.ImageImportError) -> SynapseError:
    return SynapseError(
        code=exc.code,
        message=str(exc),
        retryable=exc.retryable,
        status=exc.status,
    )


def _as_synapse_error(exc: image_assets.ImageGenerationError) -> SynapseError:
    return SynapseError(
        code=exc.code,
        message=str(exc),
        retryable=exc.retryable,
        status=exc.status,
    )


def _as_edit_synapse_error(exc: image_editing.ImageEditError) -> SynapseError:
    return SynapseError(
        code=exc.code,
        message=str(exc),
        retryable=exc.retryable,
        status=exc.status,
    )


def build_image_generation_router(storage: Storage) -> APIRouter:
    """Build the daemon's canonical image-asset API."""
    router = APIRouter(prefix="/image-generation", tags=["image-generation"])

    @router.get("/status", response_model=ImageGenerationStatusResponse)
    async def image_generation_status() -> ImageGenerationStatusResponse:
        return ImageGenerationStatusResponse.model_validate(
            image_assets.image_generation_status(storage)
        )

    @router.put("/credentials/openai")
    async def set_openai_image_credential(
        payload: OpenAIImageCredentialRequest,
    ) -> dict[str, Any]:
        try:
            status = await asyncio.to_thread(
                image_credentials.set_openai_api_key,
                storage,
                payload.api_key,
            )
        except image_credentials.ImageCredentialError as exc:
            raise SynapseError(
                code="image_credentials.invalid",
                message=str(exc),
                retryable=False,
                status=422,
            ) from exc
        return {
            "provider": "openai",
            "configured": status["configured"],
            "source": status["source"],
            "stored_secret": status["stored_secret"],
            "environment_override": status["environment_override"],
        }

    @router.delete("/credentials/openai")
    async def clear_openai_image_credential() -> dict[str, Any]:
        status = await asyncio.to_thread(image_credentials.clear_openai_api_key, storage)
        return {
            "provider": "openai",
            "configured": status["configured"],
            "source": status["source"],
            "stored_secret": status["stored_secret"],
            "environment_override": status["environment_override"],
        }

    @router.post("/generate", response_model=GenerateImageResponse)
    async def generate_image(payload: GenerateImageRequest) -> GenerateImageResponse:
        try:
            result: dict[str, Any] = await asyncio.to_thread(
                image_assets.generate_project_image,
                storage,
                project_id=payload.project_id,
                prompt=payload.prompt,
                relative_path=payload.relative_path,
                size=payload.size,
                quality=payload.quality,
                output_format=payload.output_format,
                background=payload.background,
                overwrite=payload.overwrite,
                audit_source="auto",
            )
        except image_assets.ImageGenerationError as exc:
            raise _as_synapse_error(exc) from exc

        return GenerateImageResponse.model_validate(result)

    @router.post("/uploads/begin")
    async def begin_image_upload(payload: BeginImageUploadRequest) -> dict[str, Any]:
        try:
            return await asyncio.to_thread(
                image_uploads.begin_image_upload,
                storage,
                project_id=payload.project_id,
                relative_path=payload.relative_path,
                source_name=payload.source_name,
                origin=payload.origin,
                provider=payload.provider,
                model=payload.model,
                prompt=payload.prompt,
                overwrite=payload.overwrite,
                expected_sha256=payload.expected_sha256,
            )
        except image_uploads.ImageUploadError as exc:
            raise SynapseError(
                code=exc.code,
                message=str(exc),
                retryable=exc.retryable,
                status=exc.status,
            ) from exc

    @router.post("/uploads/{upload_id}/append")
    async def append_image_upload(
        upload_id: str,
        payload: AppendImageUploadRequest,
    ) -> dict[str, Any]:
        try:
            return await asyncio.to_thread(
                image_uploads.append_image_upload_chunk,
                storage,
                upload_id=upload_id,
                chunk_base64=payload.chunk_base64,
            )
        except image_uploads.ImageUploadError as exc:
            raise SynapseError(
                code=exc.code,
                message=str(exc),
                retryable=exc.retryable,
                status=exc.status,
            ) from exc

    @router.post("/uploads/{upload_id}/finish")
    async def finish_image_upload(upload_id: str) -> dict[str, Any]:
        try:
            return await asyncio.to_thread(
                image_uploads.finish_image_upload,
                storage,
                upload_id=upload_id,
                audit_source="auto",
            )
        except image_uploads.ImageUploadError as exc:
            raise SynapseError(
                code=exc.code,
                message=str(exc),
                retryable=exc.retryable,
                status=exc.status,
            ) from exc

    @router.post("/import-file", response_model=ImportImageFileResponse)
    async def import_image_file(payload: ImportImageFileRequest) -> ImportImageFileResponse:
        try:
            result: dict[str, Any] = await asyncio.to_thread(
                image_imports.import_project_image_file,
                storage,
                project_id=payload.project_id,
                source_path=payload.source_path,
                relative_path=payload.relative_path,
                origin=payload.origin,
                provider=payload.provider,
                model=payload.model,
                prompt=payload.prompt,
                overwrite=payload.overwrite,
                audit_source="auto",
            )
        except image_imports.ImageImportError as exc:
            raise _as_import_synapse_error(exc) from exc

        return ImportImageFileResponse.model_validate(result)

    @router.post("/edit", response_model=EditImageResponse)
    async def edit_image(payload: EditImageRequest) -> EditImageResponse:
        try:
            result: dict[str, Any] = await asyncio.to_thread(
                image_editing.edit_project_image,
                storage,
                project_id=payload.project_id,
                prompt=payload.prompt,
                input_paths=payload.input_paths,
                relative_path=payload.relative_path,
                mask_path=payload.mask_path,
                size=payload.size,
                quality=payload.quality,
                output_format=payload.output_format,
                background=payload.background,
                overwrite=payload.overwrite,
                audit_source="auto",
            )
        except image_editing.ImageEditError as exc:
            raise _as_edit_synapse_error(exc) from exc

        return EditImageResponse.model_validate(result)

    @router.get("/assets/{project_id}")
    async def list_project_images(
        project_id: str,
        verify_hashes: bool = Query(default=False),
    ) -> dict[str, Any]:
        project = projects_module.get(storage.conn, project_id)
        return await asyncio.to_thread(
            image_asset_catalog.load_image_assets,
            project.path,
            verify_hashes=verify_hashes,
        )

    @router.get("/asset/{project_id}")
    async def get_image_asset(
        project_id: str,
        relative_path: str = Query(min_length=1, max_length=1_024),
        verify_hash: bool = Query(default=False),
    ) -> dict[str, Any]:
        project = projects_module.get(storage.conn, project_id)
        return {
            "project_id": project_id,
            "asset": await asyncio.to_thread(
                image_asset_catalog.get_image_asset,
                project.path,
                relative_path,
                verify_hash=verify_hash,
            ),
        }

    @router.get("/assets/{project_id}/audit")
    async def audit_project_images(project_id: str) -> dict[str, Any]:
        project = projects_module.get(storage.conn, project_id)
        return {
            "project_id": project_id,
            **await asyncio.to_thread(image_asset_catalog.audit_image_assets, project.path),
        }

    return router
