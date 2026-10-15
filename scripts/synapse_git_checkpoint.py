"""Scoped, fail-closed automatic Git checkpoints for Synapse worker builds.

Designed to be invoked after a worker's tests pass. Never stages unrelated files.
Publishing remains a separate, explicitly authorized action.
"""
from __future__ import annotations
import argparse
import json
import subprocess
from pathlib import Path


def git(root: Path, *args: str) -> str:
    result = subprocess.run(["git", "-C", str(root), *args], capture_output=True,
                            text=True, timeout=30, check=False)
    if result.returncode:
        raise RuntimeError(f"Git operation failed: {args[0]}: {result.stderr.strip()[:200]}")
    return result.stdout.strip()


def checkpoint(repo: Path, paths: list[str], *, commit: bool = False, message: str = "") -> dict:
    repo = repo.resolve(strict=True)
    top = Path(git(repo, "rev-parse", "--show-toplevel")).resolve()
    if repo != top:
        raise ValueError("Specify the repository root")
    if not paths or any(not p or p.startswith(("/", "\\")) or ".." in Path(p).parts for p in paths):
        raise ValueError("Explicit safe relative paths required")
    if not git(repo, "branch", "--show-current"):
        raise ValueError("Detached HEAD")
    for item in paths:
        resolved = (repo / item).resolve()
        if not resolved.is_relative_to(repo):
            raise ValueError("Path escapes repository")
        if not resolved.exists():
            raise ValueError("Missing checkpoint path: " + item)
    # Reject pre-staged unrelated changes to avoid accidentally including other workers' work.
    already_staged = set(git(repo, "diff", "--cached", "--name-only").splitlines())
    allowed = tuple(p.rstrip("/") + "/" for p in paths)
    if any(not (name in paths or name.startswith(allowed)) for name in already_staged):
        raise ValueError("Unrelated staged changes: refusing checkpoint")
    changed = git(repo, "status", "--porcelain", "--", *paths)
    if not changed:
        return {"changed": False, "committed": False}
    if not commit:
        return {"changed": True, "committed": False, "preview": changed.splitlines()[:40]}
    if not message or len(message) > 150:
        raise ValueError("A concise checkpoint message is required")
    git(repo, "add", "--", *paths)
    staged = git(repo, "diff", "--cached", "--name-only")
    if not staged:
        return {"changed": False, "committed": False}
    git(repo, "commit", "-m", message, "--only", "--", *paths)
    return {"changed": True, "committed": True, "commit": git(repo, "rev-parse", "--short", "HEAD"),
            "paths": paths}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True, type=Path)
    parser.add_argument("--path", action="append", required=True)
    parser.add_argument("--commit", action="store_true")
    parser.add_argument("--message", default="")
    args = parser.parse_args()
    print(json.dumps(checkpoint(args.repo, args.path, commit=args.commit, message=args.message)))


if __name__ == "__main__":
    main()
