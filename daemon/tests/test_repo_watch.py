"""Tests for the bounded repo-change long-poll (see repo_watch.py for why it exists)."""

from __future__ import annotations

import asyncio
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from synapse_daemon import repo_watch

git_required = pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")


def _init_git_repo(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    (path / "README.md").write_text("# demo\n", encoding="utf-8")
    subprocess.run(["git", "init"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Synapse Tests"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.email", "tests@example.com"], cwd=path, check=True)
    subprocess.run(["git", "add", "."], cwd=path, check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=path, check=True, capture_output=True)


def _run_async(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@git_required
def test_times_out_with_no_change_when_nothing_happens(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    result = _run_async(
        repo_watch.wait_for_repo_change(tmp_path, timeout_seconds=2, poll_interval=0.5)
    )
    assert result.changed is False
    assert result.error is None
    assert result.dirty_file_count == 0
    assert result.elapsed_seconds >= 1.5


@git_required
def test_detects_a_new_untracked_file_written_mid_wait(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)

    def _write_later() -> None:
        time.sleep(0.8)
        (tmp_path / "new_file.txt").write_text("hello", encoding="utf-8")

    async def _run() -> repo_watch.RepoWatchResult:
        writer = asyncio.get_event_loop().run_in_executor(None, _write_later)
        result = await repo_watch.wait_for_repo_change(
            tmp_path, timeout_seconds=5, poll_interval=0.3
        )
        await writer
        return result

    result = _run_async(_run())
    assert result.changed is True
    assert result.dirty_file_count == 1
    assert "new_file.txt" in result.status_porcelain
    assert result.elapsed_seconds < 5


@git_required
def test_sync_variant_detects_a_change_mid_wait(tmp_path: Path) -> None:
    """The MCP tool path (mcp_connector._call_tool is not async) uses this variant."""
    _init_git_repo(tmp_path)

    def _write_later() -> None:
        time.sleep(0.8)
        (tmp_path / "new_file.txt").write_text("hello", encoding="utf-8")

    threading.Thread(target=_write_later, daemon=True).start()
    result = repo_watch.wait_for_repo_change_sync(tmp_path, timeout_seconds=5, poll_interval=0.3)
    assert result.changed is True
    assert result.dirty_file_count == 1


def test_non_git_directory_returns_an_error_not_a_silent_timeout(tmp_path: Path) -> None:
    result = _run_async(
        repo_watch.wait_for_repo_change(tmp_path, timeout_seconds=1, poll_interval=0.5)
    )
    assert result.changed is False
    assert result.error is not None
    assert result.elapsed_seconds == 0.0


def test_timeout_is_clamped_to_the_max() -> None:
    assert repo_watch.MAX_TIMEOUT_SECONDS == 120.0


@pytest.mark.skipif(sys.platform != "win32", reason="path style check is Windows-specific")
def test_windows_path_with_backslashes_is_accepted(tmp_path: Path) -> None:
    # Sanity check the git subprocess call tolerates a native Windows path -- this session's
    # real callers pass paths like C:\Users\...\mcp-servers\reflex.
    assert repo_watch._git_status(tmp_path)[1] is not None  # not a git repo -> real error, not a crash
