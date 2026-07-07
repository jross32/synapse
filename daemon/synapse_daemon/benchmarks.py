"""Benchmark records and scoring helpers for Synapse coder surfaces."""

from __future__ import annotations

import json
import math
import platform
import secrets
import sqlite3
import statistics
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from . import __version__
from .coder_workspace import CoderRun
from .errors import invalid, not_found
from .runtime_paths import repo_root
from .time_utils import from_iso, to_iso, utc_now


class BenchmarkSurfaceKind(str, Enum):
    DIRECT_CLI = "direct_cli"
    SYNAPSE_CODER_THREAD = "synapse_coder_thread"
    SYNAPSE_WORKBENCH = "synapse_workbench"
    SYNAPSE_RAW_PTY = "synapse_raw_pty"
    PROJECT_LAUNCHER = "project_launcher"


class BenchmarkExecutionMode(str, Enum):
    SERIAL = "serial"
    CONCURRENT = "concurrent"


class BenchmarkRunStatus(str, Enum):
    DRAFT = "draft"
    READY = "ready"
    RUNNING = "running"
    COMPLETED = "completed"


class BenchmarkAttemptStatus(str, Enum):
    PENDING = "pending"
    LAUNCHED = "launched"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    UNAVAILABLE = "unavailable"
    INGESTED = "ingested"


class BenchmarkTokenProvenance(str, Enum):
    REPORTED = "reported"
    ESTIMATED = "estimated"
    UNKNOWN = "unknown"


class BenchmarkTokenSource(str, Enum):
    OLLAMA_API = "ollama_api"
    RUNTIME_SELF_REPORT = "runtime_self_report"
    TRANSCRIPT_ESTIMATOR = "transcript_estimator"
    UNAVAILABLE = "unavailable"


class BenchmarkConfidenceLabel(str, Enum):
    SINGLE_SAMPLE = "single-sample"
    DIRECTIONAL = "directional"
    STABLE = "stable"


class BenchmarkEnvFingerprint(BaseModel):
    host_platform: str = Field(default_factory=platform.system)
    host_release: str = Field(default_factory=platform.release)
    python_version: str = Field(default_factory=platform.python_version)
    node_version: str | None = None
    synapse_version: str = __version__
    extra: dict[str, Any] = Field(default_factory=dict)


class BenchmarkArtifact(BaseModel):
    id: str
    attempt_id: str
    kind: str
    label: str = ""
    path: str
    mime: str = "application/octet-stream"
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)


class BenchmarkScore(BaseModel):
    quality_score_100: float | None = None
    objective_pass_rate: float | None = None
    rubric_score_100: float | None = None
    elapsed_seconds: float | None = None
    quality_per_1k_tokens: float | None = None
    quality_per_minute: float | None = None
    tokens_per_passed_check: float | None = None
    # Bug-hunt scenarios (Plan 3 Phase 2 -- scored against a fixture answer key).
    bugs_found_true_positive: int | None = None
    false_positive_rate: float | None = None
    bugs_per_1k_tokens: float | None = None


class BugHuntScore(BaseModel):
    """Result of grading a bug-hunt run against a fixture answer key.

    Mirrors ``benchmarks/bug-hunt-fixture/grade.py`` so a squad/route can score a run in-process.
    ``bugs_per_1k_tokens`` is the headline efficiency number the topology benchmark ranks on.
    """

    total_bugs: int = 0
    true_positives: int = 0
    false_positives: int = 0
    duplicates: int = 0
    missed: list[str] = Field(default_factory=list)
    recall: float = 0.0
    false_positive_rate: float = 0.0
    bugs_per_1k_tokens: float | None = None


class BugHuntScoreRequest(BaseModel):
    """Grade a bug-hunt run. Provide the answer key one of two ways: inline via ``answer_key``,
    or by name via ``fixture`` (e.g. ``"bug-hunt-fixture"``) to load the shipped key from
    ``benchmarks/<fixture>/answer-key.json`` -- so a caller need not paste the whole key. Plus the
    run's ``findings`` and the ``total_tokens`` it spent."""

    answer_key: dict[str, Any] | None = None
    fixture: str | None = None
    findings: list[dict[str, Any]] = Field(default_factory=list)
    total_tokens: int = 0


class BenchmarkFailure(BaseModel):
    code: str
    message: str


class BenchmarkScenario(BaseModel):
    id: str
    spec_id: str
    name: str
    description: str = ""
    version: str = "v1"
    prompt_md: str = ""
    artifact_contract: dict[str, Any] = Field(default_factory=dict)
    verifier_contract: dict[str, Any] = Field(default_factory=dict)
    rubric_contract: dict[str, Any] = Field(default_factory=dict)
    reset_procedure_md: str = ""
    time_budget_seconds: int = 900
    objective_weight: float = 60.0
    rubric_weight: float = 40.0
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class BenchmarkSpec(BaseModel):
    id: str
    name: str
    description: str = ""
    primary_surface: BenchmarkSurfaceKind = BenchmarkSurfaceKind.SYNAPSE_CODER_THREAD
    default_repeat_count: int = 3
    official_weight_quality: float = 70.0
    official_weight_efficiency: float = 20.0
    official_weight_speed: float = 10.0
    strict_comparable_policy: str = "matching-provenance"
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class BenchmarkSpecBundle(BaseModel):
    spec: BenchmarkSpec
    scenarios: list[BenchmarkScenario] = Field(default_factory=list)


class BenchmarkRun(BaseModel):
    id: str
    spec_id: str
    project_id: str | None = None
    title: str
    status: BenchmarkRunStatus = BenchmarkRunStatus.DRAFT
    execution_mode: BenchmarkExecutionMode = BenchmarkExecutionMode.SERIAL
    repeat_count: int = 3
    notes_md: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    launched_at: datetime | None = None
    completed_at: datetime | None = None


class BenchmarkAttempt(BaseModel):
    id: str
    run_id: str
    scenario_id: str
    project_id: str | None = None
    thread_id: str | None = None
    coder_run_id: str | None = None
    repeat_index: int = 1
    candidate_group_key: str = ""
    intended_runtime_id: str = ""
    actual_runtime_id: str | None = None
    provider: str = ""
    model: str = ""
    runtime_version: str | None = None
    surface_kind: BenchmarkSurfaceKind
    surface_profile_version: str = ""
    workspace_context_mode: str = "project"
    attachments_count: int = 0
    hidden_context_hash: str | None = None
    workspace_context_hash: str | None = None
    workspace_overhead_bytes: int = 0
    context_items_injected: int = 0
    scenario_version: str = "v1"
    prompt_hash: str | None = None
    env_fingerprint: BenchmarkEnvFingerprint = Field(default_factory=BenchmarkEnvFingerprint)
    status: BenchmarkAttemptStatus = BenchmarkAttemptStatus.PENDING
    failure_code: str | None = None
    failure_message: str | None = None
    exit_code: int | None = None
    started_at: datetime | None = None
    ended_at: datetime | None = None
    elapsed_seconds: float | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    token_provenance: BenchmarkTokenProvenance = BenchmarkTokenProvenance.UNKNOWN
    token_source: BenchmarkTokenSource = BenchmarkTokenSource.UNAVAILABLE
    quality_score_100: float | None = None
    objective_pass_rate: float | None = None
    rubric_score_100: float | None = None
    quality_per_1k_tokens: float | None = None
    quality_per_minute: float | None = None
    tokens_per_passed_check: float | None = None
    verifier_summary: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class BenchmarkComparison(BaseModel):
    scenario_id: str
    runtime_id: str
    winner_candidate_key: str | None = None
    confidence_label: BenchmarkConfidenceLabel = BenchmarkConfidenceLabel.SINGLE_SAMPLE
    noisy: bool = True
    comparable_attempt_count: int = 0
    notes: str = ""


