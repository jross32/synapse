"""Bounded server-side long-poll for real file changes in a git repo.

Built for the pattern this session actually needed: an AI waiting on delegated work (another AI
session working through a connector, a background build) doesn't need to burn a full
context-gathering turn every time it checks in -- it can hold one bounded wait call open
instead, and only spend a real turn when something actually changed on disk. Reuses `git status
--porcelain` rather than a generic file-mtime walk because every path this needed to watch this
session already was a git repo, and porcelain output already covers new/modified/deleted,
tracked and untracked, in one cheap call.

Capped at MAX_TIMEOUT_SECONDS so no single call can tie up a request indefinitely -- a caller
wanting to wait longer just calls again. Non-git paths are a known, honest gap (returned as an
error rather than silently doing nothing): a generic mtime-walk fallback is real future work,
not built here because nothing this session needed to watch was outside a git repo.
"""

from __future__ import annotations

import asyncio
import subprocess
import time
from pathlib import Path

from pydantic import BaseModel

MAX_TIMEOUT_SECONDS = 120.0
DEFAULT_TIMEOUT_SECONDS = 60.0
POLL_INTERVAL_SECONDS = 2.0


class RepoWatchResult(BaseModel):
    changed: bool
    elapsed_seconds: float
    dirty_file_count: int
    status_porcelain: str = ""
    error: str | None = None


def _git_status(path: Path) -> tuple[str | None, str | None]:
    """Returns (porcelain output, error message) -- exactly one is None."""
    try:
        result = subprocess.run(
            ["git", "-C", str(path), "status", "--porcelain"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return None, f"{type(exc).__name__}: {exc}"
    if result.returncode != 0:
        detail = (result.stderr or "git status failed").strip()[:500]
        return None, detail
    return result.stdout, None


def _dirty_count(porcelain: str) -> int:
    return len([line for line in porcelain.splitlines() if line.strip()])


async def wait_for_repo_change(
    path: Path,
    *,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    poll_interval: float = POLL_INTERVAL_SECONDS,
) -> RepoWatchResult:
    """Poll ``path`` (must be inside a git working tree) until its `git status` output
    changes or ``timeout_seconds`` elapses, whichever comes first.

    Blocking git calls run via ``asyncio.to_thread`` so this never stalls the event loop --
    other requests are served normally while a caller holds this open.
    """
    timeout_seconds = max(1.0, min(timeout_seconds, MAX_TIMEOUT_SECONDS))
    started = time.monotonic()

    baseline, error = await asyncio.to_thread(_git_status, path)
    if error is not None:
        return RepoWatchResult(changed=False, elapsed_seconds=0.0, dirty_file_count=0, error=error)

    while True:
        elapsed = time.monotonic() - started
        remaining = timeout_seconds - elapsed
        if remaining <= 0:
            return RepoWatchResult(
                changed=False,
                elapsed_seconds=round(elapsed, 1),
                dirty_file_count=_dirty_count(baseline),
                status_porcelain=baseline,
            )
        await asyncio.sleep(min(poll_interval, remaining))
        current, error = await asyncio.to_thread(_git_status, path)
        elapsed = time.monotonic() - started
        if error is not None:
            return RepoWatchResult(
                changed=False, elapsed_seconds=round(elapsed, 1), dirty_file_count=0, error=error
            )
        if current != baseline:
            return RepoWatchResult(
                changed=True,
                elapsed_seconds=round(elapsed, 1),
                dirty_file_count=_dirty_count(current),
                status_porcelain=current,
            )


def wait_for_repo_change_sync(
    path: Path,
    *,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    poll_interval: float = POLL_INTERVAL_SECONDS,
) -> RepoWatchResult:
    """Same contract as ``wait_for_repo_change``, blocking rather than async.

    For callers on the synchronous MCP tool-dispatch path (``mcp_connector._call_tool`` is not
    async), where holding the thread for the wait duration is the existing convention --
    ``synapse_run_command`` and other tools already block their calling thread for their
    duration, not just this one.
    """
    timeout_seconds = max(1.0, min(timeout_seconds, MAX_TIMEOUT_SECONDS))
    started = time.monotonic()

    baseline, error = _git_status(path)
    if error is not None:
        return RepoWatchResult(changed=False, elapsed_seconds=0.0, dirty_file_count=0, error=error)

    while True:
        elapsed = time.monotonic() - started
        remaining = timeout_seconds - elapsed
        if remaining <= 0:
            return RepoWatchResult(
                changed=False,
                elapsed_seconds=round(elapsed, 1),
                dirty_file_count=_dirty_count(baseline),
                status_porcelain=baseline,
            )
        time.sleep(min(poll_interval, remaining))
        current, error = _git_status(path)
        elapsed = time.monotonic() - started
        if error is not None:
            return RepoWatchResult(
                changed=False, elapsed_seconds=round(elapsed, 1), dirty_file_count=0, error=error
            )
        if current != baseline:
            return RepoWatchResult(
                changed=True,
                elapsed_seconds=round(elapsed, 1),
                dirty_file_count=_dirty_count(current),
                status_porcelain=current,
            )
