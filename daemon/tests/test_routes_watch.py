"""Tests for POST /api/v1/watch/repo (see repo_watch.py for why this endpoint exists)."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from synapse_daemon.app import build_app
from synapse_daemon.storage import Storage
from synapse_daemon.ws import EventBus

git_required = pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")


def _harness(tmp_path: Path) -> TestClient:
    storage = Storage(tmp_path / "data")
    storage.open()
    storage.migrate()
    app = build_app(storage, EventBus())
    return TestClient(app, headers={"X-Synapse-Token": app.state.auth.local_token})


def _init_git_repo(path: Path) -> None:
    subprocess.run(["git", "init"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.email", "t@example.com"], cwd=path, check=True)


@git_required
def test_watch_repo_times_out_cleanly_via_rest(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    client = _harness(tmp_path)
    res = client.post("/api/v1/watch/repo", json={"path": str(tmp_path), "timeout_seconds": 1})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["changed"] is False
    assert body["error"] is None


def test_watch_repo_rejects_a_relative_path(tmp_path: Path) -> None:
    client = _harness(tmp_path)
    res = client.post("/api/v1/watch/repo", json={"path": "relative/dir", "timeout_seconds": 1})
    assert res.status_code == 422, res.text


def test_watch_repo_404s_a_missing_directory(tmp_path: Path) -> None:
    client = _harness(tmp_path)
    res = client.post(
        "/api/v1/watch/repo", json={"path": str(tmp_path / "nope"), "timeout_seconds": 1}
    )
    assert res.status_code == 422, res.text
