from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import repair_plan
import ui_forge
import workflow_state

SCRIPT_DIR = Path(__file__).resolve().parent
PACKAGE_ROOT = SCRIPT_DIR.parent
DEFAULT_CONTRACT = PACKAGE_ROOT / "references" / "workflow-contract.json"
DEFAULT_STATE_RELATIVE = Path(".synapse") / "ui-forge" / "run-state.json"

PHASE_RECIPES: dict[str, list[str]] = {
    "inspect": [
        "Read Synapse project AI context/records and inspect the actual source tree before editing.",
        "Run or open the current app and capture the baseline UI, or record why that is impossible.",
        "Write the UI Forge brief and baseline runtime state into run artifacts.",
    ],
    "design_grammar": [
        "Recover the existing tokens/components first; do not create a parallel design system by accident.",
        "Choose one product-specific experience direction and record the token/component contract.",
    ],
    "plan": [
        "Split the requested work into bounded vertical slices.",
        "Record must-preserve behavior, responsive/state scope, and the browser verification plan.",
    ],
    "implement": [
        "Implement only the next coherent slice and keep the diff bounded.",
        "For precision edits, prefer visual_edit_bridge.js + source_locator.py / data-ui-forge-source.",
        "Run/build the app immediately after the slice.",
    ],
    "browser_proof": [
        "Exercise the primary path in a real browser at representative desktop and mobile viewports.",
        "Run browser_audit.js and inspect console/runtime errors.",
        "Capture screenshots/evidence and record objective findings rather than prose-only claims.",
    ],
    "score": [
        "Provide evidence JSON covering all eight UI Forge dimensions.",
        "Run the deterministic quality gate; critical failures block completion regardless of weighted score.",
    ],
    "repair_or_finish": [
        "If the score/design gate fails, fix only the first highest-priority root cause.",
        "Rerun only the affected proof plus any structural audit, then rescore.",
        "Stop when the score gate passes and no structural action remains.",
    ],
    "learn": [
        "Record reusable project design knowledge and any recurring friction.",
        "Persist the handoff into Synapse AI context/backlog when the lesson is reusable.",
    ],
}


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _resolve_state_path(project_root: str | Path, state_path: str | None) -> Path:
    if state_path:
        return Path(state_path).expanduser().resolve()
    return Path(project_root).expanduser().resolve() / DEFAULT_STATE_RELATIVE


def _phase_contract(contract: dict[str, Any], phase: str) -> dict[str, Any]:
    phases = contract.get("phases") if isinstance(contract.get("phases"), list) else []
    for item in phases:
        if isinstance(item, dict) and item.get("id") == phase:
            return item
    raise ValueError(f"phase {phase!r} is not present in the workflow contract")


def _artifact_value_exists(value: Any, project_root: Path) -> bool:
    if value in (None, ""):
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return True
    if isinstance(value, dict):
        if not value:
            return False
        path_value = value.get("path")
        if isinstance(path_value, str) and path_value.strip():
            candidate = Path(path_value)
            if not candidate.is_absolute():
                candidate = project_root / candidate
            return candidate.exists()
        return True
    if isinstance(value, list):
        return bool(value)
    text = str(value).strip()
    if not text:
        return False
    # Values that look like paths must actually exist. Human-readable summaries/ids are
    # allowed as evidence values without forcing them onto disk.
    looks_pathlike = any(sep in text for sep in ("/", "\\")) or Path(text).suffix.lower() in {
        ".json", ".md", ".txt", ".png", ".jpg", ".jpeg", ".webp", ".html", ".log"
    }
    if looks_pathlike:
        candidate = Path(text)
        if not candidate.is_absolute():
            candidate = project_root / candidate
        return candidate.exists()
    return True


