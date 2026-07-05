"""Durable quality gates, UI contracts, browser-proof evidence, and impact maps.

This turns UI quality guidance into records the daemon can enforce across
cases, squads, review passes, quick actions, and benchmark attempts.
"""

from __future__ import annotations

import fnmatch
import json
import secrets
import sqlite3
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from . import ai_factory
from .errors import invalid, not_found
from .time_utils import from_iso, to_iso, utc_now


class QualityGateStatus(str, Enum):
    OPEN = "open"
    PASSED = "passed"
    FAILED = "failed"
    WAIVED = "waived"


class QualityGateWaiverState(str, Enum):
    NONE = "none"
    REQUESTED = "requested"
    WAIVED = "waived"


class UiContractSeverity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class QualityEvidenceVerdict(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    INFO = "info"


class ReviewFinding(BaseModel):
    title: str
    severity: UiContractSeverity = UiContractSeverity.MEDIUM
    summary: str = ""
    surface_id: str | None = None
    contract_id: str | None = None


class ReviewVerdict(BaseModel):
    findings: list[ReviewFinding] = Field(default_factory=list)
    severity: UiContractSeverity = UiContractSeverity.LOW
    blocking: bool = False
    surface_ids: list[str] = Field(default_factory=list)
    contract_ids: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    recommended_next_step: str = ""
    summary: str = ""


class QualityGate(BaseModel):
    id: str
    subject_type: str
    subject_id: str
    gate_kind: str
    title: str = ""
    blocking: bool = True
    status: QualityGateStatus = QualityGateStatus.OPEN
    required_evidence: list[str] = Field(default_factory=list)
    linked_surface_ids: list[str] = Field(default_factory=list)
    linked_contract_ids: list[str] = Field(default_factory=list)
    waiver_state: QualityGateWaiverState = QualityGateWaiverState.NONE
    opened_at: datetime = Field(default_factory=utc_now)
    resolved_at: datetime | None = None
    resolved_by: str | None = None
    audit_details: dict[str, Any] = Field(default_factory=dict)


class QualityGateCreate(BaseModel):
    subject_type: str
    subject_id: str
    gate_kind: str
    title: str = ""
    blocking: bool = True
    required_evidence: list[str] = Field(default_factory=list)
    linked_surface_ids: list[str] = Field(default_factory=list)
    linked_contract_ids: list[str] = Field(default_factory=list)
    audit_details: dict[str, Any] = Field(default_factory=dict)


class QualityGateResolveRequest(BaseModel):
    status: QualityGateStatus = QualityGateStatus.PASSED
    resolved_by: str = "human"
    note: str = ""


class QualityGateWaiveRequest(BaseModel):
    resolved_by: str = "human"
    note: str = ""


class UiSurfaceMapEntry(BaseModel):
    id: str
    title: str
    route: str = ""
    description: str = ""
    action_ids: list[str] = Field(default_factory=list)
    file_patterns: list[str] = Field(default_factory=list)
    linked_surface_ids: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    builtin: bool = False
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class UiContract(BaseModel):
    id: str
    title: str
    surface_id: str
    severity: UiContractSeverity = UiContractSeverity.MEDIUM
    route: str = ""
    action_id: str | None = None
    preconditions: list[str] = Field(default_factory=list)
    steps: list[str] = Field(default_factory=list)
    assertions: list[str] = Field(default_factory=list)
    touched_file_patterns: list[str] = Field(default_factory=list)
    linked_surface_ids: list[str] = Field(default_factory=list)
    latest_evidence_ids: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    builtin: bool = False
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class UiContractCreate(BaseModel):
    id: str
    title: str
    surface_id: str
    severity: UiContractSeverity = UiContractSeverity.MEDIUM
    route: str = ""
    action_id: str | None = None
    preconditions: list[str] = Field(default_factory=list)
    steps: list[str] = Field(default_factory=list)
    assertions: list[str] = Field(default_factory=list)
    touched_file_patterns: list[str] = Field(default_factory=list)
    linked_surface_ids: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    builtin: bool = False


class UiContractRunRequest(BaseModel):
    subject_type: str
    subject_id: str
    gate_id: str | None = None
    evidence_kind: str = "browser-proof"
    label: str = ""
    route: str | None = None
    action_id: str | None = None
    selector: str | None = None
    verdict: QualityEvidenceVerdict
    artifact_path: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class UiContractPromoteRequest(BaseModel):
    id: str
    title: str
    surface_id: str
    severity: UiContractSeverity = UiContractSeverity.HIGH
    route: str = ""
    action_id: str | None = None
    preconditions: list[str] = Field(default_factory=list)
    steps: list[str] = Field(default_factory=list)
    assertions: list[str] = Field(default_factory=list)
    touched_file_patterns: list[str] = Field(default_factory=list)
    linked_surface_ids: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class QualityEvidence(BaseModel):
    id: str
    subject_type: str
    subject_id: str
    gate_id: str | None = None
    contract_id: str | None = None
    evidence_kind: str
    label: str = ""
    surface_id: str | None = None
    route: str = ""
    action_id: str | None = None
    selector: str | None = None
    verdict: QualityEvidenceVerdict
    artifact_path: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)


class UiImpactAuditRequest(BaseModel):
    file_paths: list[str] = Field(default_factory=list)
    surface_ids: list[str] = Field(default_factory=list)
    subject_type: str | None = None
    subject_id: str | None = None
    open_gates: bool = False
    blocking_only: bool = False


