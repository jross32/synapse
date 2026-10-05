#!/usr/bin/env python3
"""Deterministic safety/precision benchmark for UI Forge direct JSX edits.

This benchmark measures only the local direct-edit subsystem. It does not benchmark
model quality, full UI Forge app-building quality, or Lovable.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
EDITOR = REPO_ROOT / "templates" / "skills" / "ui-forge" / "scripts" / "direct_ast_edit.mjs"


def _run(root: Path, edit: dict[str, Any]) -> tuple[int, dict[str, Any], float]:
    edit_path = root / "edit.json"
    edit_path.write_text(json.dumps(edit), encoding="utf-8")
    started = time.perf_counter()
    proc = subprocess.run(
        ["node", str(EDITOR), str(root), str(edit_path)],
        text=True,
        capture_output=True,
        check=False,
    )
    elapsed = time.perf_counter() - started
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError:
        payload = {"ok": False, "error": "non-JSON editor output", "stdout": proc.stdout, "stderr": proc.stderr}
    return proc.returncode, payload, elapsed


def _pointer(source: str, needle: str = "<button") -> str:
    return f"src/App.jsx:1:{source.index(needle) + 1}"


def _positive_cases(repeats_per_kind: int) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    for index in range(repeats_per_kind):
        name = f"Text{index:02d}"
        before = f'export function {name}(){{return <button className="go">Go</button>}}\n'
        after = before.replace(">Go</button>", f">Launch {index}</button>")
        cases.append({
            "id": f"text-{index:02d}",
            "before": before,
            "after": after,
            "edit": {"operation": {"type": "set_text", "value": f"Launch {index}"}},
        })

        name = f"Class{index:02d}"
        before = f'export function {name}(){{return <button className="go">Go</button>}}\n'
        after = before.replace('className="go"', 'className="go px-4 font-semibold"')
        cases.append({
            "id": f"class-{index:02d}",
            "before": before,
            "after": after,
            "edit": {"operation": {"type": "class_tokens", "add": ["px-4", "font-semibold"]}},
        })

        name = f"Attr{index:02d}"
        before = f'export function {name}(){{return <button className="go">Go</button>}}\n'
        after = before.replace('className="go">', f'className="go" aria-label="Launch item {index}">')
        cases.append({
            "id": f"attr-{index:02d}",
            "before": before,
            "after": after,
            "edit": {"operation": {"type": "set_attribute", "name": "aria-label", "value": f"Launch item {index}"}},
        })
    return cases


def _negative_cases(repeats: int) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    for index in range(repeats):
        dynamic = f'export function Dynamic{index:02d}({{kind}}){{return <button className={{kind}}>Go</button>}}\n'
        cases.append({
            "id": f"dynamic-class-{index:02d}",
            "before": dynamic,
            "edit": {"operation": {"type": "class_tokens", "add": ["px-4"]}},
            "error_contains": "dynamic className",
        })
        nested = f'export function Nested{index:02d}(){{return <button><span>Go</span></button>}}\n'
        cases.append({
            "id": f"nested-text-{index:02d}",
            "before": nested,
            "edit": {"operation": {"type": "set_text", "value": "Launch"}},
            "error_contains": "exactly one static JSX text child",
        })
    return cases


def run_suite(repeats_per_kind: int, negative_repeats: int) -> dict[str, Any]:
    positive = _positive_cases(repeats_per_kind)
    negative = _negative_cases(negative_repeats)
    results: list[dict[str, Any]] = []
    timings: list[float] = []
    positive_passes = 0
    negative_passes = 0

    with tempfile.TemporaryDirectory(prefix="ui-forge-direct-edit-") as temp:
        root = Path(temp)
        src = root / "src"
        src.mkdir(parents=True)
        target = src / "App.jsx"

        for case in positive:
            target.write_text(case["before"], encoding="utf-8")
            edit = dict(case["edit"])
            edit["source"] = _pointer(case["before"])
            code, payload, elapsed = _run(root, edit)
            timings.append(elapsed)
            actual = target.read_text(encoding="utf-8")
            exact = actual == case["after"]
            passed = code == 0 and payload.get("ok") is True and exact
            positive_passes += int(passed)
            results.append({
                "id": case["id"],
                "kind": "positive",
                "passed": passed,
                "exact_source_match": exact,
                "exit_code": code,
                "schema": payload.get("schema"),
            })

        for case in negative:
            target.write_text(case["before"], encoding="utf-8")
            edit = dict(case["edit"])
            edit["source"] = _pointer(case["before"])
            code, payload, elapsed = _run(root, edit)
            timings.append(elapsed)
            unchanged = target.read_text(encoding="utf-8") == case["before"]
            expected_error = case["error_contains"] in str(payload.get("error", ""))
            passed = code != 0 and payload.get("ok") is False and unchanged and expected_error
            negative_passes += int(passed)
            results.append({
                "id": case["id"],
                "kind": "negative",
                "passed": passed,
                "source_unchanged": unchanged,
                "expected_refusal": expected_error,
                "exit_code": code,
            })

    ordered = sorted(timings)
    total = len(results)
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "scope": "deterministic static-JSX direct-edit precision and refusal safety only",
        "cases": {
            "positive": len(positive),
            "negative": len(negative),
            "total": total,
        },
        "positive": {
            "passed": positive_passes,
            "pass_rate": round(positive_passes / max(1, len(positive)), 4),
            "exact_source_preservation_rate": round(
                sum(1 for item in results if item["kind"] == "positive" and item["exact_source_match"]) / max(1, len(positive)),
                4,
            ),
        },
        "negative": {
            "passed": negative_passes,
            "pass_rate": round(negative_passes / max(1, len(negative)), 4),
            "unchanged_on_refusal_rate": round(
                sum(1 for item in results if item["kind"] == "negative" and item["source_unchanged"]) / max(1, len(negative)),
                4,
            ),
        },
        "timing": {
            "median_ms": round(ordered[len(ordered) // 2] * 1000, 3) if ordered else 0.0,
            "max_ms": round(max(ordered) * 1000, 3) if ordered else 0.0,
        },
        "overall_pass": positive_passes == len(positive) and negative_passes == len(negative),
        "claims": {
            "safe_static_direct_edit_gate": positive_passes == len(positive) and negative_passes == len(negative),
            "not_a_full_ui_forge_or_lovable_claim": True,
        },
        "results": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repeats-per-kind", type=int, default=12)
    parser.add_argument("--negative-repeats", type=int, default=6)
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parent / "results" / "direct_edit_latest.json")
    args = parser.parse_args()
    payload = run_suite(max(1, args.repeats_per_kind), max(1, args.negative_repeats))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in payload.items() if key != "results"}, indent=2))
    return 0 if payload["overall_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
