"""Opt-in verified worker checkpoint hook. Never pushes to a remote."""
from __future__ import annotations
import json
import os
import subprocess
import sys
import shlex
from pathlib import Path


def checkpoint_after_verified_run(workspace: Path, *, completed: bool, environ=None) -> dict:
    env = os.environ if environ is None else environ
    if not completed:
        return {"skipped": "worker incomplete"}
    if env.get("SYNAPSE_GIT_CHECKPOINT") != "1":
        return {"skipped": "not enabled"}
    test_command = env.get("SYNAPSE_GIT_TEST_COMMAND", "").strip()
    if not test_command:
        return {"error": "A real test command is required before checkpointing"}
    try:
        tests = subprocess.run(shlex.split(test_command, posix=os.name != "nt"),
                               cwd=str(workspace), capture_output=True, text=True,
                               timeout=180, check=False)
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        return {"error": "Test execution failed: " + type(exc).__name__}
    if tests.returncode:
        return {"error": "Verification tests failed; checkpoint refused"}
    paths = [p.strip() for p in env.get("SYNAPSE_GIT_OWNED_PATHS", "").split(",") if p.strip()]
    message = env.get("SYNAPSE_GIT_CHECKPOINT_MESSAGE", "")
    if not paths or not message:
        return {"error": "Owned paths and checkpoint message required"}
    script = Path(__file__).resolve().parents[2] / "scripts" / "synapse_git_checkpoint.py"
    cmd = [sys.executable, str(script), "--repo", str(workspace)]
    for path in paths:
        cmd.extend(["--path", path])
    cmd.extend(["--commit", "--message", message])
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=45, check=False)
        if result.returncode:
            return {"error": (result.stderr or "Checkpoint rejected")[:300]}
        receipt = json.loads(result.stdout)
        if receipt.get("committed") and env.get("SYNAPSE_GIT_AUTO_PUSH") == "1":
            from .worker_git_publish import publish_verified_branch
            try:
                receipt["publish"] = publish_verified_branch(
                    Path(workspace), owner=env.get("SYNAPSE_GITHUB_OWNER", ""),
                    branch=env.get("SYNAPSE_GIT_PUSH_BRANCH", ""))
            except (OSError, RuntimeError, ValueError, subprocess.TimeoutExpired) as exc:
                receipt["publish"] = {"pushed": False, "error": str(exc)[:200]}
        return receipt
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        return {"error": type(exc).__name__}
