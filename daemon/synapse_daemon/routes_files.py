"""REST endpoints for project files (ADR-0003 Phase A · v0.1.30).

  POST   /api/v1/projects/{project_id}/files       -- multipart upload (N files / request)
  GET    /api/v1/projects/{project_id}/files       -- list metadata
  GET    /api/v1/projects/{project_id}/files/{id}  -- download
  DELETE /api/v1/projects/{project_id}/files/{id}  -- soft delete

  POST   /api/v1/files                             -- shared upload (project_id IS NULL)
  GET    /api/v1/files                             -- shared list
  GET    /api/v1/files/{id}                        -- shared download
  DELETE /api/v1/files/{id}                        -- shared soft delete

Per-project upload audits as ``file.upload``. Wired in the app builder under
the existing token guard. Phase B (pre-upload inspection) and Phase C
(AV sweep) hook in here but are not wired yet.
"""

from __future__ import annotations

import io
import logging
import mimetypes
import os
from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, File, Path as FPath, UploadFile
from fastapi.responses import FileResponse

from . import projects as projects_module
from .audit import AuditRecord, audit
from .errors import invalid, not_found
from .files_storage import (
    DEFAULT_MAX_FILE_BYTES,
    FileTooLargeError,
    drop_quarantined,
    final_dir_for,
    finalize_after_scan,
    find_existing_duplicate,
    get_file,
    insert_file_row,
    list_for_project,
    soft_delete_file,
    write_streaming_with_hash,
)
from .models import AuditSource
from .storage import Storage

log = logging.getLogger(__name__)

#: Per-request file count cap. Mirrored from the ADR.
DEFAULT_MAX_FILES_PER_REQUEST = 100


def _max_files_per_request() -> int:
    raw = os.environ.get("SYNAPSE_MAX_FILES_PER_REQUEST", "")
    try:
        return max(1, int(raw)) if raw else DEFAULT_MAX_FILES_PER_REQUEST
    except ValueError:
        return DEFAULT_MAX_FILES_PER_REQUEST


def _max_file_bytes() -> int:
    raw = os.environ.get("SYNAPSE_MAX_FILE_BYTES", "")
    try:
        return max(1, int(raw)) if raw else DEFAULT_MAX_FILE_BYTES
    except ValueError:
        return DEFAULT_MAX_FILE_BYTES


def _guess_mime(filename: str) -> str:
    """Phase A: best-effort by extension. Phase B will add magic-byte
    detection -- until then octet-stream is the honest fallback."""

    mime, _ = mimetypes.guess_type(filename)
    return mime or "application/octet-stream"


async def _store_one_file(
    storage: Storage,
    upload: UploadFile,
    *,
    project_id: str | None,
    source_label: AuditSource,
) -> dict[str, Any]:
    """Stream one UploadFile through quarantine + dedup. Returns the
    per-file response shape from the ADR.

    Does NOT raise on a per-file failure -- the response carries
    ``ok=false`` + a reason so a multi-file batch can be partially
    successful. The top-level route still returns 200 unless something
    structural is wrong (token, project missing, etc.).
    """

    name = upload.filename or "untitled"
    payload = await upload.read()
    data_dir = storage.data_dir
    try:
        blob = write_streaming_with_hash(
            io.BytesIO(payload),
            original_name=name,
            data_dir=data_dir,
            max_bytes=_max_file_bytes(),
        )
    except FileTooLargeError as exc:
        return {"ok": False, "reason": str(exc), "original_name": name}

    mime = _guess_mime(name)

    # Insert + dedup reconciliation under one transaction (test pass issue #2).
    with storage.transaction() as conn:
        insert_file_row(
            conn,
            file_id=blob.file_id,
            project_id=project_id,
            original_name=name,
            on_disk_name=blob.on_disk_name,
            mime=mime,
            size_bytes=blob.size_bytes,
            sha256=blob.sha256,
            source="upload",
        )
        canonical = find_existing_duplicate(
            conn,
            sha256=blob.sha256,
            project_id=project_id,
            exclude_id=blob.file_id,
        )
        if canonical is not None:
            # We are a duplicate -- drop our quarantined bytes, point at the
            # canonical. The on-disk slot for this row never gets filled.
            drop_quarantined(blob)
            conn.execute(
                "UPDATE project_files SET duplicate_of = ? WHERE id = ?",
                (canonical, blob.file_id),
            )
        else:
            # Canonical -- promote bytes from quarantine into the final slot.
            finalize_after_scan(blob, data_dir, project_id=project_id)

        audit(
            conn,
            AuditRecord(
                entity_type="project" if project_id else "file",
                entity_id=project_id or blob.file_id,
                action="file.upload",
                source=source_label,
                result="success",
                details={
                    "file_id": blob.file_id,
                    "original_name": name,
                    "size_bytes": blob.size_bytes,
                    "sha256": blob.sha256,
                    "duplicate_of": canonical,
                },
            ),
        )

    return {
        "ok": True,
        "id": blob.file_id,
        "original_name": name,
        "size_bytes": blob.size_bytes,
        "mime": mime,
        "sha256": blob.sha256,
        "scan_result": None,         # Phase C will fill this
        "duplicate_of": canonical,
    }


