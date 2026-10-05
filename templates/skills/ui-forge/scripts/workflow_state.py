from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

PHASES = [
    "inspect",
    "design_grammar",
    "plan",
    "implement",
    "browser_proof",
    "score",
    "repair_or_finish",
    "learn",
]
TERMINAL = {"done", "blocked"}


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _read(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("workflow state must be a JSON object")
    return payload


def _write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def new_state(project_root: str, goal: str, target_url: str | None = None) -> dict[str, Any]:
    created = _now()
    return {
        "schema": "ui-forge-run-state-v1",
        "project_root": str(Path(project_root).resolve()),
        "goal": goal.strip(),
        "target_url": target_url or None,
        "created_at": created,
        "updated_at": created,
        "status": "running",
        "current_phase": "inspect",
        "phases": {
            phase: {
                "status": "pending",
                "started_at": None,
                "completed_at": None,
                "artifacts": {},
                "proof": [],
                "blockers": [],
                "notes": [],
            }
            for phase in PHASES
        },
        "history": [],
    }


def _next_incomplete(payload: dict[str, Any]) -> str:
    for phase in PHASES:
        if payload["phases"][phase]["status"] != "complete":
            return phase
    return "done"


def update_phase(
    payload: dict[str, Any],
    phase: str,
    status: str,
    *,
    proof: list[str] | None = None,
    blockers: list[str] | None = None,
    notes: list[str] | None = None,
    artifacts: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if phase not in PHASES:
        raise ValueError(f"unknown phase: {phase}")
    if status not in {"running", "complete", "blocked"}:
        raise ValueError("status must be running, complete, or blocked")
    entry = payload["phases"][phase]
    now = _now()
    if entry["started_at"] is None:
        entry["started_at"] = now
    entry["status"] = status
    if proof:
        entry["proof"] = sorted(set(entry.get("proof", [])) | {str(item) for item in proof})
    if blockers:
        entry["blockers"] = sorted(set(entry.get("blockers", [])) | {str(item) for item in blockers})
    if notes:
        entry["notes"].extend(str(item) for item in notes)
    if artifacts:
        entry["artifacts"].update(artifacts)
    if status == "complete":
        entry["completed_at"] = now
    payload["history"].append({"at": now, "phase": phase, "status": status})
    payload["updated_at"] = now
    if status == "blocked":
        payload["status"] = "blocked"
        payload["current_phase"] = phase
    else:
        nxt = _next_incomplete(payload)
        payload["current_phase"] = nxt
        payload["status"] = "done" if nxt == "done" else "running"
    return payload


def validate_state(payload: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if payload.get("schema") != "ui-forge-run-state-v1":
        errors.append("unexpected or missing schema")
    phases = payload.get("phases")
    if not isinstance(phases, dict):
        return errors + ["phases must be an object"]
    for phase in PHASES:
        if phase not in phases:
            errors.append(f"missing phase: {phase}")
            continue
        status = phases[phase].get("status")
        if status not in {"pending", "running", "complete", "blocked"}:
            errors.append(f"invalid status for {phase}: {status}")
    return errors


def summary(payload: dict[str, Any]) -> dict[str, Any]:
    errors = validate_state(payload)
    completed = [phase for phase in PHASES if payload.get("phases", {}).get(phase, {}).get("status") == "complete"]
    blocked = [phase for phase in PHASES if payload.get("phases", {}).get(phase, {}).get("status") == "blocked"]
    current = payload.get("current_phase", _next_incomplete(payload) if not errors else None)
    return {
        "valid": not errors,
        "errors": errors,
        "status": payload.get("status"),
        "current_phase": current,
        "completed": completed,
        "blocked": blocked,
        "next_action": (
            "workflow complete"
            if current == "done"
            else f"execute UI Forge phase: {current}"
            if current
            else "repair invalid state"
        ),
    }


def _parse_pairs(values: list[str] | None) -> dict[str, str]:
    out: dict[str, str] = {}
    for value in values or []:
        if "=" not in value:
            raise ValueError(f"artifact must be key=value: {value}")
        key, item = value.split("=", 1)
        if not key.strip():
            raise ValueError("artifact key cannot be empty")
        out[key.strip()] = item
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Persistent state machine for AI workers running UI Forge")
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init")
    init.add_argument("state")
    init.add_argument("--project-root", required=True)
    init.add_argument("--goal", required=True)
    init.add_argument("--url")

    mutate = sub.add_parser("phase")
    mutate.add_argument("state")
    mutate.add_argument("phase", choices=PHASES)
    mutate.add_argument("status", choices=["running", "complete", "blocked"])
    mutate.add_argument("--proof", action="append")
    mutate.add_argument("--blocker", action="append")
    mutate.add_argument("--note", action="append")
    mutate.add_argument("--artifact", action="append")

    show = sub.add_parser("show")
    show.add_argument("state")

    args = parser.parse_args(argv)
    path = Path(args.state)
    try:
        if args.command == "init":
            payload = new_state(args.project_root, args.goal, args.url)
            _write(path, payload)
        else:
            payload = _read(path)
            if args.command == "phase":
                payload = update_phase(
                    payload,
                    args.phase,
                    args.status,
                    proof=args.proof,
                    blockers=args.blocker,
                    notes=args.note,
                    artifacts=_parse_pairs(args.artifact),
                )
                _write(path, payload)
        print(json.dumps(summary(payload), indent=2, sort_keys=True))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}, indent=2))
        return 2
    return 0 if not validate_state(payload) else 1


if __name__ == "__main__":
    raise SystemExit(main())
