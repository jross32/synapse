"""Helpers for isolated git worktree management for AI cases."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from .errors import invalid


def resolve_repo_root(path: str) -> Path:
    project_path = Path(path).expanduser().resolve()
    if not project_path.exists():
        raise invalid("ai_case", f"Primary project path does not exist: {project_path}")
    result = subprocess.run(
        ["git", "-C", str(project_path), "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        message = (result.stderr or result.stdout or "not a git repository").strip()
        raise invalid("ai_case", f"Primary project is not in a git repository: {message}")
    return Path(result.stdout.strip()).resolve()


def ensure_worktree(
    *,
    primary_project_path: str,
    worktree_path: Path,
    branch_name: str,
) -> tuple[Path, Path]:
    if shutil.which("git") is None:
        raise invalid("ai_case", "git is not available on PATH.")
    repo_root = resolve_repo_root(primary_project_path)
    worktree_path = worktree_path.resolve()
    worktree_path.parent.mkdir(parents=True, exist_ok=True)
    if worktree_path.exists() and any(worktree_path.iterdir()):
        return repo_root, worktree_path

    worktree_path.mkdir(parents=True, exist_ok=True)
    add = subprocess.run(
        [
            "git",
            "-C",
            str(repo_root),
            "worktree",
            "add",
            "-b",
            branch_name,
            str(worktree_path),
            "HEAD",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if add.returncode != 0:
        # Retry the common "branch already exists" path by attaching to it.
        retry = subprocess.run(
            [
                "git",
                "-C",
                str(repo_root),
                "worktree",
                "add",
                str(worktree_path),
                branch_name,
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if retry.returncode != 0:
            message = (retry.stderr or add.stderr or retry.stdout or add.stdout).strip()
            raise invalid("ai_case", f"Could not create isolated worktree: {message}")
    return repo_root, worktree_path

