"""Tests for the on-disk + SQLite file layer (ADR-0003 Phase A, v0.1.30).

These tests are the executable encoding of the ADR's *Detailed design*
section -- if the schema or the soft-delete / promotion rules drift,
something here breaks.
"""

from __future__ import annotations

import hashlib
import io
from pathlib import Path

import pytest

from synapse_daemon.files_storage import (
    FileTooLargeError,
    cascade_delete_project_files,
    drop_quarantined,
    final_dir_for,
    find_existing_duplicate,
    finalize_after_scan,
    get_file,
    insert_file_row,
    list_for_project,
    new_file_id,
    soft_delete_file,
    write_streaming_with_hash,
)
from synapse_daemon.projects import Project, create
from synapse_daemon.storage import Storage


def _storage(tmp_path: Path) -> Storage:
    s = Storage(tmp_path / "data")
    s.open()
    s.migrate()
    return s


def _seed_project(s: Storage, pid: str = "demo") -> None:
    with s.transaction() as conn:
        create(
            conn,
            Project(
                id=pid,
                name=pid.title(),
                path=str(Path(s.data_dir).parent),
                launch_cmd="echo hi",
            ),
        )


# ── streaming write + hash ────────────────────────────────────────────────


def test_write_streaming_hashes_correctly(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    payload = b"hello synapse files\n" * 2048
    blob = write_streaming_with_hash(io.BytesIO(payload), "notes.txt", data_dir)
    assert blob.size_bytes == len(payload)
    assert blob.sha256 == hashlib.sha256(payload).hexdigest()
    assert blob.quarantine_path.exists()
    assert blob.quarantine_path.name == blob.on_disk_name
    # Extension preserved.
    assert blob.on_disk_name.endswith(".txt")


def test_file_id_extension_strips_path_traversal_attempts(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    blob = write_streaming_with_hash(io.BytesIO(b"x"), "../../evil.exe", data_dir)
    # Suffix Path() saw was '.exe' -- safe characters, kept. The traversal
    # bits never reach disk because we only ever use the suffix.
    assert blob.on_disk_name.endswith(".exe")
    assert "/" not in blob.on_disk_name and "\\" not in blob.on_disk_name


def test_write_streaming_caps_at_max_bytes(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    payload = b"x" * 4096
    with pytest.raises(FileTooLargeError):
        write_streaming_with_hash(
            io.BytesIO(payload), "big.bin", data_dir, max_bytes=1024
        )
    # The aborted partial file is cleaned up.
    quarantine = list((data_dir / "quarantine").iterdir())
    assert quarantine == []


def test_finalize_moves_to_per_project_dir(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    blob = write_streaming_with_hash(io.BytesIO(b"hi"), "x.txt", data_dir)
    final = finalize_after_scan(blob, data_dir, project_id="demo")
    assert final == data_dir / "projects" / "demo" / "files" / blob.on_disk_name
    assert final.exists()
    assert not blob.quarantine_path.exists()


def test_finalize_uses_shared_dir_when_project_id_is_none(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    blob = write_streaming_with_hash(io.BytesIO(b"hi"), "x.txt", data_dir)
    final = finalize_after_scan(blob, data_dir, project_id=None)
    assert final == data_dir / "files" / "_shared" / blob.on_disk_name


def test_drop_quarantined_cleans_up(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    blob = write_streaming_with_hash(io.BytesIO(b"hi"), "x.txt", data_dir)
    assert blob.quarantine_path.exists()
    drop_quarantined(blob)
    assert not blob.quarantine_path.exists()


# ── DB CRUD ──────────────────────────────────────────────────────────────


def test_insert_and_get_file(tmp_path: Path) -> None:
    s = _storage(tmp_path)
    _seed_project(s)
    try:
        fid = new_file_id()
        with s.transaction() as conn:
            insert_file_row(
                conn,
                file_id=fid,
                project_id="demo",
                original_name="notes.md",
                on_disk_name=f"{fid}.md",
                mime="text/markdown",
                size_bytes=42,
                sha256="abc",
                source="upload",
            )
        row = get_file(s.conn, fid)
        assert row is not None
        assert row.project_id == "demo"
        assert row.source == "upload"
        assert row.scan_result is None
        assert row.duplicate_of is None
    finally:
        s.close()


def test_list_for_project_filters_correctly(tmp_path: Path) -> None:
    s = _storage(tmp_path)
    _seed_project(s, "alpha")
    _seed_project(s, "beta")
    try:
        with s.transaction() as conn:
            for pid in ("alpha", "alpha", "beta", None):
                fid = new_file_id()
                insert_file_row(
                    conn,
                    file_id=fid,
                    project_id=pid,
                    original_name=f"{fid}.txt",
                    on_disk_name=f"{fid}.txt",
                    mime="text/plain",
                    size_bytes=1,
                    sha256="z",
                    source="upload",
                )
        assert len(list_for_project(s.conn, "alpha")) == 2
        assert len(list_for_project(s.conn, "beta")) == 1
        # NULL = shared scope.
        assert len(list_for_project(s.conn, None)) == 1
    finally:
        s.close()


# ── dedup + soft delete + promotion (test pass issues #2, #3) ────────────


def _seed_blob(s: Storage, data_dir: Path, project_id: str | None, content: bytes):
    blob = write_streaming_with_hash(io.BytesIO(content), "x.bin", data_dir)
    final = finalize_after_scan(blob, data_dir, project_id=project_id)
    with s.transaction() as conn:
        insert_file_row(
            conn,
            file_id=blob.file_id,
            project_id=project_id,
            original_name="x.bin",
            on_disk_name=blob.on_disk_name,
            mime="application/octet-stream",
            size_bytes=blob.size_bytes,
            sha256=blob.sha256,
            source="upload",
        )
    return blob, final


def test_find_existing_duplicate_scopes_per_project(tmp_path: Path) -> None:
    s = _storage(tmp_path)
    _seed_project(s, "alpha")
    _seed_project(s, "beta")
    data_dir = s.data_dir
    try:
        a_blob, _ = _seed_blob(s, data_dir, "alpha", b"same bytes")
        # A second upload of the same bytes inside alpha -> match.
        b_blob, _ = _seed_blob(s, data_dir, "alpha", b"same bytes")
        match = find_existing_duplicate(
            s.conn,
            sha256=b_blob.sha256,
            project_id="alpha",
            exclude_id=b_blob.file_id,
        )
        assert match == a_blob.file_id
        # Same bytes in a different scope -> no match.
        match = find_existing_duplicate(
            s.conn,
            sha256=a_blob.sha256,
            project_id="beta",
            exclude_id="zzz",
        )
        assert match is None
    finally:
        s.close()


def test_soft_delete_promotes_a_surviving_duplicate(tmp_path: Path) -> None:
    """ADR test pass issue #3 -- deleting the canonical must not orphan
    its duplicates' bytes."""

    s = _storage(tmp_path)
    _seed_project(s, "demo")
    data_dir = s.data_dir
    try:
        # Original holds the bytes.
        original, original_path = _seed_blob(s, data_dir, "demo", b"important content")
        # Duplicate row -- zero-length on disk, duplicate_of points at original.
        dup_id = new_file_id()
        dup_disk_name = f"{dup_id}.bin"
        dup_path = final_dir_for(data_dir, "demo") / dup_disk_name
        dup_path.parent.mkdir(parents=True, exist_ok=True)
        dup_path.write_bytes(b"")  # zero-length placeholder
        with s.transaction() as conn:
            insert_file_row(
                conn,
                file_id=dup_id,
                project_id="demo",
                original_name="copy.bin",
                on_disk_name=dup_disk_name,
                mime="application/octet-stream",
                size_bytes=original.size_bytes,
                sha256=original.sha256,
                source="upload",
                duplicate_of=original.file_id,
            )

        # Soft-delete the original.
        with s.transaction() as conn:
            soft_delete_file(conn, data_dir, original.file_id)

        # Original is soft-deleted; the duplicate is now canonical and has
        # the bytes.
        deleted_row = get_file(s.conn, original.file_id)
        assert deleted_row is not None
        assert deleted_row.deleted_at is not None
        survivor = get_file(s.conn, dup_id)
        assert survivor is not None
        assert survivor.duplicate_of is None  # promoted
        assert dup_path.exists()
        assert dup_path.read_bytes() == b"important content"
    finally:
        s.close()


def test_soft_delete_renames_for_purge_when_no_duplicates(tmp_path: Path) -> None:
    s = _storage(tmp_path)
    _seed_project(s, "demo")
    data_dir = s.data_dir
    try:
        blob, final = _seed_blob(s, data_dir, "demo", b"alone")
        with s.transaction() as conn:
            soft_delete_file(conn, data_dir, blob.file_id)
        # Original on-disk file got renamed to *.deleted-<iso>.
        assert not final.exists()
        siblings = list(final.parent.iterdir())
        assert any(".deleted-" in p.name for p in siblings)
    finally:
        s.close()


def test_cascade_delete_project_files(tmp_path: Path) -> None:
    """ADR test pass issue #6 -- deleting a project soft-deletes its files."""

    s = _storage(tmp_path)
    _seed_project(s, "demo")
    data_dir = s.data_dir
    try:
        _seed_blob(s, data_dir, "demo", b"a")
        _seed_blob(s, data_dir, "demo", b"b")
        with s.transaction() as conn:
            touched = cascade_delete_project_files(conn, data_dir, "demo")
        assert touched == 2
        assert list_for_project(s.conn, "demo") == []
    finally:
        s.close()
