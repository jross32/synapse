"""On-disk + SQLite layer for project files (ADR-0003 Phase A + D, v0.1.30).

The functions in this module own the disk and the ``project_files`` table.
The REST router (Phase A's ``routes_files.py``) and the PTY session-exit
hook (Phase D's transcript persistence) both call into here -- nothing
else writes files or rows directly.

Storage layout (mirrors the ADR's "Detailed design" section):

    <data_dir>/
      projects/<project_id>/files/<file_id><.ext>      # per-project
      files/_shared/<file_id><.ext>                    # shared (project_id IS NULL)
      projects/<project_id>/transcripts/<session_id>.log
      quarantine/<file_id><.ext>                       # AV staging (Phase C)

Key invariants:

- The ``project_files.id`` is the trust anchor; the on-disk filename is
  ``<id><.ext>`` so a corrupt row can never collide with another row's
  bytes.
- Hashing happens *during* the write -- one pass over the bytes, no
  re-read. The hash is what makes deduplication possible (ADR-0003
  issue #2 + #3).
- All writes land in ``quarantine/`` first so Phase C can scan in place
  before promoting via :func:`finalize_after_scan`. Pre-Phase-C the
  finalize step is unconditional.
"""

from __future__ import annotations

import hashlib
import logging
import os
import secrets
import shutil
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Literal

from .time_utils import to_iso, utc_now

log = logging.getLogger(__name__)

#: Streaming chunk size for ``write_streaming_with_hash``. Big enough to keep
#: syscall overhead low; small enough that a malicious upload can be aborted
#: without writing many MB to disk first.
CHUNK_BYTES = 64 * 1024

#: Default cap per uploaded file. Mirrors ``SYNAPSE_MAX_FILE_BYTES`` from the
#: ADR. The route exposes the env override; the storage layer enforces it.
DEFAULT_MAX_FILE_BYTES = 256 * 1024 * 1024  # 256 MiB

FileSource = Literal["upload", "transcript", "chatgpt-import"]
ScanResult = Literal["clean", "blocked", "unavailable"]


# ── data classes ───────────────────────────────────────────────────────────


@dataclass
class StoredBlob:
    """Result of streaming an upload into the quarantine area."""

    file_id: str
    on_disk_name: str
    quarantine_path: Path
    size_bytes: int
    sha256: str


@dataclass
class FileRow:
    """One row of ``project_files``, hydrated for the REST layer."""

    id: str
    project_id: str | None
    original_name: str
    on_disk_name: str
    mime: str
    size_bytes: int
    sha256: str
    source: FileSource
    source_session: str | None
    uploaded_at: str
    deleted_at: str | None
    scan_result: ScanResult | None
    scan_engine: str | None
    duplicate_of: str | None


class FileTooLargeError(Exception):
    """Raised when a streaming write exceeds ``max_bytes``."""


# ── path resolution ───────────────────────────────────────────────────────


def new_file_id() -> str:
    """12 hex characters; same alphabet as PTY session ids (v0.1.25)."""

    return secrets.token_hex(6)


def _safe_ext(original_name: str) -> str:
    """Preserve a *short* extension only -- prevents path-traversal via tricks
    like ``..\\..\\..\\evil.exe`` reaching the on-disk filename."""

    ext = Path(original_name).suffix
    if not ext:
        return ""
    # No path separators, no dots-in-name games. Cap length so a payload
    # can't tunnel a megabyte of garbage into the filename.
    if any(c in ext for c in ("/", "\\", "\x00")) or len(ext) > 16:
        return ""
    return ext


def quarantine_dir(data_dir: Path) -> Path:
    return data_dir / "quarantine"


def final_dir_for(data_dir: Path, project_id: str | None) -> Path:
    """Resolve the per-project or shared destination directory."""

    if project_id is None:
        return data_dir / "files" / "_shared"
    return data_dir / "projects" / project_id / "files"


def transcript_dir(data_dir: Path, project_id: str) -> Path:
    return data_dir / "projects" / project_id / "transcripts"


def ensure_storage_dirs(data_dir: Path) -> None:
    """Create the parent directories the storage layer uses. Idempotent."""

    (data_dir / "files" / "_shared").mkdir(parents=True, exist_ok=True)
    quarantine_dir(data_dir).mkdir(parents=True, exist_ok=True)


# ── streaming write + hash ────────────────────────────────────────────────


