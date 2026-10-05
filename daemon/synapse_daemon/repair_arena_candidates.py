from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any

from .git_worktrees import ensure_worktree, resolve_repo_root
from .subprocess_utils import headless_creationflags


DEFAULT_CANDIDATE_ROOT = Path.home() / ".synapse-repair-arena" / "worktrees"


def _slug(value: str, *, fallback: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", str(value or "").strip()).strip("-._")
    return (cleaned or fallback)[:80]


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        check=False,
        creationflags=headless_creationflags(),
    )
    if result.returncode != 0:
        message = (result.stderr or result.stdout or "git command failed").strip()
        raise RuntimeError(message)
    return result.stdout.strip()


def _status(repo: Path) -> str:
    return _git(repo, "status", "--porcelain=v1", "--untracked-files=all")


def _candidate_brief(
    *,
    project_id: str,
    project_name: str,
    tournament_id: str,
    candidate: dict[str, Any],
    baseline: dict[str, Any] | None,
    findings: list[dict[str, Any]] | None,
    base_commit: str,
) -> dict[str, Any]:
    return {
        "contract_version": "1.0",
        "source": "synapse-repair-arena",
        "project": {"id": project_id, "name": project_name},
        "tournament_id": tournament_id,
        "base_commit": base_commit,
        "candidate": {
            "rank": candidate.get("rank"),
            "agent_id": candidate.get("agent_id"),
            "name": candidate.get("name"),
            "score": candidate.get("score"),
            "plan": candidate.get("plan") or "",
        },
        "baseline": baseline or {},
        "findings": findings or [],
        "implementation_contract": {
            "scope": "smallest coherent repair that addresses the cited evidence",
            "preserve_unrelated_work": True,
            "main_working_tree_off_limits": True,
            "auto_merge": False,
            "required_before_promotion": [
                "inspect cited evidence before changing code",
                "add or tighten a regression test for the real defect when practical",
                "run proportionate tests",
                "run browser/runtime proof for user-visible changes",
                "re-scan with App Doctor and compare finding-level deltas",
            ],
        },
    }


