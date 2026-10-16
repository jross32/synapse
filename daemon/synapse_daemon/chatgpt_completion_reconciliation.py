"""Evidence-backed terminal reconciliation for managed ChatGPT coding work items.

UI replies are only handoffs. This optional explicit path verifies Git HEAD, clean
tree and an actual pytest run before a work item may be marked completed.
"""
from __future__ import annotations

import sys
from pathlib import Path

from .chatgpt_commit_verification import verify_coding_receipt
from .chatgpt_worker_checkpoints import WorkerCheckpointStore


def reconcile_verified_coding_work(storage, work_item_id: str, worker_id: str,
                                    worktree: str, commit: str, test_paths: list[str],
                                    conversation_url: str) -> dict:
    if not worker_id or not work_item_id:
        raise ValueError("worker id and work item required")
    result = verify_coding_receipt(Path(worktree), commit, test_paths, sys.executable)
    if not result["verified"]:
        raise RuntimeError("focused tests failed; work item cannot complete")
    checkpoint = WorkerCheckpointStore(storage.data_dir / "chatgpt-worker-checkpoints.sqlite")
    current = checkpoint.get(work_item_id)
    if not current or current["worker"] != worker_id:
        raise RuntimeError("work item has no matching managed worker checkpoint")
    if current["state"] not in {"needs_recovery", "observing", "sent"}:
        raise RuntimeError("worker has no verified observed response")
    if not current["evidence"].get("reply_observed"):
        raise RuntimeError("worker response was not confirmed")
    checkpoint.record(work_item_id, worker_id, "verified",
                      conversation_url=conversation_url,
                      evidence={
                          "commit": result["commit"],
                          "tests_passed": True,
                          "completion_confirmed": True,
                          "changed_files": result["changed_files"],
                          "test_output": result["test_output"],
                      })
    return result