def write_streaming_with_hash(
    source: BinaryIO,
    original_name: str,
    data_dir: Path,
    *,
    max_bytes: int = DEFAULT_MAX_FILE_BYTES,
) -> StoredBlob:
    """Stream ``source`` into ``<data>/quarantine/<file_id><ext>``,
    hashing as we go. Raises :class:`FileTooLargeError` (and deletes the
    partial file) if the upload exceeds ``max_bytes``.

    Returns the ``StoredBlob`` for the caller to either finalise via
    :func:`finalize_after_scan` or discard via
    :func:`drop_quarantined`.
    """

    ensure_storage_dirs(data_dir)
    file_id = new_file_id()
    ext = _safe_ext(original_name)
    on_disk_name = f"{file_id}{ext}"
    target = quarantine_dir(data_dir) / on_disk_name

    digest = hashlib.sha256()
    total = 0
    with target.open("wb") as out:
        while True:
            chunk = source.read(CHUNK_BYTES)
            if not chunk:
                break
            total += len(chunk)
            if total > max_bytes:
                out.close()
                target.unlink(missing_ok=True)
                raise FileTooLargeError(
                    f"upload exceeded {max_bytes} bytes "
                    f"(stopped at {total}; original_name={original_name!r})"
                )
            digest.update(chunk)
            out.write(chunk)

    return StoredBlob(
        file_id=file_id,
        on_disk_name=on_disk_name,
        quarantine_path=target,
        size_bytes=total,
        sha256=digest.hexdigest(),
    )


def drop_quarantined(blob: StoredBlob) -> None:
    """Delete a staged blob (AV blocked, request aborted, etc.)."""

    try:
        blob.quarantine_path.unlink(missing_ok=True)
    except OSError:  # pragma: no cover -- best effort
        log.warning("Could not drop quarantined file %s", blob.quarantine_path)


def finalize_after_scan(
    blob: StoredBlob,
    data_dir: Path,
    project_id: str | None,
) -> Path:
    """Move a quarantined blob into its final destination. Returns the
    final on-disk path the caller should record in
    ``project_files.on_disk_name``."""

    dest_dir = final_dir_for(data_dir, project_id)
    dest_dir.mkdir(parents=True, exist_ok=True)
    final_path = dest_dir / blob.on_disk_name
    os.replace(blob.quarantine_path, final_path)
    return final_path


# ── DB ────────────────────────────────────────────────────────────────────


def _row_to_filerow(row: sqlite3.Row) -> FileRow:
    return FileRow(
        id=row["id"],
        project_id=row["project_id"],
        original_name=row["original_name"],
        on_disk_name=row["on_disk_name"],
        mime=row["mime"],
        size_bytes=row["size_bytes"],
        sha256=row["sha256"],
        source=row["source"],
        source_session=row["source_session"],
        uploaded_at=row["uploaded_at"],
        deleted_at=row["deleted_at"],
        scan_result=row["scan_result"],
        scan_engine=row["scan_engine"],
        duplicate_of=row["duplicate_of"],
    )


