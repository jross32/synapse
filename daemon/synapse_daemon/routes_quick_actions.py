"""AI quick-actions REST API (ADR-0003 Phase F · v0.1.34).

  GET  /api/v1/quick-actions
      Return the list of curated AI prompt templates ("New MCP server",
      "New Synapse tool", and any user-dropped JSONs).

  POST /api/v1/quick-actions/{id}/launch
      Lazy-create the 'scratch' project (kind='other', kept at
      data/projects/scratch/), write the template prompt to PROMPT.md
      inside that project, spawn a workbench PTY with default_argv (or
      the request override), and return the PTY session summary.

Honest scope: the route ships the shortcut. The actual AI work is the
job of the Claude / Codex CLI running inside the PTY. We expose the
templated prompt two ways so the AI sees it on prompt 1:

  1. ``PROMPT.md`` in the session's cwd  -- ``cat PROMPT.md``.
  2. ``SYNAPSE_QUICK_ACTION_PROMPT`` env var in the PTY -- ``$SYNAPSE_QUICK_ACTION_PROMPT``.

The route is token-guarded like every other data route. Audited as
``quick_action.launch`` so the audit log records which template fired
in which project.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from . import projects as projects_module
from .audit import AuditRecord, audit
from .errors import invalid, not_found
from .models import AuditSource
from .projects import Project, ProjectKind
from .pty_sessions import PtySessionManager
from .quick_actions import find_template, load_templates
from .storage import Storage

log = logging.getLogger(__name__)

#: The lazy-created scratch project that houses one-off quick-action runs.
_SCRATCH_PROJECT_ID = "scratch"
_SCRATCH_PROJECT_NAME = "Quick-action scratchpad"


class QuickActionLaunchRequest(BaseModel):
    """Optional overrides for a single launch."""

    argv: list[str] | None = None
    rows: int = Field(default=24, ge=1, le=300)
    cols: int = Field(default=80, ge=1, le=500)
    source: AuditSource = AuditSource.DESKTOP


def _ensure_scratch_project(storage: Storage) -> Project:
    """Create the scratch project on first launch. Returns its row."""

    existing = projects_module.get_or_none(storage.conn, _SCRATCH_PROJECT_ID)
    if existing is not None:
        return existing
    scratch_path = storage.data_dir / "projects" / _SCRATCH_PROJECT_ID
    scratch_path.mkdir(parents=True, exist_ok=True)
    with storage.transaction() as conn:
        return projects_module.create(
            conn,
            Project(
                id=_SCRATCH_PROJECT_ID,
                name=_SCRATCH_PROJECT_NAME,
                path=str(scratch_path),
                launch_cmd="echo 'quick-action scratchpad'",
                kind=ProjectKind.OTHER,
                description=(
                    "Auto-created on first quick-action launch. Holds one-off "
                    "scratch sessions that don't belong to a real project. "
                    "Safe to rename or delete."
                ),
            ),
        )


def _write_prompt_file(project_path: Path, action_id: str, prompt: str) -> Path:
    """Write the templated prompt where the AI session can ``cat`` it.

    A fresh file per action keeps the latest prompt easy to find without
    deleting history.
    """

    project_path.mkdir(parents=True, exist_ok=True)
    target = project_path / f"PROMPT-{action_id}.md"
    target.write_text(prompt, encoding="utf-8")
    # Also drop a stable symlink/copy at PROMPT.md pointing at the latest
    # so AI sessions can rely on a known filename. Plain copy here -- the
    # workbench cwd is rarely on a junction-aware filesystem and a copy is
    # cheaper than a symlink that fails on Windows.
    (project_path / "PROMPT.md").write_text(prompt, encoding="utf-8")
    return target


def build_quick_actions_router(
    storage: Storage, manager: PtySessionManager
) -> APIRouter:
    router = APIRouter(prefix="/quick-actions", tags=["quick-actions"])

    @router.get("", response_model=None)
    async def list_quick_actions() -> dict[str, Any]:
        actions = load_templates()
        return {"actions": [a.to_dict() for a in actions]}

    @router.post("/{action_id}/launch", response_model=None)
    async def launch_quick_action(
        action_id: str,
        payload: QuickActionLaunchRequest | None = None,
    ) -> dict[str, Any]:
        template = find_template(action_id)
        if template is None:
            raise not_found("quick_action", action_id)

        body = payload or QuickActionLaunchRequest()
        argv = body.argv if body.argv else (template.default_argv or ["claude"])
        if not argv or not argv[0].strip():
            raise invalid("quick_action", "argv must be non-empty.")

        scratch = _ensure_scratch_project(storage)
        prompt_path = _write_prompt_file(Path(scratch.path), template.id, template.prompt)

        env_overrides = {
            "SYNAPSE_QUICK_ACTION_ID": template.id,
            "SYNAPSE_QUICK_ACTION_PROMPT": template.prompt,
            "SYNAPSE_QUICK_ACTION_PROMPT_FILE": str(prompt_path),
        }

        try:
            session = await manager.spawn(
                argv=argv,
                cwd=scratch.path,
                env=env_overrides,
                rows=body.rows,
                cols=body.cols,
                project_id=scratch.id,
            )
        except FileNotFoundError as exc:
            raise invalid("quick_action", str(exc))

        with storage.transaction() as conn:
            audit(
                conn,
                AuditRecord(
                    entity_type="project",
                    entity_id=scratch.id,
                    action="quick_action.launch",
                    source=body.source,
                    result="success",
                    details={
                        "action_id": template.id,
                        "session_id": session.session_id,
                        "argv": argv,
                        "prompt_file": str(prompt_path),
                    },
                ),
            )

        summary = session.summary()
        return {
            **summary.__dict__,
            "project_id": scratch.id,
            "project_name": scratch.name,
            "action_id": template.id,
            "action_name": template.name,
            "prompt_file": str(prompt_path),
        }

    return router
