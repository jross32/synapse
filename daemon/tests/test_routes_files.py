"""Tests for the file REST endpoints (ADR-0003 Phase A · v0.1.30)."""

from __future__ import annotations

import io
from pathlib import Path

from fastapi.testclient import TestClient

from synapse_daemon.app import build_app
from synapse_daemon.projects import Project, create
from synapse_daemon.storage import Storage
from synapse_daemon.ws import EventBus


def _harness(tmp_path: Path):
    storage = Storage(tmp_path / "data")
    storage.open()
    storage.migrate()
    with storage.transaction() as conn:
        create(
            conn,
            Project(
                id="demo",
                name="Demo",
                path=str(tmp_path),
                launch_cmd="echo hi",
            ),
        )
    app = build_app(storage, EventBus())
    client = TestClient(app, headers={"X-Synapse-Token": app.state.auth.local_token})
    return client, storage


def _post(client: TestClient, url: str, *files: tuple[str, bytes, str]):
    payload = [("files", (name, io.BytesIO(data), mime)) for name, data, mime in files]
    return client.post(url, files=payload)


# ── per-project happy path ────────────────────────────────────────────────


def test_upload_list_download_delete_roundtrip(tmp_path: Path) -> None:
    client, _ = _harness(tmp_path)
    with client as c:
        # Upload.
        res = _post(c, "/api/v1/projects/demo/files", ("notes.md", b"# hi", "text/markdown"))
        assert res.status_code == 200
        body = res.json()
        assert len(body["files"]) == 1
        entry = body["files"][0]
        assert entry["ok"] is True
        assert entry["original_name"] == "notes.md"
        assert entry["size_bytes"] == 4
        assert entry["mime"] == "text/markdown"
        assert entry["duplicate_of"] is None
        fid = entry["id"]

        # List.
        listed = c.get("/api/v1/projects/demo/files").json()
        assert any(f["id"] == fid for f in listed["files"])

        # Download.
        dl = c.get(f"/api/v1/projects/demo/files/{fid}")
        assert dl.status_code == 200
        assert dl.content == b"# hi"

        # Delete.
        gone = c.delete(f"/api/v1/projects/demo/files/{fid}")
        assert gone.status_code == 204

        # Subsequent fetches 404.
        assert c.get(f"/api/v1/projects/demo/files/{fid}").status_code == 404


def test_multi_file_upload_in_one_request(tmp_path: Path) -> None:
    client, _ = _harness(tmp_path)
    with client as c:
        res = _post(
            c,
            "/api/v1/projects/demo/files",
            ("a.txt", b"alpha", "text/plain"),
            ("b.txt", b"beta",  "text/plain"),
            ("c.txt", b"gamma", "text/plain"),
        )
        assert res.status_code == 200
        names = sorted(e["original_name"] for e in res.json()["files"])
        assert names == ["a.txt", "b.txt", "c.txt"]


def test_dedup_links_second_upload_to_first(tmp_path: Path) -> None:
    """Test pass issue #2 -- second upload of same bytes gets duplicate_of."""

    client, _ = _harness(tmp_path)
    with client as c:
        first = _post(c, "/api/v1/projects/demo/files", ("a.bin", b"same", "application/octet-stream")).json()
        second = _post(c, "/api/v1/projects/demo/files", ("b.bin", b"same", "application/octet-stream")).json()

    canonical_id = first["files"][0]["id"]
    assert second["files"][0]["duplicate_of"] == canonical_id


def test_download_of_duplicate_serves_canonical_bytes(tmp_path: Path) -> None:
    client, _ = _harness(tmp_path)
    with client as c:
        _post(c, "/api/v1/projects/demo/files", ("a.bin", b"same content", "application/octet-stream"))
        dup = _post(c, "/api/v1/projects/demo/files", ("b.bin", b"same content", "application/octet-stream")).json()
        dup_id = dup["files"][0]["id"]
        # The duplicate row has no bytes on disk -- it should redirect to the canonical.
        dl = c.get(f"/api/v1/projects/demo/files/{dup_id}")
        assert dl.status_code == 200
        assert dl.content == b"same content"


