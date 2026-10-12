"""Shared quality gate for Synapse-managed UI work.

An AI's completed status requires verified browser evidence for UI work.
"""
from __future__ import annotations

import re
from pathlib import Path
from . import quality_os

_UI_WORDS = re.compile(
    r"(?i)(?:\bui\b|\bux\b|frontend|front.end|interface|web.?site|"
    r"landing.?page|dashboard|responsive|mobile.?layout|visual|css|"
    r"style(?:sheet|s|d|ing)?\b|theme|color|contrast|component|"
    r"button|form|dialog|modal|accessibility|screenshot|design)"
)
_EXCLUSIONS = re.compile(r"(?i)(?:\b(?:not|no|non)[\s-]*(?:ui|visual|frontend)\b|backend.?only|server.?only|documentation.?only)")
_GATE_KIND = "universal-visual-qa"


def requires_visual_qa(title: str, instructions: str = "") -> bool:
    text = f"{title}\n{instructions}"
    return bool(_UI_WORDS.search(text)) and not bool(_EXCLUSIONS.search(text))


def ensure_work_item_gate(conn, item) -> None:
    if not requires_visual_qa(item.title, item.instructions_md):
        return
    quality_os.create_gate(conn, quality_os.QualityGateCreate(
        subject_type="agent_work_item",
        subject_id=item.id,
        gate_kind=_GATE_KIND,
        title="Universal visual QA: verified browser contrast and interaction proof",
        blocking=True,
        required_evidence=["browser-proof"],
        audit_details={"policy":"global-ui-qa-v1"},
    ))


def assert_work_item_can_complete(conn, item) -> None:
    if requires_visual_qa(item.title, item.instructions_md):
        proofs = quality_os.latest_browser_proof(
            conn, subject_type="agent_work_item", subject_id=item.id, limit=30
        )
        # Only real, locally readable artifact-backed passing evidence can clear the gate.
        valid = bool(proofs) and all(
            proof.verdict == quality_os.QualityEvidenceVerdict.PASS
            and proof.artifact_path
            and Path(proof.artifact_path).is_absolute()
            and Path(proof.artifact_path).is_file()
            and proof.metadata.get("visual_qa_passed") is True
            for proof in proofs[:1]
        )
        # A passing browser report must be the most recent evidence; an older
        # success cannot conceal a regression recorded after it.
        valid = bool(proofs) and proofs[0].verdict == quality_os.QualityEvidenceVerdict.PASS and valid
        if valid:
            for gate in quality_os.blocking_gates_for_subject(conn, "agent_work_item", item.id):
                if gate.gate_kind == _GATE_KIND:
                    quality_os.resolve_gate(conn, gate.id, quality_os.QualityGateResolveRequest(
                        status=quality_os.QualityGateStatus.PASSED,
                        resolved_by="verified-browser-proof",
                    ))
        else:
            ensure_work_item_gate(conn, item)
    quality_os.assert_subject_can_complete(conn, "agent_work_item", item.id)

