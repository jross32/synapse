"""Reconcile flags open proposals whose id appears in a recent commit as *possibly
addressed* -- without resolving them. Fixes the "a bug was fixed but its idea stayed
stale in the inbox" case, while never auto-removing an idea (the human confirms).
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
        "cafef00 chore: mentions ccc333 in the body",
    ]
    assert pm.find_addressed_proposal_ids(proposals, commits) == {"aaa111", "ccc333"}


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
