"""Tests for the project workbench endpoint (v0.1.29 · ADR-0002 Phase B)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from synapse_daemon.app import build_app
from synapse_daemon.projects import Project, create
from synapse_daemon.storage import Storage
from synapse_daemon.ws import EventBus

posix_only = pytest.mark.skipif(
    sys.platform == "win32", reason="POSIX PTY only in tests"
)


def _harness(tmp_path: Path):
    storage = Storage(tmp_path / "data")
    storage.open()
    storage.migrate()
    with storage.transaction() as conn:
        create(
            conn,
            Project(
                id="ws-demo",
                name="Workbench Demo",
                path=str(tmp_path),
                launch_cmd="echo hi",
            ),
        )
    app = build_app(storage, EventBus())
    client = TestClient(app, headers={"X-Synapse-Token": app.state.auth.local_token})
    return client


@posix_only
def test_workbench_opens_pre_cd_into_project_path(tmp_path: Path) -> None:
    client = _harness(tmp_path)
    with client as c:
        res = c.post(
            "/api/v1/projects/ws-demo/workbench",
            json={"argv": ["/bin/cat"]},
        )
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["project_id"] == "ws-demo"
        assert body["cwd"] == str(tmp_path)
        # Clean up so the next test isn't racing leftover children.
        c.delete(f"/api/v1/pty/{body['session_id']}")


def test_workbench_unknown_project_is_404(tmp_path: Path) -> None:
    client = _harness(tmp_path)
    with client as c:
        res = c.post("/api/v1/projects/never-heard-of/workbench")
        assert res.status_code == 404


def test_workbench_requires_auth(tmp_path: Path) -> None:
    storage = Storage(tmp_path / "data")
    storage.open()
    storage.migrate()
    app = build_app(storage, EventBus())
    unauthed = TestClient(app)
    assert unauthed.post("/api/v1/projects/x/workbench").status_code == 401


@posix_only
def test_workbench_session_persists_transcript_on_exit(tmp_path: Path) -> None:
    """ADR-0003 Phase D -- workbench-tagged sessions write scrollback to
    project_files with source='transcript' when they exit."""

    client = _harness(tmp_path)
    with client as c:
        # echo prints + exits cleanly; the scrollback is captured.
        spawn = c.post(
            "/api/v1/projects/ws-demo/workbench",
            json={"argv": ["/bin/echo", "transcript-smoke"]},
        )
        assert spawn.status_code == 200
        sid = spawn.json()["session_id"]

        # Wait for the session to exit (echo is fast).
        import time

        for _ in range(40):
            if c.get(f"/api/v1/pty/{sid}").status_code == 404:
                break
            time.sleep(0.1)

        files = c.get("/api/v1/projects/ws-demo/files").json()["files"]
        transcripts = [f for f in files if f["source"] == "transcript"]
        assert transcripts, "expected at least one transcript file"
        assert transcripts[0]["source_session"] == sid
        # Pull the bytes back and confirm the echo output round-tripped.
        dl = c.get(f"/api/v1/projects/ws-demo/files/{transcripts[0]['id']}")
        assert dl.status_code == 200
        assert b"transcript-smoke" in dl.content
