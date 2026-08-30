"""Fast, read-only project diagnostics for AI operators.

Project Doctor intentionally avoids mutating a workspace.  It compresses the
first several debugging calls an AI normally makes (path/git/runtime/port/test
signals) into one deterministic report that can be exposed through Synapse.
"""

from __future__ import annotations

import json
import socket
import subprocess
from pathlib import Path
from typing import Any


def _run(args: list[str], cwd: Path, timeout: float = 5.0) -> dict[str, Any]:
    try:
        proc = subprocess.run(
            args,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return {
            "ok": proc.returncode == 0,
            "exit_code": proc.returncode,
            "stdout": proc.stdout.strip(),
            "stderr": proc.stderr.strip(),
        }
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"ok": False, "exit_code": None, "stdout": "", "stderr": str(exc)}


def _port_open(port: int | None) -> bool | None:
    if port is None:
        return None
    try:
        with socket.create_connection(("127.0.0.1", int(port)), timeout=0.35):
            return True
    except OSError:
        return False


def _detect_stack(root: Path) -> dict[str, Any]:
    markers = {
        "node": root / "package.json",
        "python": root / "pyproject.toml",
        "python_requirements": root / "requirements.txt",
        "git": root / ".git",
        "docker": root / "Dockerfile",
    }
    result: dict[str, Any] = {key: path.exists() for key, path in markers.items()}
    if markers["node"].exists():
        try:
            package = json.loads(markers["node"].read_text(encoding="utf-8"))
            result["package_name"] = package.get("name")
            result["package_version"] = package.get("version")
            result["npm_scripts"] = sorted((package.get("scripts") or {}).keys())
        except (OSError, json.JSONDecodeError):
            result["package_json_invalid"] = True
    return result


def diagnose_project(path: str | Path, expected_port: int | None = None) -> dict[str, Any]:
    """Return a compact, read-only health report for a project workspace."""
    root = Path(path).expanduser().resolve()
    report: dict[str, Any] = {
        "path": str(root),
        "exists": root.exists(),
        "is_directory": root.is_dir(),
        "expected_port": expected_port,
        "port_open": _port_open(expected_port),
    }
    if not root.is_dir():
        report.update({"stack": {}, "git": {"is_repo": False}, "issues": ["project_path_missing"]})
        report["healthy"] = False
        return report

    report["stack"] = _detect_stack(root)
    inside = _run(["git", "rev-parse", "--is-inside-work-tree"], root)
    is_repo = inside["ok"] and inside["stdout"].lower() == "true"
    git: dict[str, Any] = {"is_repo": is_repo}
    if is_repo:
        status = _run(["git", "status", "--porcelain=v1", "--branch"], root)
        lines = status["stdout"].splitlines() if status["stdout"] else []
        git.update(
            {
                "branch": lines[0][3:] if lines and lines[0].startswith("## ") else None,
                "dirty": any(not line.startswith("## ") for line in lines),
                "change_count": sum(1 for line in lines if not line.startswith("## ")),
            }
        )
    report["git"] = git

    issues: list[str] = []
    if expected_port is not None and report["port_open"] is False:
        issues.append("expected_port_closed")
    if is_repo and git.get("dirty"):
        issues.append("git_worktree_dirty")
    report["issues"] = issues
    # A dirty worktree is noteworthy, not unhealthy. Runtime/path failures are health failures.
    report["healthy"] = report["exists"] and report["is_directory"] and "expected_port_closed" not in issues
    return report
