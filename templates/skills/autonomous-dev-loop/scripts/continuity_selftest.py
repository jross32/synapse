#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
CLI = HERE / "autonomous_dev_loop.py"


def run(root: Path, *args: str, expect: int = 0) -> dict:
    proc = subprocess.run(
        [sys.executable, "-B", str(CLI), "--root", str(root), *args],
        text=True,
        capture_output=True,
        encoding="utf-8",
        timeout=20,
    )
    if proc.returncode != expect:
        raise AssertionError(
            f"command {args!r} returned {proc.returncode}, expected {expect}\n"
            f"stdout={proc.stdout}\nstderr={proc.stderr}"
        )
    if not proc.stdout.strip():
        return {}
    return json.loads(proc.stdout)


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="adl-continuity-") as td:
        root = Path(td)

        created = run(
            root,
            "init",
            "--project-id",
            "demo",
            "--goal",
            "prove resumable continuity",
            "--soft-minutes",
            "15",
            "--soft-actions",
            "4",
        )
        assert created["created"] is True
        assert created["state"]["schema_version"] == 2

        home = run(
            root,
            "set-chat-home",
            "--worker-chat-id",
            "chat-home-1",
            "--work-item-id",
            "work-home-1",
            "--conversation-url",
            "https://chatgpt.com/c/home-1",
        )
        assert home["chat_home"]["work_item_id"] == "work-home-1"

        began = run(
            root,
            "begin",
            "--hypothesis",
            "checkpointing preserves an in-progress iteration",
            "--scope",
            "controller continuity only",
            "--acceptance",
            "resume-plan restores the exact next action",
            "--proof",
            "CLI lifecycle self-test",
        )
        assert began["iteration"]["number"] == 1

        progress = run(root, "progress", "--actions", "3")
        assert progress["budget"]["checkpoint_recommended"] is True
        assert progress["budget"]["soft_boundary_reached"] is False

        checkpointed = run(
            root,
            "checkpoint",
            "--reason",
            "soft_budget",
            "--phase",
            "implement",
            "--summary",
            "source mutation is durable",
            "--next-step",
            "run focused verification",
            "--pending",
            "verification remains",
            "--dirty-state",
            "demo.py modified",
            "--pause",
        )
        token = checkpointed["checkpoint"]["resume_token"]
        assert token.endswith(":1")
        assert checkpointed["state_status"] == "paused"

        plan = run(root, "resume-plan")["resume_plan"]
        assert plan["resume_token"] == token
        assert plan["resume_current_iteration"] is True
        assert plan["next_step"] == "run focused verification"
        assert plan["chat_home"]["worker_chat_id"] == "chat-home-1"

        refused = subprocess.run(
            [
                sys.executable,
                "-B",
                str(CLI),
                "--root",
                str(root),
                "retire-chat",
                "--work-item-id",
                "work-home-1",
                "--reason",
                "must refuse home retirement",
            ],
            text=True,
            capture_output=True,
            encoding="utf-8",
            timeout=20,
        )
        assert refused.returncode != 0
        assert "Refusing to retire current project home chat" in refused.stderr

        queued = run(
            root,
            "retire-chat",
            "--work-item-id",
            "old-work-2",
            "--conversation-url",
            "https://chatgpt.com/c/old-2",
            "--reason",
            "redundant temporary chat",
        )
        assert queued["archive_queue_size"] == 1

        resumed = run(root, "resume")
        assert resumed["resumed"] is True
        assert resumed["resume_current_iteration"] is True

        finished = run(
            root,
            "finish",
            "--outcome",
            "improved",
            "--summary",
            "continuity lifecycle verified",
            "--evidence",
            "self-test assertions passed",
            "--touched",
            "controller state only",
            "--next-step",
            "continue next bounded iteration",
        )
        assert finished["recorded"] is True
        assert finished["checkpoint"]["reason"] == "iteration_complete"
        assert finished["checkpoint"]["sequence"] == 2

        final_plan = run(root, "resume-plan")["resume_plan"]
        assert final_plan["resume_current_iteration"] is False
        assert final_plan["next_step"] == "continue next bounded iteration"
        assert final_plan["archive_queue_size"] == 1

    print(json.dumps({"ok": True, "checks": 16, "skill": "autonomous-dev-loop", "schema": 2}))


if __name__ == "__main__":
    main()
