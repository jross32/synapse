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

    return router
