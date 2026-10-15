"""Push a branch and verify remote state even when transport feedback is lost.

Usage: python scripts/verified_git_push.py <branch> [remote]
Does not retry blindly or force-push. Safe to run again after a lost response.
"""
from __future__ import annotations

import re
import subprocess
import sys


def git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], text=True, capture_output=True, timeout=90)


def remote_sha(remote: str, branch: str) -> str | None:
    result = git("ls-remote", "--heads", remote, branch)
    if result.returncode:
        raise RuntimeError("Remote verification unavailable; outcome unknown. Do not retry automatically.")
    for line in result.stdout.splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[1] == "refs/heads/" + branch:
            return parts[0]
    return None


def main() -> int:
    if len(sys.argv) not in (2, 3):
        print("Usage: verified_git_push.py <branch> [remote]", file=sys.stderr)
        return 2
    branch = sys.argv[1]
    remote = sys.argv[2] if len(sys.argv) == 3 else "origin"
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/-]*", branch) or ".." in branch or branch.endswith(("/", ".")):
        print("Invalid branch", file=sys.stderr)
        return 2
    local = git("rev-parse", "--verify", "refs/heads/" + branch)
    if local.returncode:
        print("Local branch not found", file=sys.stderr)
        return 2
    sha = local.stdout.strip()
    try:
        if remote_sha(remote, branch) == sha:
            print(f"VERIFIED_ALREADY_PUBLISHED {branch} {sha}")
            return 0
        result = git("push", remote, "refs/heads/" + branch + ":refs/heads/" + branch)
        # Do not trust the push response alone: verify immutable remote SHA.
        actual = remote_sha(remote, branch)
        if actual == sha:
            print(f"VERIFIED_PUBLISHED {branch} {sha}")
            return 0
        print(f"NOT_VERIFIED {branch}; push exit={result.returncode}; remote={actual or 'missing'}", file=sys.stderr)
        return 1
    except (RuntimeError, subprocess.TimeoutExpired) as exc:
        print(f"OUTCOME_UNKNOWN: {exc}; check remote before retrying", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