class BenchmarkCandidateSummary(BaseModel):
    candidate_key: str
    surface_kind: BenchmarkSurfaceKind
    intended_runtime_id: str
    provider: str = ""
    model: str = ""
    attempts_count: int = 0
    comparable_attempt_count: int = 0
    median_quality_score_100: float | None = None
    pass_rate: float = 0.0
    median_elapsed_seconds: float | None = None
    median_total_tokens: float | None = None
    median_quality_per_1k_tokens: float | None = None
    median_quality_per_minute: float | None = None
    composite_score: float | None = None
    efficiency_frontier: bool = False
    confidence_label: BenchmarkConfidenceLabel = BenchmarkConfidenceLabel.SINGLE_SAMPLE
    noisy: bool = True


class BenchmarkRunReport(BaseModel):
    run: BenchmarkRun
    official_quality_ranking: list[BenchmarkCandidateSummary] = Field(default_factory=list)
    efficiency_frontier: list[BenchmarkCandidateSummary] = Field(default_factory=list)
    composite_score: list[BenchmarkCandidateSummary] = Field(default_factory=list)
    strict_comparable_attempt_ids: list[str] = Field(default_factory=list)
    comparisons: list[BenchmarkComparison] = Field(default_factory=list)
    all_attempts: list[BenchmarkAttempt] = Field(default_factory=list)
    lessons: dict[str, Any] = Field(default_factory=dict)


class BenchmarkMatrixEntry(BaseModel):
    scenario_id: str
    runtime_id: str
    provider: str = ""
    model: str = ""
    surface_kind: BenchmarkSurfaceKind
    runtime_version: str | None = None
    argv: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class BenchmarkSpecCreate(BaseModel):
    id: str
    name: str
    description: str = ""
    primary_surface: BenchmarkSurfaceKind = BenchmarkSurfaceKind.SYNAPSE_CODER_THREAD
    default_repeat_count: int = 3
    official_weight_quality: float = 70.0
    official_weight_efficiency: float = 20.0
    official_weight_speed: float = 10.0
    strict_comparable_policy: str = "matching-provenance"
    metadata: dict[str, Any] = Field(default_factory=dict)
    scenarios: list[BenchmarkScenario] = Field(default_factory=list)


class BenchmarkRunCreate(BaseModel):
    spec_id: str
    project_id: str | None = None
    title: str
    execution_mode: BenchmarkExecutionMode = BenchmarkExecutionMode.SERIAL
    repeat_count: int = 3
    notes_md: str = ""
    matrix: list[BenchmarkMatrixEntry] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class BenchmarkLaunchRequest(BaseModel):
    attempt_id: str | None = None
    argv: list[str] = Field(default_factory=list)
    runtime_version: str | None = None
    open_in_tab: bool = False


class BenchmarkDirectIngestRequest(BaseModel):
    attempt_id: str
    actual_runtime_id: str | None = None
    runtime_version: str | None = None
    status: BenchmarkAttemptStatus = BenchmarkAttemptStatus.INGESTED
    failure: BenchmarkFailure | None = None
    exit_code: int | None = None
    started_at: datetime | None = None
    ended_at: datetime | None = None
    elapsed_seconds: float | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    token_provenance: BenchmarkTokenProvenance = BenchmarkTokenProvenance.UNKNOWN
    token_source: BenchmarkTokenSource = BenchmarkTokenSource.UNAVAILABLE
    quality_score_100: float | None = None
    objective_pass_rate: float | None = None
    rubric_score_100: float | None = None
    verifier_summary: dict[str, Any] = Field(default_factory=dict)
    env_fingerprint: BenchmarkEnvFingerprint | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    artifacts: list[dict[str, Any]] = Field(default_factory=list)


def _new_id() -> str:
    return secrets.token_hex(6)


def _dumps(payload: Any) -> str:
    return json.dumps(payload)


def _loads_dict(payload: str | None) -> dict[str, Any]:
    if not payload:
        return {}
    try:
        decoded = json.loads(payload)
    except json.JSONDecodeError:
        return {}
    return decoded if isinstance(decoded, dict) else {}


def _loads_model_dict(payload: str | None) -> dict[str, Any]:
    value = _loads_dict(payload)
    return value if isinstance(value, dict) else {}


def _median(values: list[float | int | None]) -> float | None:
    data = [float(item) for item in values if item is not None]
    return statistics.median(data) if data else None


def _coefficient_variation(values: list[float | int | None]) -> float | None:
    data = [float(item) for item in values if item is not None]
    if len(data) < 2:
        return None
    mean = statistics.fmean(data)
    if mean == 0:
        return 0.0
    return statistics.pstdev(data) / mean


def _prompt_hash(text: str) -> str:
    import hashlib

    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def default_env_fingerprint() -> BenchmarkEnvFingerprint:
    return BenchmarkEnvFingerprint()


def _row_to_spec(row: sqlite3.Row) -> BenchmarkSpec:
    return BenchmarkSpec(
        id=row["id"],
        name=row["name"],
        description=row["description"] or "",
        primary_surface=BenchmarkSurfaceKind(row["primary_surface"]),
        default_repeat_count=row["default_repeat_count"] or 3,
        official_weight_quality=float(row["official_weight_quality"] or 70.0),
        official_weight_efficiency=float(row["official_weight_efficiency"] or 20.0),
        official_weight_speed=float(row["official_weight_speed"] or 10.0),
        strict_comparable_policy=row["strict_comparable_policy"] or "matching-provenance",
        metadata=_loads_dict(row["metadata_json"]),
        created_at=from_iso(row["created_at"]),
        updated_at=from_iso(row["updated_at"]),
    )


