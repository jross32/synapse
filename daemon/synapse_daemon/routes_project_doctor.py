"""Project Doctor API: one-call, read-only diagnostics for AI operators."""

from __future__ import annotations

from fastapi import APIRouter

from . import projects as projects_module
from .project_doctor import diagnose_project
from .storage import Storage


def build_project_doctor_router(storage: Storage) -> APIRouter:
    router = APIRouter(prefix="/project-doctor", tags=["project-doctor"])

    @router.get("/{project_id}", response_model=None)
    async def diagnose(project_id: str) -> dict:
        project = projects_module.get(storage.conn, project_id)
        report = diagnose_project(project.path, expected_port=project.expected_port)
        return {
            "project": {
                "id": project.id,
                "name": project.name,
                "status": project.status.value,
                "kind": project.kind.value,
                "expected_port": project.expected_port,
            },
            "doctor": report,
        }

    return router
