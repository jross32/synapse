"""REST routes for project auto-discovery (v0.1.8.5).

  GET  /api/v1/discovery/scan?root=<path>&depth=<n>
       -> scan a folder, return every project found, flagging the ones
          already in the registry.

  POST /api/v1/discovery/import
       -> bulk-create projects (discovered=True) from the user's picks.

All under ``/api/v1`` -- mounted by app.build_app().
"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel, Field

from .audit import AuditRecord, audit
from .discovery import DetectedProject, scan_directory
from .errors import invalid
from . import projects as projects_module
from .models import AuditSource
from .projects import Project
from .storage import Storage


class ScanResponse(BaseModel):
    root: str
    count: int
    projects: list[DetectedProject]


class ImportRequestItem(BaseModel):
    """One project the user chose to import (possibly with an edited command)."""

    id: str
    name: str
    path: str
    launch_cmd: str
    description: str | None = None
    expected_port: int | None = None
    icon: str | None = None
    group: str | None = None
    tags: list[str] = Field(default_factory=list)


class ImportRequest(BaseModel):
    projects: list[ImportRequestItem]


class ImportReport(BaseModel):
    imported: list[str] = Field(default_factory=list)
    skipped: list[dict] = Field(default_factory=list)   # {id, reason}


def _default_scan_root() -> Path:
    """Where to scan when the caller doesn't pass ?root= -- the parent of
    the Synapse install, i.e. the user's workspace folder."""

    return Path(os.path.expanduser("~"))


def build_discovery_router(storage: Storage) -> APIRouter:
    router = APIRouter(prefix="/discovery", tags=["discovery"])

    @router.get("/scan", response_model=None)
    async def scan(root: str | None = None, depth: int = 2) -> dict:
        root_path = Path(root) if root else _default_scan_root()
        if not root_path.exists() or not root_path.is_dir():
            raise invalid("discovery", f"Scan root '{root_path}' is not an existing folder.")
        capped_depth = max(1, min(depth, 4))

        detected = scan_directory(root_path, max_depth=capped_depth)

        # Flag the ones already registered (match on normalised path).
        existing = projects_module.list_projects(storage.conn, include_deleted=False)
        known_paths = {_norm(p.path) for p in existing}
        for d in detected:
            d.already_registered = _norm(d.path) in known_paths

        return ScanResponse(
            root=str(root_path), count=len(detected), projects=detected
        ).model_dump(mode="json")

    @router.post("/import", response_model=None)
    async def import_projects(payload: ImportRequest) -> dict:
        report = ImportReport()
        existing_ids = {p.id for p in projects_module.list_projects(storage.conn, include_deleted=True)}

        for item in payload.projects:
            target_id = item.id
            # Resolve id collisions by suffixing -2, -3, ...
            if target_id in existing_ids:
                base, n = target_id, 2
                while f"{base}-{n}" in existing_ids:
                    n += 1
                target_id = f"{base}-{n}"

            try:
                project = Project(
                    id=target_id,
                    name=item.name,
                    path=item.path,
                    launch_cmd=item.launch_cmd or "echo set-a-launch-command",
                    description=item.description,
                    expected_port=item.expected_port,
                    icon=item.icon,
                    group=item.group,
                    tags=item.tags,
                    discovered=True,
                )
            except Exception as exc:  # invalid id / fields
                report.skipped.append({"id": item.id, "reason": str(exc)})
                continue

            with storage.transaction() as conn:
                projects_module.create(conn, project)
                audit(conn, AuditRecord(
                    entity_type="project",
                    entity_id=target_id,
                    action="import",
                    source=AuditSource.DESKTOP,
                    result="success",
                    details={"path": item.path, "via": "auto-discovery"},
                ))
            existing_ids.add(target_id)
            report.imported.append(target_id)

        return report.model_dump(mode="json")

    return router


def _norm(path: str) -> str:
    """Normalise a path for comparison -- case-insensitive on Windows,
    forward/back slashes unified, trailing slash removed."""

    return os.path.normcase(os.path.normpath(path))