class UiImpactAuditResult(BaseModel):
    surfaces: list[UiSurfaceMapEntry] = Field(default_factory=list)
    contracts: list[UiContract] = Field(default_factory=list)
    created_gates: list[QualityGate] = Field(default_factory=list)


def _new_id() -> str:
    return secrets.token_hex(6)


def _dumps(payload: Any) -> str:
    return json.dumps(payload)


def _loads_list(payload: str | None) -> list[str]:
    if not payload:
        return []
    try:
        decoded = json.loads(payload)
    except json.JSONDecodeError:
        return []
    return [str(item) for item in decoded] if isinstance(decoded, list) else []


def _loads_dict(payload: str | None) -> dict[str, Any]:
    if not payload:
        return {}
    try:
        decoded = json.loads(payload)
    except json.JSONDecodeError:
        return {}
    return decoded if isinstance(decoded, dict) else {}


def _row_to_surface(row: sqlite3.Row) -> UiSurfaceMapEntry:
    return UiSurfaceMapEntry(
        id=row["id"],
        title=row["title"],
        route=row["route"] or "",
        description=row["description"] or "",
        action_ids=_loads_list(row["action_ids_json"]),
        file_patterns=_loads_list(row["file_patterns_json"]),
        linked_surface_ids=_loads_list(row["linked_surface_ids_json"]),
        metadata=_loads_dict(row["metadata_json"]),
        builtin=bool(row["builtin"]),
        created_at=from_iso(row["created_at"]),
        updated_at=from_iso(row["updated_at"]),
    )


def _row_to_contract(row: sqlite3.Row) -> UiContract:
    return UiContract(
        id=row["id"],
        title=row["title"],
        surface_id=row["surface_id"],
        severity=UiContractSeverity(row["severity"]),
        route=row["route"] or "",
        action_id=row["action_id"],
        preconditions=_loads_list(row["preconditions_json"]),
        steps=_loads_list(row["steps_json"]),
        assertions=_loads_list(row["assertions_json"]),
        touched_file_patterns=_loads_list(row["touched_file_patterns_json"]),
        linked_surface_ids=_loads_list(row["linked_surface_ids_json"]),
        latest_evidence_ids=_loads_list(row["latest_evidence_ids_json"]),
        metadata=_loads_dict(row["metadata_json"]),
        builtin=bool(row["builtin"]),
        created_at=from_iso(row["created_at"]),
        updated_at=from_iso(row["updated_at"]),
    )


def _row_to_gate(row: sqlite3.Row) -> QualityGate:
    return QualityGate(
        id=row["id"],
        subject_type=row["subject_type"],
        subject_id=row["subject_id"],
        gate_kind=row["gate_kind"],
        title=row["title"] or "",
        blocking=bool(row["blocking"]),
        status=QualityGateStatus(row["status"]),
        required_evidence=_loads_list(row["required_evidence_json"]),
        linked_surface_ids=_loads_list(row["linked_surface_ids_json"]),
        linked_contract_ids=_loads_list(row["linked_contract_ids_json"]),
        waiver_state=QualityGateWaiverState(row["waiver_state"]),
        opened_at=from_iso(row["opened_at"]),
        resolved_at=from_iso(row["resolved_at"]) if row["resolved_at"] else None,
        resolved_by=row["resolved_by"],
        audit_details=_loads_dict(row["audit_details_json"]),
    )


def _row_to_evidence(row: sqlite3.Row) -> QualityEvidence:
    return QualityEvidence(
        id=row["id"],
        subject_type=row["subject_type"],
        subject_id=row["subject_id"],
        gate_id=row["gate_id"],
        contract_id=row["contract_id"],
        evidence_kind=row["evidence_kind"],
        label=row["label"] or "",
        surface_id=row["surface_id"],
        route=row["route"] or "",
        action_id=row["action_id"],
        selector=row["selector"],
        verdict=QualityEvidenceVerdict(row["verdict"]),
        artifact_path=row["artifact_path"],
        metadata=_loads_dict(row["metadata_json"]),
        created_at=from_iso(row["created_at"]),
    )


def list_surfaces(conn: sqlite3.Connection) -> list[UiSurfaceMapEntry]:
    rows = conn.execute(
        "SELECT * FROM ui_surface_map ORDER BY route, builtin DESC, title COLLATE NOCASE"
    ).fetchall()
    return [_row_to_surface(row) for row in rows]


def get_surface(conn: sqlite3.Connection, surface_id: str) -> UiSurfaceMapEntry:
    row = conn.execute("SELECT * FROM ui_surface_map WHERE id = ?", (surface_id,)).fetchone()
    if row is None:
        raise not_found("ui_surface", surface_id)
    return _row_to_surface(row)


