"""REST routes for per-project decision records, backlog, and versions (ADR-0011)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from . import project_records as records
from . import projects as projects_module
from .audit import AuditRecord, audit
from .models import AuditSource
from .project_records import (
    ProjectAdrCreate,
    ProjectAdrUpdate,
    ProjectBacklogItemCreate,
    ProjectBacklogItemUpdate,
    ProjectVersionCreate,
    ProjectVersionUpdate,
)
from .storage import Storage


def build_project_records_router(storage: Storage) -> APIRouter:
    router = APIRouter(tags=["project-records"])

    # ── Bundle ───────────────────────────────────────────────────────────────

    @router.get("/projects/{project_id}/records", response_model=None)
    async def get_records(project_id: str) -> dict[str, Any]:
        projects_module.get(storage.conn, project_id)
        return records.get_records(storage.conn, project_id).model_dump(mode="json")

    # ── ADRs ─────────────────────────────────────────────────────────────────

    @router.get("/projects/{project_id}/adrs", response_model=None)
    async def list_adrs(project_id: str) -> dict[str, Any]:
        projects_module.get(storage.conn, project_id)
        return {
            "adrs": [a.model_dump(mode="json") for a in records.list_adrs(storage.conn, project_id)]
        }

    @router.post("/projects/{project_id}/adrs", response_model=None, status_code=201)
    async def create_adr(project_id: str, payload: ProjectAdrCreate) -> dict[str, Any]:
        projects_module.get(storage.conn, project_id)
        with storage.transaction() as conn:
            adr = records.create_adr(conn, project_id, payload)
            audit(
                conn,
                AuditRecord(
                    entity_type="project_adr",
                    entity_id=adr.id,
                    action="create",
                    source=payload.source,
                    result="success",
                    details={"project_id": project_id, "title": adr.title, "status": adr.status.value},
                ),
            )
        return adr.model_dump(mode="json")

    @router.get("/project-adrs/{adr_id}", response_model=None)
    async def get_adr(adr_id: str) -> dict[str, Any]:
        return records.get_adr(storage.conn, adr_id).model_dump(mode="json")

    @router.patch("/project-adrs/{adr_id}", response_model=None)
    async def patch_adr(adr_id: str, payload: ProjectAdrUpdate) -> dict[str, Any]:
        with storage.transaction() as conn:
            adr = records.update_adr(conn, adr_id, payload)
            audit(
                conn,
                AuditRecord(
                    entity_type="project_adr",
                    entity_id=adr_id,
                    action="update",
                    source=payload.source,
                    result="success",
                    details={"title": adr.title, "status": adr.status.value},
                ),
            )
        return adr.model_dump(mode="json")

    @router.delete("/project-adrs/{adr_id}", status_code=204, response_model=None)
    async def delete_adr(adr_id: str) -> None:
        with storage.transaction() as conn:
            records.delete_adr(conn, adr_id)
            audit(
                conn,
                AuditRecord(
                    entity_type="project_adr",
                    entity_id=adr_id,
                    action="delete",
                    source=AuditSource.DESKTOP,
                    result="success",
                ),
            )

    @router.post("/project-adrs/{adr_id}/promote", response_model=None)
    async def promote_adr(adr_id: str) -> dict[str, Any]:
        with storage.transaction() as conn:
            adr = records.promote_adr(conn, adr_id)
            audit(
                conn,
                AuditRecord(
                    entity_type="project_adr",
                    entity_id=adr_id,
                    action="promote",
                    source=AuditSource.DESKTOP,
                    result="success",
                    details={"number": adr.number, "status": adr.status.value},
                ),
            )
        return adr.model_dump(mode="json")

    # ── Backlog ──────────────────────────────────────────────────────────────

    @router.get("/projects/{project_id}/backlog", response_model=None)
    async def list_backlog(project_id: str) -> dict[str, Any]:
        projects_module.get(storage.conn, project_id)
        return {
            "items": [i.model_dump(mode="json") for i in records.list_backlog(storage.conn, project_id)]
        }

    @router.post("/projects/{project_id}/backlog", response_model=None, status_code=201)
    async def create_backlog(project_id: str, payload: ProjectBacklogItemCreate) -> dict[str, Any]:
        projects_module.get(storage.conn, project_id)
        with storage.transaction() as conn:
            item = records.create_backlog_item(conn, project_id, payload)
            audit(
                conn,
                AuditRecord(
                    entity_type="project_backlog_item",
                    entity_id=item.id,
                    action="create",
                    source=payload.source,
                    result="success",
                    details={"project_id": project_id, "title": item.title},
                ),
            )
        return item.model_dump(mode="json")

    @router.patch("/project-backlog/{item_id}", response_model=None)
    async def patch_backlog(item_id: str, payload: ProjectBacklogItemUpdate) -> dict[str, Any]:
        with storage.transaction() as conn:
            item = records.update_backlog_item(conn, item_id, payload)
            audit(
                conn,
                AuditRecord(
                    entity_type="project_backlog_item",
                    entity_id=item_id,
                    action="update",
                    source=payload.source,
                    result="success",
                    details={"status": item.status.value, "priority": item.priority.value},
                ),
            )
        return item.model_dump(mode="json")

    @router.delete("/project-backlog/{item_id}", status_code=204, response_model=None)
    async def delete_backlog(item_id: str) -> None:
        with storage.transaction() as conn:
            records.delete_backlog_item(conn, item_id)
            audit(
                conn,
                AuditRecord(
                    entity_type="project_backlog_item",
                    entity_id=item_id,
                    action="delete",
                    source=AuditSource.DESKTOP,
                    result="success",
                ),
            )

    # ── Versions ─────────────────────────────────────────────────────────────

    @router.get("/projects/{project_id}/versions", response_model=None)
    async def list_versions(project_id: str) -> dict[str, Any]:
        projects_module.get(storage.conn, project_id)
        return {
            "versions": [v.model_dump(mode="json") for v in records.list_versions(storage.conn, project_id)]
        }

    @router.post("/projects/{project_id}/versions", response_model=None, status_code=201)
    async def create_version(project_id: str, payload: ProjectVersionCreate) -> dict[str, Any]:
        projects_module.get(storage.conn, project_id)
        with storage.transaction() as conn:
            version = records.create_version(conn, project_id, payload)
            audit(
                conn,
                AuditRecord(
                    entity_type="project_version",
                    entity_id=version.id,
                    action="create",
                    source=payload.source,
                    result="success",
                    details={"project_id": project_id, "version": version.version},
                ),
            )
        return version.model_dump(mode="json")

    @router.patch("/project-versions/{version_id}", response_model=None)
    async def patch_version(version_id: str, payload: ProjectVersionUpdate) -> dict[str, Any]:
        with storage.transaction() as conn:
            version = records.update_version(conn, version_id, payload)
            audit(
                conn,
                AuditRecord(
                    entity_type="project_version",
                    entity_id=version_id,
                    action="update",
                    source=payload.source,
                    result="success",
                    details={"version": version.version},
                ),
            )
        return version.model_dump(mode="json")

    @router.delete("/project-versions/{version_id}", status_code=204, response_model=None)
    async def delete_version(version_id: str) -> None:
        with storage.transaction() as conn:
            records.delete_version(conn, version_id)
            audit(
                conn,
                AuditRecord(
                    entity_type="project_version",
                    entity_id=version_id,
                    action="delete",
                    source=AuditSource.DESKTOP,
                    result="success",
                ),
            )

    return router
