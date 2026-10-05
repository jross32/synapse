#!/usr/bin/env python3
"""Deterministic benchmark for UI Forge browser-to-source precision.

This is intentionally not a model benchmark. It isolates one subsystem: mapping a rendered
DOM selection back to source when many JSX elements are semantically indistinguishable.
Baseline uses semantic/tag/text/class matching only. Challenger uses UI Forge's dev-only
`data-ui-forge-source` pointer. The same synthetic source tree and target sequence are used.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import math
import statistics
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
LOCATOR_PATH = REPO_ROOT / "templates" / "skills" / "ui-forge" / "scripts" / "source_locator.py"


def _load_locator():
    spec = importlib.util.spec_from_file_location("ui_forge_source_locator_bench", LOCATOR_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {LOCATOR_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _fixture(root: Path, count: int) -> list[str]:
    files: list[str] = []
    for index in range(count):
        relative = f"src/cards/Card{index:03d}.jsx"
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            "export function Card(){return <button className=\"action shared\">Continue</button>}\n",
            encoding="utf-8",
        )
        files.append(relative)
    return files


def _measure(action) -> tuple[float, Any]:
    started = time.perf_counter()
    result = action()
    return time.perf_counter() - started, result


def _stats(values: list[float]) -> dict[str, float]:
    ordered = sorted(values)
    return {
        "median_ms": round(statistics.median(values) * 1000, 4),
        "p90_ms": round(ordered[max(0, math.ceil(len(ordered) * 0.9) - 1)] * 1000, 4),
        "min_ms": round(min(values) * 1000, 4),
        "max_ms": round(max(values) * 1000, 4),
    }


def run(count: int, repeats: int) -> dict[str, Any]:
    locator = _load_locator()
    baseline_times: list[float] = []
    challenger_times: list[float] = []
    baseline_hits = 0
    challenger_hits = 0
    attempts = 0

    with tempfile.TemporaryDirectory(prefix="ui-forge-precision-") as temp:
        root = Path(temp)
        files = _fixture(root, count)
        target_sequence = [files[index % len(files)] for index in range(repeats)]
        for relative in target_sequence:
            target_line = 1
            # This is what a browser worker can know without UI Forge source tags: the target is
            # a button whose semantic/text/class signature is shared by many source locations.
            baseline_probe = {
                "tag": "button",
                "text": "Continue",
                "classes": ["action", "shared"],
            }
            # UI Forge adds the owning source pointer during development. Everything else remains
            # identical, so the benchmark isolates the source-tag treatment.
            challenger_probe = {
                **baseline_probe,
                "ui_forge_source": f"{relative}:{target_line}:31",
                "ui_forge_id": "fixture-id",
            }

            baseline_elapsed, baseline = _measure(lambda: locator.locate_source(root, baseline_probe, limit=1))
            challenger_elapsed, challenger = _measure(lambda: locator.locate_source(root, challenger_probe, limit=1))
            baseline_times.append(baseline_elapsed)
            challenger_times.append(challenger_elapsed)
            attempts += 1
            if baseline and baseline[0].get("file") == relative:
                baseline_hits += 1
            if challenger and challenger[0].get("file") == relative:
                challenger_hits += 1

    baseline_accuracy = baseline_hits / attempts
    challenger_accuracy = challenger_hits / attempts
    baseline_stats = _stats(baseline_times)
    challenger_stats = _stats(challenger_times)
    speed_ratio = baseline_stats["median_ms"] / max(challenger_stats["median_ms"], 0.0001)
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "scope": "deterministic browser-to-source disambiguation only",
        "fixture": {"ambiguous_source_files": count, "attempts": attempts},
        "baseline": {
            "treatment": "semantic DOM fingerprint only",
            "top1_accuracy": round(baseline_accuracy, 4),
            "timing": baseline_stats,
        },
        "challenger": {
            "treatment": "UI Forge data-ui-forge-source development tag",
            "top1_accuracy": round(challenger_accuracy, 4),
            "timing": challenger_stats,
        },
        "delta": {
            "accuracy_points": round((challenger_accuracy - baseline_accuracy) * 100, 2),
            "median_speed_ratio": round(speed_ratio, 2),
        },
        "claims": {
            "source_tag_precision_pass": challenger_accuracy == 1.0,
            "beats_semantic_baseline_accuracy": challenger_accuracy > baseline_accuracy,
            "not_a_full_ui_forge_or_lovable_claim": True,
        },
    }


def _summary(payload: dict[str, Any]) -> str:
    return f"""# UI Forge precision mapping benchmark

Scope: **{payload['scope']}**.

- Ambiguous source files: **{payload['fixture']['ambiguous_source_files']}**
- Attempts: **{payload['fixture']['attempts']}**
- Semantic-only baseline top-1 accuracy: **{payload['baseline']['top1_accuracy'] * 100:.1f}%**
- UI Forge source-tag top-1 accuracy: **{payload['challenger']['top1_accuracy'] * 100:.1f}%**
- Accuracy improvement: **+{payload['delta']['accuracy_points']:.2f} points**
- Median locator speed ratio: **{payload['delta']['median_speed_ratio']:.2f}x** baseline/challenger

This proves only the source-location subsystem on an intentionally ambiguous fixture. It does **not** prove full UI Forge quality or superiority to Lovable.
"""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--files", type=int, default=80)
    parser.add_argument("--repeats", type=int, default=80)
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parent / "results")
    args = parser.parse_args()
    if args.files < 2 or args.repeats < 2:
        parser.error("--files and --repeats must both be >= 2")
    payload = run(args.files, args.repeats)
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "latest.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    (args.output / "summary.md").write_text(_summary(payload), encoding="utf-8")
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
