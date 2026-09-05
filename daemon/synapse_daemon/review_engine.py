"""Token-aware review planning for every Synapse project.

The review engine is deliberately cheap before it is clever:

1. inspect only the current change (or an explicitly supplied PR diff),
2. run deterministic risk/missing-evidence checks without an LLM,
3. choose the smallest useful review depth,
4. queue only the specialist AI passes justified by that change.

This module does not launch a model.  The existing coder-review-pass runtime owns
that concern, so Synapse keeps one execution/usage/accounting path for Codex,
Claude, Copilot, and the other coder runtimes.
"""

from __future__ import annotations

import json
import math
import re
import subprocess
from enum import Enum
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from . import projects as projects_module


class ReviewMode(str, Enum):
    AUTO = "auto"
    ECONOMY = "economy"
    STANDARD = "standard"
    THOROUGH = "thorough"
    RELEASE = "release"


class ReviewRisk(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ReviewFinding(BaseModel):
    id: str
    severity: Literal["info", "warning", "blocking"]
    title: str
    detail: str


class ReviewPassPlan(BaseModel):
    review_kind: str
    title: str
    requested_runtime_id: str
    reason: str
    focus_points: list[str] = Field(default_factory=list)


class ReviewPolicy(BaseModel):
    mode: ReviewMode
    token_budget: int
    max_ai_passes: int
    max_diff_chars: int
    focus_points: list[str] = Field(default_factory=list)
    source: str = "defaults"


class ReviewEngineRequest(BaseModel):
    mode: ReviewMode = ReviewMode.AUTO
    source: str = "local"
    diff_text: str | None = Field(default=None, max_length=500_000)
    changed_files: list[str] = Field(default_factory=list, max_length=500)
    primary_runtime: str | None = None
    change_title: str | None = Field(default=None, max_length=300)
    force_ai: bool = False


class ChangeSnapshot(BaseModel):
    changed_files: list[str] = Field(default_factory=list)
    diff_text: str = ""
    diff_chars: int = 0
    estimated_diff_tokens: int = 0
    docs_only: bool = False
    source: str = "local"
    change_title: str | None = None
    untracked_files: list[str] = Field(default_factory=list)
    diff_complete: bool = True
    git_error: str | None = None


class ReviewPlan(BaseModel):
    project_id: str
    project_name: str
    risk: ReviewRisk
    mode: ReviewMode
    policy: ReviewPolicy
    change: ChangeSnapshot
    estimated_context_tokens: int
    budget_remaining_after_context: int
    ai_review_required: bool
    deterministic_findings: list[ReviewFinding] = Field(default_factory=list)
    review_passes: list[ReviewPassPlan] = Field(default_factory=list)
    reason: str


_MODE_DEFAULTS: dict[ReviewMode, tuple[int, int, int]] = {
    # token budget, max AI passes, maximum diff characters copied into reviewer context
    ReviewMode.ECONOMY: (8_000, 1, 20_000),
    ReviewMode.STANDARD: (30_000, 2, 60_000),
    ReviewMode.THOROUGH: (60_000, 3, 100_000),
    ReviewMode.RELEASE: (100_000, 4, 120_000),
}

_HIGH_RISK_PATH_PARTS = (
    "auth",
    "security",
    "payment",
    "billing",
    "checkout",
    "migration",
    "migrations",
    "deploy",
    "deployment",
    "infra",
    "terraform",
    "secret",
    "broker",
    "trading",
    "execution",
    ".github/workflows",
)
_MEDIUM_RISK_PATH_PARTS = (
    "api",
    "route",
    "server",
    "database",
    "storage",
    "schema",
    "model",
    "daemon",
    "backend",
)
_UI_PATH_PARTS = ("frontend", "renderer", "ui", "components", "pages", "styles", "css")
_DOC_SUFFIXES = (".md", ".rst", ".txt")
_TEST_MARKERS = ("test_", "_test.", "/tests/", "\\tests\\", ".spec.", ".test.")
_SOURCE_SUFFIXES = (".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".rs", ".java", ".cs")
_RELEASE_FILES = {"changelog.md", "readme.md", "pyproject.toml", "package.json"}
_SECRET_FILENAMES = {".env", ".env.local", ".env.production", "credentials.json", "secrets.json"}
_SECRET_ASSIGNMENT_RE = re.compile(
    r"(?im)^[+ ]?\s*[A-Z0-9_.-]*(?:TOKEN|SECRET|PASSWORD|PASSWD|API[_-]?KEY|PRIVATE[_-]?KEY|CREDENTIAL)[A-Z0-9_.-]*\s*[:=]\s*[\"']?([^\s\"']{8,})"
)
_BEARER_VALUE_RE = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]{12,}")
_SAFE_SECRET_HINTS = ("example", "placeholder", "redacted", "dummy", "fake", "test-value", "changeme")


def _diff_has_secret_like_value(diff_text: str) -> bool:
    if _BEARER_VALUE_RE.search(diff_text):
        return True
    for match in _SECRET_ASSIGNMENT_RE.finditer(diff_text):
        value = match.group(1).lower()
        if not any(hint in value for hint in _SAFE_SECRET_HINTS):
            return True
    return False


def _normalise_path(path: str) -> str:
    return path.strip().replace("\\", "/").lower()


def _is_test(path: str) -> bool:
    normalized = f"/{_normalise_path(path)}"
    return any(marker in normalized for marker in _TEST_MARKERS)


def _is_docs(path: str) -> bool:
    normalized = _normalise_path(path)
    return normalized.startswith("docs/") or normalized.endswith(_DOC_SUFFIXES)


def _is_source(path: str) -> bool:
    return _normalise_path(path).endswith(_SOURCE_SUFFIXES) and not _is_test(path)


def _bounded_unique(values: list[str], *, limit: int = 30) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for raw in values:
        value = str(raw).strip()
        if not value or value in seen:
            continue
        seen.add(value)
        out.append(value[:500])
        if len(out) >= limit:
            break
    return out


def _git(project_path: str, args: list[str], *, timeout: int = 20) -> tuple[str, str | None]:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return "", str(exc)[:500]
    if result.returncode != 0:
        return "", (result.stderr or result.stdout or f"git exited {result.returncode}").strip()[:500]
    return result.stdout, None


def _status_paths(status_text: str) -> list[str]:
    paths: list[str] = []
    for line in status_text.splitlines():
        if len(line) < 4:
            continue
        path = line[3:].strip()
        if " -> " in path:
            path = path.rsplit(" -> ", 1)[-1]
        if path:
            paths.append(path)
    return _bounded_unique(paths, limit=500)


def collect_change_snapshot(
    project: projects_module.Project,
    request: ReviewEngineRequest,
) -> ChangeSnapshot:
    """Return a bounded, local-only view of the change to be reviewed."""

    if request.diff_text is not None or request.changed_files:
        diff_text = request.diff_text or ""
        changed_files = _bounded_unique(request.changed_files, limit=500)
        return ChangeSnapshot(
            changed_files=changed_files,
            diff_text=diff_text,
            diff_chars=len(diff_text),
            estimated_diff_tokens=math.ceil(len(diff_text) / 4),
            docs_only=bool(changed_files) and all(_is_docs(path) for path in changed_files),
            source=request.source,
            change_title=request.change_title,
            diff_complete=bool(diff_text.strip()) or not changed_files,
        )

    project_path = Path(project.path)
    if not project_path.exists():
        return ChangeSnapshot(source=request.source, git_error="Project path does not exist.")

    status_text, status_error = _git(project.path, ["status", "--porcelain=v1", "--untracked-files=all"])
    changed_files = _status_paths(status_text)
    untracked_files = _bounded_unique(
        [line[3:].strip() for line in status_text.splitlines() if line.startswith("?? ")],
        limit=500,
    )
    diff_text, diff_error = _git(
        project.path,
        ["diff", "--no-ext-diff", "--unified=3", "HEAD", "--", "."],
    )
    git_error = status_error or diff_error
    return ChangeSnapshot(
        changed_files=changed_files,
        diff_text=diff_text,
        diff_chars=len(diff_text),
        estimated_diff_tokens=math.ceil(len(diff_text) / 4),
        docs_only=bool(changed_files) and all(_is_docs(path) for path in changed_files),
        source=request.source,
        change_title=request.change_title,
        untracked_files=untracked_files,
        diff_complete=not untracked_files,
        git_error=git_error,
    )


def classify_risk(changed_files: list[str], diff_text: str = "") -> ReviewRisk:
    normalized = [_normalise_path(path) for path in changed_files]
    joined = "\n".join(normalized)
    if any(part in joined for part in _HIGH_RISK_PATH_PARTS):
        return ReviewRisk.HIGH
    # A change that can alter credentials, authorization, destructive execution, or money
    # is high risk even when the filename itself is bland.
    if re.search(
        r"(?i)\b(password|api[_ -]?key|authorization|delete\s+from|place[_ -]?order|submit[_ -]?order|live[_ -]?execution)\b",
        diff_text[:120_000],
    ):
        return ReviewRisk.HIGH
    if any(part in joined for part in _MEDIUM_RISK_PATH_PARTS):
        return ReviewRisk.MEDIUM
    source_count = sum(1 for path in changed_files if _is_source(path))
    if source_count >= 8 or len(diff_text) >= 50_000:
        return ReviewRisk.MEDIUM
    return ReviewRisk.LOW


def _auto_mode(change: ChangeSnapshot, risk: ReviewRisk) -> ReviewMode:
    normalized_names = {_normalise_path(path).rsplit("/", 1)[-1] for path in change.changed_files}
    release_title = bool(
        change.change_title
        and re.search(r"(?i)(?:\brelease\b|\bv?\d+\.\d+(?:\.\d+)?\b)", change.change_title)
    )
    release_signal = release_title or (
        bool(normalized_names & _RELEASE_FILES)
        and bool(re.search(r"(?i)\b(version|release|changelog)\b", change.diff_text[:100_000]))
    )
    if release_signal:
        return ReviewMode.RELEASE
    if risk == ReviewRisk.HIGH:
        return ReviewMode.THOROUGH
    if risk == ReviewRisk.MEDIUM:
        return ReviewMode.STANDARD
    return ReviewMode.ECONOMY


def _read_project_override(project: projects_module.Project) -> dict[str, Any]:
    """Read an optional, repo-local review contract without executing project code."""

    try:
        root = Path(project.path).resolve()
        candidate = (root / ".synapse" / "review-policy.json").resolve()
        if root not in candidate.parents or not candidate.is_file() or candidate.stat().st_size > 64_000:
            return {}
        data = json.loads(candidate.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def effective_policy(
    project: projects_module.Project,
    request: ReviewEngineRequest,
    change: ChangeSnapshot,
    risk: ReviewRisk,
) -> ReviewPolicy:
    override = _read_project_override(project)
    requested_mode = request.mode
    if requested_mode == ReviewMode.AUTO:
        configured = str(override.get("mode") or "").strip().lower()
        try:
            requested_mode = ReviewMode(configured) if configured else _auto_mode(change, risk)
        except ValueError:
            requested_mode = _auto_mode(change, risk)
        if requested_mode == ReviewMode.AUTO:
            requested_mode = _auto_mode(change, risk)

    token_budget, max_ai_passes, max_diff_chars = _MODE_DEFAULTS[requested_mode]
    if isinstance(override.get("token_budget"), int):
        token_budget = max(4_000, min(int(override["token_budget"]), 120_000))
    if isinstance(override.get("max_ai_passes"), int):
        max_ai_passes = max(0, min(int(override["max_ai_passes"]), 4))
    if isinstance(override.get("max_diff_chars"), int):
        max_diff_chars = max(4_000, min(int(override["max_diff_chars"]), 120_000))

    focus = override.get("focus_points")
    focus_points = _bounded_unique(focus if isinstance(focus, list) else [], limit=20)
    return ReviewPolicy(
        mode=requested_mode,
        token_budget=token_budget,
        max_ai_passes=max_ai_passes,
        max_diff_chars=max_diff_chars,
        focus_points=focus_points,
        source=".synapse/review-policy.json" if override else "defaults",
    )


def deterministic_findings(
    change: ChangeSnapshot,
    mode: ReviewMode,
) -> list[ReviewFinding]:
    files = [_normalise_path(path) for path in change.changed_files]
    findings: list[ReviewFinding] = []

    secret_files = [path for path in files if path.rsplit("/", 1)[-1] in _SECRET_FILENAMES]
    if secret_files:
        findings.append(
            ReviewFinding(
                id="secret-file-changed",
                severity="blocking",
                title="Secret-bearing file is part of the change",
                detail="Do not send secret-bearing files to an AI reviewer or commit them. Review: "
                + ", ".join(secret_files[:8]),
            )
        )

    if not change.diff_complete and change.changed_files:
        findings.append(
            ReviewFinding(
                id="diff-evidence-incomplete",
                severity="warning",
                title="Changed-file evidence is incomplete",
                detail=(
                    "The exact diff is missing for one or more changed files"
                    + (f" (including untracked: {', '.join(change.untracked_files[:8])})" if change.untracked_files else "")
                    + ". Collect an exact bounded diff before spending AI review tokens."
                ),
            )
        )

    if _diff_has_secret_like_value(change.diff_text):
        findings.append(
            ReviewFinding(
                id="secret-like-value-in-diff",
                severity="blocking",
                title="Secret-like value detected in the diff",
                detail="Synapse withheld the diff from AI review. Remove/redact the value or use a clearly fake test placeholder before retrying.",
            )
        )

    source_files = [path for path in files if _is_source(path)]
    test_files = [path for path in files if _is_test(path)]
    if source_files and not test_files:
        findings.append(
            ReviewFinding(
                id="source-without-tests",
                severity="warning",
                title="Source changed without a test change",
                detail="Existing tests may still cover this change, but the reviewer should require concrete verification before completion.",
            )
        )

    migration_files = [path for path in files if "migration" in path]
    if migration_files and not test_files:
        findings.append(
            ReviewFinding(
                id="migration-without-tests",
                severity="warning",
                title="Migration changed without migration-focused tests",
                detail="Check upgrade, rollback/forward compatibility, and existing-data behavior.",
            )
        )

    if mode == ReviewMode.RELEASE:
        basenames = {path.rsplit("/", 1)[-1] for path in files}
        missing = sorted({"changelog.md", "readme.md"} - basenames)
        if missing:
            findings.append(
                ReviewFinding(
                    id="release-metadata-not-touched",
                    severity="warning",
                    title="Release documentation was not updated in this change",
                    detail="Release mode requires checking runtime/package version plus README/CHANGELOG truthfulness; untouched artifacts: "
                    + ", ".join(missing),
                )
            )

    if change.git_error:
        findings.append(
            ReviewFinding(
                id="git-inspection-incomplete",
                severity="warning",
                title="Local git inspection was incomplete",
                detail=change.git_error,
            )
        )
    return findings


def _independent_runtime(primary_runtime: str | None, ordinal: int) -> str:
    primary = (primary_runtime or "").strip().lower()
    ladder = ["codex", "claude", "copilot"]
    if primary in ladder:
        ladder.remove(primary)
        ladder.append(primary)
    return ladder[ordinal % len(ladder)]


def _specialist_passes(
    project: projects_module.Project,
    change: ChangeSnapshot,
    risk: ReviewRisk,
    policy: ReviewPolicy,
    primary_runtime: str | None,
) -> list[ReviewPassPlan]:
    files_text = "\n".join(_normalise_path(path) for path in change.changed_files)
    candidates: list[tuple[str, str, str, list[str]]] = []

    candidates.append(
        (
            "qa",
            "Correctness & regression review",
            "Every material code change benefits from one independent correctness pass.",
            [
                "Find concrete bugs or regressions in the changed diff, not speculative repo-wide cleanup.",
                "Require evidence for claims of completion and identify the smallest missing test/proof.",
            ],
        )
    )
    if any(part in files_text for part in _UI_PATH_PARTS):
        candidates.append(
            (
                "ux",
                "UI/UX human-impact review",
                "The change touches a user-facing surface.",
                ["Check mobile/desktop behavior, hierarchy, navigation escape paths, and accessibility."],
            )
        )
    if risk == ReviewRisk.HIGH:
        candidates.append(
            (
                "security",
                "Safety & boundary review",
                "High-risk paths or behavior changed.",
                [
                    "Check authorization, secret exposure, destructive actions, money/execution boundaries, and failure modes.",
                    "Prefer a specific exploitable or integrity failure over generic security advice.",
                ],
            )
        )
    if policy.mode in {ReviewMode.THOROUGH, ReviewMode.RELEASE}:
        candidates.append(
            (
                "judge",
                "Independent release judge",
                "Risk/depth justifies a second-opinion gate before declaring the change done.",
                ["Judge only material findings and state whether another AI pass is actually worth its token cost."],
            )
        )
    if policy.mode == ReviewMode.RELEASE:
        candidates.insert(
            1,
            (
                "release",
                "Release integrity review",
                "Release mode must reconcile code, package/runtime version, docs, changelog, and reload behavior.",
                ["Verify release metadata and operational reload/version gates are internally consistent."],
            ),
        )

    # Repo-local review contracts are appended to every selected pass. This is how Stock Hunter,
    # WhatIf Pulse, games, or future projects can carry their own invariants without hard-coding
    # project names into Synapse.
    selected: list[ReviewPassPlan] = []
    for index, (kind, title, reason, focus) in enumerate(candidates[: policy.max_ai_passes]):
        selected.append(
            ReviewPassPlan(
                review_kind=kind,
                title=title,
                requested_runtime_id=_independent_runtime(primary_runtime, index),
                reason=reason,
                focus_points=_bounded_unique([*focus, *policy.focus_points], limit=24),
            )
        )
    return selected


def plan_project_review(
    project: projects_module.Project,
    request: ReviewEngineRequest,
) -> ReviewPlan:
    change = collect_change_snapshot(project, request)
    risk = classify_risk(change.changed_files, change.diff_text)
    policy = effective_policy(project, request, change, risk)
    findings = deterministic_findings(change, policy.mode)

    # Rough but intentionally conservative. We only need a budget guard before the real
    # runtime reports exact usage to the existing Synapse ledgers.
    diff_chars_in_context = min(change.diff_chars, policy.max_diff_chars)
    estimated_context_tokens = math.ceil(diff_chars_in_context / 4) + 1_500
    remaining = max(policy.token_budget - estimated_context_tokens, 0)
    has_material_change = bool(change.changed_files or change.diff_text.strip())
    has_blocker = any(item.severity == "blocking" for item in findings)
    evidence_complete = change.diff_complete
    ai_required = (
        has_material_change
        and not has_blocker
        and evidence_complete
        and policy.max_ai_passes > 0
        and (request.force_ai or not change.docs_only)
        and remaining >= 1_000
    )
    passes = (
        _specialist_passes(project, change, risk, policy, request.primary_runtime)
        if ai_required
        else []
    )

    if has_blocker:
        reason = "Deterministic blocking finding must be resolved before any diff is sent to an AI reviewer."
    elif not has_material_change:
        reason = "No material local change was found, so spending review tokens would add no value."
    elif not evidence_complete:
        reason = "Exact diff evidence is incomplete, so Synapse will not spend review tokens or claim the change was reviewed yet."
    elif change.docs_only and not request.force_ai:
        reason = "Docs-only change passed through the token-free deterministic lane; AI review was skipped."
    elif remaining < 1_000:
        reason = "Estimated context would consume the configured review budget; AI review was not queued."
    else:
        reason = f"{policy.mode.value} review selected for {risk.value}-risk change with {len(passes)} targeted AI pass(es)."

    return ReviewPlan(
        project_id=project.id,
        project_name=project.name,
        risk=risk,
        mode=policy.mode,
        policy=policy,
        change=change,
        estimated_context_tokens=estimated_context_tokens,
        budget_remaining_after_context=remaining,
        ai_review_required=ai_required,
        deterministic_findings=findings,
        review_passes=passes,
        reason=reason,
    )


def bounded_diff_for_prompt(plan: ReviewPlan) -> str:
    """Return only the budgeted diff slice; never include a known secret-bearing change."""

    if any(item.id in {"secret-file-changed", "secret-like-value-in-diff"} for item in plan.deterministic_findings):
        return "[diff withheld: deterministic secret-file guard triggered]"
    text = plan.change.diff_text
    cap = plan.policy.max_diff_chars
    if len(text) <= cap:
        return text
    omitted = len(text) - cap
    return text[:cap] + f"\n\n[diff truncated by Synapse review budget; {omitted} characters omitted]"
