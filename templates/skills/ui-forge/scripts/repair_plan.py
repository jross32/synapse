from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

DIMENSION_ACTIONS = {
    "request_fidelity": "Re-read the exact request and acceptance criteria; remove unrequested scope and trace every requested behavior to visible browser proof.",
    "visual_design": "Fix hierarchy first: focal point, typography scale, spacing rhythm, contrast, and surface depth before decorative detail.",
    "ux": "Shorten the primary path, clarify the dominant action, and repair state/recovery friction at the lowest-confidence user step.",
    "responsive": "Repair the smallest failing viewport first: overflow, wrapping, fixed widths, touch reachability, and content priority; then recheck desktop.",
    "accessibility": "Fix critical-path semantics, keyboard operation, visible focus, contrast, and status/error announcements; then rerun keyboard/structural proof.",
    "runtime_correctness": "Stop visual iteration and repair runtime/build/test/interaction regressions before further styling; reproduce in the running app and fix the smallest root cause.",
    "browser_proof": "Run the actual app and capture representative desktop/mobile evidence; exercise the primary path and relevant states and inspect console/runtime errors.",
    "originality": "Replace recognizable template/vendor mimicry with product-specific hierarchy, interaction, copy, and component composition; synthesize references rather than copying pixels.",
}


def _load(path: str | None) -> dict[str, Any]:
    if not path:
        return {}
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _design_drift_action(design_audit: dict[str, Any] | None) -> tuple[dict[str, Any], dict[str, Any] | None]:
    if not design_audit:
        return {}, None
    counts = design_audit.get("counts") if isinstance(design_audit.get("counts"), dict) else {}
    adherence = design_audit.get("adherence_score")
    summary = {"adherence_score": adherence, "counts": counts}
    numeric = [int(v) for v in counts.values() if isinstance(v, int)]
    total = sum(numeric)
    attention = isinstance(adherence, (int, float)) and not isinstance(adherence, bool) and float(adherence) < 85
    if not attention and total == 0:
        return summary, None
    top = sorted(((int(v), str(k)) for k, v in counts.items() if isinstance(v, int) and v > 0), reverse=True)[:3]
    return summary, {
        "priority": 2,
        "kind": "design_system_drift",
        "reason": f"design adherence is {adherence}; {total} drift finding(s); top kinds: {top}",
        "action": "Consolidate repeated one-off values into semantic tokens/shared variants, starting with the highest-frequency drift. Preserve intentional exceptions, then rerun the audit and browser proof.",
    }


def build_repair_plan(score_report: dict[str, Any], design_audit: dict[str, Any] | None = None, max_actions: int = 8) -> dict[str, Any]:
    scores = score_report.get("scores") if isinstance(score_report.get("scores"), dict) else {}
    blocking = score_report.get("blocking_reasons") if isinstance(score_report.get("blocking_reasons"), list) else []
    pass_state = bool(score_report.get("pass"))
    actions: list[dict[str, Any]] = []

    for reason in blocking:
        text = str(reason)
        if "critical failure" in text:
            actions.append({"priority": 0, "kind": "critical", "reason": text, "action": "Resolve and re-prove this critical failure before any visual polish."})
        elif "runtime_correctness" in text:
            actions.append({"priority": 1, "kind": "runtime_correctness", "reason": text, "action": DIMENSION_ACTIONS["runtime_correctness"]})
        elif "browser_proof" in text:
            actions.append({"priority": 1, "kind": "browser_proof", "reason": text, "action": DIMENSION_ACTIONS["browser_proof"]})
        else:
            actions.append({"priority": 2, "kind": "gate", "reason": text, "action": "Raise the weakest measured dimensions with the smallest high-leverage repair, then rescore."})

    design_summary, drift_action = _design_drift_action(design_audit)
    if drift_action is not None:
        actions.append(drift_action)

    existing = {item["kind"] for item in actions}
    ranked: list[tuple[float, str]] = []
    for name in DIMENSION_ACTIONS:
        value = scores.get(name)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            continue
        ranked.append((float(value), name))
    ranked.sort(key=lambda item: (item[0], item[1]))

    # Failed gates need repair. Passing gates should not trigger endless restyling: only
    # surface truly weak (<85) dimensions as required work. Scores below 90 are reported
    # separately as optional next-focus hints.
    for value, name in ranked:
        if name in existing or value >= 85:
            continue
        actions.append({"priority": 2, "kind": name, "reason": f"{name} score is {value:.1f}", "action": DIMENSION_ACTIONS[name]})
        existing.add(name)
        if len(actions) >= max_actions:
            break

    actions.sort(key=lambda item: (item["priority"], item["kind"]))
    actions = actions[:max_actions]
    optional_focus = [
        {"kind": name, "score": value}
        for value, name in ranked
        if 85 <= value < 90 and name not in {item["kind"] for item in actions}
    ][:3]

    return {
        "already_passes": pass_state and not actions,
        "score_gate_passes": pass_state,
        "blocking_reasons": blocking,
        "design_audit": design_summary,
        "actions": actions,
        "optional_next_focus": optional_focus,
        "stop_rule": "Stop when the score gate passes, no structural drift/action remains, and unresolved issues are explicit low-risk tradeoffs.",
        "repair_loop": [
            "fix only the first highest-priority root cause",
            "run/build the app",
            "repeat only the affected browser proof",
            "rerun structural audit when relevant",
            "rescore UI Forge evidence",
            "stop when the gate and stop rule are satisfied",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate a deterministic UI Forge repair plan")
    parser.add_argument("score_report", help="JSON output from ui_forge.py")
    parser.add_argument("--design-audit", help="Optional JSON output from design_audit.py")
    parser.add_argument("--max-actions", type=int, default=8)
    args = parser.parse_args(argv)
    try:
        score_report = _load(args.score_report)
        design_audit = _load(args.design_audit) if args.design_audit else None
        result = build_repair_plan(score_report, design_audit, max(1, min(args.max_actions, 20)))
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({"error": str(exc)}, indent=2))
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
