"""Proposal lifecycle reconciliation uses strong, inspectable evidence only."""

from __future__ import annotations

import json
from pathlib import Path

from synapse_daemon import proposals as pm
from synapse_daemon.storage import Storage
from synapse_daemon.time_utils import to_iso, utc_now


def _storage(tmp_path: Path) -> Storage:
    storage = Storage(tmp_path / "data")
    storage.open()
    storage.migrate()
    return storage


class _Stub:
    def __init__(self, pid: str) -> None:
        self.id = pid


def test_find_addressed_proposal_ids_requires_resolution_language() -> None:
    proposals = [_Stub("aaa111"), _Stub("bbb222"), _Stub("ccc333")]
    commits = [
        "deadbee v0.1.9: fix the thing (resolves aaa111)",
        "cafef00 chore: mentions ccc333 in the body",
    ]
    assert pm.find_addressed_proposal_ids(proposals, commits) == {"aaa111"}


def test_skip_warning_and_already_fixed_commentary_do_not_count_as_completion() -> None:
    target = _Stub("8f62b94f0ff2")
    commits = [
        """7e92fc9 maintenance notes

- Skipped proposal 8f62b94f0ff2 this pass: verifying it requires a restart.
- 8f62b94f0ff2 is already fixed -- do not re-fix it here.
- Regression fixture says 8f62b94f0ff2 should not be flagged as resolved.
"""
    ]
    assert pm.find_addressed_proposal_ids([target], commits) == set()


def test_direct_completion_claim_counts_and_hint_is_claiming_line() -> None:
    target = _Stub("abc123def456")
    commits = [
        """9999999 v0.2.0: rewrite the scheduler

Fixed:
- Closes review-inbox proposal abc123def456 (the modal focus bug).
"""
    ]
    hints = pm.find_addressed_proposal_hints([target], commits)
    assert "abc123def456" in hints
    assert "modal focus bug" in hints["abc123def456"]
    assert "rewrite the scheduler" not in hints["abc123def456"]


def test_commit_completion_marks_done_and_persists_evidence(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    with storage.transaction() as conn:
        p1 = pm.create_proposal(conn, pm.ProposalCreate(title="Fix the freeze"))
        p2 = pm.create_proposal(conn, pm.ProposalCreate(title="Something else"))

    commit_texts = [f"abc1234 v0.1.50: fixed it (resolves {p1.id})\n\nbody text"]
    with storage.transaction() as conn:
        changed = pm.reconcile_proposals(conn, commit_texts)

    assert {p.id for p in changed} == {p1.id}
    p1_after = pm.get_proposal(storage.conn, p1.id)
    assert p1_after.status == pm.ProposalStatus.DONE
    assert p1_after.done_at is not None
    assert p1_after.lifecycle_source == "commit"
    assert p1_after.lifecycle_evidence[-1].source == "commit"
    assert p1.id in p1_after.lifecycle_evidence[-1].detail

    p2_after = pm.get_proposal(storage.conn, p2.id)
    assert p2_after.status == pm.ProposalStatus.PROPOSED


def test_explicit_live_session_moves_proposed_to_in_progress(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    from synapse_daemon.projects import Project, create as create_project

    now = to_iso(utc_now())
    with storage.transaction() as conn:
        create_project(conn, Project(id="proj1", name="Proj", path="C:/tmp", launch_cmd="echo hi"))
        proposal = pm.create_proposal(
            conn, pm.ProposalCreate(title="Live-linked work", project_id="proj1")
        )
        conn.execute(
            "INSERT INTO agent_sessions "
            "(id, project_id, runtime_id, agent_label, coder_thread_id, task, status, last_intent, "
            " registered_at, last_heartbeat_at, ended_at, metadata_json) "
            "VALUES ('session-live','proj1','codex','worker',NULL,?,'active','',?,?,NULL,?)",
            (
                f"Implement proposal {proposal.id}",
                now,
                now,
                json.dumps({"proposal_id": proposal.id}),
            ),
        )

    with storage.transaction() as conn:
        changed = pm.reconcile_proposals(conn, [])
    assert [p.id for p in changed] == [proposal.id]
    current = pm.get_proposal(storage.conn, proposal.id)
    assert current.status == pm.ProposalStatus.IN_PROGRESS
    assert current.lifecycle_source == "session"
    assert current.lifecycle_evidence[-1].ref_id == "session-live"


def test_auto_in_progress_falls_back_when_live_signal_disappears(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    with storage.transaction() as conn:
        proposal = pm.create_proposal(conn, pm.ProposalCreate(title="Temporary live work"))
        pm.transition_proposal(
            conn,
            proposal.id,
            pm.ProposalStatus.IN_PROGRESS,
            source="session",
            detail="live session",
            ref_id="gone-session",
            evidence_status="active",
        )

    with storage.transaction() as conn:
        changed = pm.reconcile_proposals(conn, [])
    assert [p.id for p in changed] == [proposal.id]
    current = pm.get_proposal(storage.conn, proposal.id)
    assert current.status == pm.ProposalStatus.PROPOSED
    assert current.lifecycle_source == "reconcile"
    assert "no longer active" in current.lifecycle_evidence[-1].detail


def test_manual_in_progress_does_not_auto_fall_back(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    with storage.transaction() as conn:
        proposal = pm.create_proposal(conn, pm.ProposalCreate(title="Manual work"))
        pm.transition_proposal(
            conn,
            proposal.id,
            pm.ProposalStatus.IN_PROGRESS,
            source="manual",
            detail="human says work is active",
        )
    with storage.transaction() as conn:
        assert pm.reconcile_proposals(conn, []) == []
    assert pm.get_proposal(storage.conn, proposal.id).status == pm.ProposalStatus.IN_PROGRESS


def test_declined_proposals_are_not_auto_advanced(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    with storage.transaction() as conn:
        proposal = pm.create_proposal(conn, pm.ProposalCreate(title="Declined"))
        pm.set_proposal_decision(conn, proposal.id, pm.ProposalDecision.DECLINED, "no")
    with storage.transaction() as conn:
        changed = pm.reconcile_proposals(
            conn, [f"abc1234 fixes proposal {proposal.id}"]
        )
    assert changed == []
    assert pm.get_proposal(storage.conn, proposal.id).status == pm.ProposalStatus.PROPOSED