def create_surface(conn: sqlite3.Connection, payload: UiSurfaceMapEntry) -> UiSurfaceMapEntry:
    now = utc_now()
    if conn.execute("SELECT 1 FROM ui_surface_map WHERE id = ?", (payload.id,)).fetchone():
        raise invalid("ui_surface", f"Surface id '{payload.id}' already exists.")
    conn.execute(
        """
        INSERT INTO ui_surface_map (
            id, title, route, description, action_ids_json, file_patterns_json,
            linked_surface_ids_json, metadata_json, builtin, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            payload.id,
            payload.title,
            payload.route,
            payload.description,
            _dumps(payload.action_ids),
            _dumps(payload.file_patterns),
            _dumps(payload.linked_surface_ids),
            _dumps(payload.metadata),
            1 if payload.builtin else 0,
            to_iso(now),
            to_iso(now),
        ),
    )
    return get_surface(conn, payload.id)


def list_contracts(conn: sqlite3.Connection) -> list[UiContract]:
    rows = conn.execute(
        "SELECT * FROM ui_contracts ORDER BY severity DESC, builtin DESC, title COLLATE NOCASE"
    ).fetchall()
    return [_row_to_contract(row) for row in rows]


def get_contract(conn: sqlite3.Connection, contract_id: str) -> UiContract:
    row = conn.execute("SELECT * FROM ui_contracts WHERE id = ?", (contract_id,)).fetchone()
    if row is None:
        raise not_found("ui_contract", contract_id)
    return _row_to_contract(row)


def create_contract(conn: sqlite3.Connection, payload: UiContractCreate) -> UiContract:
    get_surface(conn, payload.surface_id)
    if conn.execute("SELECT 1 FROM ui_contracts WHERE id = ?", (payload.id,)).fetchone():
        raise invalid("ui_contract", f"Contract id '{payload.id}' already exists.")
    now = utc_now()
    conn.execute(
        """
        INSERT INTO ui_contracts (
            id, title, surface_id, severity, route, action_id, preconditions_json,
            steps_json, assertions_json, touched_file_patterns_json,
            linked_surface_ids_json, latest_evidence_ids_json, metadata_json, builtin,
            created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '[]', ?, ?, ?, ?)
        """,
        (
            payload.id,
            payload.title,
            payload.surface_id,
            payload.severity.value,
            payload.route,
            payload.action_id,
            _dumps(payload.preconditions),
            _dumps(payload.steps),
            _dumps(payload.assertions),
            _dumps(payload.touched_file_patterns),
            _dumps(payload.linked_surface_ids),
            _dumps(payload.metadata),
            1 if payload.builtin else 0,
            to_iso(now),
            to_iso(now),
        ),
    )
    return get_contract(conn, payload.id)


def promote_contract(conn: sqlite3.Connection, payload: UiContractPromoteRequest) -> UiContract:
    return create_contract(
        conn,
        UiContractCreate(
            id=payload.id,
            title=payload.title,
            surface_id=payload.surface_id,
            severity=payload.severity,
            route=payload.route,
            action_id=payload.action_id,
            preconditions=payload.preconditions,
            steps=payload.steps,
            assertions=payload.assertions,
            touched_file_patterns=payload.touched_file_patterns,
            linked_surface_ids=payload.linked_surface_ids,
            metadata=payload.metadata,
        ),
    )


def _matching_open_gate(
    conn: sqlite3.Connection,
    payload: QualityGateCreate,
) -> QualityGate | None:
    rows = conn.execute(
        """
        SELECT *
        FROM quality_gates
        WHERE subject_type = ? AND subject_id = ? AND gate_kind = ?
          AND status = ?
        ORDER BY opened_at DESC
        """,
        (
            payload.subject_type,
            payload.subject_id,
            payload.gate_kind,
            QualityGateStatus.OPEN.value,
        ),
    ).fetchall()
    for row in rows:
        gate = _row_to_gate(row)
        if (
            set(gate.linked_surface_ids) == set(payload.linked_surface_ids)
            and set(gate.linked_contract_ids) == set(payload.linked_contract_ids)
            and gate.blocking == payload.blocking
        ):
            return gate
    return None


def create_gate(conn: sqlite3.Connection, payload: QualityGateCreate) -> QualityGate:
    existing = _matching_open_gate(conn, payload)
    if existing is not None:
        return existing
    gate_id = _new_id()
    now = utc_now()
    conn.execute(
        """
        INSERT INTO quality_gates (
            id, subject_type, subject_id, gate_kind, title, blocking, status,
            required_evidence_json, linked_surface_ids_json, linked_contract_ids_json,
            waiver_state, opened_at, resolved_at, resolved_by, audit_details_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, ?)
        """,
        (
            gate_id,
            payload.subject_type,
            payload.subject_id,
            payload.gate_kind,
            payload.title,
            1 if payload.blocking else 0,
            QualityGateStatus.OPEN.value,
            _dumps(payload.required_evidence),
            _dumps(payload.linked_surface_ids),
            _dumps(payload.linked_contract_ids),
            QualityGateWaiverState.NONE.value,
            to_iso(now),
            _dumps(payload.audit_details),
        ),
    )
    return get_gate(conn, gate_id)


def list_gates(
    conn: sqlite3.Connection,
    *,
    subject_type: str | None = None,
    subject_id: str | None = None,
    status: QualityGateStatus | None = None,
    blocking: bool | None = None,
) -> list[QualityGate]:
    clauses: list[str] = []
    params: list[Any] = []
    if subject_type is not None:
        clauses.append("subject_type = ?")
        params.append(subject_type)
    if subject_id is not None:
        clauses.append("subject_id = ?")
        params.append(subject_id)
    if status is not None:
        clauses.append("status = ?")
        params.append(status.value)
    if blocking is not None:
        clauses.append("blocking = ?")
        params.append(1 if blocking else 0)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = conn.execute(
        f"SELECT * FROM quality_gates {where} ORDER BY opened_at DESC",  # noqa: S608
        tuple(params),
    ).fetchall()
    return [_row_to_gate(row) for row in rows]


def get_gate(conn: sqlite3.Connection, gate_id: str) -> QualityGate:
    row = conn.execute("SELECT * FROM quality_gates WHERE id = ?", (gate_id,)).fetchone()
    if row is None:
        raise not_found("quality_gate", gate_id)
    return _row_to_gate(row)


def resolve_gate(
    conn: sqlite3.Connection, gate_id: str, payload: QualityGateResolveRequest
) -> QualityGate:
    gate = get_gate(conn, gate_id)
    if payload.status == QualityGateStatus.WAIVED:
        raise invalid("quality_gate", "Use the waive route to waive a gate.")
    if payload.status == QualityGateStatus.OPEN:
        raise invalid("quality_gate", "A gate cannot be resolved back to open.")
    details = {**gate.audit_details}
    if payload.note.strip():
        details["resolution_note"] = payload.note.strip()
    now = utc_now()
    conn.execute(
        """
        UPDATE quality_gates
        SET status = ?, resolved_at = ?, resolved_by = ?, waiver_state = ?, audit_details_json = ?
        WHERE id = ?
        """,
        (
            payload.status.value,
            to_iso(now),
            payload.resolved_by.strip() or "human",
            gate.waiver_state.value,
            _dumps(details),
            gate_id,
        ),
    )
    return get_gate(conn, gate_id)


def waive_gate(
    conn: sqlite3.Connection, gate_id: str, payload: QualityGateWaiveRequest
) -> QualityGate:
    gate = get_gate(conn, gate_id)
    details = {**gate.audit_details}
    if payload.note.strip():
        details["waiver_note"] = payload.note.strip()
    now = utc_now()
    conn.execute(
        """
        UPDATE quality_gates
        SET status = ?, resolved_at = ?, resolved_by = ?, waiver_state = ?, audit_details_json = ?
        WHERE id = ?
        """,
        (
            QualityGateStatus.WAIVED.value,
            to_iso(now),
            payload.resolved_by.strip() or "human",
            QualityGateWaiverState.WAIVED.value,
            _dumps(details),
            gate_id,
        ),
    )
    return get_gate(conn, gate_id)


def list_evidence(
    conn: sqlite3.Connection,
    *,
    subject_type: str | None = None,
    subject_id: str | None = None,
    contract_id: str | None = None,
    gate_id: str | None = None,
) -> list[QualityEvidence]:
    clauses: list[str] = []
    params: list[Any] = []
    if subject_type is not None:
        clauses.append("subject_type = ?")
        params.append(subject_type)
    if subject_id is not None:
        clauses.append("subject_id = ?")
        params.append(subject_id)
    if contract_id is not None:
        clauses.append("contract_id = ?")
        params.append(contract_id)
    if gate_id is not None:
        clauses.append("gate_id = ?")
        params.append(gate_id)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = conn.execute(
        f"SELECT * FROM quality_evidence {where} ORDER BY created_at DESC",  # noqa: S608
        tuple(params),
    ).fetchall()
    return [_row_to_evidence(row) for row in rows]


def _update_contract_latest_evidence(
    conn: sqlite3.Connection, contract_id: str, evidence_id: str
) -> None:
    contract = get_contract(conn, contract_id)
    latest = [evidence_id, *[item for item in contract.latest_evidence_ids if item != evidence_id]]
    conn.execute(
        "UPDATE ui_contracts SET latest_evidence_ids_json = ?, updated_at = ? WHERE id = ?",
        (_dumps(latest[:5]), to_iso(utc_now()), contract_id),
    )


def add_evidence(conn: sqlite3.Connection, payload: QualityEvidence) -> QualityEvidence:
    if payload.gate_id:
        get_gate(conn, payload.gate_id)
    if payload.contract_id:
        get_contract(conn, payload.contract_id)
    if payload.surface_id:
        get_surface(conn, payload.surface_id)
    conn.execute(
        """
        INSERT INTO quality_evidence (
            id, subject_type, subject_id, gate_id, contract_id, evidence_kind, label,
            surface_id, route, action_id, selector, verdict, artifact_path, metadata_json, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            payload.id,
            payload.subject_type,
            payload.subject_id,
            payload.gate_id,
            payload.contract_id,
            payload.evidence_kind,
            payload.label,
            payload.surface_id,
            payload.route,
            payload.action_id,
            payload.selector,
            payload.verdict.value,
            payload.artifact_path,
            _dumps(payload.metadata),
            to_iso(payload.created_at),
        ),
    )
    if payload.contract_id:
        _update_contract_latest_evidence(conn, payload.contract_id, payload.id)
    row = conn.execute("SELECT * FROM quality_evidence WHERE id = ?", (payload.id,)).fetchone()
    assert row is not None
    return _row_to_evidence(row)


