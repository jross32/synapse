"""Read-only GitHub source publishing evidence for worker completion gates."""
from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PublishEvidence:
    ready: bool
    reason: str
    local_sha: str | None = None
    remote_sha: str | None = None
    branch: str | None = None


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=repo, capture_output=True, text=True,
        timeout=20, check=True,
    )
    return result.stdout.strip()


def check_github_publish(repo: Path, *, expected_sha: str | None = None) -> PublishEvidence:
    """Never mutate Git state; fail closed if the exact SHA is not on origin."""
    try:
        remote = _git(repo, "remote", "get-url", "origin")
        if not re.search(r"(?:github\.com[:/])jross32/synapse(?:\.git)?$", remote, re.I):
            return PublishEvidence(False, "unexpected_remote")
        branch = _git(repo, "symbolic-ref", "--quiet", "--short", "HEAD")
        if not branch or branch in {"main", "master"}:
            return PublishEvidence(False, "unsafe_branch", branch=branch)
        sha = _git(repo, "rev-parse", "HEAD")
        if not re.fullmatch(r"[0-9a-f]{40}", sha):
            return PublishEvidence(False, "invalid_sha", branch=branch)
        if expected_sha is not None and sha != expected_sha:
            return PublishEvidence(False, "head_changed", sha, branch=branch)
        lines = _git(repo, "ls-remote", "--heads", "origin", f"refs/heads/{branch}").splitlines()
        if len(lines) != 1:
            return PublishEvidence(False, "remote_branch_missing", sha, branch=branch)
        parts = lines[0].split()
        if len(parts) != 2 or parts[1] != f"refs/heads/{branch}":
            return PublishEvidence(False, "invalid_remote_response", sha, branch=branch)
        remote_sha = parts[0]
        if not re.fullmatch(r"[0-9a-f]{40}", remote_sha):
            return PublishEvidence(False, "invalid_remote_sha", sha, branch=branch)
        if sha != remote_sha:
            return PublishEvidence(False, "not_pushed", sha, remote_sha, branch)
        return PublishEvidence(True, "verified", sha, remote_sha, branch)
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return PublishEvidence(False, "git_unavailable")
