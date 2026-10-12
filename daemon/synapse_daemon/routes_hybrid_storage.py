"""Authenticated read-only hybrid storage inventory endpoints.

Cloud linking stays disabled until a verified user-to-provider binding exists.
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from .auth import AuthManager, require_token
from .hybrid_storage import disk_capacity, migration_preview, scan_tree


class ScanRequest(BaseModel):
    project_path: str = Field(min_length=1, max_length=4096)


class PreviewRequest(ScanRequest):
    provider: str = "google_drive"
    min_size_bytes: int = Field(default=10 * 1024 * 1024, ge=0)


def build_hybrid_storage_router(auth: AuthManager, allowed_root: Path) -> APIRouter:
    router = APIRouter(prefix="/storage-manager", tags=["storage-manager"],
                       dependencies=[Depends(require_token(auth))])
    base = allowed_root.resolve(strict=True)

    def allowed(path: str) -> Path:
        # Only registered local projects under the user's home directory.
        p = Path(path).resolve(strict=True)
        if p != base and base not in p.parents:
            raise HTTPException(status_code=403, detail="Path outside authorized storage root")
        if not p.is_dir():
            raise HTTPException(status_code=400, detail="Directory required")
        return p

    def check_caller(request: Request) -> None:
        subject = request.state.auth_subject
        if subject.kind == "worker":
            raise HTTPException(status_code=403, detail="Worker tokens cannot inventory user storage")

    @router.get("/providers")
    async def providers(request: Request) -> dict:
        check_caller(request)
        return {"mode": "local_first", "providers": [
            {"id": "local", "status": "ready"},
            {"id": "google_drive", "status": "not_connected", "account_bound": False},
            {"id": "icloud", "status": "not_connected", "account_bound": False},
        ], "cloud_mutations_enabled": False}

    @router.post("/inventory")
    async def inventory(payload: ScanRequest, request: Request) -> dict:
        check_caller(request)
        p = allowed(payload.project_path)
        result = await asyncio.to_thread(scan_tree, p)
        return {"inventory": result.to_dict(), "disk": disk_capacity(p), "read_only": True}

    @router.post("/migration-preview")
    async def preview(payload: PreviewRequest, request: Request) -> dict:
        check_caller(request)
        p = allowed(payload.project_path)
        try:
            return await asyncio.to_thread(
                migration_preview, p, payload.provider, payload.min_size_bytes)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.post("/search")
    async def search(payload: SearchRequest, request: Request) -> dict:
        check_caller(request)
        p = allowed(payload.project_path)
        results = await asyncio.to_thread(search_names, p, payload.query, payload.limit)
        return {"results": results, "read_only": True, "limited": len(results) >= payload.limit}

    return router

class SearchRequest(ScanRequest):
    query: str = Field(min_length=2, max_length=120)
    limit: int = Field(default=50, ge=1, le=100)


def search_names(root: Path, query: str, limit: int) -> list[dict]:
    """Bounded metadata-only filename search, never follows links/junctions."""
    import os
    from .hybrid_storage import DEFAULT_EXCLUSIONS
    found: list[dict] = []
    pending = [root]
    needle = query.casefold()
    visited = 0
    while pending and len(found) < limit and visited < 100000:
        folder = pending.pop()
        try:
            with os.scandir(folder) as entries:
                for entry in entries:
                    visited += 1
                    if visited >= 100000:
                        break
                    try:
                        if entry.is_symlink() or (hasattr(entry, 'is_junction') and entry.is_junction()):
                            continue
                        if entry.is_dir(follow_symlinks=False):
                            if entry.name.lower() not in DEFAULT_EXCLUSIONS:
                                pending.append(Path(entry.path))
                        elif entry.is_file(follow_symlinks=False) and needle in entry.name.casefold():
                            found.append({'name': entry.name, 'relative_path': str(Path(entry.path).relative_to(root)), 'size_bytes': entry.stat(follow_symlinks=False).st_size})
                            if len(found) >= limit:
                                break
                    except OSError:
                        continue
        except OSError:
            continue
    return found