def phase_readiness(state: dict[str, Any], contract: dict[str, Any], phase: str) -> dict[str, Any]:
    if phase not in workflow_state.PHASES:
        raise ValueError(f"unknown phase: {phase}")
    phase_state = state.get("phases", {}).get(phase, {})
    if not isinstance(phase_state, dict):
        raise ValueError(f"state for phase {phase!r} is malformed")
    phase_contract = _phase_contract(contract, phase)
    artifacts = phase_state.get("artifacts") if isinstance(phase_state.get("artifacts"), dict) else {}
    proof = {str(item) for item in phase_state.get("proof", []) if str(item).strip()}
    project_root = Path(str(state.get("project_root", "."))).resolve()

    required_outputs = [str(item) for item in phase_contract.get("required_outputs", [])]
    required_proof = [str(item) for item in phase_contract.get("proof", [])]
    missing_outputs = [
        key for key in required_outputs
        if key not in artifacts or not _artifact_value_exists(artifacts.get(key), project_root)
    ]
    missing_proof = [item for item in required_proof if item not in proof]
    blockers = [str(item) for item in phase_state.get("blockers", []) if str(item).strip()]
    return {
        "phase": phase,
        "phase_status": phase_state.get("status", "pending"),
        "ready_to_complete": not missing_outputs and not missing_proof and not blockers,
        "missing_outputs": missing_outputs,
        "missing_proof": missing_proof,
        "blockers": blockers,
        "required_outputs": required_outputs,
        "required_proof": required_proof,
        "recipe": PHASE_RECIPES.get(phase, []),
        "recommended_tools": phase_contract.get("recommended_tools", []),
    }


def _score_from_artifacts(state: dict[str, Any]) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    score_phase = state.get("phases", {}).get("score", {})
    artifacts = score_phase.get("artifacts") if isinstance(score_phase, dict) and isinstance(score_phase.get("artifacts"), dict) else {}
    evidence_value = artifacts.get("ui_forge_score") or artifacts.get("evidence")
    if not evidence_value:
        return None, None
    project_root = Path(str(state.get("project_root", "."))).resolve()
    candidate = Path(str(evidence_value))
    if not candidate.is_absolute():
        candidate = project_root / candidate
    if not candidate.exists():
        return None, None
    evidence = _load_json(candidate)
    return evidence, ui_forge.score_ui_forge(evidence)


def _design_audit_from_state(state: dict[str, Any]) -> dict[str, Any] | None:
    project_root = Path(str(state.get("project_root", "."))).resolve()
    for phase in ("score", "repair_or_finish", "browser_proof"):
        entry = state.get("phases", {}).get(phase, {})
        artifacts = entry.get("artifacts") if isinstance(entry, dict) and isinstance(entry.get("artifacts"), dict) else {}
        raw = artifacts.get("design_audit")
        if not raw:
            continue
        path = Path(str(raw))
        if not path.is_absolute():
            path = project_root / path
        if path.exists():
            return _load_json(path)
    return None


def next_packet(state: dict[str, Any], contract: dict[str, Any]) -> dict[str, Any]:
    state_summary = workflow_state.summary(state)
    current = state_summary.get("current_phase")
    if current in (None, "done"):
        return {
            "schema": "ui-forge-conductor-v1",
            "workflow": state_summary,
            "current_phase": current,
            "next_action": "workflow complete" if current == "done" else "repair invalid workflow state",
            "readiness": None,
            "score_report": None,
            "repair_plan": None,
        }

    readiness = phase_readiness(state, contract, str(current))
    evidence, score_report = _score_from_artifacts(state)
    design_audit = _design_audit_from_state(state)
    generated_repair = repair_plan.build_repair_plan(score_report, design_audit) if score_report else None

    if current == "score" and score_report:
        next_action = (
            "record evidence_scored proof and complete score phase"
            if readiness["ready_to_complete"]
            else "satisfy missing score-phase evidence/proof, then complete score phase"
        )
    elif current == "repair_or_finish" and generated_repair:
        if generated_repair.get("already_passes"):
            next_action = "record stop_rule_evaluated and finish decision; do not restyle further"
        else:
            actions = generated_repair.get("actions") or []
            next_action = actions[0].get("action") if actions else "evaluate stop rule and record finish decision"
    elif readiness["ready_to_complete"]:
        next_action = f"complete phase {current}; all declared requirements are present"
    else:
        missing = readiness["missing_outputs"] + readiness["missing_proof"]
        next_action = f"collect missing phase evidence: {', '.join(missing)}" if missing else f"resolve blockers for phase {current}"

    return {
        "schema": "ui-forge-conductor-v1",
        "workflow": state_summary,
        "current_phase": current,
        "next_action": next_action,
        "readiness": readiness,
        "score_report": score_report,
        "repair_plan": generated_repair,
        "evidence_loaded": evidence is not None,
    }