def _row_to_scenario(row: sqlite3.Row) -> BenchmarkScenario:
    return BenchmarkScenario(
        id=row["id"],
        spec_id=row["spec_id"],
        name=row["name"],
        description=row["description"] or "",
        version=row["version"] or "v1",
        prompt_md=row["prompt_md"] or "",
        artifact_contract=_loads_dict(row["artifact_contract_json"]),
        verifier_contract=_loads_dict(row["verifier_contract_json"]),
        rubric_contract=_loads_dict(row["rubric_contract_json"]),
        reset_procedure_md=row["reset_procedure_md"] or "",
        time_budget_seconds=row["time_budget_seconds"] or 900,
        objective_weight=float(row["objective_weight"] or 60.0),
        rubric_weight=float(row["rubric_weight"] or 40.0),
        metadata=_loads_dict(row["metadata_json"]),
        created_at=from_iso(row["created_at"]),
        updated_at=from_iso(row["updated_at"]),
    )


def _row_to_run(row: sqlite3.Row) -> BenchmarkRun:
    return BenchmarkRun(
        id=row["id"],
        spec_id=row["spec_id"],
        project_id=row["project_id"],
        title=row["title"],
        status=BenchmarkRunStatus(row["status"]),
        execution_mode=BenchmarkExecutionMode(row["execution_mode"]),
        repeat_count=row["repeat_count"] or 3,
        notes_md=row["notes_md"] or "",
        metadata=_loads_dict(row["metadata_json"]),
        created_at=from_iso(row["created_at"]),
        updated_at=from_iso(row["updated_at"]),
        launched_at=from_iso(row["launched_at"]) if row["launched_at"] else None,
        completed_at=from_iso(row["completed_at"]) if row["completed_at"] else None,
    )


def _row_to_attempt(row: sqlite3.Row) -> BenchmarkAttempt:
    fingerprint = _loads_model_dict(row["env_fingerprint_json"])
    return BenchmarkAttempt(
        id=row["id"],
        run_id=row["run_id"],
        scenario_id=row["scenario_id"],
        project_id=row["project_id"],
        thread_id=row["thread_id"],
        coder_run_id=row["coder_run_id"],
        repeat_index=row["repeat_index"] or 1,
        candidate_group_key=row["candidate_group_key"] or "",
        intended_runtime_id=row["intended_runtime_id"] or "",
        actual_runtime_id=row["actual_runtime_id"],
        provider=row["provider"] or "",
        model=row["model"] or "",
        runtime_version=row["runtime_version"],
        surface_kind=BenchmarkSurfaceKind(row["surface_kind"]),
        surface_profile_version=row["surface_profile_version"] or "",
        workspace_context_mode=row["workspace_context_mode"] or "project",
        attachments_count=row["attachments_count"] or 0,
        hidden_context_hash=row["hidden_context_hash"],
        workspace_context_hash=row["workspace_context_hash"],
        workspace_overhead_bytes=row["workspace_overhead_bytes"] or 0,
        context_items_injected=row["context_items_injected"] or 0,
        scenario_version=row["scenario_version"] or "v1",
        prompt_hash=row["prompt_hash"],
        env_fingerprint=BenchmarkEnvFingerprint(**fingerprint) if fingerprint else default_env_fingerprint(),
        status=BenchmarkAttemptStatus(row["status"]),
        failure_code=row["failure_code"],
        failure_message=row["failure_message"],
        exit_code=row["exit_code"],
        started_at=from_iso(row["started_at"]) if row["started_at"] else None,
        ended_at=from_iso(row["ended_at"]) if row["ended_at"] else None,
        elapsed_seconds=float(row["elapsed_seconds"]) if row["elapsed_seconds"] is not None else None,
        input_tokens=row["input_tokens"],
        output_tokens=row["output_tokens"],
        total_tokens=row["total_tokens"],
        token_provenance=BenchmarkTokenProvenance(row["token_provenance"]),
        token_source=BenchmarkTokenSource(row["token_source"]),
        quality_score_100=float(row["quality_score_100"]) if row["quality_score_100"] is not None else None,
        objective_pass_rate=float(row["objective_pass_rate"]) if row["objective_pass_rate"] is not None else None,
        rubric_score_100=float(row["rubric_score_100"]) if row["rubric_score_100"] is not None else None,
        quality_per_1k_tokens=float(row["quality_per_1k_tokens"]) if row["quality_per_1k_tokens"] is not None else None,
        quality_per_minute=float(row["quality_per_minute"]) if row["quality_per_minute"] is not None else None,
        tokens_per_passed_check=float(row["tokens_per_passed_check"]) if row["tokens_per_passed_check"] is not None else None,
        verifier_summary=_loads_dict(row["verifier_summary_json"]),
        metadata=_loads_dict(row["metadata_json"]),
        created_at=from_iso(row["created_at"]),
        updated_at=from_iso(row["updated_at"]),
    )


def _row_to_artifact(row: sqlite3.Row) -> BenchmarkArtifact:
    return BenchmarkArtifact(
        id=row["id"],
        attempt_id=row["attempt_id"],
        kind=row["kind"],
        label=row["label"] or "",
        path=row["path"],
        mime=row["mime"] or "application/octet-stream",
        metadata=_loads_dict(row["metadata_json"]),
        created_at=from_iso(row["created_at"]),
    )


def _seed_spec_if_missing(
    conn: sqlite3.Connection,
    *,
    spec_id: str,
    name: str,
    description: str,
    primary_surface: BenchmarkSurfaceKind,
    metadata: dict[str, Any],
    scenarios: list[dict[str, Any]],
) -> None:
    if conn.execute("SELECT 1 FROM benchmark_specs WHERE id = ?", (spec_id,)).fetchone():
        return
    now = to_iso(utc_now())
    conn.execute(
        """
        INSERT INTO benchmark_specs (
            id, name, description, primary_surface, default_repeat_count,
            official_weight_quality, official_weight_efficiency, official_weight_speed,
            strict_comparable_policy, metadata_json, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            spec_id,
            name,
            description,
            primary_surface.value,
            3,
            70.0,
            20.0,
            10.0,
            "matching-provenance",
            _dumps(metadata),
            now,
            now,
        ),
    )
    for raw in scenarios:
        prompt = (
            f"Benchmark scenario: {raw['name']}\n\n"
            "Produce a working result, keep notes concise, preserve runtime provenance, "
            "and end with a verification-oriented summary."
        )
        conn.execute(
            """
            INSERT INTO benchmark_scenarios (
                id, spec_id, name, description, version, prompt_md,
                artifact_contract_json, verifier_contract_json, rubric_contract_json,
                reset_procedure_md, time_budget_seconds, objective_weight, rubric_weight,
                metadata_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, 'v1', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                raw["id"],
                spec_id,
                raw["name"],
                raw["description"],
                prompt,
                _dumps({"required": ["transcript", "verifier-output", "result-summary"]}),
                _dumps({"owner": "synapse", "surface": "project-launcher"}),
                _dumps({"blind_review": True}),
                "Reset the workspace or fixture snapshot before the attempt. Keep auth/runtime caches warm.",
                raw["time_budget_seconds"],
                raw["objective_weight"],
                raw["rubric_weight"],
                _dumps({**raw.get("metadata", {}), "scenario_family": raw["id"]}),
                now,
                now,
            ),
        )


