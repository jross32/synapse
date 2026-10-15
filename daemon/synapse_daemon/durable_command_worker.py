"""Detached command execution with durable receipts and restart-safe polling.

The daemon is not the parent of the command's lifecycle: a separate Python
supervisor waits for it and persists the result.  Running receipts are never
mistaken for completed jobs after a daemon restart.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from .command_job_store import read_job, save_job


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def launch(data_dir: str | Path, job_id: str, shell_argv: list[str],
           cwd: str, timeout: float | None) -> dict:
    """Start a detached supervisor. Its receipt is durable before return."""
    root = Path(data_dir) / "command-jobs"
    root.mkdir(parents=True, exist_ok=True)
    request = root / (job_id + ".request.json")
    # Request files contain command arguments; never log them or expose via MCP.
    fd = os.open(request, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        json.dump({"argv": shell_argv, "cwd": cwd, "timeout": timeout}, stream)
        stream.flush()
        os.fsync(stream.fileno())
    save_job(data_dir, job_id, {"status": "starting", "cwd": cwd, "started_at": _now()})
    flags = 0
    kwargs = {}
    if os.name == "nt":
        flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True
    try:
        supervisor = subprocess.Popen(
            [sys.executable, "-m", "synapse_daemon.durable_command_worker",
             str(data_dir), job_id],
            cwd=cwd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, close_fds=True, creationflags=flags, **kwargs,
        )
    except BaseException:
        request.unlink(missing_ok=True)
        save_job(data_dir, job_id, {
            "status": "failed_to_start", "cwd": cwd, "finished_at": _now(),
            "result": {"ok": False, "error": "Supervisor launch failed"},
        })
        raise
    return {"job_id": job_id, "status": "starting", "supervisor_pid": supervisor.pid}


def run(data_dir: str | Path, job_id: str) -> None:
    root = Path(data_dir) / "command-jobs"
    request = root / (job_id + ".request.json")
    try:
        args = json.loads(request.read_text(encoding="utf-8"))
        request.unlink(missing_ok=True)
        cwd = args["cwd"]
        started = _now()
        save_job(data_dir, job_id, {
            "status": "running", "cwd": cwd, "started_at": started,
            "supervisor_pid": os.getpid(),
        })
        # Output is captured by the detached supervisor, not the daemon.
        try:
            completed = subprocess.run(
                args["argv"], cwd=cwd, capture_output=True, text=True,
                errors="replace", timeout=args["timeout"],
            )
            result = {
                "ok": completed.returncode == 0,
                "exit_code": completed.returncode,
                "stdout": completed.stdout[-100000:],
                "stderr": completed.stderr[-100000:],
            }
        except subprocess.TimeoutExpired:
            result = {"ok": False, "timed_out": True, "error": "Command timed out"}
        save_job(data_dir, job_id, {
            "status": "done", "cwd": cwd, "started_at": started,
            "finished_at": _now(), "result": result,
        })
    except BaseException as exc:
        save_job(data_dir, job_id, {
            "status": "done", "finished_at": _now(),
            "result": {"ok": False, "error": str(exc)},
        })


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("usage: python -m synapse_daemon.durable_command_worker DATA_DIR JOB_ID")
    run(sys.argv[1], sys.argv[2])
