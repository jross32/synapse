"""Project-scoped workbench launcher (v0.1.29 · ADR-0002 Phase B).

  POST /api/v1/projects/{project_id}/workbench
      Open a PTY session pre-``cd``'d into the project's working directory.
      Picks a sensible default coder (claude → codex → shell) if no
      argv is supplied; the caller can override.

Audits as ``workbench.open`` so the audit log shows which project was
opened from where (Contract #11).
"""

from __future__ import annotations

import shutil
import sys
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from . import projects as projects_module
from .audit import AuditRecord, audit
from .errors import invalid
from .models import AuditSource
from .pty_sessions import PtySessionManager
from .storage import Storage


class WorkbenchRequest(BaseModel):
    """Optional overrides for the workbench launch."""

    argv: list[str] | None = None
    rows: int = Field(default=24, ge=1, le=300)
    cols: int = Field(default=80, ge=1, le=500)
    source: AuditSource = AuditSource.DESKTOP


def _default_coder_argv() -> list[str]:
    """Best-effort default: prefer Claude, then Codex, fall back to a shell."""

    for candidate in ("claude", "codex"):
        if shutil.which(candidate):
            return [candidate]
    if sys.platform == "win32":
        return ["powershell.exe", "-NoLogo"]
    if sys.platform == "darwin":
        return ["zsh", "-i"]
    return ["bash", "-i"]


def build_workbench_router(storage: Storage, manager: PtySessionManager) -> APIRouter:
    router = APIRouter(prefix="/projects", tags=["workbench"])

    @router.post("/{project_id}/workbench", response_model=None)
    async def open_workbench(
        project_id: str,
        payload: WorkbenchRequest | None = None,
    ) -> dict[str, Any]:
        project = projects_module.get(storage.conn, project_id)
        body = payload or WorkbenchRequest()
        argv = body.argv if body.argv else _default_coder_argv()
        if not argv or not argv[0].strip():
            raise invalid("workbench", "argv must be non-empty.")

        try:
            # project_id tags the session so the manager persists its
            # scrollback to a transcript file row on exit (ADR-0003 Phase D).
            session = await manager.spawn(
                argv=argv,
                cwd=project.path,
                rows=body.rows,
                cols=body.cols,
                project_id=project_id,
            )
        except FileNotFoundError as exc:
            raise invalid("workbench", str(exc))

        with storage.transaction() as conn:
            audit(
                conn,
                AuditRecord(
                    entity_type="project",
                    entity_id=project_id,
                    action="workbench.open",
                    source=body.source,
                    result="success",
                    details={
                        "argv": argv,
                        "session_id": session.session_id,
                        "cwd": project.path,
                    },
                ),
            )

        # Same shape as POST /pty so the renderer can reuse its existing types.
        summary = session.summary()
        return {
            **summary.__dict__,
            "project_id": project_id,
            "project_name": project.name,
        }

    return router