def complete_phase(state: dict[str, Any], contract: dict[str, Any], phase: str) -> dict[str, Any]:
    current = state.get("current_phase")
    if current != phase:
        raise ValueError(f"cannot complete {phase!r}; current phase is {current!r}")
    readiness = phase_readiness(state, contract, phase)
    if not readiness["ready_to_complete"]:
        missing = readiness["missing_outputs"] + readiness["missing_proof"]
        details = []
        if missing:
            details.append("missing=" + ",".join(missing))
        if readiness["blockers"]:
            details.append("blockers=" + ",".join(readiness["blockers"]))
        raise ValueError(f"phase {phase!r} is not complete-ready ({'; '.join(details)})")
    return workflow_state.update_phase(state, phase, "complete")


def _parse_pairs(values: list[str] | None) -> dict[str, str]:
    out: dict[str, str] = {}
    for raw in values or []:
        if "=" not in raw:
            raise ValueError(f"expected key=value, got: {raw}")
        key, value = raw.split("=", 1)
        if not key.strip() or not value.strip():
            raise ValueError(f"key=value cannot contain an empty side: {raw}")
        out[key.strip()] = value.strip()
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fail-closed AI conductor for UI Forge workflow runs")
    parser.add_argument("--contract", default=str(DEFAULT_CONTRACT))
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init")
    init.add_argument("--project-root", required=True)
    init.add_argument("--goal", required=True)
    init.add_argument("--url")
    init.add_argument("--state")

    status = sub.add_parser("status")
    status.add_argument("state")

    record = sub.add_parser("record")
    record.add_argument("state")
    record.add_argument("--phase")
    record.add_argument("--proof", action="append")
    record.add_argument("--artifact", action="append")
    record.add_argument("--note", action="append")
    record.add_argument("--blocker", action="append")

    complete = sub.add_parser("complete")
    complete.add_argument("state")
    complete.add_argument("phase", choices=workflow_state.PHASES)

    args = parser.parse_args(argv)
    try:
        contract = _load_json(Path(args.contract).resolve())
        if args.command == "init":
            state_path = _resolve_state_path(args.project_root, args.state)
            state = workflow_state.new_state(args.project_root, args.goal, args.url)
            workflow_state.update_phase(state, "inspect", "running")
            _write_json(state_path, state)
            result = {"state_path": str(state_path), **next_packet(state, contract)}
        else:
            state_path = Path(args.state).resolve()
            state = _load_json(state_path)
            if args.command == "record":
                phase = args.phase or state.get("current_phase")
                if phase not in workflow_state.PHASES:
                    raise ValueError(f"cannot record against phase: {phase!r}")
                state = workflow_state.update_phase(
                    state,
                    str(phase),
                    "running",
                    proof=args.proof,
                    blockers=args.blocker,
                    notes=args.note,
                    artifacts=_parse_pairs(args.artifact),
                )
                _write_json(state_path, state)
            elif args.command == "complete":
                state = complete_phase(state, contract, args.phase)
                if state.get("current_phase") in workflow_state.PHASES:
                    state = workflow_state.update_phase(state, str(state["current_phase"]), "running")
                _write_json(state_path, state)
            result = {"state_path": str(state_path), **next_packet(state, contract)}
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}, indent=2))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