def seed_default_specs(conn: sqlite3.Connection) -> None:
    _seed_spec_if_missing(
        conn,
        spec_id="coder-workspace-v1",
        name="Coder Workspace v1",
        description="Mixed mini-suite for chat-first workspace, workbench, raw PTY, and direct CLI comparisons.",
        primary_surface=BenchmarkSurfaceKind.SYNAPSE_CODER_THREAD,
        metadata={"suite": "mixed-mini"},
        scenarios=[
            {
                "id": "static-app-mini",
                "name": "Static app mini",
                "description": "Very small app with layout, content structure, and basic polish.",
                "objective_weight": 60.0,
                "rubric_weight": 40.0,
                "time_budget_seconds": 900,
            },
            {
                "id": "stateful-app-mini",
                "name": "Stateful app mini",
                "description": "Small app with local state and interactive behavior.",
                "objective_weight": 60.0,
                "rubric_weight": 40.0,
                "time_budget_seconds": 900,
            },
            {
                "id": "repo-fix-mini",
                "name": "Repo fix mini",
                "description": "Small targeted bug-fix task inside an existing repo.",
                "objective_weight": 70.0,
                "rubric_weight": 30.0,
                "time_budget_seconds": 1500,
            },
            {
                "id": "repo-extend-mini",
                "name": "Repo extend mini",
                "description": "Small feature extension in an existing repo with tests and verification.",
                "objective_weight": 70.0,
                "rubric_weight": 30.0,
                "time_budget_seconds": 1500,
            },
        ],
    )
    _seed_spec_if_missing(
        conn,
        spec_id="quality-loop-v1",
        name="Quality Loop v1",
        description=(
            "Compares cheaper targeted-review loops against heavier second-pass "
            "and harvest-plus-judge flows for self-improvement and design remix work."
        ),
        primary_surface=BenchmarkSurfaceKind.SYNAPSE_CODER_THREAD,
        metadata={
            "suite": "quality-loop",
            "escalation_policy": "cheap-first-targeted-review",
        },
        scenarios=[
            {
                "id": "single-pass-build",
                "name": "Single-pass build",
                "description": "One build pass with no reviewer or harvest assist.",
                "objective_weight": 65.0,
                "rubric_weight": 35.0,
                "time_budget_seconds": 1200,
                "metadata": {"comparison_mode": "single-pass-build"},
            },
            {
                "id": "build-targeted-review",
                "name": "Build plus targeted reviewer",
                "description": "Primary build with one focused review pass instead of a full rebuild.",
                "objective_weight": 65.0,
                "rubric_weight": 35.0,
                "time_budget_seconds": 1400,
                "metadata": {"comparison_mode": "build-targeted-review"},
            },
            {
                "id": "harvest-build",
                "name": "Harvest plus build",
                "description": "Authorized reference harvest feeding a single implementation pass.",
                "objective_weight": 60.0,
                "rubric_weight": 40.0,
                "time_budget_seconds": 1500,
                "metadata": {"comparison_mode": "harvest-build"},
            },
            {
                "id": "harvest-build-judge",
                "name": "Harvest plus build plus judge",
                "description": "Reference harvest feeding implementation plus a final judging pass.",
                "objective_weight": 60.0,
                "rubric_weight": 40.0,
                "time_budget_seconds": 1800,
                "metadata": {"comparison_mode": "harvest-build-judge"},
            },
        ],
    )


def list_spec_bundles(conn: sqlite3.Connection) -> list[BenchmarkSpecBundle]:
    specs = [_row_to_spec(row) for row in conn.execute("SELECT * FROM benchmark_specs ORDER BY name").fetchall()]
    bundles: list[BenchmarkSpecBundle] = []
    for spec in specs:
        rows = conn.execute(
            "SELECT * FROM benchmark_scenarios WHERE spec_id = ? ORDER BY name",
            (spec.id,),
        ).fetchall()
        bundles.append(BenchmarkSpecBundle(spec=spec, scenarios=[_row_to_scenario(row) for row in rows]))
    return bundles


def get_spec_bundle(conn: sqlite3.Connection, spec_id: str) -> BenchmarkSpecBundle:
    row = conn.execute("SELECT * FROM benchmark_specs WHERE id = ?", (spec_id,)).fetchone()
    if row is None:
        raise not_found("benchmark_spec", spec_id)
    spec = _row_to_spec(row)
    rows = conn.execute("SELECT * FROM benchmark_scenarios WHERE spec_id = ? ORDER BY name", (spec_id,)).fetchall()
    return BenchmarkSpecBundle(spec=spec, scenarios=[_row_to_scenario(item) for item in rows])


def create_spec(conn: sqlite3.Connection, payload: BenchmarkSpecCreate) -> BenchmarkSpecBundle:
    now = to_iso(utc_now())
    conn.execute(
        """
        INSERT INTO benchmark_specs (
            id, name, description, primary_surface, default_repeat_count,
            official_weight_quality, official_weight_efficiency, official_weight_speed,
            strict_comparable_policy, metadata_json, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            payload.id,
            payload.name,
            payload.description,
            payload.primary_surface.value,
            payload.default_repeat_count,
            payload.official_weight_quality,
            payload.official_weight_efficiency,
            payload.official_weight_speed,
            payload.strict_comparable_policy,
            _dumps(payload.metadata),
            now,
            now,
        ),
    )
    for scenario in payload.scenarios:
        conn.execute(
            """
            INSERT INTO benchmark_scenarios (
                id, spec_id, name, description, version, prompt_md,
                artifact_contract_json, verifier_contract_json, rubric_contract_json,
                reset_procedure_md, time_budget_seconds, objective_weight, rubric_weight,
                metadata_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                scenario.id,
                payload.id,
                scenario.name,
                scenario.description,
                scenario.version,
                scenario.prompt_md,
                _dumps(scenario.artifact_contract),
                _dumps(scenario.verifier_contract),
                _dumps(scenario.rubric_contract),
                scenario.reset_procedure_md,
                scenario.time_budget_seconds,
                scenario.objective_weight,
                scenario.rubric_weight,
                _dumps(scenario.metadata),
                now,
                now,
            ),
        )
    return get_spec_bundle(conn, payload.id)


def list_runs(conn: sqlite3.Connection) -> list[BenchmarkRun]:
    rows = conn.execute("SELECT * FROM benchmark_runs ORDER BY updated_at DESC").fetchall()
    return [_row_to_run(row) for row in rows]


def get_run(conn: sqlite3.Connection, run_id: str) -> BenchmarkRun:
    row = conn.execute("SELECT * FROM benchmark_runs WHERE id = ?", (run_id,)).fetchone()
    if row is None:
        raise not_found("benchmark_run", run_id)
    return _row_to_run(row)


