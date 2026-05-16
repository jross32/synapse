"""REST routes for the project registry (Contracts #1, #2, #7).

All endpoints live under ``/api/v1/projects``. Returns ``ErrorEnvelope`` JSON
on any failure via the app's global exception handler.

Wired into the app by :func:`synapse_daemon.app.build_app` calling
:func:`build_projects_router` with the live ProcessManager + Storage handles.
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from .audit import AuditRecord, audit
from .errors import invalid, not_found
from .models import AuditSource
from . import projects as projects_module
from .process_manager import ProcessManager
from .projects import Project, ProjectUpdate
from .storage import Storage


class ActionRequest(BaseModel):
    """Body for launch / stop / delete endpoints — only the audit source."""

    source: AuditSource = AuditSource.DESKTOP


class ListResponse(BaseModel):
    projects: list[dict]


def build_projects_router(
    storage: Storage,
    pm: ProcessManager,
) -> APIRouter:
    router = APIRouter(prefix="/projects", tags=["projects"])

    @router.get("", response_model=None)
    async def list_all() -> dict:
        items = projects_module.list_projects(storage.conn)
        return {"projects": [projects_module.model_dump_for_client(p) for p in items]}

    @router.get("/{project_id}", response_model=None)
    async def get_one(project_id: str) -> dict:
        project = projects_module.get(storage.conn, project_id)
        return projects_module.model_dump_for_client(project)

    @router.post("", response_model=None, status_code=201)
    async def create_one(payload: Project) -> dict:
        with storage.transaction() as conn:
            created = projects_module.create(conn, payload)
            audit(conn, AuditRecord(
                entity_type="project",
                entity_id=created.id,
                action="create",
                source=AuditSource.DESKTOP,
                result="success",
            ))
        return projects_module.model_dump_for_client(created)

    @router.patch("/{project_id}", response_model=None)
    async def patch_one(project_id: str, payload: ProjectUpdate) -> dict:
        with storage.transaction() as conn:
            updated = projects_module.update(conn, project_id, payload)
            audit(conn, AuditRecord(
                entity_type="project",
                entity_id=project_id,
                action="update",
                source=AuditSource.DESKTOP,
                result="success",
                details=payload.model_dump(exclude_none=True),
            ))
        return projects_module.model_dump_for_client(updated)

    @router.delete("/{project_id}", status_code=204)
    async def delete_one(project_id: str) -> None:
        with storage.transaction() as conn:
            projects_module.soft_delete(conn, project_id)
            audit(conn, AuditRecord(
                entity_type="project",
                entity_id=project_id,
                action="delete",
                source=AuditSource.DESKTOP,
                result="success",
            ))

    @router.post("/{project_id}/launch", response_model=None)
    async def launch_one(project_id: str, payload: ActionRequest | None = None) -> dict:
        source = (payload or ActionRequest()).source
        await pm.launch(project_id, source=source)
        return projects_module.model_dump_for_client(
            projects_module.get(storage.conn, project_id)
        )

    @router.post("/{project_id}/stop", response_model=None)
    async def stop_one(project_id: str, payload: ActionRequest | None = None) -> dict:
        source = (payload or ActionRequest()).source
        await pm.stop(project_id, source=source)
        return projects_module.model_dump_for_client(
            projects_module.get(storage.conn, project_id)
        )

    @router.get("/{project_id}/logs", response_model=None)
    async def get_logs(project_id: str, lines: int = 200) -> dict:
        # Confirm the project exists first (404 with a proper envelope).
        projects_module.get(storage.conn, project_id)
        capped = max(1, min(lines, 2000))
        return pm.tail_log(project_id, max_lines=capped)

    return router
