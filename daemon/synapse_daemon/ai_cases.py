"""Durable models + bundle helpers for advanced AI Operating System cases."""

from __future__ import annotations

import json
import secrets
import sqlite3
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from .errors import invalid, not_found
from .projects import Project
from .time_utils import from_iso, to_iso, utc_now


class AiCaseMode(str, Enum):
    RESEARCH = "research"
    GENERATE = "generate"
    HYBRID = "hybrid"
    AUDIT = "audit"
    REPAIR = "repair"
    MIGRATE = "migrate"
    REPLICATE = "replicate"
    BENCHMARK = "benchmark"
    HARVEST = "harvest"
    PORTFOLIO = "portfolio"
    CHALLENGE = "challenge"


_LEGACY_MODE_ALIASES = {
    "repo-research": AiCaseMode.RESEARCH,
    "architecture-decision": AiCaseMode.RESEARCH,
}


class AiCaseStatus(str, Enum):
    DRAFT = "draft"
    RUNNING = "running"
    STOPPED = "stopped"
    COMPLETED = "completed"
    ERROR = "error"


class AiCasePhase(str, Enum):
    SETUP = "setup"
    ORIENT = "orient"
    RESEARCH = "research"
    GENERATE = "generate"
    COMPARE = "compare"
    REVIEW = "review"
    VERIFY = "verify"
    HANDOFF = "handoff"
    STOPPED = "stopped"
    ERROR = "error"


class AiCaseTargetRelation(str, Enum):
    PRIMARY = "primary"
    NEIGHBOR = "neighbor"
    REFERENCE = "reference"
    INTEGRATION = "integration"


