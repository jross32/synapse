"""Fail-closed, explicitly authorized non-force GitHub feature-branch publishing."""
from __future__ import annotations
import re
import subprocess
from pathlib import Path

_SAFE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._/-]{0,120}$")
_OWNER = re.compile(r"^[a-zA-Z0-9-]{1,39}$")


def _git(root: Path, *args: str, ok: bool = True) -> subprocess.CompletedProcess:
    result = subprocess.run(["git", "-C", str(root), *args], capture_output=True,
                            text=True, timeout=30, check=False)
    if ok and result.returncode:
        raise RuntimeError("Git operation failed: " + args[0])
    return result


def publish_verified_branch(root: Path, *, owner: str, branch: str) -> dict:
    """Push current feature branch only when origin is the explicitly expected GitHub owner.

    Does not create repositories, merge branches, change remote config, or force-push.
    """
    root = root.resolve(strict=True)
    if not _OWNER.fullmatch(owner or "") or not _SAFE.fullmatch(branch or ""):
        raise ValueError("Invalid owner or branch")
    if not branch.startswith("feature/") or ".." in branch or branch.endswith((".", "/")):
        raise ValueError("Only named feature branches can be auto-published")
    top = Path(_git(root, "rev-parse", "--show-toplevel").stdout.strip()).resolve()
    if top != root:
        raise ValueError("Repository root required")
    if _git(root, "branch", "--show-current").stdout.strip() != branch:
        raise ValueError("Branch mismatch")
    if _git(root, "status", "--porcelain").stdout.strip():
        raise ValueError("Working tree not clean; publication blocked")
    remote = _git(root, "remote", "get-url", "origin").stdout.strip()
    prefixes = ("https://github.com/", "git@github.com:")
    suffix = remote.removeprefix(prefixes[0]) if remote.startswith(prefixes[0]) else (
        remote.removeprefix(prefixes[1]) if remote.startswith(prefixes[1]) else "")
    parts = suffix.removesuffix(".git").split("/")
    if len(parts) != 2 or parts[0].lower() != owner.lower() or not parts[1]:
        raise ValueError("Unapproved GitHub origin")
    ref = "refs/heads/" + branch
    advertised = _git(root, "ls-remote", "--heads", "origin", ref).stdout.strip()
    if advertised:
        remote_sha = advertised.split()[0]
        # Fetch only the explicitly requested branch, then prove non-divergence.
        _git(root, "fetch", "--no-tags", "origin", ref)
        ancestor = _git(root, "merge-base", "--is-ancestor", remote_sha, "HEAD", ok=False)
        if ancestor.returncode != 0:
            raise ValueError("Remote branch has diverged; refusing push")
    _git(root, "push", "origin", "HEAD:" + ref)
    return {"pushed": True, "branch": branch, "commit": _git(root, "rev-parse", "--short", "HEAD").stdout.strip()}
