"""REST for the What's New + Roadmap surface (ADR-0019)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pathlib import Path
from .runtime_paths import repo_root

from . import about
from .about import Changelog, Roadmap
from .release_manifest import ReleaseManifest, release_manifest


def build_about_router() -> APIRouter:
    router = APIRouter(prefix="/about", tags=["about"])

    @router.get("/changelog", response_model=Changelog)
    async def changelog() -> Changelog:
        return about.load_changelog()

    @router.get("/roadmap", response_model=Roadmap)
    async def roadmap() -> Roadmap:
        return about.load_roadmap()

    @router.get("/releases", response_model=ReleaseManifest)
    async def releases() -> ReleaseManifest:
        return release_manifest()

    @router.get("/download/{filename}")
    async def download(filename: str):
        manifest = release_manifest()
        artifact = next((a for a in manifest.artifacts if a.filename == filename and a.status == "ready"), None)
        if artifact is None or Path(filename).name != filename:
            raise HTTPException(status_code=404, detail="Release not found")
        file_path = repo_root() / "release" / filename
        if not file_path.is_file():
            raise HTTPException(status_code=404, detail="Release not found")
        return FileResponse(file_path, filename=filename, media_type="application/octet-stream")

    return router
