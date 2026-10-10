"""Fail-closed Git publication readiness check for Synapse-managed projects."""
from __future__ import annotations

import subprocess
from pathlib import Path
from urllib.parse import urlparse


def _git(root: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(root), *args], capture_output=True,
        text=True, timeout=12, check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError("Git check failed: " + " ".join(args))
    return completed.stdout.strip()


def publication_readiness(root: Path, expected_owner: str) -> dict:
    """Read-only checks. Success does not authorize a push or replace CI."""
    blockers = []
    facts = {}
    if not expected_owner or "/" in expected_owner or "\\" in expected_owner:
        return {"ready": False, "blockers": ["Valid GitHub owner required"], "facts": facts}
    try:
        root = root.resolve(strict=True)
        top = Path(_git(root, "rev-parse", "--show-toplevel")).resolve()
        if top != root:
            blockers.append("Project path is not the repository root")
        if _git(root, "status", "--porcelain"):
            blockers.append("Working tree has uncommitted changes")
        branch = _git(root, "branch", "--show-current")
        facts["branch"] = branch
        if not branch:
            blockers.append("Detached HEAD")
        remotes = _git(root, "remote", "get-url", "origin")
        # Accept only conventional GitHub SSH or HTTPS Git remote syntax.
        if remotes.startswith("git@github.com:"):
            repo_path = remotes[len("git@github.com:"):]
        elif remotes.startswith("https://github.com/"):
            repo_path = remotes[len("https://github.com/"):]
        else:
            repo_path = ""
        parts = repo_path.removesuffix(".git").split("/")
        if len(parts) != 2 or parts[0].lower() != expected_owner.lower() or not parts[1]:
            blockers.append("Origin is not a repository owned by the expected GitHub account")
        else:
            facts["repository"] = parts[0] + "/" + parts[1]
        upstream = _git(root, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}")
        facts["upstream"] = upstream
        counts = _git(root, "rev-list", "--left-right", "--count", "HEAD..." + upstream).split()
        if len(counts) != 2:
            blockers.append("Unable to compare local and upstream commits")
        else:
            ahead, behind = map(int, counts)
            facts.update(ahead=ahead, behind=behind)
            if behind:
                blockers.append("Upstream has commits not present locally")
    except (OSError, RuntimeError, subprocess.TimeoutExpired, ValueError) as error:
        blockers.append("Unable to verify Git state: " + type(error).__name__)
    # This check cannot independently prove authorization or release quality.
    blockers.append("GitHub authorization and project quality gates have not been independently verified")
    return {"ready": not blockers, "blockers": blockers, "facts": facts,
            "requires": ["Verified authenticated GitHub identity",
                         "Project test and quality gates", "Branch protection / review policy"]}
