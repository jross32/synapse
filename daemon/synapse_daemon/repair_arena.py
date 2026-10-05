from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path
from types import ModuleType
from typing import Any


CONTRACT_VERSION = "1.1"
DEFAULT_APP_DOCTOR_ROOT = Path.home() / "AppDoctor"
DEFAULT_AGENT_ARCADE_ROOT = Path.home() / "AgentArcade"


def _external_root(env_name: str, default: Path) -> Path:
    raw = os.getenv(env_name, "").strip()
    root = Path(raw).expanduser() if raw else default
    root = root.resolve()
    if not root.exists() or not root.is_dir():
        raise RuntimeError(f"Required Repair Arena component is unavailable: {root}")
    return root


def _load_module(path: Path, logical_name: str) -> ModuleType:
    if not path.exists() or not path.is_file():
        raise RuntimeError(f"Required Repair Arena module is unavailable: {path}")
    cache_key = f"_synapse_repair_arena_{logical_name}_{abs(hash(str(path)))}"
    cached = sys.modules.get(cache_key)
    if cached is not None:
        return cached
    spec = importlib.util.spec_from_file_location(cache_key, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load Repair Arena module: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[cache_key] = module
    spec.loader.exec_module(module)
    return module


def _latest_winning_plan(tournament: dict[str, Any]) -> str:
    champion = tournament.get("champion") or {}
    champion_id = champion.get("agent_id")
    for round_result in reversed(tournament.get("rounds") or []):
        for row in round_result.get("rankings") or []:
            if row.get("agent_id") == champion_id:
                return str(row.get("response") or "")
    return ""


def _candidate_plans(tournament: dict[str, Any], limit: int = 3) -> list[dict[str, Any]]:
    score_rows = {
        str(row.get("agent_id") or ""): row
        for row in (tournament.get("scoreboard") or [])
        if isinstance(row, dict) and row.get("agent_id")
    }
    rounds = tournament.get("rounds") or []
    final_rankings = []
    if rounds and isinstance(rounds[-1], dict):
        final_rankings = rounds[-1].get("rankings") or []

    out: list[dict[str, Any]] = []
    for row in final_rankings:
        if not isinstance(row, dict):
            continue
        agent_id = str(row.get("agent_id") or "").strip()
        plan = str(row.get("response") or "").strip()
        if not agent_id or not plan:
            continue
        score = score_rows.get(agent_id, {})
        rank = score.get("rank")
        out.append({
            "agent_id": agent_id,
            "name": score.get("name") or row.get("name") or agent_id,
            "rank": rank if isinstance(rank, int) and not isinstance(rank, bool) else len(out) + 1,
            "score": score.get("average_score"),
            "plan": plan,
        })
    out.sort(key=lambda item: (item.get("rank") or 999, str(item.get("agent_id") or "")))
    return out[: max(1, min(int(limit or 3), 3))]


def _validate_args(project_path: str, rounds: int, mode: str) -> Path:
    root = Path(project_path).expanduser().resolve()
    if not root.exists() or not root.is_dir():
        raise ValueError("project_path must be an existing directory")
    if isinstance(rounds, bool) or not isinstance(rounds, int) or not 1 <= rounds <= 3:
        raise ValueError("rounds must be between 1 and 3")
    if mode not in {"demo", "gemini"}:
        raise ValueError("mode must be demo or gemini")
    return root


def run_repair_arena(
    project_path: str,
    *,
    project_id: str = "",
    project_name: str = "",
    rounds: int = 2,
    mode: str = "demo",
    persist: bool = True,
    prepare_candidates: bool = False,
    candidate_count: int = 3,
    candidate_workspace_root: str | None = None,
) -> dict[str, Any]:
    """Run App Doctor -> Agent Arcade as one planning-only Synapse capability.

    The target repository is scanned read-only. Project-controlled tests are discovered but
    never executed here. Agent Arcade competes on repair *plans* only; no candidate patch is
    written or merged. Completed tournaments are persisted to Agent Arcade's SQLite history
    when ``persist`` is true.
    """
    root = _validate_args(project_path, rounds, mode)
    app_doctor_root = _external_root("SYNAPSE_APP_DOCTOR_ROOT", DEFAULT_APP_DOCTOR_ROOT)
    agent_arcade_root = _external_root("SYNAPSE_AGENT_ARCADE_ROOT", DEFAULT_AGENT_ARCADE_ROOT)

    doctor_engine = _load_module(app_doctor_root / "doctor_engine.py", "doctor_engine")
    evidence_runner = _load_module(app_doctor_root / "evidence_runner.py", "evidence_runner")
    bridge = _load_module(app_doctor_root / "repair_arena_bridge.py", "repair_arena_bridge")
    arena_engine = _load_module(agent_arcade_root / "arena_engine.py", "arena_engine")
    history_store = _load_module(agent_arcade_root / "history_store.py", "history_store")

    report = doctor_engine.scan_project(str(root))
    repair_prompt = doctor_engine.format_repair_prompt(report)
    test_plans = evidence_runner.discover_test_plans(str(root))
    challenge = bridge.build_repair_challenge(
        report,
        test_plans,
        repair_prompt=repair_prompt,
    )

    tournament = arena_engine.run_tournament(
        challenge["objective"],
        bridge.DEFAULT_REPAIR_AGENTS,
        rounds=rounds,
        mode=mode,
    )
    if persist:
        db_path = agent_arcade_root / "data" / "agent_arcade.sqlite3"
        tournament = history_store.TournamentHistoryStore(db_path).save(tournament)

    findings = challenge.get("findings") or []
    scoreboard = tournament.get("scoreboard") or []
    champion = tournament.get("champion") or {}
    winning_plan = _latest_winning_plan(tournament)
    candidate_plans = _candidate_plans(tournament, limit=candidate_count)
    candidate_staging = None
    if prepare_candidates:
        from .repair_arena_candidates import prepare_candidate_worktrees

        staging_tournament_id = str(
            tournament.get("tournament_id")
            or challenge.get("challenge_id")
            or "repair-arena-unpersisted"
        )
        candidate_staging = prepare_candidate_worktrees(
            str(root),
            project_id=project_id,
            project_name=project_name or challenge.get("project", {}).get("name") or root.name,
            tournament_id=staging_tournament_id,
            candidates=candidate_plans,
            baseline=challenge.get("baseline") or {},
            findings=findings,
            candidate_count=candidate_count,
            workspace_root=candidate_workspace_root,
        )

    return {
        "contract_version": CONTRACT_VERSION,
        "source": "synapse-repair-arena",
        "project": {
            "id": project_id,
            "name": project_name or challenge.get("project", {}).get("name") or root.name,
            "path": str(root),
            "stack": challenge.get("project", {}).get("stack") or [],
        },
        "baseline": challenge.get("baseline") or {},
        "findings": findings,
        "test_plans": challenge.get("test_plans") or [],
        "challenge_id": challenge.get("challenge_id"),
        "tournament": {
            "tournament_id": tournament.get("tournament_id"),
            "created_at": tournament.get("created_at"),
            "mode": tournament.get("mode", mode),
            "rounds": rounds,
            "champion": champion,
            "scoreboard": scoreboard,
            "winning_plan": winning_plan,
            "candidate_plans": candidate_plans,
        },
        "candidate_staging": candidate_staging,
        "execution_policy": {
            "planning_only": True,
            "target_repository_modified": False,
            "project_tests_executed": False,
            "project_code_executed": False,
            "auto_merge": False,
            "tournament_history_persisted": bool(persist),
            "isolated_candidate_worktrees_prepared": bool(candidate_staging and candidate_staging.get("prepared")),
            "repository_metadata_modified": bool(candidate_staging and candidate_staging.get("repository_metadata_modified")),
            "primary_working_tree_preserved": (
                candidate_staging.get("primary_working_tree_preserved") if candidate_staging else True
            ),
        },
        "promotion_gate": {
            "eligible_now": False,
            "requires": [
                "inspect the winning plan against the real cited evidence",
                "implement in an isolated branch/worktree",
                "run proportionate tests",
                "run browser/runtime proof when user-visible behavior changes",
                "re-scan with App Doctor and reject regressions",
            ],
        },
        "limitations": (
            ["Demo mode uses deterministic local strategy simulation, not independent live model reasoning."]
            if mode == "demo"
            else ["Gemini mode can use an external model/runtime and may depend on its availability/quota."]
        ),
    }


def readiness() -> dict[str, Any]:
    app_doctor_root = _external_root("SYNAPSE_APP_DOCTOR_ROOT", DEFAULT_APP_DOCTOR_ROOT)
    agent_arcade_root = _external_root("SYNAPSE_AGENT_ARCADE_ROOT", DEFAULT_AGENT_ARCADE_ROOT)
    required = {
        "app_doctor": ["doctor_engine.py", "evidence_runner.py", "repair_arena_bridge.py"],
        "agent_arcade": ["arena_engine.py", "history_store.py"],
    }
    missing: list[str] = []
    for name in required["app_doctor"]:
        if not (app_doctor_root / name).is_file():
            missing.append(str(app_doctor_root / name))
    for name in required["agent_arcade"]:
        if not (agent_arcade_root / name).is_file():
            missing.append(str(agent_arcade_root / name))
    return {
        "ok": not missing,
        "contract_version": CONTRACT_VERSION,
        "app_doctor_root": str(app_doctor_root),
        "agent_arcade_root": str(agent_arcade_root),
        "missing": missing,
        "default_mode": "demo",
        "planning_only": True,
    }
