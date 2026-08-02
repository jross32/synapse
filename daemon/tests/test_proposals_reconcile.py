"""Reconcile flags open proposals a recent commit *claims to have addressed* -- without
resolving them. Fixes the "a bug was fixed but its idea stayed stale in the inbox" case,
while never auto-removing an idea (the human confirms).

v0.1.108 tightened the match. Flagging on a bare mention looked safe in principle but was
wrong in practice: commits legitimately name a proposal to record that it was *skipped*,
or to warn the next agent that it is already handled. Those were being reported as done.
"""

from __future__ import annotations

from pathlib import Path

from synapse_daemon import proposals as pm
from synapse_daemon.storage import Storage


def _storage(tmp_path: Path) -> Storage:
    storage = Storage(tmp_path / "data")
    storage.open()
    storage.migrate()
    return storage


class _Stub:
    def __init__(self, pid: str) -> None:
        self.id = pid


def test_find_addressed_proposal_ids_is_pure() -> None:
    proposals = [_Stub("aaa111"), _Stub("bbb222"), _Stub("ccc333")]
    commits = [
        "deadbee v0.1.9: fix the thing (resolves aaa111)",
        # A bare mention in the body is not a claim to have done anything. This case
        # used to be flagged; see the skip test below for why that was misleading.
        "cafef00 chore: mentions ccc333 in the body",
    ]
    assert pm.find_addressed_proposal_ids(proposals, commits) == {"aaa111"}


def test_a_commit_explaining_a_skip_is_not_treated_as_a_fix() -> None:
    """The actual regression, taken from a commit that caused it.

    Recording honestly why an idea was deferred is good practice, and it must not mark
    that idea as done. Two proposals were wrongly flagged this way in one session, both
    explicitly skipped -- which makes the inbox claim work happened that nobody did.
    """
    skipped = _Stub("8f62b94f0ff2")
    commits = [
        """7e92fc9 v0.1.103: let read-only reviewers file the review they just wrote

Notes:
- Skipped proposal 8f62b94f0ff2 (duplicate restart cycle) this pass: verifying it
  requires performing real restarts, and Codex is live in coordination session #063.
"""
    ]
    assert pm.find_addressed_proposal_ids([skipped], commits) == set()


def test_the_hint_is_the_claiming_line_not_the_commit_subject() -> None:
    """A multi-topic commit must not attach an unrelated summary to a proposal.

    The hint used to be the commit's first line, so a proposal about restart cycles could
    display "let read-only reviewers file the review they just wrote" as its evidence.
    """
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


def test_a_claim_in_the_subject_counts() -> None:
    """The rule is uniform: a resolution word is required on the line, subject included."""
    target = _Stub("feedfacefeed")
    commits = ["1111111 fix: handle the empty case (feedfacefeed)\n\nbody without the id"]
    assert pm.find_addressed_proposal_ids([target], commits) == {"feedfacefeed"}


def test_a_bare_id_in_the_subject_does_not_count() -> None:
    """No exception for the subject line -- "chore: mentions <id>" is a subject too."""
    target = _Stub("feedfacefeed")
    commits = ["1111111 chore: touched things near feedfacefeed\n\nbody"]
    assert pm.find_addressed_proposal_ids([target], commits) == set()


def test_a_warning_about_prior_work_is_a_known_residual_false_positive() -> None:
    """Records a limit of the keyword rule rather than implying there is none.

    "<id> is already fixed -- do not re-fix" contains a resolution word, so it still
    flags. That is a weaker failure than before (the idea genuinely *is* addressed, just
    not by this commit), and closing it would need intent parsing rather than keywords.
    """
    warned = _Stub("dee782caee18")
    commits = [
        """abc1234 v0.1.99: something unrelated

- dee782caee18 is already fixed in code but still open -- do not re-fix it here.
"""
    ]
    assert pm.find_addressed_proposal_ids([warned], commits) == {"dee782caee18"}


def test_reconcile_flags_open_addressed_proposals_without_resolving(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    with storage.transaction() as conn:
        p1 = pm.create_proposal(conn, pm.ProposalCreate(title="Fix the freeze", project_id=None))
        p2 = pm.create_proposal(conn, pm.ProposalCreate(title="Something else", project_id=None))

    commit_texts = [f"abc1234 v0.1.50: fixed it (resolves {p1.id})\n\nbody text"]
    with storage.transaction() as conn:
        flagged = pm.reconcile_addressed_proposals(conn, commit_texts)

    flagged_ids = {p.id for p in flagged}
    assert p1.id in flagged_ids
    assert p2.id not in flagged_ids

    # p1 is flagged but still OPEN (never auto-resolved); metadata carries the commit hint.
    p1_after = pm.get_proposal(storage.conn, p1.id)
    assert p1_after.status == pm.ProposalStatus.OPEN
    assert p1_after.metadata.get("addressed_by", "").startswith("abc1234")

    # p2 is untouched.
    p2_after = pm.get_proposal(storage.conn, p2.id)
    assert "addressed_by" not in p2_after.metadata