def list_attempts_for_run(conn: sqlite3.Connection, run_id: str) -> list[BenchmarkAttempt]:
    get_run(conn, run_id)
    rows = conn.execute(
        "SELECT * FROM benchmark_attempts WHERE run_id = ? ORDER BY scenario_id, repeat_index, created_at",
        (run_id,),
    ).fetchall()
    return [_row_to_attempt(row) for row in rows]


def get_attempt(conn: sqlite3.Connection, attempt_id: str) -> BenchmarkAttempt:
    row = conn.execute("SELECT * FROM benchmark_attempts WHERE id = ?", (attempt_id,)).fetchone()
    if row is None:
        raise not_found("benchmark_attempt", attempt_id)
    return _row_to_attempt(row)


def list_artifacts(conn: sqlite3.Connection, attempt_id: str) -> list[BenchmarkArtifact]:
    rows = conn.execute(
        "SELECT * FROM benchmark_artifacts WHERE attempt_id = ? ORDER BY created_at",
        (attempt_id,),
    ).fetchall()
    return [_row_to_artifact(row) for row in rows]


def create_run(conn: sqlite3.Connection, payload: BenchmarkRunCreate) -> BenchmarkRun:
    spec_bundle = get_spec_bundle(conn, payload.spec_id)
    if not payload.matrix:
        raise invalid("benchmark_run", "At least one matrix entry is required.")
    known_scenarios = {scenario.id: scenario for scenario in spec_bundle.scenarios}
    run_id = _new_id()
    now = to_iso(utc_now())
    conn.execute(
        """
        INSERT INTO benchmark_runs (
            id, spec_id, project_id, title, status, execution_mode, repeat_count,
            notes_md, metadata_json, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            run_id,
            payload.spec_id,
            payload.project_id,
            payload.title.strip() or "Benchmark run",
            BenchmarkRunStatus.READY.value,
            payload.execution_mode.value,
            payload.repeat_count,
            payload.notes_md,
            _dumps(payload.metadata),
            now,
            now,
        ),
    )
    for entry in payload.matrix:
        scenario = known_scenarios.get(entry.scenario_id)
        if scenario is None:
            raise invalid("benchmark_run", f"Unknown scenario '{entry.scenario_id}'.")
        for repeat_index in range(1, payload.repeat_count + 1):
            attempt_id = _new_id()
            candidate_group_key = f"{entry.surface_kind.value}:{entry.runtime_id}:{entry.model or entry.provider or 'runtime'}"
            conn.execute(
                """
                INSERT INTO benchmark_attempts (
                    id, run_id, scenario_id, project_id, repeat_index, candidate_group_key,
                    intended_runtime_id, provider, model, runtime_version, surface_kind,
                    surface_profile_version, workspace_context_mode, attachments_count,
                    scenario_version, prompt_hash, env_fingerprint_json, status,
                    token_provenance, token_source, verifier_summary_json, metadata_json,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    attempt_id,
                    run_id,
                    entry.scenario_id,
                    payload.project_id,
                    repeat_index,
                    candidate_group_key,
                    entry.runtime_id,
                    entry.provider,
                    entry.model,
                    entry.runtime_version,
                    entry.surface_kind.value,
                    f"{entry.surface_kind.value}/v1",
                    "project",
                    scenario.version,
                    _prompt_hash(scenario.prompt_md),
                    _dumps(default_env_fingerprint().model_dump(mode="json")),
                    BenchmarkAttemptStatus.PENDING.value,
                    BenchmarkTokenProvenance.UNKNOWN.value,
                    BenchmarkTokenSource.UNAVAILABLE.value,
                    _dumps({}),
                    _dumps({"argv": entry.argv, **entry.metadata}),
                    now,
                    now,
                ),
            )
    return get_run(conn, run_id)


def next_launchable_attempt(conn: sqlite3.Connection, run_id: str) -> BenchmarkAttempt | None:
    row = conn.execute(
        """
        SELECT * FROM benchmark_attempts
        WHERE run_id = ? AND status IN (?, ?)
        ORDER BY scenario_id, repeat_index, created_at
        LIMIT 1
        """,
        (run_id, BenchmarkAttemptStatus.PENDING.value, BenchmarkAttemptStatus.UNAVAILABLE.value),
    ).fetchone()
    return _row_to_attempt(row) if row is not None else None


def mark_run_launched(conn: sqlite3.Connection, run_id: str) -> BenchmarkRun:
    get_run(conn, run_id)
    now = to_iso(utc_now())
    conn.execute(
        "UPDATE benchmark_runs SET status = ?, launched_at = COALESCE(launched_at, ?), updated_at = ? WHERE id = ?",
        (BenchmarkRunStatus.RUNNING.value, now, now, run_id),
    )
    return get_run(conn, run_id)


def update_attempt_after_launch(
    conn: sqlite3.Connection,
    attempt_id: str,
    *,
    thread_id: str | None = None,
    coder_run_id: str | None = None,
    surface_profile_version: str | None = None,
    workspace_context_mode: str | None = None,
    attachments_count: int | None = None,
    workspace_context_hash: str | None = None,
    hidden_context_hash: str | None = None,
    workspace_overhead_bytes: int | None = None,
    context_items_injected: int | None = None,
    status: BenchmarkAttemptStatus = BenchmarkAttemptStatus.LAUNCHED,
) -> BenchmarkAttempt:
    current = get_attempt(conn, attempt_id)
    now = to_iso(utc_now())
    conn.execute(
        """
        UPDATE benchmark_attempts
        SET thread_id = ?, coder_run_id = ?, surface_profile_version = ?,
            workspace_context_mode = ?, attachments_count = ?, workspace_context_hash = ?,
            hidden_context_hash = ?, workspace_overhead_bytes = ?, context_items_injected = ?,
            status = ?, started_at = COALESCE(started_at, ?), updated_at = ?
        WHERE id = ?
        """,
        (
            current.thread_id if thread_id is None else thread_id,
            current.coder_run_id if coder_run_id is None else coder_run_id,
            current.surface_profile_version if surface_profile_version is None else surface_profile_version,
            current.workspace_context_mode if workspace_context_mode is None else workspace_context_mode,
            current.attachments_count if attachments_count is None else attachments_count,
            current.workspace_context_hash if workspace_context_hash is None else workspace_context_hash,
            current.hidden_context_hash if hidden_context_hash is None else hidden_context_hash,
            current.workspace_overhead_bytes if workspace_overhead_bytes is None else workspace_overhead_bytes,
            current.context_items_injected if context_items_injected is None else context_items_injected,
            status.value,
            now,
            now,
            attempt_id,
        ),
    )
    conn.execute("UPDATE benchmark_runs SET updated_at = ? WHERE id = ?", (now, current.run_id))
    return get_attempt(conn, attempt_id)


