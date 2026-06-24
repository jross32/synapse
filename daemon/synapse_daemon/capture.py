"""Capture inbox (ADR-0016, Phase R).

Jot a note from anywhere -- typed or dictated on the phone -- and route it where
it belongs without leaving what you're doing:

* ``backlog``    -> a quick item in a project's backlog (ADR-0011 records).
* ``ai_context`` -> appended to the project's ``.synapse-ai-context.md`` so the
  next agent run reads it.

"Send to the active session" isn't here -- the command pad (with voice) already
covers typing into a live terminal.
"""

from __future__ import annotations

import sqlite3
from enum import Enum
from pathlib import Path

from pydantic import BaseModel

from . import ai_context_memory
from . import project_records
from . import projects
from .errors import invalid
from .models import AuditSource
from .project_records import ProjectBacklogItemCreate


class CaptureDestination(str, Enum):
    BACKLOG = "backlog"
    AI_CONTEXT = "ai_context"


class CaptureRequest(BaseModel):
    content: str
    destination: CaptureDestination = CaptureDestination.BACKLOG
    project_id: str
    title: str | None = None  # backlog only; defaults to the first line
    source: AuditSource = AuditSource.MOBILE


class CaptureResult(BaseModel):
    destination: CaptureDestination
    project_id: str
    ref_id: str | None = None  # backlog item id, or the context file name
    message: str


def _title_from(content: str, title: str | None) -> str:
    if title and title.strip():
        return title.strip()[:80]
    first_line = content.strip().splitlines()[0] if content.strip() else ""
    return first_line[:80].strip() or "Captured note"


def capture(conn: sqlite3.Connection, data_dir: Path, payload: CaptureRequest) -> CaptureResult:
    content = payload.content.strip()
    if not content:
        raise invalid("capture", "Nothing to capture — the note is empty.")
    project = projects.get(conn, payload.project_id)  # 404 if missing/deleted

    if payload.destination == CaptureDestination.BACKLOG:
        item = project_records.create_backlog_item(
            conn,
            project.id,
            ProjectBacklogItemCreate(
                title=_title_from(content, payload.title),
                body_md=content,
                source=payload.source,
            ),
        )
        return CaptureResult(
            destination=payload.destination,
            project_id=project.id,
            ref_id=item.id,
            message=f"Added to {project.name} backlog.",
        )

    path = ai_context_memory.append_capture_note(
        data_dir=data_dir,
        project_id=project.id,
        project_name=project.name,
        note=content,
        source=payload.source.value,
    )
    return CaptureResult(
        destination=payload.destination,
        project_id=project.id,
        ref_id=path.name,
        message=f"Saved to {project.name} AI memory.",
    )