def insert_file_row(
    conn: sqlite3.Connection,
    *,
    file_id: str,
    project_id: str | None,
    original_name: str,
    on_disk_name: str,
    mime: str,
    size_bytes: int,
    sha256: str,
    source: FileSource,
    source_session: str | None = None,
    scan_result: ScanResult | None = None,
    scan_engine: str | None = None,
    duplicate_of: str | None = None,
) -> None:
    conn.execute(
        """
        INSERT INTO project_files (
          id, project_id, original_name, on_disk_name, mime, size_bytes,
          sha256, source, source_session, uploaded_at, scan_result,
          scan_engine, duplicate_of
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            file_id,
            project_id,
            original_name,
            on_disk_name,
            mime,
            size_bytes,
            sha256,
            source,
            source_session,
            to_iso(utc_now()),
            scan_result,
            scan_engine,
            duplicate_of,
        ),
    )


def find_existing_duplicate(
    conn: sqlite3.Connection,
    *,
    sha256: str,
    project_id: str | None,
    exclude_id: str,
) -> str | None:
    """Look for an older live row in the same scope with this hash. Returns
    the **canonical** file id we should set ``duplicate_of`` to (issue #2
    from the test pass).
    """

    if project_id is None:
        cursor = conn.execute(
            "SELECT id FROM project_files WHERE sha256 = ? AND project_id IS NULL "
            "AND deleted_at IS NULL AND id != ? "
            "AND duplicate_of IS NULL "
            "ORDER BY uploaded_at LIMIT 1",
            (sha256, exclude_id),
        )
    else:
        cursor = conn.execute(
            "SELECT id FROM project_files WHERE sha256 = ? AND project_id = ? "
            "AND deleted_at IS NULL AND id != ? "
            "AND duplicate_of IS NULL "
            "ORDER BY uploaded_at LIMIT 1",
            (sha256, project_id, exclude_id),
        )
    row = cursor.fetchone()
    return row["id"] if row else None


def get_file(conn: sqlite3.Connection, file_id: str) -> FileRow | None:
    row = conn.execute(
        "SELECT * FROM project_files WHERE id = ?", (file_id,)
    ).fetchone()
    return _row_to_filerow(row) if row else None


def list_for_project(
    conn: sqlite3.Connection, project_id: str | None
) -> list[FileRow]:
    if project_id is None:
        cursor = conn.execute(
            "SELECT * FROM project_files WHERE project_id IS NULL "
            "AND deleted_at IS NULL ORDER BY uploaded_at DESC"
        )
    else:
        cursor = conn.execute(
            "SELECT * FROM project_files WHERE project_id = ? "
            "AND deleted_at IS NULL ORDER BY uploaded_at DESC",
            (project_id,),
        )
    return [_row_to_filerow(r) for r in cursor.fetchall()]


# ── soft delete + duplicate promotion ────────────────────────────────────


def soft_delete_file(
    conn: sqlite3.Connection,
    data_dir: Path,
    file_id: str,
) -> None:
    """Soft-delete a file. Handles the dangling-duplicate case (test pass
    issue #3): if the row being deleted *owns* the on-disk bytes and other
    live rows reference it via ``duplicate_of``, promote the oldest survivor
    to be the new canonical (copy bytes + null its duplicate_of)."""

    row = conn.execute(
        "SELECT * FROM project_files WHERE id = ? AND deleted_at IS NULL",
        (file_id,),
    ).fetchone()
    if row is None:
        return

    now_iso = to_iso(utc_now())

    # Who else points at THIS row's bytes?
    referrers = conn.execute(
        "SELECT id FROM project_files WHERE duplicate_of = ? "
        "AND deleted_at IS NULL ORDER BY uploaded_at LIMIT 1",
        (file_id,),
    ).fetchall()

    is_canonical = referrers and row["duplicate_of"] is None
    if is_canonical:
        # Promote the oldest referrer to canonical. Copy the bytes into its
        # on-disk slot, then null its duplicate_of.
        new_canonical_id = referrers[0]["id"]
        new_canonical = conn.execute(
            "SELECT project_id, on_disk_name FROM project_files WHERE id = ?",
            (new_canonical_id,),
        ).fetchone()
        old_path = final_dir_for(data_dir, row["project_id"]) / row["on_disk_name"]
        new_path = (
            final_dir_for(data_dir, new_canonical["project_id"])
            / new_canonical["on_disk_name"]
        )
        new_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(old_path, new_path)
        conn.execute(
            "UPDATE project_files SET duplicate_of = NULL WHERE id = ?",
            (new_canonical_id,),
        )
        # Re-point other referrers at the new canonical.
        conn.execute(
            "UPDATE project_files SET duplicate_of = ? "
            "WHERE duplicate_of = ? AND id != ?",
            (new_canonical_id, file_id, new_canonical_id),
        )

    # Mark soft-deleted.
    conn.execute(
        "UPDATE project_files SET deleted_at = ? WHERE id = ?",
        (now_iso, file_id),
    )

    # Decide whether to rename the on-disk file. If after this delete no
    # live rows share the sha256, rename to *.deleted-<iso> so the 30-day
    # purge sweep can clean it later.
    remaining = conn.execute(
        "SELECT COUNT(*) AS c FROM project_files "
        "WHERE sha256 = ? AND deleted_at IS NULL AND id != ?",
        (row["sha256"], file_id),
    ).fetchone()["c"]

    if remaining == 0 and not is_canonical:
        # Bytes belong to this row alone; mark for purge. The on-disk suffix
        # has to be filename-safe -- Windows rejects ':' (from the ISO
        # timestamp), so we strip the punctuation here.
        purge_stamp = (
            now_iso.replace(":", "").replace("-", "").replace(".", "").replace("+", "Z")
        )
        disk_path = final_dir_for(data_dir, row["project_id"]) / row["on_disk_name"]
        try:
            disk_path.rename(
                disk_path.with_name(f"{disk_path.name}.deleted-{purge_stamp}")
            )
        except FileNotFoundError:  # pragma: no cover -- raced with another caller
            pass


def cascade_delete_project_files(
    conn: sqlite3.Connection,
    data_dir: Path,
    project_id: str,
) -> int:
    """When a project itself is soft-deleted (test pass issue #6), soft-
    delete every one of its files. Returns the count touched."""

    rows = conn.execute(
        "SELECT id FROM project_files WHERE project_id = ? AND deleted_at IS NULL",
        (project_id,),
    ).fetchall()
    for r in rows:
        soft_delete_file(conn, data_dir, r["id"])
    return len(rows)
