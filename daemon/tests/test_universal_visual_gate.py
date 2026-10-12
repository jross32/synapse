"""Universal UI quality gate regression checks."""
from pathlib import Path
import pytest
from synapse_daemon import quality_os, agent_squads
from synapse_daemon.storage import Storage


def test_universal_visual_gate_blocks_without_proof_and_clears_with_proof(tmp_path):
    from synapse_daemon.universal_visual_gate import (
        ensure_work_item_gate, assert_work_item_can_complete, requires_visual_qa
    )
    assert requires_visual_qa("Fix dashboard CSS colors")
    assert not requires_visual_qa("Repair backend-only SQLite migration")
    store = Storage(tmp_path / "db")
    store.open()
    store.migrate()
    class Item:
        id = "ui-test-work"
        title = "Fix dashboard CSS colors"
        instructions_md = "Verify actual interface"
    item = Item()
    with store.transaction() as conn:
        ensure_work_item_gate(conn, item)
        ensure_work_item_gate(conn, item)
        gates = quality_os.blocking_gates_for_subject(conn, "agent_work_item", item.id)
        assert len(gates) == 1
        with pytest.raises(Exception):
            assert_work_item_can_complete(conn, item)
    artifact = tmp_path / "proof.png"
    artifact.write_bytes(b"browser proof")
    with store.transaction() as conn:
        quality_os.add_evidence(conn, quality_os.QualityEvidence(
            id="ui-test-proof",
            subject_type="agent_work_item",
            subject_id=item.id,
            evidence_kind="browser-proof",
            verdict=quality_os.QualityEvidenceVerdict.PASS,
            artifact_path=str(artifact),
            metadata={"visual_qa_passed": True},
        ))
        assert_work_item_can_complete(conn, item)
        assert not quality_os.blocking_gates_for_subject(conn, "agent_work_item", item.id)
    store.close()


def test_stale_success_does_not_override_new_failure(tmp_path):
    from synapse_daemon.universal_visual_gate import ensure_work_item_gate, assert_work_item_can_complete
    store = Storage(tmp_path / 'db')
    store.open()
    store.migrate()
    class Item:
        id = 'ui-regression'
        title = 'Fix mobile UI'
        instructions_md = 'Check browser rendering'
    item = Item()
    artifact = tmp_path / 'proof.png'
    artifact.write_bytes(b'proof')
    with store.transaction() as conn:
        ensure_work_item_gate(conn, item)
        for evidence_id, verdict in [('old-pass', quality_os.QualityEvidenceVerdict.PASS), ('new-fail', quality_os.QualityEvidenceVerdict.FAIL)]:
            quality_os.add_evidence(conn, quality_os.QualityEvidence(
                id=evidence_id, subject_type='agent_work_item', subject_id=item.id,
                evidence_kind='browser-proof', verdict=verdict,
                artifact_path=str(artifact), metadata={'visual_qa_passed': verdict == quality_os.QualityEvidenceVerdict.PASS},
            ))
        with pytest.raises(Exception):
            assert_work_item_can_complete(conn, item)
    store.close()
