"""Independent evidence reconciliation for authenticated ChatGPT coding work.

A response is not proof of a commit. Verify that the requested commit exists,
that the tree is clean and that a specified focused pytest command succeeds.
This module does not change any work item directly.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

COMMIT_RE = re.compile(r"\b[0-9a-f]{7,40}\b")

def verify_coding_receipt(worktree: Path, commit: str, test_paths: list[str],
                          python_executable: str, *, timeout: int = 120) -> dict:
    root = Path(worktree).resolve()
    if not root.is_dir() or not COMMIT_RE.fullmatch(commit):
        raise ValueError("valid worktree and commit required")
    if not test_paths or any(not re.fullmatch(r"daemon/tests/test_[A-Za-z0-9_]+\.py", p) for p in test_paths):
        raise ValueError("tests must be explicit local regression modules")
    def run(argv):
        return subprocess.run(argv, cwd=root, capture_output=True, text=True,
                              timeout=timeout, check=False)
    inside = run(["git", "rev-parse", "--is-inside-work-tree"])
    if inside.returncode != 0 or inside.stdout.strip() != "true":
        raise RuntimeError("not a Git working tree")
    head = run(["git", "rev-parse", "HEAD"])
    target = run(["git", "rev-parse", f"{commit}^{{commit}}"])
    if head.returncode or target.returncode or head.stdout.strip() != target.stdout.strip():
        raise RuntimeError("expected commit is not HEAD")
    clean = run(["git", "status", "--porcelain"])
    if clean.returncode or clean.stdout.strip():
        raise RuntimeError("worktree not clean")
    changed = run(["git", "diff-tree", "--root", "--no-commit-id", "--name-only", "-r", "HEAD"])
    if changed.returncode or not changed.stdout.strip():
        raise RuntimeError("commit has no changed files")
    tests = run([python_executable, "-m", "pytest", *test_paths, "-q"])
    return {
        "verified": tests.returncode == 0,
        "commit": head.stdout.strip(),
        "changed_files": changed.stdout.splitlines(),
        "tests_passed": tests.returncode == 0,
        "test_output": (tests.stdout + "\n" + tests.stderr)[-3000:],
    }