def mark_attempt_unavailable(
    conn: sqlite3.Connection, attempt_id: str, *, code: str, message: str
) -> BenchmarkAttempt:
    now = to_iso(utc_now())
    conn.execute(
        """
        UPDATE benchmark_attempts
        SET status = ?, failure_code = ?, failure_message = ?, updated_at = ?
        WHERE id = ?
        """,
        (BenchmarkAttemptStatus.UNAVAILABLE.value, code, message, now, attempt_id),
    )
    return get_attempt(conn, attempt_id)


def sync_attempt_from_coder_run(conn: sqlite3.Connection, run: CoderRun) -> BenchmarkAttempt | None:
    if not run.benchmark_attempt_id:
        return None
    current = get_attempt(conn, run.benchmark_attempt_id)
    now = to_iso(utc_now())
    elapsed = None
    if run.ended_at is not None:
        elapsed = max(0.0, (run.ended_at - run.started_at).total_seconds())
    status = current.status
    if run.status.value == "running":
        status = BenchmarkAttemptStatus.RUNNING
    elif run.status.value == "completed":
        status = BenchmarkAttemptStatus.COMPLETED
    elif run.status.value in {"failed", "crashed", "stopped"}:
        status = BenchmarkAttemptStatus.FAILED
    conn.execute(
        """
        UPDATE benchmark_attempts
        SET coder_run_id = ?, thread_id = COALESCE(thread_id, ?),
            actual_runtime_id = COALESCE(actual_runtime_id, ?), exit_code = ?,
            status = ?, started_at = COALESCE(started_at, ?), ended_at = ?,
            elapsed_seconds = COALESCE(?, elapsed_seconds),
            failure_code = COALESCE(failure_code, ?),
            failure_message = COALESCE(failure_message, ?),
            updated_at = ?
        WHERE id = ?
        """,
        (
            run.id,
            run.thread_id,
            run.runtime_id or None,
            run.exit_code,
            status.value,
            to_iso(run.started_at),
            to_iso(run.ended_at) if run.ended_at else None,
            elapsed,
            "runtime.crash" if run.status.value == "crashed" else None,
            run.crash_reason,
            now,
            current.id,
        ),
    )
    return get_attempt(conn, current.id)


def recompute_attempt_metrics(conn: sqlite3.Connection, attempt_id: str) -> BenchmarkAttempt:
    attempt = get_attempt(conn, attempt_id)
    total_tokens = attempt.total_tokens
    if total_tokens is None and attempt.input_tokens is not None and attempt.output_tokens is not None:
        total_tokens = attempt.input_tokens + attempt.output_tokens
    quality_per_1k_tokens = None
    if total_tokens and total_tokens > 0 and attempt.quality_score_100 is not None:
        quality_per_1k_tokens = attempt.quality_score_100 / (total_tokens / 1000.0)
    quality_per_minute = None
    if attempt.elapsed_seconds and attempt.elapsed_seconds > 0 and attempt.quality_score_100 is not None:
        quality_per_minute = attempt.quality_score_100 / (attempt.elapsed_seconds / 60.0)
    tokens_per_passed_check = None
    if total_tokens and total_tokens > 0 and attempt.objective_pass_rate not in (None, 0):
        tokens_per_passed_check = total_tokens / max(0.001, attempt.objective_pass_rate)
    now = to_iso(utc_now())
    conn.execute(
        """
        UPDATE benchmark_attempts
        SET total_tokens = ?, quality_per_1k_tokens = ?, quality_per_minute = ?,
            tokens_per_passed_check = ?, updated_at = ?
        WHERE id = ?
        """,
        (total_tokens, quality_per_1k_tokens, quality_per_minute, tokens_per_passed_check, now, attempt_id),
    )
    return get_attempt(conn, attempt_id)


def _norm_text(text: str) -> str:
    return " ".join(str(text).lower().split())


def score_bug_hunt(
    answer_key: dict[str, Any],
    findings: list[dict[str, Any]],
    total_tokens: int,
) -> BugHuntScore:
    """Grade bug-hunt ``findings`` against a fixture ``answer_key`` (see bug-hunt-fixture/).

    Each finding is ``{"text": str, "surface"?: str}``. A finding is a true positive when its
    text (plus surface) contains any of a bug's ``match`` phrases; each bug is claimed at most
    once (later matches are ``duplicates``), and a finding matching no bug is a false positive.
    Deterministic and dependency-free -- the in-process twin of ``grade.py``.
    """
    bugs = answer_key.get("bugs", [])
    claimed: dict[str, int] = {}
    false_positives = 0
    duplicates = 0

    for idx, finding in enumerate(findings):
        blob = _norm_text(finding.get("text", "")) + " " + _norm_text(finding.get("surface", ""))
        matched_id: str | None = None
        for bug in bugs:
            terms = [_norm_text(t) for t in bug.get("match", [])]
            if any(term and term in blob for term in terms):
                matched_id = bug.get("id")
                break
        if matched_id is None:
            false_positives += 1
        elif matched_id in claimed:
            duplicates += 1
        else:
            claimed[matched_id] = idx

    true_positives = len(claimed)
    missed = [b.get("id") for b in bugs if b.get("id") not in claimed]
    denom_fp = true_positives + false_positives
    tokens = max(int(total_tokens or 0), 0)
    return BugHuntScore(
        total_bugs=len(bugs),
        true_positives=true_positives,
        false_positives=false_positives,
        duplicates=duplicates,
        missed=missed,
        recall=round(true_positives / len(bugs), 4) if bugs else 0.0,
        false_positive_rate=round(false_positives / denom_fp, 4) if denom_fp else 0.0,
        bugs_per_1k_tokens=round(true_positives / (tokens / 1000.0), 4) if tokens else None,
    )


def load_fixture_answer_key(fixture: str) -> dict[str, Any]:
    """Resolve a shipped bug-hunt fixture's answer key by name (e.g. ``"bug-hunt-fixture"``).

    Lets a caller score against the fixture without pasting the whole key. The name is validated
    to a single safe path segment (no separators / traversal). Raises ``not_found`` when the
    fixture -- or its ``answer-key.json`` -- is absent (e.g. a packaged build that does not ship
    ``benchmarks/``), so the caller degrades to passing ``answer_key`` inline.
    """
    name = (fixture or "").strip()
    if not name or name != Path(name).name:
        raise invalid("bug_hunt_fixture", f"Invalid fixture name: {fixture!r}")
    path = repo_root() / "benchmarks" / name / "answer-key.json"
    if not path.is_file():
        raise not_found("bug_hunt_fixture", name)
    return json.loads(path.read_text(encoding="utf-8"))


