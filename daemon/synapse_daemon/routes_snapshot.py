"""REST routes for snapshot / restore (Contract #28 · v0.1.10.5).

  GET  /api/v1/snapshot
       -> the whole project registry as one JSON SnapshotPayload. The UI
          saves it to a file; it is a portable backup.

  POST /api/v1/restore
       -> accepts a SnapshotPayload, checks compatibility, then merges it
          into the registry (create new projects, update existing by id).
          Non-destructive — nothing is deleted. Returns a RestoreReport.

All under ``/api/v1`` — mounted by :func:`synapse_daemon.app.build_app`.
"""

from __future__ import annotations

from fastapi import APIRouter

from .audit import AuditRecord, audit
from .errors import invalid
from .models import AuditSource
from .snapshot import (
    SnapshotPayload,
    assert_compatible,
    build_snapshot,
    restore_snapshot,
)
from .storage import Storage
from .tools_registry import ToolRegistry


def build_snapshot_router(storage: Storage, registry: ToolRegistry) -> APIRouter:
    router = APIRouter(tags=["snapshot"])

    @router.get("/snapshot", response_model=None)
    async def export_snapshot() -> dict:
        tool_ids = [m.id for m in registry.list_manifests()]
        payload = build_snapshot(storage, tool_ids=tool_ids)
        return payload.model_dump(mode="json")

    @router.post("/restore", response_model=None)
    async def import_snapshot(payload: SnapshotPayload) -> dict:
        current_schema = storage.schema_migration()
        try:
            compat_warnings = assert_compatible(payload, current_schema)
        except ValueError as exc:
            raise invalid("snapshot", str(exc)) from exc

        report = restore_snapshot(storage, payload)
        report.warnings = [*compat_warnings, *report.warnings]

        with storage.transaction() as conn:
            audit(
                conn,
                AuditRecord(
                    entity_type="snapshot",
                    entity_id=None,
                    action="restore",
                    source=AuditSource.DESKTOP,
                    result="success",
                    details={
                        "projects_created": report.projects_created,
                        "projects_updated": report.projects_updated,
                        "warnings": len(report.warnings),
                    },
                ),
            )

        return report.model_dump(mode="json")

    return router
