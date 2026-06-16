"""External-data importers (ADR-0003 Phase E · v0.1.33).

  POST /api/v1/imports/chatgpt
      Body: multipart/form-data with a single ``file`` part containing the
      official ChatGPT ``Settings -> Data Controls -> Export Data`` zip.
      Each conversation lands as a Markdown file under the lazy-created
      ``_imported-chatgpt`` project, tagged source='chatgpt-import' so the
      Files surface + /ai/context inline it like any other file.

The ADR pins this as a one-shot ingest from the user-initiated export. We
do NOT scrape ChatGPT, hit a private API, or sync continuously.
"""

from __future__ import annotations

import io
import json
import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, UploadFile

from . import projects as projects_module
from .audit import AuditRecord, audit
from .chatgpt_import import (
    ChatgptImportError,
    filename_for,
    parse_export,
    render_markdown,
)
from .errors import invalid
from .files_storage import (
    DEFAULT_MAX_FILE_BYTES,
    FileTooLargeError,
    drop_quarantined,
    finalize_after_scan,
    find_existing_duplicate,
    insert_file_row,
    write_streaming_with_hash,
)
from .models import AuditSource
from .projects import Project, ProjectKind
from .storage import Storage

log = logging.getLogger(__name__)

#: The lazy-created project that holds every ChatGPT import.
_IMPORT_PROJECT_ID = "imported-chatgpt"
_IMPORT_PROJECT_NAME = "ChatGPT imports"


def _ensure_import_project(storage: Storage) -> str:
    """Create ``_imported-chatgpt`` on first import. Returns its id.

    The ADR is explicit: this is a real ``projects`` row (kind='other'),
    not a schema special-case -- so it appears in the Apps page, in
    ``/ai/context``, and obeys all the normal project rules. Auto-created
    here so the user doesn't have to set it up by hand.
    """

    existing = projects_module.get_or_none(storage.conn, _IMPORT_PROJECT_ID)
    if existing is not None:
        return existing.id
    with storage.transaction() as conn:
        projects_module.create(
            conn,
            Project(
                id=_IMPORT_PROJECT_ID,
                name=_IMPORT_PROJECT_NAME,
                path=str(storage.data_dir / "projects" / _IMPORT_PROJECT_ID),
                launch_cmd="echo 'imported chats live here'",
                kind=ProjectKind.OTHER,
                description=(
                    "Holds every conversation imported from a ChatGPT data export. "
                    "Auto-created by the importer; safe to rename or pin."
                ),
            ),
        )
    return _IMPORT_PROJECT_ID


def build_imports_router(storage: Storage) -> APIRouter:
    router = APIRouter(prefix="/imports", tags=["imports"])

    @router.post("/chatgpt", response_model=None)
    async def import_chatgpt(file: UploadFile = File(...)) -> dict[str, Any]:
        if not file.filename:
            raise invalid("imports", "Upload a ChatGPT export zip as 'file'.")
        payload = await file.read()
        if not payload:
            raise invalid("imports", "Uploaded file is empty.")
        if len(payload) > DEFAULT_MAX_FILE_BYTES:
            raise invalid(
                "imports",
                f"Zip is larger than the configured cap ({DEFAULT_MAX_FILE_BYTES} bytes).",
            )
        try:
            conversations = parse_export(payload)
        except ChatgptImportError as exc:
            raise invalid("imports", str(exc))
        if not conversations:
            return {
                "imported": 0,
                "skipped_empty": 0,
                "duplicates": 0,
                "project_id": _IMPORT_PROJECT_ID,
                "note": "Zip parsed but contained zero conversations.",
            }

        project_id = _ensure_import_project(storage)

        imported: list[dict[str, Any]] = []
        skipped_empty: list[str] = []
        duplicates: list[str] = []
        data_dir = storage.data_dir

        for idx, convo in enumerate(conversations):
            if not convo.messages:
                # A conversation with no renderable messages is no value to
                # the user (and would just clutter the project). Skip
                # silently but surface a count.
                skipped_empty.append(convo.title)
                continue
            md = render_markdown(convo).encode("utf-8")
            original_name = filename_for(convo, idx)
            try:
                blob = write_streaming_with_hash(
                    io.BytesIO(md),
                    original_name=original_name,
                    data_dir=data_dir,
                    max_bytes=DEFAULT_MAX_FILE_BYTES,
                )
            except FileTooLargeError:  # pragma: no cover -- chats shouldn't be this big
                continue

            with storage.transaction() as conn:
                insert_file_row(
                    conn,
                    file_id=blob.file_id,
                    project_id=project_id,
                    original_name=original_name,
                    on_disk_name=blob.on_disk_name,
                    mime="text/markdown",
                    size_bytes=blob.size_bytes,
                    sha256=blob.sha256,
                    source="chatgpt-import",
                )
                canonical = find_existing_duplicate(
                    conn,
                    sha256=blob.sha256,
                    project_id=project_id,
                    exclude_id=blob.file_id,
                )
                if canonical is not None:
                    drop_quarantined(blob)
                    conn.execute(
                        "UPDATE project_files SET duplicate_of = ? WHERE id = ?",
                        (canonical, blob.file_id),
                    )
                    duplicates.append(original_name)
                else:
                    finalize_after_scan(blob, data_dir, project_id=project_id)
                imported.append(
                    {
                        "id": blob.file_id,
                        "original_name": original_name,
                        "title": convo.title,
                        "size_bytes": blob.size_bytes,
                        "duplicate_of": canonical,
                    }
                )

        with storage.transaction() as conn:
            audit(
                conn,
                AuditRecord(
                    entity_type="project",
                    entity_id=project_id,
                    action="chatgpt.import",
                    source=AuditSource.DESKTOP,
                    result="success",
                    details={
                        "imported": len(imported),
                        "duplicates": len(duplicates),
                        "skipped_empty": len(skipped_empty),
                    },
                ),
            )

        return {
            "imported": len(imported),
            "duplicates": len(duplicates),
            "skipped_empty": len(skipped_empty),
            "project_id": project_id,
            "files": imported,
            "duplicate_names": duplicates,
            "skipped_titles": skipped_empty,
        }

    return router