class AiRiskTolerance(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class AiUrgency(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class AiAutonomyMode(str, Enum):
    FULL_AUTOPILOT = "full_autopilot"
    SUPERVISED = "supervised"
    MANUAL = "manual"


class AiGenerationMode(str, Enum):
    PROTOTYPE = "prototype"
    LOCAL_FULLSTACK = "local_fullstack"


class AiRecipeSelectionMode(str, Enum):
    MANUAL = "manual"
    AUTO_BEST_FIT = "auto_best_fit"
    COMPARE_TOP_N = "compare_top_n"


class AiWritePolicy(str, Enum):
    READ_ONLY = "read_only"
    PRIMARY_ONLY = "primary_only"
    CHILD_CASE_SEQUENCED = "child_case_sequenced"
    MULTI_TARGET = "multi_target"


class ClaimCardKind(str, Enum):
    REPO_BACKED = "repo-backed"
    TOOL_OBSERVED = "tool-observed"
    OFFICIAL_DOC = "official-doc"
    WEB = "web"
    INFERRED = "inferred"
    SPECULATIVE = "speculative"


class ContradictionStatus(str, Enum):
    OPEN = "open"
    RESOLVED = "resolved"


class AiJobStatus(str, Enum):
    QUEUED = "queued"
    STARTING = "starting"
    RUNNING = "running"
    REVIEWING = "reviewing"
    TESTING = "testing"
    COMPLETED = "completed"
    FAILED = "failed"
    STOPPED = "stopped"


class AiCaseIntent(BaseModel):
    goal_md: str = ""
    success_criteria_md: str = ""
    non_goals_md: str = ""
    constraints_md: str = ""
    definition_of_done_md: str = ""
    risk_tolerance: AiRiskTolerance = AiRiskTolerance.MEDIUM
    urgency: AiUrgency = AiUrgency.MEDIUM
    autonomy_mode: AiAutonomyMode = AiAutonomyMode.FULL_AUTOPILOT


class AiCaseTargets(BaseModel):
    primary_project_id: str = ""
    neighbor_project_ids: list[str] = Field(default_factory=list)
    reference_project_ids: list[str] = Field(default_factory=list)
    reference_urls: list[str] = Field(default_factory=list)
    attached_source_ids: list[str] = Field(default_factory=list)
    target_project_spec: dict[str, Any] = Field(default_factory=dict)
    integration_target_ids: list[str] = Field(default_factory=list)


class AiComponentOverride(BaseModel):
    component_id: str | None = None
    family: str | None = None
    notes_md: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class AiCaseDirectives(BaseModel):
    selected_recipe_id: str | None = None
    candidate_recipe_ids: list[str] = Field(default_factory=list)
    component_overrides: list[AiComponentOverride] = Field(default_factory=list)
    recipe_selection_mode: AiRecipeSelectionMode = AiRecipeSelectionMode.MANUAL
    generation_mode: AiGenerationMode = AiGenerationMode.PROTOTYPE
    brand_profile_id: str | None = None
    tech_profile_id: str | None = None
    data_profile_id: str | None = None
    test_profile_id: str | None = None
    deployment_profile_id: str | None = None
    output_profile_id: str | None = None


class AiCasePolicies(BaseModel):
    quality_profile_id: str | None = "quality-default"
    similarity_policy_id: str | None = "similarity-advisory"
    evidence_policy_id: str | None = "evidence-repo-first"
    provenance_policy_id: str | None = "provenance-aware"
    write_policy_id: str | None = AiWritePolicy.PRIMARY_ONLY.value
    runtime_mix_policy_id: str | None = "runtime-mix-optional"
    budget_policy_id: str | None = "budget-balanced"
    parallelism_policy_id: str | None = "parallelism-moderate"
    review_policy_id: str | None = "review-required"
    project_policy_id: str | None = None
    ux_policy_id: str | None = None


class AiCaseTarget(BaseModel):
    case_id: str
    project_id: str
    relation: AiCaseTargetRelation
    created_at: datetime = Field(default_factory=utc_now)


class AiCase(BaseModel):
    id: str
    title: str = ""
    primary_project_id: str
    case_mode: AiCaseMode = AiCaseMode.RESEARCH
    mission_profile_id: str | None = None
    intent: AiCaseIntent = Field(default_factory=AiCaseIntent)
    targets: AiCaseTargets = Field(default_factory=AiCaseTargets)
    directives: AiCaseDirectives = Field(default_factory=AiCaseDirectives)
    policies: AiCasePolicies = Field(default_factory=AiCasePolicies)
    parent_case_id: str | None = None
    root_case_id: str | None = None
    comparison_set_id: str | None = None
    candidate_label: str | None = None
    spawn_reason: str | None = None
    winning_child_case_id: str | None = None
    status: AiCaseStatus = AiCaseStatus.DRAFT
    phase: AiCasePhase = AiCasePhase.SETUP
    squad_id: str | None = None
    lead_work_item_id: str | None = None
    lead_session_id: str | None = None
    branch_name: str | None = None
    worktree_path: str | None = None
    bundle_path: str
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    stopped_at: datetime | None = None
    last_error_code: str | None = None
    last_error_message: str | None = None


class AiCaseCreate(BaseModel):
    case_mode: AiCaseMode | str = AiCaseMode.RESEARCH
    mission_profile_id: str | None = None
    intent: AiCaseIntent = Field(default_factory=AiCaseIntent)
    targets: AiCaseTargets = Field(default_factory=AiCaseTargets)
    directives: AiCaseDirectives = Field(default_factory=AiCaseDirectives)
    policies: AiCasePolicies = Field(default_factory=AiCasePolicies)
    parent_case_id: str | None = None
    root_case_id: str | None = None
    comparison_set_id: str | None = None
    candidate_label: str | None = None
    spawn_reason: str | None = None
    winning_child_case_id: str | None = None
    title: str = ""
    # Legacy flat fields kept for compatibility with earlier AI OS work.
    primary_project_id: str | None = None
    neighbor_project_ids: list[str] = Field(default_factory=list)
    goal_md: str = ""
    selected_recipe_id: str | None = None
    quality_profile_id: str | None = None
    review_policy_id: str | None = None
    project_policy_id: str | None = None
    ux_policy_id: str | None = None

    @model_validator(mode="after")
    def _normalize(self) -> "AiCaseCreate":
        self.case_mode = normalize_case_mode(self.case_mode)
        if self.primary_project_id and not self.targets.primary_project_id:
            self.targets.primary_project_id = self.primary_project_id
        if self.neighbor_project_ids:
            merged = [*self.targets.neighbor_project_ids, *self.neighbor_project_ids]
            self.targets.neighbor_project_ids = list(dict.fromkeys(pid for pid in merged if pid))
        if self.goal_md and not self.intent.goal_md:
            self.intent.goal_md = self.goal_md
        if self.selected_recipe_id and not self.directives.selected_recipe_id:
            self.directives.selected_recipe_id = self.selected_recipe_id
        if self.quality_profile_id and not self.policies.quality_profile_id:
            self.policies.quality_profile_id = self.quality_profile_id
        if self.review_policy_id and not self.policies.review_policy_id:
            self.policies.review_policy_id = self.review_policy_id
        if self.project_policy_id and not self.policies.project_policy_id:
            self.policies.project_policy_id = self.project_policy_id
        if self.ux_policy_id and not self.policies.ux_policy_id:
            self.policies.ux_policy_id = self.ux_policy_id
        if not self.mission_profile_id:
            self.mission_profile_id = default_mission_profile_id(self.case_mode)
        if not self.targets.primary_project_id:
            raise ValueError("targets.primary_project_id is required.")
        return self


class AiCaseSpawnRequest(BaseModel):
    case_mode: AiCaseMode | str | None = None
    mission_profile_id: str | None = None
    intent: AiCaseIntent | None = None
    targets: AiCaseTargets | None = None
    directives: AiCaseDirectives | None = None
    policies: AiCasePolicies | None = None
    candidate_label: str | None = None
    spawn_reason: str = ""
    comparison_set_id: str | None = None
    title: str | None = None

    @model_validator(mode="after")
    def _normalize(self) -> "AiCaseSpawnRequest":
        if self.case_mode is not None:
            self.case_mode = normalize_case_mode(self.case_mode)
        return self


class AiCaseRunRequest(BaseModel):
    preferred_runtime: str | None = None
    open_in_tab: bool = True


class ClaimCard(BaseModel):
    id: str
    title: str
    kind: ClaimCardKind
    summary: str = ""
    confidence: Literal["low", "medium", "high"] = "medium"
    project_id: str | None = None
    source_label: str | None = None
    source_ref: str | None = None
    evidence: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)


class ContradictionSide(BaseModel):
    label: str
    evidence: list[str] = Field(default_factory=list)


class ContradictionDocketItem(BaseModel):
    id: str
    question: str
    stakes: str = ""
    left: ContradictionSide
    right: ContradictionSide
    ruling: str | None = None
    status: ContradictionStatus = ContradictionStatus.OPEN
    created_at: datetime = Field(default_factory=utc_now)
    resolved_at: datetime | None = None


class MinorityReport(BaseModel):
    summary: str = ""
    strongest_losing_argument: str = ""
    watchpoints: list[str] = Field(default_factory=list)


class BlastRadius(BaseModel):
    touched_areas: list[str] = Field(default_factory=list)
    contracts: list[str] = Field(default_factory=list)
    tests: list[str] = Field(default_factory=list)
    likely_regressions: list[str] = Field(default_factory=list)


class Verdict(BaseModel):
    summary: str = ""
    chosen_direction: str = ""
    rationale: str = ""
    rejected_paths: list[str] = Field(default_factory=list)
    decided_at: datetime | None = None


class DecisionHandoffPack(BaseModel):
    first_steps: list[str] = Field(default_factory=list)
    tests: list[str] = Field(default_factory=list)
    rollback_notes: list[str] = Field(default_factory=list)
    unresolved_questions: list[str] = Field(default_factory=list)


class TimelineEntry(BaseModel):
    id: str
    phase: AiCasePhase
    label: str
    summary: str = ""
    at: datetime = Field(default_factory=utc_now)


class AiSimilarityDimension(BaseModel):
    key: str
    label: str
    score: float | None = None
    threshold: float | None = None
    notes: str = ""


class AiSimilarityReport(BaseModel):
    reference_basis: str = ""
    similarity_explanation_md: str = ""
    quality_explanation_md: str = ""
    dimensions: list[AiSimilarityDimension] = Field(default_factory=list)


class AiScorecardItem(BaseModel):
    key: str
    label: str
    status: Literal["pending", "pass", "warn", "fail"] = "pending"
    summary: str = ""


class AiScorecard(BaseModel):
    summary_md: str = ""
    prioritized_backlog: list[str] = Field(default_factory=list)
    items: list[AiScorecardItem] = Field(default_factory=list)


class AiLedgerEntry(BaseModel):
    id: str
    title: str
    summary: str = ""
    created_at: datetime = Field(default_factory=utc_now)


class AiCandidateResult(BaseModel):
    case_id: str | None = None
    candidate_label: str = ""
    summary: str = ""
    quality_score: float | None = None
    token_estimate: int | None = None
    elapsed_summary: str = ""
    winner: bool = False


class AiPromotionProposal(BaseModel):
    source_id: str | None = None
    asset_family: str
    suggested_id: str
    title: str
    rationale: str = ""


class AiFailureMatrixItem(BaseModel):
    risk: str
    consequence: str = ""
    mitigation: str = ""


class AiJobRun(BaseModel):
    id: str
    case_id: str
    phase: AiCasePhase
    label: str
    status: AiJobStatus
    worker_role_id: str | None = None
    runtime: str | None = None
    session_id: str | None = None
    cwd: str | None = None
    artifact_path: str | None = None
    transcript_file_id: str | None = None
    notes_md: str = ""
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    exit_code: int | None = None


class AiCaseGraphNode(BaseModel):
    id: str
    title: str
    case_mode: AiCaseMode
    status: AiCaseStatus
    phase: AiCasePhase
    mission_profile_id: str | None = None
    candidate_label: str | None = None
    primary_project_id: str


class AiCaseGraphEdge(BaseModel):
    parent_case_id: str
    child_case_id: str
    reason: str = ""


class AiCaseGraph(BaseModel):
    root_case_id: str
    nodes: list[AiCaseGraphNode] = Field(default_factory=list)
    edges: list[AiCaseGraphEdge] = Field(default_factory=list)
    winning_child_case_id: str | None = None


class AiCaseBundle(BaseModel):
    case_id: str
    title: str
    primary_project_id: str
    mission_profile_id: str | None = None
    case_mode: AiCaseMode
    intent: AiCaseIntent = Field(default_factory=AiCaseIntent)
    targets: AiCaseTargets = Field(default_factory=AiCaseTargets)
    directives: AiCaseDirectives = Field(default_factory=AiCaseDirectives)
    policies: AiCasePolicies = Field(default_factory=AiCasePolicies)
    constitution_md: str = ""
    claim_cards: list[ClaimCard] = Field(default_factory=list)
    contradiction_docket: list[ContradictionDocketItem] = Field(default_factory=list)
    minority_report: MinorityReport = Field(default_factory=MinorityReport)
    blast_radius: BlastRadius = Field(default_factory=BlastRadius)
    verdict: Verdict = Field(default_factory=Verdict)
    handoff_pack: DecisionHandoffPack = Field(default_factory=DecisionHandoffPack)
    timeline: list[TimelineEntry] = Field(default_factory=list)
    scorecard: AiScorecard = Field(default_factory=AiScorecard)
    similarity_report: AiSimilarityReport = Field(default_factory=AiSimilarityReport)
    migration_ledger: list[AiLedgerEntry] = Field(default_factory=list)
    stabilization_ledger: list[AiLedgerEntry] = Field(default_factory=list)
    failure_matrix: list[AiFailureMatrixItem] = Field(default_factory=list)
    candidate_leaderboard: list[AiCandidateResult] = Field(default_factory=list)
    promotions: list[AiPromotionProposal] = Field(default_factory=list)
    notes_md: str = ""
    updated_at: datetime = Field(default_factory=utc_now)

    @property
    def neighbor_project_ids(self) -> list[str]:
        return self.targets.neighbor_project_ids


class AiCaseBundleSummary(BaseModel):
    claim_count: int = 0
    contradiction_count: int = 0
    verdict_summary: str | None = None
    minority_summary: str | None = None
    active_job_count: int = 0


class AiCaseWorkerSummary(BaseModel):
    work_item_id: str
    title: str
    status: str
    assigned_role_id: str | None = None
    pty_session_id: str | None = None
    transcript_file_id: str | None = None


class AiCaseDetail(BaseModel):
    case: AiCase
    targets: list[AiCaseTarget]
    bundle_summary: AiCaseBundleSummary
    active_workers: list[AiCaseWorkerSummary] = Field(default_factory=list)
    jobs: list[AiJobRun] = Field(default_factory=list)
    graph: AiCaseGraph | None = None


class AiCaseAngleContract(BaseModel):
    key: str
    title: str
    assigned_role_id: str
    fallback_role_ids: list[str] = Field(default_factory=list)
    preferred_personality_id: str | None = None
    fallback_personality_ids: list[str] = Field(default_factory=list)
    instructions_md: str


class AiMissionProfile(BaseModel):
    id: str
    title: str
    summary: str
    case_mode: AiCaseMode
    recommended_generation_mode: AiGenerationMode | None = None
    recommended_recipe_selection_mode: AiRecipeSelectionMode = AiRecipeSelectionMode.MANUAL
    tags: list[str] = Field(default_factory=list)


def _new_id() -> str:
    return secrets.token_hex(6)


def normalize_case_mode(value: AiCaseMode | str) -> AiCaseMode:
    if isinstance(value, AiCaseMode):
        return value
    if value in _LEGACY_MODE_ALIASES:
        return _LEGACY_MODE_ALIASES[value]
    try:
        return AiCaseMode(value)
    except ValueError as exc:
        raise invalid("ai_case", f"Unknown case_mode '{value}'.") from exc


def default_mission_profile_id(case_mode: AiCaseMode) -> str:
    defaults = {
        AiCaseMode.RESEARCH: "repo-decision",
        AiCaseMode.GENERATE: "new-app-from-brief",
        AiCaseMode.HYBRID: "product-architecture",
        AiCaseMode.AUDIT: "ux-hardening-pass",
        AiCaseMode.REPAIR: "broken-repo-rescue",
        AiCaseMode.MIGRATE: "stack-upgrade",
        AiCaseMode.REPLICATE: "inspired-clone",
        AiCaseMode.BENCHMARK: "multi-candidate-bakeoff",
        AiCaseMode.HARVEST: "recipe-library-intake",
        AiCaseMode.PORTFOLIO: "portfolio-sweep",
        AiCaseMode.CHALLENGE: "challenge-pass",
    }
    return defaults[case_mode]


def mission_profiles() -> list[AiMissionProfile]:
    return [
        AiMissionProfile(id="repo-decision", title="Repo decision", summary="Research an existing repo, preserve dissent, and ship a verdict + handoff.", case_mode=AiCaseMode.RESEARCH, tags=["research", "repo"]),
        AiMissionProfile(id="product-architecture", title="Product architecture", summary="Research first, then implement the chosen architecture direction.", case_mode=AiCaseMode.HYBRID, recommended_generation_mode=AiGenerationMode.LOCAL_FULLSTACK, tags=["hybrid", "architecture"]),
        AiMissionProfile(id="new-app-from-brief", title="New app from brief", summary="Turn a short brief into a generated app with review/test gates.", case_mode=AiCaseMode.GENERATE, recommended_generation_mode=AiGenerationMode.PROTOTYPE, tags=["generate", "app"]),
        AiMissionProfile(id="inspired-clone", title="Inspired clone", summary="Replicate a reference experience while tracking similarity and provenance.", case_mode=AiCaseMode.REPLICATE, recommended_generation_mode=AiGenerationMode.LOCAL_FULLSTACK, tags=["replicate", "similarity"]),
        AiMissionProfile(id="broken-repo-rescue", title="Broken repo rescue", summary="Stabilize a broken or low-quality repo and produce a regression summary.", case_mode=AiCaseMode.REPAIR, tags=["repair", "stability"]),
        AiMissionProfile(id="stack-upgrade", title="Stack upgrade", summary="Migrate a codebase with an explicit ledger, rollback notes, and blast radius.", case_mode=AiCaseMode.MIGRATE, tags=["migrate", "upgrade"]),
        AiMissionProfile(id="multi-candidate-bakeoff", title="Multi-candidate bakeoff", summary="Spawn several candidate cases, compare them, and pick a winner.", case_mode=AiCaseMode.BENCHMARK, recommended_recipe_selection_mode=AiRecipeSelectionMode.COMPARE_TOP_N, tags=["benchmark", "parallel"]),
        AiMissionProfile(id="recipe-library-intake", title="Recipe library intake", summary="Harvest patterns, assets metadata, and source packs into the AI Factory.", case_mode=AiCaseMode.HARVEST, tags=["harvest", "library"]),
        AiMissionProfile(id="ux-hardening-pass", title="UX hardening pass", summary="Audit UX, information architecture, and testing depth on a live app or repo.", case_mode=AiCaseMode.AUDIT, tags=["audit", "ux"]),
        AiMissionProfile(id="fullstack-crud-generator", title="Fullstack CRUD generator", summary="Generate a locally runnable CRUD app with backend, data, and testing gates.", case_mode=AiCaseMode.GENERATE, recommended_generation_mode=AiGenerationMode.LOCAL_FULLSTACK, tags=["generate", "fullstack"]),
        AiMissionProfile(id="portfolio-sweep", title="Portfolio sweep", summary="Map several repos together and spawn sequenced child cases for focused execution.", case_mode=AiCaseMode.PORTFOLIO, tags=["portfolio", "multi_repo"]),
        AiMissionProfile(id="challenge-pass", title="Challenge pass", summary="Red-team an idea, app, ADR, or PR with structured dissent and a failure matrix.", case_mode=AiCaseMode.CHALLENGE, tags=["challenge", "red_team"]),
    ]


def mission_profile_by_id(profile_id: str | None) -> AiMissionProfile | None:
    if not profile_id:
        return None
    return next((profile for profile in mission_profiles() if profile.id == profile_id), None)


def cases_root(data_dir: Path) -> Path:
    return data_dir / "ai-cases"


def case_dir(data_dir: Path, case_id: str) -> Path:
    return cases_root(data_dir) / case_id


def bundle_file_path(data_dir: Path, case_id: str) -> Path:
    return case_dir(data_dir, case_id) / "bundle.json"


def lead_prompt_path(data_dir: Path, case_id: str) -> Path:
    return case_dir(data_dir, case_id) / "LEAD_PROMPT.md"


def draft_pr_path(data_dir: Path, case_id: str) -> Path:
    return case_dir(data_dir, case_id) / "DRAFT_PR.md"


def export_file_path(data_dir: Path, case_id: str, name: str) -> Path:
    return case_dir(data_dir, case_id) / name


def _loads_json(payload: str | None, default: dict[str, Any]) -> dict[str, Any]:
    if not payload:
        return default.copy()
    data = json.loads(payload)
    return data if isinstance(data, dict) else default.copy()


def _row_to_case(row: sqlite3.Row) -> AiCase:
    mode = normalize_case_mode(row["case_mode"])
    intent = AiCaseIntent.model_validate(_loads_json(row["intent_json"], {}))
    targets = AiCaseTargets.model_validate(_loads_json(row["targets_json"], {}))
    directives = AiCaseDirectives.model_validate(_loads_json(row["directives_json"], {}))
    policies = AiCasePolicies.model_validate(_loads_json(row["policies_json"], {}))
    return AiCase(
        id=row["id"],
        title=row["title"] or "",
        primary_project_id=row["primary_project_id"],
        case_mode=mode,
        mission_profile_id=row["mission_profile_id"],
        intent=intent,
        targets=targets,
        directives=directives,
        policies=policies,
        parent_case_id=row["parent_case_id"],
        root_case_id=row["root_case_id"],
        comparison_set_id=row["comparison_set_id"],
        candidate_label=row["candidate_label"],
        spawn_reason=row["spawn_reason"],
        winning_child_case_id=row["winning_child_case_id"],
        status=AiCaseStatus(row["status"]),
        phase=AiCasePhase(row["phase"]),
        squad_id=row["squad_id"],
        lead_work_item_id=row["lead_work_item_id"],
        lead_session_id=row["lead_session_id"],
        branch_name=row["branch_name"],
        worktree_path=row["worktree_path"],
        bundle_path=row["bundle_path"],
        created_at=from_iso(row["created_at"]),
        updated_at=from_iso(row["updated_at"]),
        started_at=from_iso(row["started_at"]) if row["started_at"] else None,
        completed_at=from_iso(row["completed_at"]) if row["completed_at"] else None,
        stopped_at=from_iso(row["stopped_at"]) if row["stopped_at"] else None,
        last_error_code=row["last_error_code"],
        last_error_message=row["last_error_message"],
    )


def _row_to_target(row: sqlite3.Row) -> AiCaseTarget:
    return AiCaseTarget(
        case_id=row["case_id"],
        project_id=row["project_id"],
        relation=AiCaseTargetRelation(row["relation"]),
        created_at=from_iso(row["created_at"]),
    )


def _row_to_job(row: sqlite3.Row) -> AiJobRun:
    return AiJobRun(
        id=row["id"],
        case_id=row["case_id"],
        phase=AiCasePhase(row["phase"]),
        label=row["label"],
        status=AiJobStatus(row["status"]),
        worker_role_id=row["worker_role_id"],
        runtime=row["runtime"],
        session_id=row["session_id"],
        cwd=row["cwd"],
        artifact_path=row["artifact_path"],
        transcript_file_id=row["transcript_file_id"],
        notes_md=row["notes_md"] or "",
        created_at=from_iso(row["created_at"]),
        updated_at=from_iso(row["updated_at"]),
        started_at=from_iso(row["started_at"]) if row["started_at"] else None,
        completed_at=from_iso(row["completed_at"]) if row["completed_at"] else None,
        exit_code=row["exit_code"],
    )


def list_cases(conn: sqlite3.Connection) -> list[AiCase]:
    rows = conn.execute(
        "SELECT * FROM ai_cases ORDER BY updated_at DESC, created_at DESC"
    ).fetchall()
    return [_row_to_case(row) for row in rows]


def get_case(conn: sqlite3.Connection, case_id: str) -> AiCase:
    row = conn.execute("SELECT * FROM ai_cases WHERE id = ?", (case_id,)).fetchone()
    if row is None:
        raise not_found("ai_case", case_id)
    return _row_to_case(row)


def list_targets(conn: sqlite3.Connection, case_id: str) -> list[AiCaseTarget]:
    rows = conn.execute(
        "SELECT * FROM ai_case_targets WHERE case_id = ? ORDER BY relation, created_at",
        (case_id,),
    ).fetchall()
    return [_row_to_target(row) for row in rows]


def create_case(
    conn: sqlite3.Connection,
    payload: AiCaseCreate,
    *,
    case_id: str | None = None,
    bundle_path: Path,
) -> AiCase:
    now = utc_now()
    case_id = case_id or _new_id()
    root_case_id = payload.root_case_id or case_id
    title = payload.title.strip() or payload.intent.goal_md.strip() or mission_profile_title(payload.mission_profile_id)
    conn.execute(
        """
        INSERT INTO ai_cases (
            id, title, primary_project_id, case_mode, mission_profile_id, intent_json, targets_json,
            directives_json, policies_json, parent_case_id, root_case_id, comparison_set_id,
            candidate_label, spawn_reason, winning_child_case_id, status, phase, squad_id,
            lead_work_item_id, lead_session_id, branch_name, worktree_path, bundle_path,
            created_at, updated_at, started_at, completed_at, stopped_at, last_error_code, last_error_message
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, NULL, NULL, NULL, ?, ?, ?, NULL, NULL, NULL, NULL, NULL)
        """,
        (
            case_id,
            title,
            payload.targets.primary_project_id,
            normalize_case_mode(payload.case_mode).value,
            payload.mission_profile_id,
            json.dumps(payload.intent.model_dump(mode="json")),
            json.dumps(payload.targets.model_dump(mode="json")),
            json.dumps(payload.directives.model_dump(mode="json")),
            json.dumps(payload.policies.model_dump(mode="json")),
            payload.parent_case_id,
            root_case_id,
            payload.comparison_set_id,
            payload.candidate_label,
            payload.spawn_reason,
            payload.winning_child_case_id,
            AiCaseStatus.DRAFT.value,
            AiCasePhase.SETUP.value,
            str(bundle_path),
            to_iso(now),
            to_iso(now),
        ),
    )
    _write_target_rows(conn, case_id, payload.targets, now)
    return get_case(conn, case_id)


def _write_target_rows(
    conn: sqlite3.Connection,
    case_id: str,
    targets: AiCaseTargets,
    now: datetime,
) -> None:
    rows: list[tuple[str, str, str, str]] = []
    if targets.primary_project_id:
        rows.append((case_id, targets.primary_project_id, AiCaseTargetRelation.PRIMARY.value, to_iso(now)))
    for project_id in dict.fromkeys(targets.neighbor_project_ids):
        if project_id and project_id != targets.primary_project_id:
            rows.append((case_id, project_id, AiCaseTargetRelation.NEIGHBOR.value, to_iso(now)))
    for project_id in dict.fromkeys(targets.reference_project_ids):
        if project_id and project_id != targets.primary_project_id:
            rows.append((case_id, project_id, AiCaseTargetRelation.REFERENCE.value, to_iso(now)))
    for project_id in dict.fromkeys(targets.integration_target_ids):
        if project_id and project_id != targets.primary_project_id:
            rows.append((case_id, project_id, AiCaseTargetRelation.INTEGRATION.value, to_iso(now)))
    if rows:
        conn.executemany(
            "INSERT OR REPLACE INTO ai_case_targets (case_id, project_id, relation, created_at) VALUES (?, ?, ?, ?)",
            rows,
        )


def update_case(
    conn: sqlite3.Connection,
    case_id: str,
    *,
    title: str | None = None,
    mission_profile_id: str | None = None,
    intent: AiCaseIntent | None = None,
    targets: AiCaseTargets | None = None,
    directives: AiCaseDirectives | None = None,
    policies: AiCasePolicies | None = None,
    status: AiCaseStatus | None = None,
    phase: AiCasePhase | None = None,
    squad_id: str | None = None,
    lead_work_item_id: str | None = None,
    lead_session_id: str | None = None,
    branch_name: str | None = None,
    worktree_path: str | None = None,
    started_at: datetime | None = None,
    completed_at: datetime | None = None,
    stopped_at: datetime | None = None,
    last_error_code: str | None = None,
    last_error_message: str | None = None,
    winning_child_case_id: str | None = None,
) -> AiCase:
    current = get_case(conn, case_id)
    data = current.model_dump()
    if title is not None:
        data["title"] = title
    if mission_profile_id is not None:
        data["mission_profile_id"] = mission_profile_id
    if intent is not None:
        data["intent"] = intent
    if targets is not None:
        data["targets"] = targets
    if directives is not None:
        data["directives"] = directives
    if policies is not None:
        data["policies"] = policies
    if status is not None:
        data["status"] = status
    if phase is not None:
        data["phase"] = phase
    if squad_id is not None:
        data["squad_id"] = squad_id
    if lead_work_item_id is not None:
        data["lead_work_item_id"] = lead_work_item_id
    if lead_session_id is not None:
        data["lead_session_id"] = lead_session_id
    if branch_name is not None:
        data["branch_name"] = branch_name
    if worktree_path is not None:
        data["worktree_path"] = worktree_path
    if started_at is not None:
        data["started_at"] = started_at
    if completed_at is not None:
        data["completed_at"] = completed_at
    if stopped_at is not None:
        data["stopped_at"] = stopped_at
    data["last_error_code"] = last_error_code
    data["last_error_message"] = last_error_message
    if winning_child_case_id is not None:
        data["winning_child_case_id"] = winning_child_case_id
    data["updated_at"] = utc_now()
    updated = AiCase.model_validate(data)
    conn.execute(
        """
        UPDATE ai_cases
        SET title = ?, mission_profile_id = ?, intent_json = ?, targets_json = ?, directives_json = ?,
            policies_json = ?, status = ?, phase = ?, squad_id = ?, lead_work_item_id = ?,
            lead_session_id = ?, branch_name = ?, worktree_path = ?, updated_at = ?, started_at = ?,
            completed_at = ?, stopped_at = ?, last_error_code = ?, last_error_message = ?,
            winning_child_case_id = ?
        WHERE id = ?
        """,
        (
            updated.title,
            updated.mission_profile_id,
            json.dumps(updated.intent.model_dump(mode="json")),
            json.dumps(updated.targets.model_dump(mode="json")),
            json.dumps(updated.directives.model_dump(mode="json")),
            json.dumps(updated.policies.model_dump(mode="json")),
            updated.status.value,
            updated.phase.value,
            updated.squad_id,
            updated.lead_work_item_id,
            updated.lead_session_id,
            updated.branch_name,
            updated.worktree_path,
            to_iso(updated.updated_at),
            to_iso(updated.started_at) if updated.started_at else None,
            to_iso(updated.completed_at) if updated.completed_at else None,
            to_iso(updated.stopped_at) if updated.stopped_at else None,
            updated.last_error_code,
            updated.last_error_message,
            updated.winning_child_case_id,
            case_id,
        ),
    )
    if targets is not None:
        conn.execute("DELETE FROM ai_case_targets WHERE case_id = ?", (case_id,))
        _write_target_rows(conn, case_id, targets, updated.updated_at)
    return get_case(conn, case_id)


def spawn_child_case(
    conn: sqlite3.Connection,
    parent: AiCase,
    payload: AiCaseSpawnRequest,
    *,
    case_id: str | None = None,
    bundle_path: Path,
) -> AiCase:
    create_payload = AiCaseCreate(
        case_mode=payload.case_mode or parent.case_mode,
        mission_profile_id=payload.mission_profile_id or parent.mission_profile_id,
        intent=payload.intent or parent.intent.model_copy(deep=True),
        targets=payload.targets or parent.targets.model_copy(deep=True),
        directives=payload.directives or parent.directives.model_copy(deep=True),
        policies=payload.policies or parent.policies.model_copy(deep=True),
        parent_case_id=parent.id,
        root_case_id=parent.root_case_id or parent.id,
        comparison_set_id=payload.comparison_set_id or parent.comparison_set_id or _new_id(),
        candidate_label=payload.candidate_label,
        spawn_reason=payload.spawn_reason or f"Spawned from case {parent.id}",
        title=(payload.title or "").strip(),
    )
    return create_case(conn, create_payload, case_id=case_id, bundle_path=bundle_path)


def list_jobs(conn: sqlite3.Connection, case_id: str) -> list[AiJobRun]:
    rows = conn.execute(
        "SELECT * FROM ai_case_jobs WHERE case_id = ? ORDER BY created_at, id",
        (case_id,),
    ).fetchall()
    return [_row_to_job(row) for row in rows]


def create_job(
    conn: sqlite3.Connection,
    *,
    case_id: str,
    phase: AiCasePhase,
    label: str,
    status: AiJobStatus,
    worker_role_id: str | None = None,
    runtime: str | None = None,
    session_id: str | None = None,
    cwd: str | None = None,
    artifact_path: str | None = None,
    notes_md: str = "",
) -> AiJobRun:
    now = utc_now()
    job_id = _new_id()
    conn.execute(
        """
        INSERT INTO ai_case_jobs (
            id, case_id, phase, label, status, worker_role_id, runtime, session_id,
            cwd, artifact_path, transcript_file_id, notes_md, created_at, updated_at,
            started_at, completed_at, exit_code
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?, ?, ?, NULL, NULL)
        """,
        (
            job_id,
            case_id,
            phase.value,
            label,
            status.value,
            worker_role_id,
            runtime,
            session_id,
            cwd,
            artifact_path,
            notes_md,
            to_iso(now),
            to_iso(now),
            to_iso(now) if status in {AiJobStatus.STARTING, AiJobStatus.RUNNING, AiJobStatus.REVIEWING, AiJobStatus.TESTING} else None,
        ),
    )
    row = conn.execute("SELECT * FROM ai_case_jobs WHERE id = ?", (job_id,)).fetchone()
    assert row is not None
    return _row_to_job(row)


def update_job(
    conn: sqlite3.Connection,
    job_id: str,
    *,
    status: AiJobStatus | None = None,
    runtime: str | None = None,
    session_id: str | None = None,
    transcript_file_id: str | None = None,
    notes_md: str | None = None,
    completed_at: datetime | None = None,
    exit_code: int | None = None,
) -> AiJobRun:
    row = conn.execute("SELECT * FROM ai_case_jobs WHERE id = ?", (job_id,)).fetchone()
    if row is None:
        raise not_found("ai_case_job", job_id)
    current = _row_to_job(row)
    data = current.model_dump()
    if status is not None:
        data["status"] = status
    if runtime is not None:
        data["runtime"] = runtime
    if session_id is not None:
        data["session_id"] = session_id
    if transcript_file_id is not None:
        data["transcript_file_id"] = transcript_file_id
    if notes_md is not None:
        data["notes_md"] = notes_md
    if completed_at is not None:
        data["completed_at"] = completed_at
    data["exit_code"] = exit_code
    data["updated_at"] = utc_now()
    updated = AiJobRun.model_validate(data)
    conn.execute(
        """
        UPDATE ai_case_jobs
        SET status = ?, runtime = ?, session_id = ?, transcript_file_id = ?, notes_md = ?,
            updated_at = ?, completed_at = ?, exit_code = ?
        WHERE id = ?
        """,
        (
            updated.status.value,
            updated.runtime,
            updated.session_id,
            updated.transcript_file_id,
            updated.notes_md,
            to_iso(updated.updated_at),
            to_iso(updated.completed_at) if updated.completed_at else None,
            updated.exit_code,
            job_id,
        ),
    )
    row = conn.execute("SELECT * FROM ai_case_jobs WHERE id = ?", (job_id,)).fetchone()
    assert row is not None
    return _row_to_job(row)


def update_job_for_session_finalization(
    conn: sqlite3.Connection,
    *,
    session_id: str,
    exit_code: int | None,
    transcript_file_id: str | None = None,
) -> AiJobRun | None:
    row = conn.execute(
        "SELECT * FROM ai_case_jobs WHERE session_id = ? ORDER BY created_at DESC LIMIT 1",
        (session_id,),
    ).fetchone()
    if row is None:
        return None
    status = AiJobStatus.COMPLETED if exit_code in (0, None) else AiJobStatus.FAILED
    return update_job(
        conn,
        row["id"],
        status=status,
        transcript_file_id=transcript_file_id,
        completed_at=utc_now(),
        exit_code=exit_code,
    )


def case_graph(conn: sqlite3.Connection, case_id: str) -> AiCaseGraph:
    case = get_case(conn, case_id)
    root_case_id = case.root_case_id or case.id
    rows = conn.execute(
        "SELECT * FROM ai_cases WHERE root_case_id = ? OR id = ? ORDER BY created_at, id",
        (root_case_id, root_case_id),
    ).fetchall()
    seen: set[str] = set()
    nodes: list[AiCaseGraphNode] = []
    edges: list[AiCaseGraphEdge] = []
    winning_child_case_id = None
    for row in rows:
        item = _row_to_case(row)
        if item.id in seen:
            continue
        seen.add(item.id)
        nodes.append(
            AiCaseGraphNode(
                id=item.id,
                title=item.title or item.intent.goal_md or "AI case",
                case_mode=item.case_mode,
                status=item.status,
                phase=item.phase,
                mission_profile_id=item.mission_profile_id,
                candidate_label=item.candidate_label,
                primary_project_id=item.primary_project_id,
            )
        )
        if item.parent_case_id:
            edges.append(
                AiCaseGraphEdge(
                    parent_case_id=item.parent_case_id,
                    child_case_id=item.id,
                    reason=item.spawn_reason or "",
                )
            )
        if item.winning_child_case_id:
            winning_child_case_id = item.winning_child_case_id
    return AiCaseGraph(
        root_case_id=root_case_id,
        nodes=nodes,
        edges=edges,
        winning_child_case_id=winning_child_case_id,
    )


def load_bundle(data_dir: Path, case_id: str) -> AiCaseBundle:
    path = bundle_file_path(data_dir, case_id)
    raw = json.loads(path.read_text(encoding="utf-8"))
    return AiCaseBundle.model_validate(raw)


def write_bundle(data_dir: Path, bundle: AiCaseBundle) -> Path:
    path = bundle_file_path(data_dir, bundle.case_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = bundle.model_copy(update={"updated_at": utc_now()})
    path.write_text(
        json.dumps(payload.model_dump(mode="json"), indent=2),
        encoding="utf-8",
    )
    return path


def ensure_bundle(
    data_dir: Path,
    case: AiCase,
    primary_project: Project,
    neighbor_projects: list[Project],
) -> AiCaseBundle:
    path = bundle_file_path(data_dir, case.id)
    if path.exists():
        return load_bundle(data_dir, case.id)
    bundle = default_bundle(case, primary_project, neighbor_projects)
    write_bundle(data_dir, bundle)
    return bundle


def mission_profile_title(profile_id: str | None) -> str:
    profile = mission_profile_by_id(profile_id)
    return profile.title if profile else "AI case"


def default_similarity_dimensions() -> list[AiSimilarityDimension]:
    keys = [
        ("stack_similarity", "Stack similarity"),
        ("language_runtime_similarity", "Language/runtime similarity"),
        ("architecture_similarity", "Architecture similarity"),
        ("layout_similarity", "Layout similarity"),
        ("navigation_similarity", "Navigation similarity"),
        ("interaction_similarity", "Interaction similarity"),
        ("visual_similarity", "Visual similarity"),
        ("data_model_similarity", "Data-model similarity"),
        ("backend_behavior_similarity", "Backend behavior similarity"),
        ("ux_quality_score", "UX quality score"),
        ("backend_readiness_score", "Backend readiness score"),
        ("testing_depth_score", "Testing depth score"),
    ]
    return [AiSimilarityDimension(key=key, label=label) for key, label in keys]


def default_scorecard(mode: AiCaseMode) -> AiScorecard:
    labels = [
        ("nav", "Navigation and movement"),
        ("ux", "User guidance and affordances"),
        ("review", "Reviewer pass"),
        ("tester", "Tester pass"),
    ]
    if mode in {AiCaseMode.GENERATE, AiCaseMode.HYBRID, AiCaseMode.REPAIR, AiCaseMode.MIGRATE, AiCaseMode.REPLICATE}:
        labels.extend(
            [
                ("backend", "Backend readiness"),
                ("mobile", "Mobile fit"),
            ]
        )
    return AiScorecard(items=[AiScorecardItem(key=key, label=label) for key, label in labels])


def default_bundle(
    case: AiCase,
    primary_project: Project,
    neighbor_projects: list[Project],
) -> AiCaseBundle:
    title = case.title or f"{primary_project.name} — {case.intent.goal_md.strip() or mission_profile_title(case.mission_profile_id)}"
    neighbor_lines = [
        f"- Neighbor ({project.id}) at `{project.path}`"
        for project in neighbor_projects
    ] or ["- No neighbor repos attached."]
    constitution_lines = [
        f"# AI Operating System Case · {title}",
        "",
        f"- Mission profile: `{case.mission_profile_id or default_mission_profile_id(case.case_mode)}`",
        f"- Case mode: `{case.case_mode.value}`",
        f"- Primary repo (write target): `{primary_project.id}` at `{primary_project.path}`",
        *neighbor_lines,
        "",
        "## Goal",
        case.intent.goal_md.strip() or "Reach a verdict, preserve dissent, and drive execution to handoff.",
        "",
        "## Success criteria",
        case.intent.success_criteria_md or "_Not captured yet._",
        "",
        "## Constraints",
        case.intent.constraints_md or "_No explicit constraints captured yet._",
        "",
        "## Operating rules",
        f"- Write policy: `{case.policies.write_policy_id or AiWritePolicy.PRIMARY_ONLY.value}`",
        "- Only one automatic write target is allowed per execution slice in v1.",
        "- Reviewer, tester, and judge passes are required for build-capable modes.",
        "- Repo-backed and tool-observed evidence outrank generic web opinion when conflicts arise.",
        "- Similarity is advisory by default; report it, do not silently block unless the policy says so.",
    ]
    bundle = AiCaseBundle(
        case_id=case.id,
        title=title,
        primary_project_id=primary_project.id,
        mission_profile_id=case.mission_profile_id,
        case_mode=case.case_mode,
        intent=case.intent,
        targets=case.targets,
        directives=case.directives,
        policies=case.policies,
        constitution_md="\n".join(constitution_lines),
        timeline=[
            TimelineEntry(
                id=f"{case.id}-created",
                phase=AiCasePhase.SETUP,
                label="Case created",
                summary="Structured case contract scaffolded and waiting to run.",
            )
        ],
        notes_md=(
            "Use this bundle as the long-lived case source of truth. Add evidence, contradiction "
            "items, mode-specific artifacts, verdicts, scorecards, similarity notes, and handoff detail here."
        ),
        scorecard=default_scorecard(case.case_mode),
        similarity_report=AiSimilarityReport(
            reference_basis=", ".join(case.targets.reference_urls) if case.targets.reference_urls else "",
            dimensions=default_similarity_dimensions(),
        ),
    )
    if case.case_mode == AiCaseMode.AUDIT:
        bundle.scorecard.summary_md = "Audit scorecard pending. Prioritize UX, architecture, performance, security, and testing observations."
    if case.case_mode == AiCaseMode.CHALLENGE:
        bundle.failure_matrix.append(
            AiFailureMatrixItem(
                risk="Hidden assumption still unchallenged",
                consequence="Weak minority report and false confidence",
                mitigation="Force explicit contradiction entries before verdict.",
            )
        )
    if case.case_mode == AiCaseMode.HARVEST:
        bundle.promotions.append(
            AiPromotionProposal(
                asset_family="recipe",
                suggested_id=f"harvest-{case.id}",
                title="Promote harvested pattern",
                rationale="Use when the council finds a reusable recipe or pack.",
            )
        )
    return bundle


def summarize_bundle(bundle: AiCaseBundle, *, active_job_count: int = 0) -> AiCaseBundleSummary:
    return AiCaseBundleSummary(
        claim_count=len(bundle.claim_cards),
        contradiction_count=len(bundle.contradiction_docket),
        verdict_summary=bundle.verdict.summary or None,
        minority_summary=bundle.minority_report.summary or None,
        active_job_count=active_job_count,
    )


def _phase_for_mode(mode: AiCaseMode) -> AiCasePhase:
    if mode in {AiCaseMode.RESEARCH, AiCaseMode.AUDIT, AiCaseMode.HARVEST, AiCaseMode.PORTFOLIO, AiCaseMode.CHALLENGE}:
        return AiCasePhase.RESEARCH
    if mode in {AiCaseMode.BENCHMARK}:
        return AiCasePhase.COMPARE
    return AiCasePhase.GENERATE


def angle_contracts(
    case: AiCase,
    primary_project: Project,
    neighbor_projects: list[Project],
    *,
    worktree_path: str | None,
    branch_name: str | None,
) -> list[AiCaseAngleContract]:
    neighbors = (
        "\n".join(f"- {project.id}: {project.path}" for project in neighbor_projects)
        if neighbor_projects
        else "- None attached for this run."
    )
    worktree_line = worktree_path or primary_project.path
    branch_line = branch_name or "(not allocated yet)"
    shared = "\n".join(
        [
            f"Primary project: {primary_project.id} ({primary_project.path})",
            f"Writable worktree: {worktree_line}",
            f"Case branch: {branch_line}",
            f"Case mode: {case.case_mode.value}",
            f"Mission profile: {case.mission_profile_id or default_mission_profile_id(case.case_mode)}",
            "Neighbors:",
            neighbors,
            "",
            f"Goal: {case.intent.goal_md or 'No goal captured yet.'}",
            f"Write policy: {case.policies.write_policy_id or AiWritePolicy.PRIMARY_ONLY.value}",
            "Important: you may read neighbor repos, but only the primary worktree is a write target in v1.",
        ]
    )
    contracts: list[AiCaseAngleContract] = [
        AiCaseAngleContract(
            key="judge",
            title="Judge / Boss",
            assigned_role_id="boss",
            preferred_personality_id="synthesist",
            fallback_personality_ids=["mediator"],
            instructions_md=(
                f"{shared}\n\nRun the case. Keep the timeline current, enforce contradiction capture, "
                "and do not mark the handoff complete until reviewer/tester/judge expectations are met."
            ),
        ),
    ]
    if case.case_mode in {AiCaseMode.RESEARCH, AiCaseMode.HYBRID, AiCaseMode.AUDIT, AiCaseMode.HARVEST, AiCaseMode.PORTFOLIO, AiCaseMode.CHALLENGE, AiCaseMode.BENCHMARK}:
        contracts.extend(
            [
                AiCaseAngleContract(
                    key="constraint-harvester",
                    title="Constraint Harvester",
                    assigned_role_id="researcher",
                    preferred_personality_id="archivist",
                    fallback_personality_ids=["perfectionist"],
                    instructions_md=f"{shared}\n\nList the hard constraints, non-goals, risks, and hidden assumptions.",
                ),
                AiCaseAngleContract(
                    key="repo-witness",
                    title="Repo Witness",
                    assigned_role_id="repo-witness",
                    fallback_role_ids=["researcher"],
                    preferred_personality_id="operator",
                    fallback_personality_ids=["pragmatist"],
                    instructions_md=f"{shared}\n\nInspect the repo(s) and surface patterns, seams, contracts, and current architecture realities.",
                ),
                AiCaseAngleContract(
                    key="docs-witness",
                    title="Docs Witness",
                    assigned_role_id="docs-witness",
                    fallback_role_ids=["docs-writer", "researcher"],
                    preferred_personality_id="archivist",
                    instructions_md=f"{shared}\n\nSummarize README guidance, ADRs, records, and documented contracts relevant to this case.",
                ),
                AiCaseAngleContract(
                    key="open-web-witness",
                    title="Open-Web Witness",
                    assigned_role_id="open-web-witness",
                    fallback_role_ids=["researcher"],
                    preferred_personality_id="scout",
                    fallback_personality_ids=["visionary"],
                    instructions_md=f"{shared}\n\nUse web evidence where helpful, but prefer official docs and clearly attributed sources.",
                ),
                AiCaseAngleContract(
                    key="blast-radius-cartographer",
                    title="Blast Radius Cartographer",
                    assigned_role_id="blast-radius-cartographer",
                    fallback_role_ids=["reviewer"],
                    preferred_personality_id="perfectionist",
                    instructions_md=f"{shared}\n\nMap touched areas, contracts, likely regressions, and the test surface.",
                ),
                AiCaseAngleContract(
                    key="skeptic",
                    title="Skeptic",
                    assigned_role_id="contract-prosecutor",
                    fallback_role_ids=["reviewer"],
                    preferred_personality_id="dissenter",
                    fallback_personality_ids=["skeptic"],
                    instructions_md=f"{shared}\n\nStress-test the majority view and preserve the strongest losing argument.",
                ),
            ]
        )
    if case.case_mode in {AiCaseMode.GENERATE, AiCaseMode.HYBRID, AiCaseMode.REPAIR, AiCaseMode.MIGRATE, AiCaseMode.REPLICATE, AiCaseMode.BENCHMARK}:
        contracts.extend(
            [
                AiCaseAngleContract(
                    key="recipe-composer",
                    title="Recipe Composer",
                    assigned_role_id="recipe-composer",
                    fallback_role_ids=["planner"],
                    preferred_personality_id="visionary",
                    instructions_md=f"{shared}\n\nChoose the best recipe/components or compare top candidates before implementation begins.",
                ),
                AiCaseAngleContract(
                    key="ux-steward",
                    title="UX Steward",
                    assigned_role_id="ux-steward",
                    fallback_role_ids=["designer"],
                    preferred_personality_id="visionary",
                    instructions_md=f"{shared}\n\nEnforce movement, navigation, density, and no unjustified long-scroll layouts.",
                ),
                AiCaseAngleContract(
                    key="implementer",
                    title="Implementer",
                    assigned_role_id="implementer",
                    preferred_personality_id="operator",
                    fallback_personality_ids=["pragmatist"],
                    instructions_md=f"{shared}\n\nExecute inside the writable worktree only. Record concrete file changes and verification.",
                ),
                AiCaseAngleContract(
                    key="tester",
                    title="Tester",
                    assigned_role_id="tester",
                    preferred_personality_id="perfectionist",
                    instructions_md=f"{shared}\n\nOwn the test pass, including browser checks when relevant. Report exact failures and residual risk.",
                ),
                AiCaseAngleContract(
                    key="reviewer",
                    title="Reviewer",
                    assigned_role_id="release-reviewer",
                    fallback_role_ids=["reviewer"],
                    preferred_personality_id="synthesist",
                    fallback_personality_ids=["mediator"],
                    instructions_md=f"{shared}\n\nReview implementation quality, blast radius, and coverage before handoff.",
                ),
            ]
        )
    if case.case_mode == AiCaseMode.REPAIR:
        contracts.append(
            AiCaseAngleContract(
                key="repair-foreman",
                title="Repair Foreman",
                assigned_role_id="repair-foreman",
                fallback_role_ids=["implementer", "planner"],
                preferred_personality_id="operator",
                fallback_personality_ids=["pragmatist"],
                instructions_md=f"{shared}\n\nSequence the rescue from fastest stabilization move to deeper cleanup, and keep the repo runnable throughout.",
            )
        )
    if case.case_mode == AiCaseMode.MIGRATE:
        contracts.append(
            AiCaseAngleContract(
                key="migration-steward",
                title="Migration Steward",
                assigned_role_id="migration-steward",
                fallback_role_ids=["planner", "reviewer"],
                preferred_personality_id="archivist",
                fallback_personality_ids=["mediator"],
                instructions_md=f"{shared}\n\nOwn the migration ledger, compatibility notes, rollout order, and rollback path.",
            )
        )
    if case.case_mode in {AiCaseMode.AUDIT, AiCaseMode.REPAIR, AiCaseMode.MIGRATE}:
        contracts.append(
            AiCaseAngleContract(
                key="regression-hunter",
                title="Regression Hunter",
                assigned_role_id="regression-hunter",
                fallback_role_ids=["tester", "reviewer"],
                preferred_personality_id="dissenter",
                fallback_personality_ids=["skeptic"],
                instructions_md=f"{shared}\n\nHunt for the most likely regressions or weak spots introduced by the proposed fix or migration.",
            )
        )
    if case.case_mode == AiCaseMode.HARVEST:
        contracts.append(
            AiCaseAngleContract(
                key="source-curator",
                title="Source Curator",
                assigned_role_id="source-curator",
                fallback_role_ids=["docs-writer", "researcher"],
                preferred_personality_id="archivist",
                instructions_md=f"{shared}\n\nTurn harvested evidence into source records, promotion ideas, and reusable factory assets.",
            )
        )
    if case.case_mode == AiCaseMode.PORTFOLIO:
        contracts.append(
            AiCaseAngleContract(
                key="portfolio-architect",
                title="Portfolio Architect",
                assigned_role_id="portfolio-architect",
                fallback_role_ids=["planner", "researcher"],
                preferred_personality_id="scout",
                fallback_personality_ids=["visionary"],
                instructions_md=f"{shared}\n\nMap cross-repo boundaries, sequence follow-up child cases, and keep the one-write-target rule explicit.",
            )
        )
    if case.case_mode == AiCaseMode.BENCHMARK:
        contracts.append(
            AiCaseAngleContract(
                key="benchmark-judge",
                title="Benchmark Judge",
                assigned_role_id="benchmark-judge",
                fallback_role_ids=["supervisor"],
                preferred_personality_id="synthesist",
                fallback_personality_ids=["mediator"],
                instructions_md=f"{shared}\n\nSpawn and compare candidate cases, maintain the leaderboard, and select the winner with rationale.",
            )
        )
    return contracts


def build_lead_prompt(
    case: AiCase,
    primary_project: Project,
    neighbor_projects: list[Project],
    *,
    worktree_path: str | None,
    branch_name: str | None,
    bundle_path: Path,
) -> str:
    contracts = angle_contracts(
        case,
        primary_project,
        neighbor_projects,
        worktree_path=worktree_path,
        branch_name=branch_name,
    )
    contract_lines = "\n".join(
        f"- {contract.title} -> role `{contract.assigned_role_id}`"
        for contract in contracts
    )
    reference_urls = "\n".join(f"- {url}" for url in case.targets.reference_urls) or "- none"
    return "\n".join(
        [
            "You are Synapse AI Operating System v1.2, running the advanced case engine.",
            "",
            f"Case id: {case.id}",
            f"Title: {case.title or mission_profile_title(case.mission_profile_id)}",
            f"Case mode: {case.case_mode.value}",
            f"Mission profile: {case.mission_profile_id or default_mission_profile_id(case.case_mode)}",
            f"Primary project: {primary_project.id} ({primary_project.path})",
            f"Writable worktree: {worktree_path or primary_project.path}",
            f"Case branch: {branch_name or '(not allocated yet)'}",
            f"Bundle path: {bundle_path}",
            "",
            "## Intent",
            case.intent.goal_md or "No goal captured yet.",
            "",
            "### Success criteria",
            case.intent.success_criteria_md or "_Not captured yet._",
            "",
            "### Non-goals",
            case.intent.non_goals_md or "_Not captured yet._",
            "",
            "### Constraints",
            case.intent.constraints_md or "_Not captured yet._",
            "",
            "### Definition of done",
            case.intent.definition_of_done_md or "_Not captured yet._",
            "",
            "## Targets",
            f"- Primary project id: {case.targets.primary_project_id}",
            f"- Neighbor ids: {', '.join(case.targets.neighbor_project_ids) or 'none'}",
            f"- Reference project ids: {', '.join(case.targets.reference_project_ids) or 'none'}",
            "### Reference URLs",
            reference_urls,
            "",
            "## Directives",
            f"- Selected recipe: {case.directives.selected_recipe_id or 'auto / not chosen'}",
            f"- Candidate recipes: {', '.join(case.directives.candidate_recipe_ids) or 'none'}",
            f"- Generation mode: {case.directives.generation_mode.value}",
            f"- Recipe selection mode: {case.directives.recipe_selection_mode.value}",
            "",
            "## Policies",
            f"- Quality profile: {case.policies.quality_profile_id or 'none'}",
            f"- Similarity policy: {case.policies.similarity_policy_id or 'none'}",
            f"- Evidence policy: {case.policies.evidence_policy_id or 'none'}",
            f"- Provenance policy: {case.policies.provenance_policy_id or 'none'}",
            f"- Write policy: {case.policies.write_policy_id or AiWritePolicy.PRIMARY_ONLY.value}",
            "",
            "## Required behavior",
            "- Keep the bundle current as the case source of truth.",
            "- Preserve contradiction entries explicitly; do not silently flatten dissent.",
            "- Use reviewer/tester/judge passes for build-capable modes.",
            "- Similarity is advisory by default: report it with explanation.",
            "- Neighbor/reference repos are read-first; only the primary worktree is writable in v1.",
            "",
            "## Angle contracts",
            contract_lines,
            "",
            "## Finish line",
            "Produce verdict + minority report + blast radius + handoff pack, and add any mode-specific artifacts (scorecard, migration ledger, failure matrix, leaderboard, promotions) that fit the case.",
        ]
    )