def run_contract(
    conn: sqlite3.Connection,
    contract_id: str,
    payload: UiContractRunRequest,
) -> tuple[UiContract, QualityEvidence, QualityGate | None]:
    contract = get_contract(conn, contract_id)
    evidence = add_evidence(
        conn,
        QualityEvidence(
            id=_new_id(),
            subject_type=payload.subject_type,
            subject_id=payload.subject_id,
            gate_id=payload.gate_id,
            contract_id=contract_id,
            evidence_kind=payload.evidence_kind,
            label=payload.label or contract.title,
            surface_id=contract.surface_id,
            route=payload.route or contract.route,
            action_id=payload.action_id or contract.action_id,
            selector=payload.selector,
            verdict=payload.verdict,
            artifact_path=payload.artifact_path,
            metadata=payload.metadata,
            created_at=utc_now(),
        ),
    )
    matching_gate: QualityGate | None = None
    if payload.gate_id:
        matching_gate = get_gate(conn, payload.gate_id)
    elif payload.subject_type and payload.subject_id:
        for gate in list_gates(
            conn,
            subject_type=payload.subject_type,
            subject_id=payload.subject_id,
            status=QualityGateStatus.OPEN,
        ):
            if contract.id in gate.linked_contract_ids:
                matching_gate = gate
                break

    if payload.verdict == QualityEvidenceVerdict.PASS and matching_gate is not None:
        matching_gate = resolve_gate(
            conn,
            matching_gate.id,
            QualityGateResolveRequest(
                status=QualityGateStatus.PASSED,
                resolved_by="browser-proof",
                note=f"Evidence {evidence.id} passed contract {contract.id}.",
            ),
        )
    elif payload.verdict == QualityEvidenceVerdict.FAIL and matching_gate is None:
        matching_gate = create_gate(
            conn,
            QualityGateCreate(
                subject_type=payload.subject_type,
                subject_id=payload.subject_id,
                gate_kind="critical-ui" if contract.severity == UiContractSeverity.CRITICAL else "ui-regression",
                title=f"{contract.title} failed",
                blocking=contract.severity in {UiContractSeverity.CRITICAL, UiContractSeverity.HIGH},
                required_evidence=["browser-proof"],
                linked_surface_ids=[contract.surface_id, *contract.linked_surface_ids],
                linked_contract_ids=[contract.id],
                audit_details={
                    "contract_id": contract.id,
                    "contract_severity": contract.severity.value,
                    "evidence_id": evidence.id,
                },
            ),
        )
    elif payload.verdict == QualityEvidenceVerdict.FAIL and matching_gate is not None:
        matching_gate = resolve_gate(
            conn,
            matching_gate.id,
            QualityGateResolveRequest(
                status=QualityGateStatus.FAILED,
                resolved_by="browser-proof",
                note=f"Evidence {evidence.id} failed contract {contract.id}.",
            ),
        )
        matching_gate = create_gate(
            conn,
            QualityGateCreate(
                subject_type=payload.subject_type,
                subject_id=payload.subject_id,
                gate_kind=matching_gate.gate_kind,
                title=matching_gate.title or f"{contract.title} failed",
                blocking=matching_gate.blocking,
                required_evidence=matching_gate.required_evidence,
                linked_surface_ids=matching_gate.linked_surface_ids,
                linked_contract_ids=matching_gate.linked_contract_ids,
                audit_details={**matching_gate.audit_details, "reopened_by_evidence": evidence.id},
            ),
        )
    return contract, evidence, matching_gate


