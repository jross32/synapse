from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

ROLES = {
    "visual_direction",
    "implementation",
    "repair",
    "correctness_review",
    "ux_review",
    "accessibility_review",
}


def _load_json(path: str) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _num(value: Any, default: float = 0.0) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return default
    return float(value)


def _role_stats(candidate: dict[str, Any], role: str) -> dict[str, Any]:
    roles = candidate.get("roles") if isinstance(candidate.get("roles"), dict) else {}
    stats = roles.get(role)
    return stats if isinstance(stats, dict) else {}


def route_model(
    runtime_status: list[dict[str, Any]],
    scorecard: dict[str, Any],
    role: str,
    minimum_runs: int = 5,
    preference: str = "quality",
) -> dict[str, Any]:
    if role not in ROLES:
        raise ValueError(f"unknown role: {role}")
    if preference not in {"quality", "balanced", "speed"}:
        raise ValueError(f"unknown preference: {preference}")

    available = {
        str(item.get("runtime")): item
        for item in runtime_status
        if isinstance(item, dict) and item.get("runtime") and bool(item.get("installed")) and bool(item.get("usable_now"))
    }
    candidates = scorecard.get("candidates") if isinstance(scorecard.get("candidates"), list) else []
    ranked: list[dict[str, Any]] = []

    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        runtime = str(candidate.get("runtime") or "")
        if runtime not in available:
            continue
        stats = _role_stats(candidate, role)
        runs = int(_num(stats.get("runs"), 0))
        if runs < minimum_runs:
            continue
        quality = max(0.0, min(100.0, _num(stats.get("median_quality"))))
        pass_rate = max(0.0, min(1.0, _num(stats.get("pass_rate"))))
        median_seconds = max(0.0, _num(stats.get("median_time_to_pass_seconds")))
        median_cost = max(0.0, _num(stats.get("median_cost_usd")))
        # Speed is deliberately capped and contributes less than quality. Unknown time
        # receives no speed bonus instead of being guessed.
        speed_score = 0.0 if median_seconds <= 0 else max(0.0, min(100.0, 100.0 * (300.0 / median_seconds)))
        if preference == "quality":
            utility = quality * 0.72 + (pass_rate * 100.0) * 0.23 + speed_score * 0.05
        elif preference == "speed":
            utility = quality * 0.50 + (pass_rate * 100.0) * 0.20 + speed_score * 0.30
        else:
            utility = quality * 0.60 + (pass_rate * 100.0) * 0.25 + speed_score * 0.15
        ranked.append({
            "runtime": runtime,
            "model": str(candidate.get("model") or ""),
            "role": role,
            "runs": runs,
            "median_quality": quality,
            "pass_rate": pass_rate,
            "median_time_to_pass_seconds": median_seconds or None,
            "median_cost_usd": median_cost or None,
            "utility": round(utility, 3),
            "runtime_note": str(available[runtime].get("note") or ""),
        })

    ranked.sort(key=lambda item: (-item["utility"], -item["median_quality"], item["runtime"], item["model"]))
    if not ranked:
        return {
            "status": "insufficient_evidence",
            "role": role,
            "selected": None,
            "available_runtimes": sorted(available),
            "minimum_runs": minimum_runs,
            "reason": "No currently usable runtime has enough comparable benchmark runs for this role. Keep the current worker or run the UI Forge benchmark; do not invent a model ranking.",
        }

    return {
        "status": "selected",
        "role": role,
        "preference": preference,
        "selected": ranked[0],
        "alternatives": ranked[1:4],
        "minimum_runs": minimum_runs,
        "reason": "Selection is based only on comparable scorecard evidence for currently usable runtimes.",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Route a UI Forge role using measured benchmark evidence")
    parser.add_argument("runtime_status", help="JSON file containing Synapse runtime status list")
    parser.add_argument("scorecard", help="UI Forge model scorecard JSON")
    parser.add_argument("role", choices=sorted(ROLES))
    parser.add_argument("--minimum-runs", type=int, default=5)
    parser.add_argument("--preference", choices=["quality", "balanced", "speed"], default="quality")
    args = parser.parse_args(argv)
    try:
        statuses = _load_json(args.runtime_status)
        scorecard = _load_json(args.scorecard)
        if not isinstance(statuses, list):
            raise ValueError("runtime_status must be a JSON list")
        if not isinstance(scorecard, dict):
            raise ValueError("scorecard must be a JSON object")
        result = route_model(statuses, scorecard, args.role, max(1, args.minimum_runs), args.preference)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({"error": str(exc)}, indent=2))
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
