"""PTY-compatible entrypoint for Synapse's existing Ollama tool-using agent.

Invoked by Agent Squads as `python -m synapse_daemon.local_worker`.
Uses the inherited Synapse work-item credential for a durable handoff.
No secret is printed or sent to Ollama.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
import urllib.error
import urllib.request

from .local_agent import PermissionMode, run_agent
from .github_publish_gate import assess_code_work_completion, snapshot_code_workspace

DEFAULT_MODEL = "qwen2.5:1.5b"


def handoff(payload: dict) -> None:
    base = os.environ["SYNAPSE_API"].rstrip("/")
    item = os.environ["SYNAPSE_WORK_ITEM_ID"]
    token = os.environ["SYNAPSE_TOKEN"]
    req = urllib.request.Request(
        f"{base}/agent-work-items/{item}/handoff",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "X-Synapse-Token": token},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=20) as response:
        if response.status not in (200, 201):
            raise RuntimeError(f"Handoff failed: HTTP {response.status}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Synapse local Ollama squad worker")
    parser.add_argument("--prompt-file", type=Path, required=True)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--authority", choices=("observe", "workspace", "full"), default="workspace")
    parser.add_argument("--model", default=os.environ.get("SYNAPSE_LOCAL_MODEL", DEFAULT_MODEL))
    parser.add_argument("--timeout", type=int, default=1800)
    args = parser.parse_args()
    prompt = args.prompt_file.read_text(encoding="utf-8")
    workspace = Path(os.environ.get("SYNAPSE_PROJECT_WORKSPACE", str(args.workspace))).resolve()
    mode = {"observe": PermissionMode.PLAN, "workspace": PermissionMode.ACCEPT_EDITS,
            "full": PermissionMode.AUTO}[args.authority]
    try:
        before = snapshot_code_workspace(workspace)
        run = asyncio.run(run_agent(
            model=args.model, task=prompt, workspace=workspace,
            mode=mode, allow_web=False, max_steps=16,
            timeout=min(max(args.timeout, 30), 3600),
        ))
        summary = run.answer or run.stop_reason or "Local worker returned no summary."
        # Code-work handoff is not complete until the exact GitHub SHA is verified.
        after = snapshot_code_workspace(workspace)
        changed = before is not None and after is not None and before != after
        evidence = assess_code_work_completion(workspace, code_changed=changed, tests_passed=(os.environ.get("SYNAPSE_WORKER_TESTS_PASSED") == "1"), expected_sha=(after[0] if changed and after and not after[1] else None)) if run.completed else None
        if evidence is not None and evidence.status != "complete":
            summary += "\nCode-work verification or GitHub publication is missing; completion remains blocked."
        payload = {
            "status": "handoff" if run.completed and (evidence is None or evidence.status == "complete") else "blocked",
            "summary_md": summary[:15000],
            "blockers_md": None if run.completed and (evidence is None or evidence.status == "complete") else ("GitHub publication evidence required" if run.completed else run.stop_reason[:4000]),
            "source": "auto",
        }
        handoff(payload)
        print(json.dumps({"completed": run.completed, "status": payload["status"],
                          "steps": len(run.steps), "reason": run.stop_reason}))
        return 0 if payload["status"] == "handoff" else 2
    except Exception as exc:
        reason = f"{type(exc).__name__}: {exc}"
        print(json.dumps({"completed": False, "error": reason}))
        try:
            handoff({"status": "blocked", "summary_md": "Local Ollama worker failed.",
                     "blockers_md": reason[:4000], "source": "auto"})
        except Exception as handoff_error:
            print(json.dumps({"handoff_error": str(handoff_error)}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
