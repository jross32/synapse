"""Isolated Git worktree management and non-destructive verified merges."""
from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path


class MergeNeedsReview(Exception):
    pass


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, timeout=60)
    if result.returncode:
        raise MergeNeedsReview(result.stderr.strip() or result.stdout.strip())
    return result.stdout.strip()


@dataclass(frozen=True)
class Worktree:
    path: Path
    branch: str
    base_commit: str


def create_agent_worktree(repo: Path, path: Path, branch: str) -> Worktree:
    repo = repo.resolve(strict=True)
    if Path(_git(repo, "rev-parse", "--show-toplevel")).resolve() != repo:
        raise ValueError("Expected repository root")
    if not branch.startswith("synapse-agent/") or not all(c.isalnum() or c in "/-_" for c in branch):
        raise ValueError("Agent branch must use synapse-agent namespace")
    if path.exists():
        raise ValueError("Worktree destination already exists")
    base = _git(repo, "rev-parse", "HEAD")
    _git(repo, "worktree", "add", "-b", branch, str(path), base)
    return Worktree(path, branch, base)


def merge_agent_worktree(repo: Path, agent: Worktree, *, validation_commands: list[list[str]]) -> str:
    """Verify source branch and merge on a temporary integration worktree.

    Never mutates the user's checked-out branch. Callers may promote the
    returned integration commit only after validating it.
    """
    repo = repo.resolve(strict=True)
    if _git(repo, "status", "--porcelain"):
        raise MergeNeedsReview("Main worktree is dirty; refusing to integrate")
    head = _git(repo, "rev-parse", "HEAD")
    if head != agent.base_commit:
        raise MergeNeedsReview("Base advanced; reconcile against current HEAD")
    if _git(agent.path, "status", "--porcelain"):
        raise MergeNeedsReview("Agent worktree has uncommitted changes")
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory(prefix="synapse-merge-") as tmp:
        target = Path(tmp) / "integration"
        _git(repo, "worktree", "add", "--detach", str(target), head)
        try:
            # A successful merge is not sufficient: conflict markers and
            # unvalidated source must never be silently promoted.
            _git(target, "merge", "--no-edit", "--no-ff", agent.branch)
            if not validation_commands:
                raise MergeNeedsReview("Validation commands are required before promotion")
            for command in validation_commands:
                result = subprocess.run(command, cwd=target, capture_output=True, text=True, timeout=180)
                if result.returncode:
                    raise MergeNeedsReview("Integration validation failed: " + " ".join(command))
            return _git(target, "rev-parse", "HEAD")
        finally:
            _git(repo, "worktree", "remove", "--force", str(target))
