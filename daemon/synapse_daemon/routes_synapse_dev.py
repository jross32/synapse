"""REST routes for gated Synapse self-improvement developer actions."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from .audit import AuditRecord, audit
from .errors import SynapseError, invalid
from .models import AuditSource
from .seed import SYNAPSE_SELF_PROJECT_ID
from .storage import Storage
from .synapse_dev import SynapseDevManager


class SynapseDevFullTestRequest(BaseModel):
    python_args: list[str] = Field(default_factory=list)
    tsc_args: list[str] = Field(default_factory=list)


class SynapseDevFileTestRequest(BaseModel):
    path: str
    python_args: list[str] = Field(default_factory=list)


def _require_enabled(manager: SynapseDevManager) -> None:
    if manager.enabled():
        return
    raise SynapseError(
        code="synapse_dev.disabled",
        message="Synapse developer actions are disabled.",
        details=manager.require_enabled_message(),
        status=403,
    )


def build_synapse_dev_router(storage: Storage, manager: SynapseDevManager) -> APIRouter:
    router = APIRouter(prefix="/synapse-dev", tags=["synapse-dev"])

    @router.post("/test/full", response_model=None)
    async def synapse_dev_test_full(
        payload: SynapseDevFullTestRequest | None = None,
    ) -> dict[str, Any]:
        _require_enabled(manager)
        body = payload or SynapseDevFullTestRequest()
        report = await manager.run_full_tests(
            python_args=body.python_args,
            tsc_args=body.tsc_args,
        )
        with storage.transaction() as conn:
            audit(
                conn,
                AuditRecord(
                    entity_type="project",
                    entity_id=SYNAPSE_SELF_PROJECT_ID,
                    action="synapse_dev.test_full",
                    source=AuditSource.AUTO,
                    result="success" if report["ok"] else "error",
                    error_code=None if report["ok"] else "synapse_dev.test_failed",
                    details={
                        "ok": report["ok"],
                        "pytest": {
                            "passed": report["pytest"]["passed"],
                            "failed": report["pytest"]["failed"],
                            "skipped": report["pytest"]["skipped"],
                        },
                        "tsc_ok": report["tsc"]["ok"],
                    },
                ),
            )
        return report

    @router.post("/test/file", response_model=None)
    async def synapse_dev_test_file(payload: SynapseDevFileTestRequest) -> dict[str, Any]:
        _require_enabled(manager)
        try:
            report = await manager.run_file_test(
                payload.path,
                python_args=payload.python_args,
            )
        except ValueError as exc:
            raise invalid("synapse_dev", str(exc))
        with storage.transaction() as conn:
            audit(
                conn,
                AuditRecord(
                    entity_type="project",
                    entity_id=SYNAPSE_SELF_PROJECT_ID,
                    action="synapse_dev.test_file",
                    source=AuditSource.AUTO,
                    result="success" if report["ok"] else "error",
                    error_code=None if report["ok"] else "synapse_dev.test_failed",
                    details={
                        "ok": report["ok"],
                        "path": report["path"],
                        "pytest": {
                            "passed": report["pytest"]["passed"],
                            "failed": report["pytest"]["failed"],
                            "skipped": report["pytest"]["skipped"],
                        },
                    },
                ),
            )
        return report

    return router