def blocking_gates_for_subject(
    conn: sqlite3.Connection, subject_type: str, subject_id: str
) -> list[QualityGate]:
    return list_gates(
        conn,
        subject_type=subject_type,
        subject_id=subject_id,
        status=QualityGateStatus.OPEN,
        blocking=True,
    )


def has_blocking_gates(conn: sqlite3.Connection, subject_type: str, subject_id: str) -> bool:
    return bool(blocking_gates_for_subject(conn, subject_type, subject_id))


def assert_subject_can_complete(conn: sqlite3.Connection, subject_type: str, subject_id: str) -> None:
    gates = blocking_gates_for_subject(conn, subject_type, subject_id)
    if not gates:
        return
    summary = ", ".join(
        gate.title or f"{gate.gate_kind}:{gate.id}"
        for gate in gates[:5]
    )
    raise invalid(
        "quality_gate",
        f"{subject_type}:{subject_id} still has blocking quality gates: {summary}",
    )


def assert_subjects_can_complete(conn: sqlite3.Connection, subjects: list[tuple[str, str]]) -> None:
    for subject_type, subject_id in subjects:
        assert_subject_can_complete(conn, subject_type, subject_id)


def latest_failing_contracts(conn: sqlite3.Connection, limit: int = 10) -> list[dict[str, Any]]:
    failing = []
    for contract in list_contracts(conn):
        latest = list_evidence(conn, contract_id=contract.id)[:1]
        if not latest or latest[0].verdict != QualityEvidenceVerdict.FAIL:
            continue
        failing.append(
            {
                "contract": contract.model_dump(mode="json"),
                "latest_evidence": latest[0].model_dump(mode="json"),
            }
        )
    return failing[:limit]


def _patterns_match(file_patterns: list[str], file_paths: list[str]) -> bool:
    normalized = [path.replace("\\", "/") for path in file_paths]
    for pattern in file_patterns:
        wildcard = pattern.replace("\\", "/")
        if any(fnmatch.fnmatch(path, wildcard) for path in normalized):
            return True
    return False


