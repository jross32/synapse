"""Regression tests for independent commit-evidence verification and strict completion receipts."""
import pytest
from synapse_daemon.chatgpt_commit_verification import COMMIT_RE, verify_coding_receipt

def test_evidence_rejects_short_or_unsafe_identifiers():
    assert COMMIT_RE.fullmatch("016d455")
    assert not COMMIT_RE.fullmatch("not-a-commit")
    assert not COMMIT_RE.fullmatch("abc1234; rm -rf /")

def test_invalid_worktree_never_proves_completion(tmp_path):
    with pytest.raises((RuntimeError, ValueError)):
        verify_coding_receipt(tmp_path, "016d455", ["daemon/tests/test_chatgpt_mcp_execution.py"], "python")
