"""Regression coverage for bounded Synapse MCP shell-command cleanup."""

from __future__ import annotations

import sys
import time
from pathlib import Path

import psutil

from synapse_daemon.mcp_connector import _run_captured_command


def test_run_captured_command_returns_normal_output(tmp_path) -> None:
    argv = [sys.executable, "-c", "print('runner-ok')"]

    result = _run_captured_command(argv, cwd=str(tmp_path), timeout=5.0)

    assert result["ok"] is True
    assert result["exit_code"] == 0
    assert "runner-ok" in result["stdout"]


def test_timeout_cannot_be_stranded_by_reparented_inherited_pipe(tmp_path) -> None:
    pid_file = Path(tmp_path) / "child.pid"
    parent_code = (
        "import pathlib,subprocess,sys; "
        "p=subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)']); "
        f"pathlib.Path({str(pid_file)!r}).write_text(str(p.pid), encoding='utf-8'); "
        "print('spawned-child')"
    )
    argv = [sys.executable, "-c", parent_code]

    child_pid: int | None = None
    started = time.monotonic()
    try:
        result = _run_captured_command(argv, cwd=str(tmp_path), timeout=1.0)
        elapsed = time.monotonic() - started

        assert result["ok"] is False
        assert result["timed_out"] is True
        assert elapsed < 5.0
        assert pid_file.exists()
        child_pid = int(pid_file.read_text(encoding="utf-8"))
    finally:
        if child_pid is None and pid_file.exists():
            child_pid = int(pid_file.read_text(encoding="utf-8"))
        if child_pid is not None:
            try:
                child = psutil.Process(child_pid)
                child.kill()
                child.wait(timeout=3)
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.TimeoutExpired):
                pass