def prepare_candidate_worktrees(
    project_path: str,
    *,
    project_id: str,
    project_name: str,
    tournament_id: str,
    candidates: list[dict[str, Any]],
    baseline: dict[str, Any] | None = None,
    findings: list[dict[str, Any]] | None = None,
    candidate_count: int = 3,
    workspace_root: str | Path | None = None,
) -> dict[str, Any]:
    """Create isolated Git worktrees for the top Repair Arena candidate plans.

    This mutates Git metadata by creating branches/worktrees, but it never writes to the
    primary working tree. Candidate briefs are stored outside each Git worktree so a newly
    staged candidate starts clean and evaluation is not polluted by orchestration files.
    """
    if isinstance(candidate_count, bool) or not isinstance(candidate_count, int) or not 1 <= candidate_count <= 3:
        raise ValueError("candidate_count must be between 1 and 3")
    if not str(tournament_id or "").strip():
        raise ValueError("tournament_id is required")

    repo_root = resolve_repo_root(project_path)
    base_commit = _git(repo_root, "rev-parse", "HEAD")
    status_before = _status(repo_root)

    root = Path(workspace_root).expanduser().resolve() if workspace_root else DEFAULT_CANDIDATE_ROOT.resolve()
    project_slug = _slug(project_id or project_name or repo_root.name, fallback="project")
    tournament_slug = _slug(tournament_id, fallback="tournament")
    tournament_root = root / project_slug / tournament_slug
    tournament_root.mkdir(parents=True, exist_ok=True)

    prepared: list[dict[str, Any]] = []
    seen_agents: set[str] = set()
    for index, candidate in enumerate(candidates or [], start=1):
        if len(prepared) >= candidate_count:
            break
        if not isinstance(candidate, dict):
            continue
        agent_id = str(candidate.get("agent_id") or f"candidate-{index}").strip()
        plan = str(candidate.get("plan") or "").strip()
        if not plan or agent_id in seen_agents:
            continue
        seen_agents.add(agent_id)

        rank = candidate.get("rank")
        rank_value = int(rank) if isinstance(rank, int) and not isinstance(rank, bool) and rank > 0 else len(prepared) + 1
        agent_slug = _slug(agent_id, fallback=f"candidate-{rank_value}")
        entry_root = tournament_root / f"{rank_value:02d}-{agent_slug}"
        worktree_path = entry_root / "worktree"
        branch_name = f"repair-arena/{project_slug}/{tournament_slug}/{rank_value:02d}-{agent_slug}"

        _, created_worktree = ensure_worktree(
            primary_project_path=str(repo_root),
            worktree_path=worktree_path,
            branch_name=branch_name,
        )
        brief = _candidate_brief(
            project_id=project_id,
            project_name=project_name or repo_root.name,
            tournament_id=tournament_id,
            candidate=candidate,
            baseline=baseline,
            findings=findings,
            base_commit=base_commit,
        )
        brief_path = entry_root / "candidate.json"
        brief_path.write_text(json.dumps(brief, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

        prepared.append(
            {
                "rank": rank_value,
                "agent_id": agent_id,
                "name": candidate.get("name") or agent_id,
                "score": candidate.get("score"),
                "branch": branch_name,
                "worktree_path": str(created_worktree),
                "brief_path": str(brief_path),
                "base_commit": base_commit,
                "worktree_clean_at_stage": _status(created_worktree) == "",
            }
        )

    status_after = _status(repo_root)
    result = {
        "prepared": bool(prepared),
        "candidate_count": len(prepared),
        "workspace_root": str(tournament_root),
        "base_commit": base_commit,
        "baseline": baseline or {},
        "baseline_findings": findings or [],
        "primary_working_tree_status_before": status_before,
        "primary_working_tree_status_after": status_after,
        "primary_working_tree_preserved": status_before == status_after,
        "repository_metadata_modified": bool(prepared),
        "auto_merge": False,
        "candidates": prepared,
    }
    receipt_path = tournament_root / "staging.json"
    result["staging_receipt_path"] = str(receipt_path)
    receipt_path.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return result


def inspect_candidate_worktree(
    worktree_path: str,
    *,
    base_commit: str,
) -> dict[str, Any]:
    """Return a non-executing evidence receipt for one staged candidate workspace."""
    worktree = Path(worktree_path).expanduser().resolve()
    if not worktree.exists() or not worktree.is_dir():
        raise ValueError("worktree_path must be an existing directory")
    repo_root = resolve_repo_root(str(worktree))
    head = _git(repo_root, "rev-parse", "HEAD")
    status = _status(repo_root)
    changed_files = [line for line in _git(repo_root, "diff", "--name-only", base_commit, "--").splitlines() if line.strip()]
    return {
        "worktree_path": str(repo_root),
        "base_commit": base_commit,
        "head_commit": head,
        "dirty": bool(status),
        "status_porcelain": status,
        "changed_files": changed_files,
        "changed_file_count": len(changed_files),
        "tests_executed": False,
        "project_code_executed": False,
        "eligible_for_promotion": False,
        "next_gate": "run proportionate verification and App Doctor before promotion",
    }


def load_staging_receipt(
    project_id: str,
    tournament_id: str,
    *,
    workspace_root: str | Path | None = None,
) -> dict[str, Any]:
    root = Path(workspace_root).expanduser().resolve() if workspace_root else DEFAULT_CANDIDATE_ROOT.resolve()
    project_slug = _slug(project_id, fallback="project")
    tournament_slug = _slug(tournament_id, fallback="tournament")
    path = root / project_slug / tournament_slug / "staging.json"
    if not path.is_file():
        raise ValueError(f"Repair Arena staging receipt was not found for {project_id}/{tournament_id}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Repair Arena staging receipt is malformed")
    return payload


def _select_candidate(staging: dict[str, Any], candidate: str | int | None) -> dict[str, Any]:
    rows = [row for row in (staging.get("candidates") or []) if isinstance(row, dict)]
    if not rows:
        raise ValueError("No staged candidates are available")
    if candidate is None or candidate == "":
        return sorted(rows, key=lambda row: int(row.get("rank") or 999))[0]
    if isinstance(candidate, int) and not isinstance(candidate, bool):
        for row in rows:
            if row.get("rank") == candidate:
                return row
    needle = str(candidate).strip().casefold()
    for row in rows:
        if str(row.get("agent_id") or "").casefold() == needle or str(row.get("name") or "").casefold() == needle:
            return row
    raise ValueError(f"Staged candidate '{candidate}' was not found")


def evaluate_staged_candidate(
    project_id: str,
    tournament_id: str,
    *,
    candidate: str | int | None = None,
    workspace_root: str | Path | None = None,
    app_doctor_root: str | Path | None = None,
) -> dict[str, Any]:
    """Read-only static evaluation of one staged implementation candidate.

    It inspects Git changes and re-runs App Doctor's read-only scanner. It never runs tests,
    project code, browser actions, or merges, so promotion always remains false at this stage.
    """
    staging = load_staging_receipt(project_id, tournament_id, workspace_root=workspace_root)
    selected = _select_candidate(staging, candidate)
    base_commit = str(selected.get("base_commit") or staging.get("base_commit") or "").strip()
    if not base_commit:
        raise ValueError("Staging receipt has no base commit")
    inspection = inspect_candidate_worktree(str(selected.get("worktree_path") or ""), base_commit=base_commit)

    from .repair_arena import DEFAULT_APP_DOCTOR_ROOT, _external_root, _load_module

    doctor_root = Path(app_doctor_root).expanduser().resolve() if app_doctor_root else _external_root(
        "SYNAPSE_APP_DOCTOR_ROOT", DEFAULT_APP_DOCTOR_ROOT
    )
    doctor_engine = _load_module(doctor_root / "doctor_engine.py", "doctor_engine")
    report = doctor_engine.scan_project(str(selected["worktree_path"]))

    baseline_findings = [row for row in (staging.get("baseline_findings") or []) if isinstance(row, dict)]
    after_findings = [row for row in (report.get("findings") or []) if isinstance(row, dict)]
    baseline_by_id = {str(row.get("id") or ""): row for row in baseline_findings if row.get("id")}
    after_by_id = {str(row.get("id") or ""): row for row in after_findings if row.get("id")}
    fixed_ids = sorted(set(baseline_by_id) - set(after_by_id))
    persisted_ids = sorted(set(baseline_by_id) & set(after_by_id))
    new_ids = sorted(set(after_by_id) - set(baseline_by_id))
    new_high_critical = [
        finding_id
        for finding_id in new_ids
        if str(after_by_id[finding_id].get("severity") or "").lower() in {"high", "critical"}
    ]

    baseline_score = (staging.get("baseline") or {}).get("score")
    after_score = report.get("score")
    score_delta = None
    if isinstance(baseline_score, (int, float)) and not isinstance(baseline_score, bool) and isinstance(after_score, (int, float)) and not isinstance(after_score, bool):
        score_delta = round(float(after_score) - float(baseline_score), 4)

    if inspection["changed_file_count"] == 0 and not inspection["dirty"]:
        provisional_outcome = "not_started_or_abstained"
    elif new_high_critical:
        provisional_outcome = "regressed"
    elif fixed_ids or (score_delta is not None and score_delta > 0):
        provisional_outcome = "static_improvement_detected"
    else:
        provisional_outcome = "no_static_improvement_detected"

    return {
        "contract_version": "1.0",
        "source": "synapse-repair-arena-candidate-evaluator",
        "project_id": project_id,
        "tournament_id": tournament_id,
        "candidate": selected,
        "inspection": inspection,
        "app_doctor": {
            "baseline_score": baseline_score,
            "after_score": after_score,
            "score_delta": score_delta,
            "fixed_finding_ids": fixed_ids,
            "persisted_finding_ids": persisted_ids,
            "new_finding_ids": new_ids,
            "new_high_or_critical_ids": new_high_critical,
        },
        "provisional_outcome": provisional_outcome,
        "verification": {
            "static_scan_completed": True,
            "tests_executed": False,
            "project_code_executed": False,
            "browser_or_runtime_proof_completed": False,
        },
        "promotion_gate": {
            "eligible_now": False,
            "reason": "Static Git/App Doctor evidence is not sufficient to promote a candidate.",
            "requires": [
                "inspect the candidate rationale against the cited evidence",
                "run proportionate tests",
                "run browser/runtime proof when user-visible behavior changes",
                "reject new high/critical findings and unrelated scope expansion",
            ],
        },
    }