def impact_audit(conn: sqlite3.Connection, payload: UiImpactAuditRequest) -> UiImpactAuditResult:
    all_surfaces = list_surfaces(conn)
    all_contracts = list_contracts(conn)
    impacted_surfaces: list[UiSurfaceMapEntry] = []
    surface_ids = set(payload.surface_ids)
    for surface in all_surfaces:
        if surface.id in surface_ids or _patterns_match(surface.file_patterns, payload.file_paths):
            impacted_surfaces.append(surface)
    impacted_surface_ids = {surface.id for surface in impacted_surfaces}
    for surface in all_surfaces:
        if impacted_surface_ids.intersection(surface.linked_surface_ids):
            impacted_surface_ids.add(surface.id)
    impacted_surfaces = [surface for surface in all_surfaces if surface.id in impacted_surface_ids]

    impacted_contracts: list[UiContract] = []
    for contract in all_contracts:
        if contract.surface_id in impacted_surface_ids:
            impacted_contracts.append(contract)
            continue
        if impacted_surface_ids.intersection(contract.linked_surface_ids):
            impacted_contracts.append(contract)
            continue
        if _patterns_match(contract.touched_file_patterns, payload.file_paths):
            impacted_contracts.append(contract)
    impacted_contracts = list({contract.id: contract for contract in impacted_contracts}.values())

    created_gates: list[QualityGate] = []
    if payload.open_gates and payload.subject_type and payload.subject_id:
        for contract in impacted_contracts:
            if payload.blocking_only and contract.severity not in {
                UiContractSeverity.CRITICAL,
                UiContractSeverity.HIGH,
            }:
                continue
            created_gates.append(
                create_gate(
                    conn,
                    QualityGateCreate(
                        subject_type=payload.subject_type,
                        subject_id=payload.subject_id,
                        gate_kind="critical-ui"
                        if contract.severity == UiContractSeverity.CRITICAL
                        else "impact-audit",
                        title=f"Re-run UI contract: {contract.title}",
                        blocking=contract.severity in {
                            UiContractSeverity.CRITICAL,
                            UiContractSeverity.HIGH,
                        },
                        required_evidence=["browser-proof"],
                        linked_surface_ids=[contract.surface_id, *contract.linked_surface_ids],
                        linked_contract_ids=[contract.id],
                        audit_details={
                            "reason": "ui-impact-audit",
                            "file_paths": payload.file_paths,
                        },
                    ),
                )
            )
    return UiImpactAuditResult(
        surfaces=impacted_surfaces,
        contracts=impacted_contracts,
        created_gates=created_gates,
    )


def latest_browser_proof(
    conn: sqlite3.Connection, *, subject_type: str | None = None, subject_id: str | None = None, limit: int = 10
) -> list[QualityEvidence]:
    evidence = [
        item
        for item in list_evidence(conn, subject_type=subject_type, subject_id=subject_id)
        if item.evidence_kind == "browser-proof"
    ]
    return evidence[:limit]


def quality_summary(conn: sqlite3.Connection) -> dict[str, Any]:
    open_gates = list_gates(conn, status=QualityGateStatus.OPEN)
    blocking = [gate for gate in open_gates if gate.blocking]
    return {
        "open_count": len(open_gates),
        "blocking_count": len(blocking),
        "open_gates": [gate.model_dump(mode="json") for gate in open_gates[:20]],
        "failing_contracts": latest_failing_contracts(conn, limit=10),
        "latest_browser_proof": [
            item.model_dump(mode="json") for item in latest_browser_proof(conn, limit=10)
        ],
    }


def seeded_policy_gate_specs(
    conn: sqlite3.Connection,
    *,
    quality_profile_id: str | None = None,
    review_policy_id: str | None = None,
    evidence_policy_id: str | None = None,
    project_policy_id: str | None = None,
    ux_policy_id: str | None = None,
) -> list[QualityGateCreate]:
    gate_specs: list[QualityGateCreate] = []
    requested = [
        quality_profile_id,
        review_policy_id,
        evidence_policy_id,
        project_policy_id,
        ux_policy_id,
    ]
    components: list[ai_factory.AiComponent] = []
    for component_id in [item for item in requested if item]:
        try:
            components.append(ai_factory.get_component(conn, component_id))
        except Exception:
            continue

    metadata_by_id = {component.id: component.metadata for component in components}
    if quality_profile_id == "quality-critical-ui":
        meta = metadata_by_id.get(quality_profile_id, {})
        gate_specs.append(
            QualityGateCreate(
                subject_type="",
                subject_id="",
                gate_kind=str(meta.get("gate_kind", "critical-ui")),
                title="Critical UI quality gate",
                blocking=bool(meta.get("blocking", True)),
                required_evidence=[str(item) for item in meta.get("required_evidence", ["browser-proof"])],
            )
        )
    if review_policy_id == "review-ui-blocking":
        meta = metadata_by_id.get(review_policy_id, {})
        gate_specs.append(
            QualityGateCreate(
                subject_type="",
                subject_id="",
                gate_kind=str(meta.get("gate_kind", "ui-review")),
                title="Structured UI review gate",
                blocking=bool(meta.get("blocking", True)),
                required_evidence=[str(item) for item in meta.get("required_evidence", ["review-verdict"])],
            )
        )
    if evidence_policy_id == "evidence-browser-proof":
        meta = metadata_by_id.get(evidence_policy_id, {})
        gate_specs.append(
            QualityGateCreate(
                subject_type="",
                subject_id="",
                gate_kind=str(meta.get("gate_kind", "browser-proof")),
                title="Browser proof required",
                blocking=bool(meta.get("blocking", True)),
                required_evidence=[str(item) for item in meta.get("required_evidence", ["browser-proof"])],
            )
        )
    if project_policy_id == "project-anchor-explicit":
        gate_specs.append(
            QualityGateCreate(
                subject_type="",
                subject_id="",
                gate_kind="project-targeting",
                title="Project targeting must be explicit",
                blocking=True,
                required_evidence=["project-selection"],
            )
        )
    if ux_policy_id == "one-window-preferred":
        gate_specs.append(
            QualityGateCreate(
                subject_type="",
                subject_id="",
                gate_kind="one-window",
                title="Prefer one-window continuation",
                blocking=False,
                required_evidence=["ux-review"],
            )
        )
    return gate_specs


