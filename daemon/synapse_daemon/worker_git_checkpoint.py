"""Opt-in verified worker checkpoint hook. Never pushes to a remote."""
from __future__ import annotations
import json
import os
import subprocess
import sys
from pathlib import Path


def checkpoint_after_verified_run(workspace: Path, *, completed: bool, environ=None) -> dict:
    env = os.environ if environ is None else environ
    if not completed:
        return {"skipped": "worker incomplete"}
    if env.get("SYNAPSE_GIT_CHECKPOINT") != "1":
        return {"skipped": "not enabled"}
    if env.get("SYNAPSE_TESTS_VERIFIED") != "1":
        return {"error": "Tests not verified; checkpoint refused"}
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
        return json.loads(result.stdout)
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        return {"error": type(exc).__name__}