def _serialise_row(row) -> dict[str, Any]:  # noqa: ANN001 -- dataclass
    return asdict(row)


def _disk_path_for(storage: Storage, row) -> str | None:  # noqa: ANN001
    """Resolve the on-disk path the caller should actually open. If this row
    is a duplicate, redirect to the canonical's bytes."""

    target_id = row.duplicate_of or row.id
    target = get_file(storage.conn, target_id) if row.duplicate_of else row
    if target is None:  # pragma: no cover -- broken FK
        return None
    return str(final_dir_for(storage.data_dir, target.project_id) / target.on_disk_name)


def build_files_router(storage: Storage) -> APIRouter:
    router = APIRouter(tags=["files"])

    # ── per-project endpoints ──────────────────────────────────────────

    @router.post("/projects/{project_id}/files", response_model=None)
    async def upload_to_project(
        project_id: str,
        files: list[UploadFile] = File(...),
    ) -> dict[str, Any]:
        # 404 fast if the project is bogus -- we don't want to write bytes
        # for a folder that doesn't exist.
        projects_module.get(storage.conn, project_id)
        if not files:
            raise invalid("files", "Provide at least one file.")
        if len(files) > _max_files_per_request():
            raise invalid(
                "files",
                f"Too many files in one request "
                f"(cap is {_max_files_per_request()}).",
            )
        results = []
        for upload in files:
            results.append(
                await _store_one_file(
                    storage,
                    upload,
                    project_id=project_id,
                    source_label=AuditSource.DESKTOP,
                )
            )
        return {"files": results}

    @router.get("/projects/{project_id}/files", response_model=None)
    async def list_project_files(project_id: str) -> dict[str, Any]:
        projects_module.get(storage.conn, project_id)
        rows = list_for_project(storage.conn, project_id)
        return {"files": [_serialise_row(r) for r in rows]}

    @router.get("/projects/{project_id}/files/{file_id}", response_model=None)
    async def download_project_file(project_id: str, file_id: str) -> FileResponse:
        projects_module.get(storage.conn, project_id)
        row = get_file(storage.conn, file_id)
        if row is None or row.project_id != project_id or row.deleted_at:
            raise not_found("file", file_id)
        disk_path = _disk_path_for(storage, row)
        if disk_path is None:
            raise not_found("file", file_id)
        return FileResponse(disk_path, filename=row.original_name, media_type=row.mime)

    @router.delete(
        "/projects/{project_id}/files/{file_id}",
        status_code=204,
        response_model=None,
    )
    async def delete_project_file(project_id: str, file_id: str) -> None:
        projects_module.get(storage.conn, project_id)
        row = get_file(storage.conn, file_id)
        if row is None or row.project_id != project_id or row.deleted_at:
            raise not_found("file", file_id)
        with storage.transaction() as conn:
            soft_delete_file(conn, storage.data_dir, file_id)
            audit(
                conn,
                AuditRecord(
                    entity_type="project",
                    entity_id=project_id,
                    action="file.delete",
                    source=AuditSource.DESKTOP,
                    result="success",
                    details={"file_id": file_id},
                ),
            )

    # ── shared (project_id IS NULL) endpoints ──────────────────────────

    @router.post("/files", response_model=None)
    async def upload_shared(files: list[UploadFile] = File(...)) -> dict[str, Any]:
        if not files:
            raise invalid("files", "Provide at least one file.")
        if len(files) > _max_files_per_request():
            raise invalid(
                "files",
                f"Too many files in one request (cap is {_max_files_per_request()}).",
            )
        results = []
        for upload in files:
            results.append(
                await _store_one_file(
                    storage, upload, project_id=None, source_label=AuditSource.DESKTOP
                )
            )
        return {"files": results}

    @router.get("/files", response_model=None)
    async def list_shared_files() -> dict[str, Any]:
        rows = list_for_project(storage.conn, None)
        return {"files": [_serialise_row(r) for r in rows]}

    @router.get("/files/{file_id}", response_model=None)
    async def download_shared_file(file_id: str) -> FileResponse:
        row = get_file(storage.conn, file_id)
        if row is None or row.project_id is not None or row.deleted_at:
            raise not_found("file", file_id)
        disk_path = _disk_path_for(storage, row)
        if disk_path is None:
            raise not_found("file", file_id)
        return FileResponse(disk_path, filename=row.original_name, media_type=row.mime)

    @router.delete("/files/{file_id}", status_code=204, response_model=None)
    async def delete_shared_file(file_id: str) -> None:
        row = get_file(storage.conn, file_id)
        if row is None or row.project_id is not None or row.deleted_at:
            raise not_found("file", file_id)
        with storage.transaction() as conn:
            soft_delete_file(conn, storage.data_dir, file_id)
            audit(
                conn,
                AuditRecord(
                    entity_type="file",
                    entity_id=file_id,
                    action="file.delete",
                    source=AuditSource.DESKTOP,
                    result="success",
                    details={"scope": "shared"},
                ),
            )

    # Silence the FPath import warning by referencing it once for future use.
    _ = FPath
    return router
