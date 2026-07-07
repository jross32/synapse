"""Isolated-worktree helpers (previously untested) -- git_worktrees.py.

Hermetic: every test builds a throwaway git repo under tmp_path. Skipped entirely when git is
not on PATH so CI without git stays green.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from synapse_daemon.errors import SynapseError
from synapse_daemon.git_worktrees import ensure_worktree, resolve_repo_root

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git not on PATH")


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True, text=True)


def _branch(cwd: Path) -> str:
    out = subprocess.run(
        ["git", "-C", str(cwd), "rev-parse", "--abbrev-ref", "HEAD"],
        check=True, capture_output=True, text=True,
    )
    return out.stdout.strip()


def _init_repo(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    _git(path, "init", "-q")
    _git(path, "config", "user.email", "t@example.com")
    _git(path, "config", "user.name", "tester")
    (path / "README.md").write_text("hi", encoding="utf-8")
    _git(path, "add", "-A")
    _git(path, "commit", "-q", "-m", "init")
    return path


def test_resolve_repo_root_from_subdir(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path / "repo")
    sub = repo / "a" / "b"
    sub.mkdir(parents=True)
    assert resolve_repo_root(str(sub)).samefile(repo)


def test_resolve_repo_root_missing_path(tmp_path: Path) -> None:
    with pytest.raises(SynapseError):
        resolve_repo_root(str(tmp_path / "does-not-exist"))


def test_resolve_repo_root_non_git(tmp_path: Path) -> None:
    plain = tmp_path / "plain"
    plain.mkdir()
    with pytest.raises(SynapseError):
        resolve_repo_root(str(plain))


def test_ensure_worktree_creates_new_branch(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path / "repo")
    wt = tmp_path / "wt"
    root, created = ensure_worktree(
        primary_project_path=str(repo), worktree_path=wt, branch_name="wt-feature"
    )
    assert root.samefile(repo)
    assert created.samefile(wt)
    assert (wt / "README.md").exists()
    assert _branch(wt) == "wt-feature"


def test_ensure_worktree_idempotent(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path / "repo")
    wt = tmp_path / "wt"
    ensure_worktree(primary_project_path=str(repo), worktree_path=wt, branch_name="wt-x")
    # Second call sees a populated worktree and returns without erroring or re-adding.
    root, created = ensure_worktree(
        primary_project_path=str(repo), worktree_path=wt, branch_name="wt-x"
    )
    assert root.samefile(repo)
    assert created.samefile(wt)


def test_ensure_worktree_attaches_existing_branch(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path / "repo")
    # Pre-create a branch (not checked out anywhere) so `add -b` fails and the retry path attaches it.
    _git(repo, "branch", "preexisting")
    wt = tmp_path / "wt"
    root, created = ensure_worktree(
        primary_project_path=str(repo), worktree_path=wt, branch_name="preexisting"
    )
    assert created.samefile(wt)
    assert _branch(wt) == "preexisting"
