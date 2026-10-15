"""Create an isolated Git worktree for a worker without modifying shared files."""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

_BRANCH = re.compile(r"^feature/[A-Za-z0-9][A-Za-z0-9._/-]{0,110}$")


def prepare_worker_worktree(repository: Path, destination: Path, branch: str) -> dict:
    repository = repository.resolve(strict=True)
    destination = destination.resolve()
    if not _BRANCH.fullmatch(branch or "") or ".." in branch or branch.endswith(("/", ".")):
        raise ValueError("A safe feature branch is required")
    if destination.exists():
        raise ValueError("Worktree destination already exists")
    if destination == repository or repository in destination.parents:
        raise ValueError("Worktree must be outside the source repository")
    top = subprocess.run(["git", "-C", str(repository), "rev-parse", "--show-toplevel"],
                         capture_output=True, text=True, timeout=15, check=True).stdout.strip()
    if Path(top).resolve() != repository:
        raise ValueError("Repository root required")
    exists = subprocess.run(["git", "-C", str(repository), "show-ref", "--verify",
                             "--quiet", "refs/heads/" + branch], timeout=15, check=False)
    if exists.returncode == 0:
        raise ValueError("Branch already exists; refusing to reuse another worker's branch")
    if exists.returncode != 1:
        raise RuntimeError("Cannot inspect branch")
    destination.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "-C", str(repository), "worktree", "add", "-b", branch,
                    str(destination), "HEAD"], capture_output=True, text=True,
                   timeout=45, check=True)
    return {"workspace": str(destination), "branch": branch, "isolated": True}
