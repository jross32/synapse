"""Shared handoff gate for Claude, Codex, Gemini, ChatGPT and local workers."""
from pathlib import Path
from unittest.mock import patch
from synapse_daemon.github_publish_gate import PublishEvidence, assess_provider_handoff
from synapse_daemon.agent_squads import AgentWorkItemHandoffRequest

SHA = "a" * 40


def test_code_handoff_requires_tests_and_remote_commit():
    repo = Path(".")
    assert assess_provider_handoff(repo, files_touched=["src/app.ts"], tests_passed=False, expected_sha=SHA).status == "verification_failed"
    assert assess_provider_handoff(repo, files_touched=["src/app.ts"], tests_passed=True, expected_sha=None).status == "verified_not_published"
    with patch("synapse_daemon.github_publish_gate.check_github_publish", return_value=PublishEvidence(True, "verified", SHA, SHA, "feature")):
        assert assess_provider_handoff(repo, files_touched=["src/app.ts"], tests_passed=True, expected_sha=SHA).status == "complete"


def test_documentation_handoff_does_not_require_commit():
    assert assess_provider_handoff(Path("."), files_touched=["README.md"], tests_passed=False, expected_sha=None).status == "complete"


def test_handoff_schema_preserves_code_evidence():
    data = AgentWorkItemHandoffRequest(summary_md="done", files_touched=["src/app.py"], code_tests_passed=True, code_commit_sha=SHA)
    assert data.model_dump()["code_commit_sha"] == SHA

def test_commit_evidence_without_file_list_still_requires_verification():
    assert assess_provider_handoff(Path("."), files_touched=[], tests_passed=False, expected_sha=SHA).status == "verification_failed"