def open_policy_gates_for_subject(
    conn: sqlite3.Connection,
    *,
    subject_type: str,
    subject_id: str,
    quality_profile_id: str | None = None,
    review_policy_id: str | None = None,
    evidence_policy_id: str | None = None,
    project_policy_id: str | None = None,
    ux_policy_id: str | None = None,
    linked_surface_ids: list[str] | None = None,
    linked_contract_ids: list[str] | None = None,
    audit_details: dict[str, Any] | None = None,
) -> list[QualityGate]:
    gates: list[QualityGate] = []
    for gate in seeded_policy_gate_specs(
        conn,
        quality_profile_id=quality_profile_id,
        review_policy_id=review_policy_id,
        evidence_policy_id=evidence_policy_id,
        project_policy_id=project_policy_id,
        ux_policy_id=ux_policy_id,
    ):
        gates.append(
            create_gate(
                conn,
                gate.model_copy(
                    update={
                        "subject_type": subject_type,
                        "subject_id": subject_id,
                        "linked_surface_ids": linked_surface_ids or [],
                        "linked_contract_ids": linked_contract_ids or [],
                        "audit_details": audit_details or {},
                    }
                ),
            )
        )
    return gates


def _ensure_surface(conn: sqlite3.Connection, payload: UiSurfaceMapEntry) -> None:
    if conn.execute("SELECT 1 FROM ui_surface_map WHERE id = ?", (payload.id,)).fetchone():
        return
    create_surface(conn, payload)


def _ensure_contract(conn: sqlite3.Connection, payload: UiContractCreate) -> None:
    if conn.execute("SELECT 1 FROM ui_contracts WHERE id = ?", (payload.id,)).fetchone():
        return
    create_contract(conn, payload)


