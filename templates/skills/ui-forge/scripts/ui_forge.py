from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

DIMENSIONS = {
    "request_fidelity": 0.15,
    "visual_design": 0.18,
    "ux": 0.15,
    "responsive": 0.10,
    "accessibility": 0.09,
    "runtime_correctness": 0.15,
    "browser_proof": 0.10,
    "originality": 0.08,
}


def _score(section: Any) -> float:
    if not isinstance(section, dict):
        return 0.0
    value = section.get("score", 0)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return 0.0
    return max(0.0, min(100.0, float(value)))


def validate_evidence(evidence: dict) -> list[str]:
    errors: list[str] = []
    if not isinstance(evidence, dict):
        return ["evidence must be a JSON object"]
    for name in DIMENSIONS:
        section = evidence.get(name)
        if section is None:
            errors.append(f"missing dimension: {name}")
            continue
        if not isinstance(section, dict):
            errors.append(f"{name} must be an object")
            continue
        value = section.get("score")
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            errors.append(f"{name}.score must be numeric")
        elif not 0 <= float(value) <= 100:
            errors.append(f"{name}.score must be between 0 and 100")
    failures = evidence.get("critical_failures", [])
    if failures is not None and not isinstance(failures, list):
        errors.append("critical_failures must be a list")
    screenshots = evidence.get("screenshots", [])
    if screenshots is not None and not isinstance(screenshots, list):
        errors.append("screenshots must be a list")
    return errors


def score_ui_forge(evidence: dict) -> dict:
    validation_errors = validate_evidence(evidence)
    scores = {name: _score(evidence.get(name)) for name in DIMENSIONS}
    weighted_total = round(sum(scores[name] * weight for name, weight in DIMENSIONS.items()), 2)
    critical = evidence.get("critical_failures", []) if isinstance(evidence, dict) else []
    if not isinstance(critical, list):
        critical = ["critical_failures malformed"]

    blocking_reasons: list[str] = []
    if critical:
        blocking_reasons.extend(f"critical failure: {item}" for item in critical)
    if scores["runtime_correctness"] < 85:
        blocking_reasons.append("runtime_correctness below 85")
    if scores["browser_proof"] < 80:
        blocking_reasons.append("browser_proof below 80")
    if weighted_total < 85:
        blocking_reasons.append("weighted_total below 85")

    warnings = list(validation_errors)
    screenshots = evidence.get("screenshots", []) if isinstance(evidence, dict) else []
    if not screenshots:
        warnings.append("no screenshots supplied")

    next_focus = [name for name, _ in sorted(scores.items(), key=lambda item: (item[1], item[0]))[:3]]
    return {
        "scores": scores,
        "weights": DIMENSIONS,
        "weighted_total": weighted_total,
        "pass": not blocking_reasons,
        "blocking_reasons": blocking_reasons,
        "warnings": warnings,
        "next_focus": next_focus,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Score UI Forge evidence JSON")
    parser.add_argument("evidence", help="Path to evidence JSON")
    args = parser.parse_args(argv)
    try:
        payload = json.loads(Path(args.evidence).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}, indent=2))
        return 2
    result = score_ui_forge(payload)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
