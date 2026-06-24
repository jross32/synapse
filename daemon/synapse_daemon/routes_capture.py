"""REST for the Capture inbox (ADR-0016, Phase R)."""

from __future__ import annotations

from fastapi import APIRouter

from . import capture as capture_mod
from .audit import AuditRecord, audit
from .capture import CaptureRequest, CaptureResult
from .storage import Storage


def build_capture_router(storage: Storage) -> APIRouter:
    router = APIRouter(prefix="/capture", tags=["capture"])

    @router.post("", response_model=CaptureResult)
    async def create_capture(payload: CaptureRequest) -> CaptureResult:
        with storage.transaction() as conn:
            result = capture_mod.capture(conn, storage.data_dir, payload)
            audit(
                conn,
                AuditRecord(
                    entity_type="capture",
                    entity_id=result.ref_id or result.project_id,
                    action=f"capture_{result.destination.value}",
                    source=payload.source,
                    result="success",
                    details={"project_id": result.project_id},
                ),
            )
        return result

    return router
