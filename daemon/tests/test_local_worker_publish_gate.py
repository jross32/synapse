"""Integration of local coding worker handoff with GitHub publication evidence."""
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from synapse_daemon import local_worker
from synapse_daemon.github_publish_gate import PublishEvidence

SHA_A = "a" * 40
SHA_B = "b" * 40


@pytest.mark.parametrize("after,remote_ready,expected_status,expected_exit", [
    ((SHA_A, ""), False, "handoff", 0),  # no code change
    ((SHA_A, " M src.py"), False, "blocked", 2),  # uncommitted source
    ((SHA_B, ""), False, "blocked", 2),  # committed but not pushed
    ((SHA_B, ""), True, "handoff", 0),  # committed and pushed
    ((SHA_A, " M src.py"), True, "blocked", 2),  # dirty even when remote matches
])
def test_worker_handoff_requires_published_code(tmp_path, monkeypatch, after, remote_ready, expected_status, expected_exit):
    monkeypatch.setenv("SYNAPSE_WORKER_TESTS_PASSED", "1")
    prompt = tmp_path / "prompt.txt"
    prompt.write_text("Implement feature")
    monkeypatch.setattr(sys, "argv", ["local_worker", "--prompt-file", str(prompt), "--workspace", str(tmp_path)])
    snapshots = iter([(SHA_A, ""), after])
    delivered = []

    async def fake_run_agent(**kwargs):
        return SimpleNamespace(completed=True, answer="Finished", stop_reason="done", steps=[])

    with patch.object(local_worker, "snapshot_code_workspace", side_effect=lambda _: next(snapshots)), \
         patch.object(local_worker, "run_agent", side_effect=fake_run_agent), \
         patch.object(local_worker, "handoff", side_effect=delivered.append), \
         patch("synapse_daemon.github_publish_gate.check_github_publish", return_value=PublishEvidence(remote_ready, "verified" if remote_ready else "not_pushed", SHA_B, SHA_B if remote_ready else SHA_A, "feature")):
        result = local_worker.main()
    assert result == expected_exit
    assert delivered[0]["status"] == expected_status