def test_oversized_upload_is_rejected_per_file(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SYNAPSE_MAX_FILE_BYTES", "100")
    client, _ = _harness(tmp_path)
    big = b"x" * 4096
    with client as c:
        res = _post(c, "/api/v1/projects/demo/files", ("big.bin", big, "application/octet-stream"))
        assert res.status_code == 200
        entry = res.json()["files"][0]
        assert entry["ok"] is False
        assert "exceeded" in entry["reason"]


def test_too_many_files_in_one_request(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SYNAPSE_MAX_FILES_PER_REQUEST", "2")
    client, _ = _harness(tmp_path)
    with client as c:
        res = _post(
            c,
            "/api/v1/projects/demo/files",
            ("a.txt", b"a", "text/plain"),
            ("b.txt", b"b", "text/plain"),
            ("c.txt", b"c", "text/plain"),
        )
        assert res.status_code == 422
        assert res.json()["code"] == "files.invalid"


def test_unknown_project_404(tmp_path: Path) -> None:
    client, _ = _harness(tmp_path)
    with client as c:
        res = _post(c, "/api/v1/projects/never/files", ("a.txt", b"a", "text/plain"))
        assert res.status_code == 404


# ── shared scope ──────────────────────────────────────────────────────────


def test_shared_upload_and_list(tmp_path: Path) -> None:
    client, _ = _harness(tmp_path)
    with client as c:
        res = _post(c, "/api/v1/files", ("shared.md", b"shared body", "text/markdown"))
        assert res.status_code == 200
        fid = res.json()["files"][0]["id"]
        listed = c.get("/api/v1/files").json()
        assert any(f["id"] == fid for f in listed["files"])

        # Per-project list MUST NOT include shared files.
        in_project = c.get("/api/v1/projects/demo/files").json()
        assert all(f["id"] != fid for f in in_project["files"])


def test_shared_file_not_returned_from_per_project_download(tmp_path: Path) -> None:
    client, _ = _harness(tmp_path)
    with client as c:
        fid = _post(c, "/api/v1/files", ("x.txt", b"hi", "text/plain")).json()["files"][0]["id"]
        # Wrong scope -> 404, no cross-scope read.
        assert c.get(f"/api/v1/projects/demo/files/{fid}").status_code == 404
        # Correct scope -> 200.
        assert c.get(f"/api/v1/files/{fid}").status_code == 200


# ── auth ──────────────────────────────────────────────────────────────────


def test_files_requires_auth(tmp_path: Path) -> None:
    storage = Storage(tmp_path / "data")
    storage.open()
    storage.migrate()
    app = build_app(storage, EventBus())
    unauthed = TestClient(app)
    assert unauthed.get("/api/v1/files").status_code == 401
    assert unauthed.post("/api/v1/projects/demo/files").status_code == 401


# ── ADR-0003 Phase C: AV scan integration ────────────────────────────────


def test_av_blocked_upload_does_not_land_on_disk(tmp_path: Path, monkeypatch) -> None:
    """A blocked scan must:
       * leave the row hidden (deleted_at set so list doesn't include it)
       * never finalise the bytes
       * return ok=false with a meaningful reason
       * audit as file.upload_blocked
    """

    from synapse_daemon import files_av, routes_files

    async def _block(_path):  # noqa: ANN001
        return files_av.ScanResult(
            result=files_av.SCAN_BLOCKED,
            engine=files_av.ENGINE_DEFENDER,
            threat_name="Test:EICAR/Demo",
        )

    monkeypatch.setattr(routes_files, "scan_file", _block)

    client, storage = _harness(tmp_path)
    with client as c:
        res = _post(
            c,
            "/api/v1/projects/demo/files",
            ("evil.bin", b"X5O!P%@AP[4\\PZX54(P^)7CC)7}$EICAR-DEMO", "application/octet-stream"),
        )
        assert res.status_code == 200
        body = res.json()["files"][0]
        assert body["ok"] is False
        assert "defender" in body["reason"].lower() or "av" in body["reason"].lower()
        assert body["scan_result"] == "blocked"
        assert body["threat_name"] == "Test:EICAR/Demo"

        listed = c.get("/api/v1/projects/demo/files").json()
        assert all(f["original_name"] != "evil.bin" for f in listed["files"])

    # Audit row recorded with the threat name in details.
    audit_row = storage.conn.execute(
        "SELECT action, error_code, details_json FROM audit_log WHERE action = 'file.upload_blocked'"
    ).fetchone()
    assert audit_row is not None
    assert audit_row["error_code"] == "files.av_blocked"
    import json

    details = json.loads(audit_row["details_json"])
    assert details["threat_name"] == "Test:EICAR/Demo"


def test_av_unavailable_still_uploads_with_banner_metadata(tmp_path: Path, monkeypatch) -> None:
    """Scanning unavailable must NOT block uploads -- it just records the
    state so the UI can show "scanning unavailable"."""

    from synapse_daemon import files_av, routes_files

    async def _unavail(_path):  # noqa: ANN001
        return files_av.ScanResult(result=files_av.SCAN_UNAVAILABLE, engine=None)

    monkeypatch.setattr(routes_files, "scan_file", _unavail)

    client, _ = _harness(tmp_path)
    with client as c:
        res = _post(c, "/api/v1/projects/demo/files", ("notes.md", b"hello", "text/markdown"))
        assert res.status_code == 200
        body = res.json()["files"][0]
        assert body["ok"] is True
        assert body["scan_result"] == "unavailable"
        assert body["scan_engine"] is None

        listed = c.get("/api/v1/projects/demo/files").json()["files"]
        match = next(f for f in listed if f["original_name"] == "notes.md")
        assert match["scan_result"] == "unavailable"


def test_av_clean_records_engine_name_on_row(tmp_path: Path) -> None:
    """The default conftest mock returns clean+defender -- a clean upload
    should persist the engine name so the UI can show it."""

    client, _ = _harness(tmp_path)
    with client as c:
        res = _post(c, "/api/v1/projects/demo/files", ("doc.md", b"safe", "text/markdown"))
        body = res.json()["files"][0]
        assert body["ok"] is True
        assert body["scan_result"] == "clean"
        assert body["scan_engine"] == "defender"

        listed = c.get("/api/v1/projects/demo/files").json()["files"]
        match = next(f for f in listed if f["original_name"] == "doc.md")
        assert match["scan_result"] == "clean"
        assert match["scan_engine"] == "defender"
