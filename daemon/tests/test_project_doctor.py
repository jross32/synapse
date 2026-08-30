from __future__ import annotations

import json
import socket
import subprocess
from pathlib import Path

from synapse_daemon.project_doctor import diagnose_project


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


def test_missing_project_is_unhealthy(tmp_path: Path) -> None:
    report = diagnose_project(tmp_path / "missing")
    assert report["healthy"] is False
    assert report["issues"] == ["project_path_missing"]
    assert report["git"]["is_repo"] is False


def test_detects_node_repo_and_dirty_tree(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text(
        json.dumps({"name": "demo", "version": "1.2.3", "scripts": {"test": "echo ok", "dev": "vite"}}),
        encoding="utf-8",
    )
    _git(tmp_path, "init")
    report = diagnose_project(tmp_path)
    assert report["stack"]["node"] is True
    assert report["stack"]["package_name"] == "demo"
    assert report["stack"]["npm_scripts"] == ["dev", "test"]
    assert report["git"]["is_repo"] is True
    assert report["git"]["dirty"] is True
    assert "git_worktree_dirty" in report["issues"]
    assert report["healthy"] is True


def test_expected_port_health(tmp_path: Path) -> None:
    with socket.socket() as server:
        server.bind(("127.0.0.1", 0))
        server.listen(1)
        port = server.getsockname()[1]
        report = diagnose_project(tmp_path, expected_port=port)
        assert report["port_open"] is True
        assert report["healthy"] is True

    closed = diagnose_project(tmp_path, expected_port=port)
    assert closed["port_open"] is False
    assert closed["healthy"] is False
    assert "expected_port_closed" in closed["issues"]