def list_bug_hunt_fixtures() -> list[dict[str, Any]]:
    """List shipped bug-hunt fixtures -- any ``benchmarks/<name>/answer-key.json``.

    Lets an AI discover valid ``fixture`` names (and their bug counts) before calling
    ``score_bug_hunt``. Returns ``[]`` when the build does not ship ``benchmarks/``.
    """
    root = repo_root() / "benchmarks"
    fixtures: list[dict[str, Any]] = []
    if not root.is_dir():
        return fixtures
    for key_path in sorted(root.glob("*/answer-key.json")):
        try:
            data = json.loads(key_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        fixtures.append(
            {
                "name": key_path.parent.name,
                "fixture": data.get("fixture"),
                "total_bugs": len(data.get("bugs", [])),
                "description": data.get("description", ""),
            }
        )
    return fixtures


def ingest_direct_attempt(conn: sqlite3.Connection, payload: BenchmarkDirectIngestRequest) -> BenchmarkAttempt:
    attempt = get_attempt(conn, payload.attempt_id)
    now = to_iso(utc_now())
    started_at = to_iso(payload.started_at) if payload.started_at else (to_iso(attempt.started_at) if attempt.started_at else None)
    ended_at = to_iso(payload.ended_at) if payload.ended_at else (to_iso(attempt.ended_at) if attempt.ended_at else None)
    conn.execute(
        """
        UPDATE benchmark_attempts
        SET actual_runtime_id = ?, runtime_version = ?, status = ?, failure_code = ?,
            failure_message = ?, exit_code = ?, started_at = ?, ended_at = ?,
            elapsed_seconds = ?, input_tokens = ?, output_tokens = ?, total_tokens = ?,
            token_provenance = ?, token_source = ?, quality_score_100 = ?,
            objective_pass_rate = ?, rubric_score_100 = ?, verifier_summary_json = ?,
            env_fingerprint_json = ?, metadata_json = ?, updated_at = ?
        WHERE id = ?
        """,
        (
            payload.actual_runtime_id or attempt.actual_runtime_id or attempt.intended_runtime_id,
            payload.runtime_version or attempt.runtime_version,
            payload.status.value,
            payload.failure.code if payload.failure else attempt.failure_code,
            payload.failure.message if payload.failure else attempt.failure_message,
            payload.exit_code,
            started_at,
            ended_at,
            payload.elapsed_seconds,
            payload.input_tokens,
            payload.output_tokens,
            payload.total_tokens,
            payload.token_provenance.value,
            payload.token_source.value,
            payload.quality_score_100,
            payload.objective_pass_rate,
            payload.rubric_score_100,
            _dumps(payload.verifier_summary),
            _dumps((payload.env_fingerprint or attempt.env_fingerprint).model_dump(mode="json")),
            _dumps({**attempt.metadata, **payload.metadata}),
            now,
            payload.attempt_id,
        ),
    )
    for artifact in payload.artifacts:
        add_artifact(
            conn,
            payload.attempt_id,
            kind=str(artifact.get("kind", "artifact")),
            path=str(artifact.get("path", "")),
            label=str(artifact.get("label", "")),
            mime=str(artifact.get("mime", "application/octet-stream")),
            metadata=dict(artifact.get("metadata", {})) if isinstance(artifact.get("metadata"), dict) else {},
        )
    return recompute_attempt_metrics(conn, payload.attempt_id)


def add_artifact(
    conn: sqlite3.Connection,
    attempt_id: str,
    *,
    kind: str,
    path: str,
    label: str = "",
    mime: str = "application/octet-stream",
    metadata: dict[str, Any] | None = None,
) -> BenchmarkArtifact:
    attempt = get_attempt(conn, attempt_id)
    if not path:
        raise invalid("benchmark_artifact", "path is required.")
    artifact_id = _new_id()
    now = to_iso(utc_now())
    conn.execute(
        """
        INSERT INTO benchmark_artifacts (
            id, attempt_id, kind, label, path, mime, metadata_json, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (artifact_id, attempt.id, kind, label, path, mime, _dumps(metadata or {}), now),
    )
    row = conn.execute("SELECT * FROM benchmark_artifacts WHERE id = ?", (artifact_id,)).fetchone()
    assert row is not None
    return _row_to_artifact(row)


def _attempt_confidence(attempts: list[BenchmarkAttempt]) -> tuple[BenchmarkConfidenceLabel, bool]:
    if len(attempts) < 3:
        return BenchmarkConfidenceLabel.SINGLE_SAMPLE, True
    elapsed_cv = _coefficient_variation([attempt.elapsed_seconds for attempt in attempts])
    token_cv = _coefficient_variation([attempt.total_tokens for attempt in attempts])
    qualities = [attempt.quality_score_100 for attempt in attempts if attempt.quality_score_100 is not None]
    quality_spread = (max(qualities) - min(qualities)) if len(qualities) >= 2 else 0.0
    noisy = False
    if elapsed_cv is not None and elapsed_cv > 0.15:
        noisy = True
    if token_cv is not None and token_cv > 0.20:
        noisy = True
    if quality_spread > 4.0:
        noisy = True
    return (BenchmarkConfidenceLabel.DIRECTIONAL if noisy else BenchmarkConfidenceLabel.STABLE), noisy


def _candidate_summary(spec: BenchmarkSpec, candidate_key: str, attempts: list[BenchmarkAttempt]) -> BenchmarkCandidateSummary:
    sample = attempts[0]
    confidence, noisy = _attempt_confidence(attempts)
    comparable = [attempt for attempt in attempts if attempt.token_provenance != BenchmarkTokenProvenance.UNKNOWN]
    median_quality = _median([attempt.quality_score_100 for attempt in attempts])
    median_elapsed = _median([attempt.elapsed_seconds for attempt in attempts])
    median_tokens = _median([attempt.total_tokens for attempt in comparable])
    median_qpt = _median([attempt.quality_per_1k_tokens for attempt in comparable])
    median_qpm = _median([attempt.quality_per_minute for attempt in attempts])
    pass_rate = 0.0
    statuses = [attempt.status for attempt in attempts]
    if statuses:
        pass_rate = sum(1 for item in statuses if item in {BenchmarkAttemptStatus.COMPLETED, BenchmarkAttemptStatus.INGESTED}) / len(statuses)
    composite = None
    if median_quality is not None and median_tokens is not None and median_elapsed is not None and median_tokens > 0 and median_elapsed > 0:
        eff = median_quality / (median_tokens / 1000.0)
        speed = median_quality / (median_elapsed / 60.0)
        composite = (
            (spec.official_weight_quality * median_quality)
            + (spec.official_weight_efficiency * eff)
            + (spec.official_weight_speed * speed)
        ) / 100.0
    return BenchmarkCandidateSummary(
        candidate_key=candidate_key,
        surface_kind=sample.surface_kind,
        intended_runtime_id=sample.intended_runtime_id,
        provider=sample.provider,
        model=sample.model,
        attempts_count=len(attempts),
        comparable_attempt_count=len(comparable),
        median_quality_score_100=median_quality,
        pass_rate=pass_rate,
        median_elapsed_seconds=median_elapsed,
        median_total_tokens=median_tokens,
        median_quality_per_1k_tokens=median_qpt,
        median_quality_per_minute=median_qpm,
        composite_score=composite,
        confidence_label=confidence,
        noisy=noisy,
    )


def _mark_efficiency_frontier(candidates: list[BenchmarkCandidateSummary]) -> list[BenchmarkCandidateSummary]:
    comparable = [candidate for candidate in candidates if candidate.median_total_tokens is not None and candidate.median_elapsed_seconds is not None and candidate.median_quality_score_100 is not None]
    for candidate in candidates:
        candidate.efficiency_frontier = False
    for candidate in comparable:
        dominated = False
        for other in comparable:
            if other.candidate_key == candidate.candidate_key:
                continue
            if (
                (other.median_quality_score_100 or -math.inf) >= (candidate.median_quality_score_100 or -math.inf)
                and (other.median_total_tokens or math.inf) <= (candidate.median_total_tokens or math.inf)
                and (other.median_elapsed_seconds or math.inf) <= (candidate.median_elapsed_seconds or math.inf)
                and (
                    (other.median_quality_score_100 or -math.inf) > (candidate.median_quality_score_100 or -math.inf)
                    or (other.median_total_tokens or math.inf) < (candidate.median_total_tokens or math.inf)
                    or (other.median_elapsed_seconds or math.inf) < (candidate.median_elapsed_seconds or math.inf)
                )
            ):
                dominated = True
                break
        candidate.efficiency_frontier = not dominated
    return candidates


def build_run_report(conn: sqlite3.Connection, run_id: str) -> BenchmarkRunReport:
    run = get_run(conn, run_id)
    spec = get_spec_bundle(conn, run.spec_id).spec
    attempts = list_attempts_for_run(conn, run_id)
    strict_ids = [attempt.id for attempt in attempts if attempt.token_provenance != BenchmarkTokenProvenance.UNKNOWN]
    grouped: dict[str, list[BenchmarkAttempt]] = {}
    for attempt in attempts:
        grouped.setdefault(attempt.candidate_group_key, []).append(attempt)
    candidates = [_candidate_summary(spec, key, items) for key, items in grouped.items()]
    candidates = _mark_efficiency_frontier(candidates)
    official = sorted(
        candidates,
        key=lambda item: (
            -(item.median_quality_score_100 or -1.0),
            -item.pass_rate,
            -(item.median_quality_per_1k_tokens or -1.0),
            item.median_elapsed_seconds or math.inf,
        ),
    )
    frontier = [item for item in candidates if item.efficiency_frontier]
    composite = sorted(
        [item for item in candidates if item.composite_score is not None],
        key=lambda item: -(item.composite_score or -1.0),
    )
    comparisons: list[BenchmarkComparison] = []
    scenario_groups: dict[tuple[str, str], list[BenchmarkAttempt]] = {}
    for attempt in attempts:
        scenario_groups.setdefault((attempt.scenario_id, attempt.intended_runtime_id), []).append(attempt)
    for (scenario_id, runtime_id), items in scenario_groups.items():
        winners = sorted(
            items,
            key=lambda item: (
                -(item.quality_score_100 or -1.0),
                -(item.objective_pass_rate or -1.0),
                item.elapsed_seconds or math.inf,
            ),
        )
        confidence, noisy = _attempt_confidence(items)
        winner = winners[0] if winners else None
        comparisons.append(
            BenchmarkComparison(
                scenario_id=scenario_id,
                runtime_id=runtime_id,
                winner_candidate_key=winner.candidate_group_key if winner else None,
                confidence_label=confidence,
                noisy=noisy,
                comparable_attempt_count=sum(
                    1 for item in items if item.token_provenance != BenchmarkTokenProvenance.UNKNOWN
                ),
                notes=(
                    "Exact token deltas are suppressed for this comparison."
                    if confidence != BenchmarkConfidenceLabel.STABLE
                    else ""
                ),
            )
        )
    failure_counts: dict[str, int] = {}
    winner_notes: list[str] = []
    for attempt in attempts:
        if attempt.failure_code:
            failure_counts[attempt.failure_code] = failure_counts.get(attempt.failure_code, 0) + 1
    if official:
        leader = official[0]
        winner_notes.append(
            f"{leader.candidate_key} led on median quality with confidence {leader.confidence_label.value}."
        )
        if leader.noisy:
            winner_notes.append("Winner is still noisy; avoid exact percentage claims.")
    lessons = {
        "failure_code_counts": failure_counts,
        "winner_notes": winner_notes,
        "strict_comparable_policy": spec.strict_comparable_policy,
    }
    return BenchmarkRunReport(
        run=run,
        official_quality_ranking=official,
        efficiency_frontier=frontier,
        composite_score=composite,
        strict_comparable_attempt_ids=strict_ids,
        comparisons=comparisons,
        all_attempts=attempts,
        lessons=lessons,
    )


def benchmark_dir(data_dir: Path, run_id: str) -> Path:
    return data_dir / "benchmarks" / run_id


@dataclass
class BenchmarkExportPaths:
    json_path: Path
    md_path: Path
    lessons_path: Path


def export_run_report(data_dir: Path, conn: sqlite3.Connection, run_id: str) -> BenchmarkExportPaths:
    report = build_run_report(conn, run_id)
    target = benchmark_dir(data_dir, run_id)
    target.mkdir(parents=True, exist_ok=True)
    json_path = target / "BENCHMARK.json"
    md_path = target / "BENCHMARK.md"
    lessons_path = target / "BENCHMARK_LESSONS.json"
    json_path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    lessons_path.write_text(json.dumps(report.lessons, indent=2), encoding="utf-8")
    lines = [
        f"# {report.run.title}",
        "",
        f"- Run id: `{report.run.id}`",
        f"- Spec: `{report.run.spec_id}`",
        f"- Status: `{report.run.status.value}`",
        "",
        "## Official quality ranking",
    ]
    for index, candidate in enumerate(report.official_quality_ranking, start=1):
        lines.append(
            f"{index}. `{candidate.candidate_key}`"
            f" | quality={candidate.median_quality_score_100}"
            f" | pass_rate={candidate.pass_rate:.2f}"
            f" | confidence={candidate.confidence_label.value}"
        )
    lines.extend(["", "## Strict comparable attempt ids"])
    lines.extend([f"- `{attempt_id}`" for attempt_id in report.strict_comparable_attempt_ids] or ["- none"])
    lines.extend(["", "## Comparison caveats"])
    for comparison in report.comparisons:
        lines.append(
            f"- `{comparison.scenario_id}` / `{comparison.runtime_id}`"
            f" -> {comparison.confidence_label.value}"
            f"{' (noisy)' if comparison.noisy else ''}"
            + (f" -- {comparison.notes}" if comparison.notes else "")
        )
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return BenchmarkExportPaths(json_path=json_path, md_path=md_path, lessons_path=lessons_path)