def seed_default_quality_os(conn: sqlite3.Connection) -> None:
    now = utc_now()
    surfaces = [
        UiSurfaceMapEntry(
            id="apps.projects-grid",
            title="Projects grid",
            route="apps",
            description="Project discovery, launch, and detail entry point.",
            action_ids=["filter-projects", "launch-project", "open-project-details"],
            file_patterns=["renderer/pages/Apps.tsx", "renderer/components/ProjectTile.tsx"],
            builtin=True,
            created_at=now,
            updated_at=now,
        ),
        UiSurfaceMapEntry(
            id="apps.project-details-modal",
            title="Project details modal",
            route="apps",
            description="Project detail modal with close, save, and dismiss behaviors.",
            action_ids=["close-dialog", "dismiss-dialog", "save-project"],
            file_patterns=[
                "renderer/components/ProjectDetailModal.tsx",
                "renderer/components/ui/modal.tsx",
            ],
            linked_surface_ids=["apps.projects-grid"],
            builtin=True,
            created_at=now,
            updated_at=now,
        ),
        UiSurfaceMapEntry(
            id="tools.hub",
            title="Tools hub",
            route="tools",
            description="Installed tools, marketplace access, MCP servers, and installed pages.",
            action_ids=["browse-tools", "open-marketplace", "open-installed-page"],
            file_patterns=["renderer/pages/Tools.tsx", "renderer/pages/Marketplace.tsx"],
            builtin=True,
            created_at=now,
            updated_at=now,
        ),
        UiSurfaceMapEntry(
            id="ai-factory.cockpit",
            title="AI Factory cockpit",
            route="ai-factory",
            description="One-window AI Factory workspace with composer, board, and inspector.",
            action_ids=["select-project", "create-case", "create-benchmark"],
            file_patterns=["renderer/pages/AiFactory.tsx"],
            builtin=True,
            created_at=now,
            updated_at=now,
        ),
        UiSurfaceMapEntry(
            id="settings.cockpit",
            title="Settings cockpit",
            route="settings",
            description="Settings categories, panes, and internal scrolling behavior.",
            action_ids=["open-profile", "open-roadmap", "open-sidebar-settings"],
            file_patterns=["renderer/pages/Settings.tsx"],
            builtin=True,
            created_at=now,
            updated_at=now,
        ),
        UiSurfaceMapEntry(
            id="coder-workspace.shell",
            title="Coder workspace",
            route="ai-coding",
            description="Thread workspace, project anchoring, review passes, and inline continuation.",
            action_ids=["select-project", "create-thread", "launch-review-pass"],
            file_patterns=["renderer/pages/CoderWorkspace.tsx", "renderer/components/CommandPalette.tsx"],
            builtin=True,
            created_at=now,
            updated_at=now,
        ),
        UiSurfaceMapEntry(
            id="shared.project-target-picker",
            title="Project target picker",
            route="shared",
            description="Shared project picker with inline creation and return-to-caller handoff.",
            action_ids=["select-project", "create-project-inline", "return-to-caller"],
            file_patterns=[
                "renderer/components/ProjectTargetPicker.tsx",
                "renderer/components/ProjectFormDialog.tsx",
            ],
            linked_surface_ids=["ai-factory.cockpit", "coder-workspace.shell"],
            builtin=True,
            created_at=now,
            updated_at=now,
        ),
    ]
    for surface in surfaces:
        _ensure_surface(conn, surface)

    contracts = [
        UiContractCreate(
            id="project-launch-action",
            title="Launch button starts the project without hidden parent-click regressions",
            surface_id="apps.projects-grid",
            severity=UiContractSeverity.CRITICAL,
            route="apps",
            action_id="launch-project",
            preconditions=["At least one project exists in the grid."],
            steps=["Click Launch on a project card once."],
            assertions=[
                "The launch action fires exactly once.",
                "The card does not reopen or redirect because of parent-click bubbling.",
                "A visible running or error state appears without silent failure.",
            ],
            touched_file_patterns=[
                "renderer/components/ProjectTile.tsx",
                "renderer/pages/Apps.tsx",
                "daemon/synapse_daemon/routes_projects.py",
            ],
            metadata={"category": "critical-control"},
            builtin=True,
        ),
        UiContractCreate(
            id="project-detail-close-button",
            title="Close button dismisses the project details modal",
            surface_id="apps.project-details-modal",
            severity=UiContractSeverity.CRITICAL,
            route="apps",
            action_id="close-dialog",
            preconditions=["The project details modal is open."],
            steps=["Click Close once."],
            assertions=[
                "The modal closes and stays closed.",
                "Focus is restored to the previous surface.",
            ],
            touched_file_patterns=[
                "renderer/components/ProjectDetailModal.tsx",
                "renderer/components/ui/modal.tsx",
                "renderer/components/ProjectTile.tsx",
            ],
            linked_surface_ids=["apps.projects-grid"],
            metadata={"category": "critical-control"},
            builtin=True,
        ),
        UiContractCreate(
            id="project-detail-backdrop-dismiss",
            title="Backdrop click dismisses non-destructive project dialogs",
            surface_id="apps.project-details-modal",
            severity=UiContractSeverity.HIGH,
            route="apps",
            action_id="dismiss-dialog",
            preconditions=["The project details modal is open and no dirty-form prompt is active."],
            steps=["Click outside the dialog body."],
            assertions=["The dialog dismisses cleanly."],
            touched_file_patterns=[
                "renderer/components/ui/modal.tsx",
                "renderer/components/ProjectDetailModal.tsx",
            ],
            builtin=True,
        ),
        UiContractCreate(
            id="tool-hub-no-nested-discover",
            title="Tools hub does not duplicate Installed and Discover navigation layers",
            surface_id="tools.hub",
            severity=UiContractSeverity.HIGH,
            route="tools",
            action_id="browse-tools",
            assertions=[
                "Installed tools remain visible without a second nested Installed or Discover bar.",
                "Marketplace lives as its own destination instead of a duplicated stack.",
            ],
            touched_file_patterns=[
                "renderer/pages/Tools.tsx",
                "renderer/lib/nav.ts",
                "renderer/components/Sidebar.tsx",
            ],
            builtin=True,
        ),
        UiContractCreate(
            id="ai-factory-one-window",
            title="AI Factory supports one-window project targeting and launch",
            surface_id="ai-factory.cockpit",
            severity=UiContractSeverity.HIGH,
            route="ai-factory",
            action_id="create-case",
            assertions=[
                "A project can be selected or created inline.",
                "The user can continue the task without being bounced to Apps.",
                "Primary inputs stay compact until more space is needed.",
            ],
            touched_file_patterns=["renderer/pages/AiFactory.tsx"],
            linked_surface_ids=["shared.project-target-picker"],
            builtin=True,
        ),
        UiContractCreate(
            id="settings-pane-scroll",
            title="Settings uses pane-owned scrolling instead of one long stacked page",
            surface_id="settings.cockpit",
            severity=UiContractSeverity.MEDIUM,
            route="settings",
            action_id="open-sidebar-settings",
            assertions=[
                "Desktop settings avoid double-scroll containers.",
                "Primary categories are visible without dumping every control at once.",
            ],
            touched_file_patterns=["renderer/pages/Settings.tsx"],
            builtin=True,
        ),
        UiContractCreate(
            id="project-target-inline-create",
            title="Project target picker supports inline creation and auto-return",
            surface_id="shared.project-target-picker",
            severity=UiContractSeverity.CRITICAL,
            route="shared",
            action_id="create-project-inline",
            assertions=[
                "The picker can create a project without leaving the current task.",
                "The new project is auto-selected and returned to the caller.",
            ],
            touched_file_patterns=[
                "renderer/components/ProjectTargetPicker.tsx",
                "renderer/components/ProjectFormDialog.tsx",
                "renderer/components/CommandPalette.tsx",
            ],
            linked_surface_ids=["ai-factory.cockpit", "coder-workspace.shell"],
            builtin=True,
        ),
    ]
    for contract in contracts:
        _ensure_contract(conn, contract)
