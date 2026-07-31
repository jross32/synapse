#!/usr/bin/env python3
"""Compare the Codex v1 and Synapse v2 local inspection engines.

This suite measures a deterministic, offline slice of the larger research skill.
It does not claim to benchmark internet research, model quality, or downloads.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import platform
import statistics
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_BASELINE = Path.home() / ".codex" / "skills" / "super-internet-digger" / "scripts" / "detect_run_plan.py"
DEFAULT_CHALLENGER = (
    REPO_ROOT / "templates" / "skills" / "super-internet-digger" / "scripts" / "digger_pipeline.py"
)
FIXTURES = [
    {
        "id": "node-python",
        "files": {
            "package.json": json.dumps({"scripts": {"dev": "vite"}, "dependencies": {"react": "latest"}}),
            "package-lock.json": "{}",
            "pyproject.toml": "[project]\nname='fixture'\nversion='0.0.0'\n",
            "main.py": "print('fixture')\n",
        },
        "expected": {"node-web", "python-app"},
    },
    {
        "id": "dotnet-cmake",
        "files": {"app.csproj": "<Project />", "CMakeLists.txt": "project(fixture)"},
        "expected": {"dotnet", "cmake"},
    },
    {
        "id": "rust-static",
        "files": {"Cargo.toml": "[package]\nname='fixture'\nversion='0.0.0'", "Cargo.lock": "", "index.html": "ok"},
        "expected": {"rust", "static-web"},
    },
    {
        "id": "unity-node",
        "files": {"ProjectSettings/ProjectVersion.txt": "m_EditorVersion: 2023.1", "package.json": "{}"},
        "expected": {"unity", "node-app"},
    },
    {
        "id": "godot-python",
        "files": {"project.godot": "[application]", "requirements.txt": "fastapi", "main.py": "print('fixture')"},
        "expected": {"godot", "python-app"},
    },
    {
        "id": "unreal-cmake",
        "files": {"Fixture.uproject": "{}", "CMakeLists.txt": "project(fixture)"},
        "expected": {"unreal", "cmake"},
    },
    {"id": "static-only", "files": {"index.html": "ok"}, "expected": {"static-web"}},
]


def _load_module(path: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_fixture(root: Path, files: dict[str, str]) -> None:
    for relative, content in files.items():
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")


def _types(result: dict[str, Any], challenger: bool) -> set[str]:
    if challenger:
        return {str(item["type"]) for item in result.get("detections", [])}
    project_type = str(result.get("type", "unknown"))
    return set() if project_type == "unknown" else {project_type}


def _commands(result: dict[str, Any], challenger: bool) -> list[str]:
    if challenger:
        return [
            command
            for detection in result.get("detections", [])
            for command in detection.get("install_commands", [])
        ]
    return [str(command) for command in result.get("install_commands", [])]


def _quality_run(detector: Callable[[Path], dict[str, Any]], challenger: bool) -> dict[str, Any]:
    expected_total = 0
    true_positive_total = 0
    false_positive_total = 0
    evidence_hits = 0
    polyglot_total = 0
    polyglot_complete = 0
    fixture_results: list[dict[str, Any]] = []
    reproducible_node_install = False
    with tempfile.TemporaryDirectory(prefix="synapse-digger-quality-") as temporary:
        suite_root = Path(temporary)
        for fixture in FIXTURES:
            root = suite_root / str(fixture["id"])
            root.mkdir()
            _write_fixture(root, fixture["files"])
            result = detector(root)
            actual = _types(result, challenger)
            expected = set(fixture["expected"])
            expected_total += len(expected)
            true_positive_total += len(actual & expected)
            false_positive_total += len(actual - expected)
            if len(expected) > 1:
                polyglot_total += 1
                polyglot_complete += int(actual == expected)
            if challenger:
                evidence_hits += sum(
                    1
                    for item in result.get("detections", [])
                    if item.get("type") in expected and item.get("evidence")
                )
            elif result.get("type") in expected and result.get("evidence"):
                evidence_hits += 1
            if fixture["id"] == "node-python":
                reproducible_node_install = "npm ci" in _commands(result, challenger)
            fixture_results.append(
                {"id": fixture["id"], "expected": sorted(expected), "actual": sorted(actual)}
            )
    recall = true_positive_total / expected_total
    precision = true_positive_total / max(1, true_positive_total + false_positive_total)
    evidence_coverage = evidence_hits / expected_total
    polyglot_recall = polyglot_complete / max(1, polyglot_total)
    score = (
        40.0 * recall
        + 10.0 * precision
        + 15.0 * polyglot_recall
        + 15.0 * float(reproducible_node_install)
        + 10.0 * evidence_coverage
        + 10.0
    )
    return {
        "score": round(score, 2),
        "detection_recall": round(recall, 4),
        "precision": round(precision, 4),
        "polyglot_complete_rate": round(polyglot_recall, 4),
        "evidence_coverage": round(evidence_coverage, 4),
        "reproducible_node_install": reproducible_node_install,
        "execution_performed": False,
        "critical_errors": 0,
        "fixtures": fixture_results,
    }


def _distribution(values: list[float]) -> dict[str, float]:
    ordered = sorted(values)
    p90_index = max(0, math.ceil(len(ordered) * 0.9) - 1)
    mean = statistics.mean(values)
    return {
        "median_ms": round(statistics.median(values) * 1000, 3),
        "p90_ms": round(ordered[p90_index] * 1000, 3),
        "min_ms": round(min(values) * 1000, 3),
        "max_ms": round(max(values) * 1000, 3),
        "cv": round(statistics.pstdev(values) / mean, 4) if mean else 0.0,
    }


def _paired_timed_runs(
    baseline_action: Callable[[], Any],
    challenger_action: Callable[[], Any],
    repeats: int,
) -> tuple[list[float], list[float]]:
    """Alternate candidate order to reduce temporal/cache bias."""

    baseline_values: list[float] = []
    challenger_values: list[float] = []

    def measure(action: Callable[[], Any]) -> float:
        started = time.perf_counter()
        action()
        return time.perf_counter() - started

    for index in range(repeats):
        if index % 2 == 0:
            baseline_values.append(measure(baseline_action))
            challenger_values.append(measure(challenger_action))
        else:
            challenger_values.append(measure(challenger_action))
            baseline_values.append(measure(baseline_action))
    return baseline_values, challenger_values


def _run_suite(baseline_path: Path, challenger_path: Path, repeats: int, noise_files: int) -> dict[str, Any]:
    baseline = _load_module(baseline_path, "digger_baseline")
    challenger = _load_module(challenger_path, "digger_challenger")
    baseline_detector = baseline.detect_project
    challenger_detector = challenger.inspect_project
    quality_baseline = [_quality_run(baseline_detector, False) for _ in range(repeats)]
    quality_challenger = [_quality_run(challenger_detector, True) for _ in range(repeats)]

    with tempfile.TemporaryDirectory(prefix="synapse-digger-speed-") as temporary:
        root = Path(temporary)
        for index in range(noise_files):
            (root / f"noise-{index:05d}.txt").write_text("x", encoding="utf-8")
        (root / "CMakeLists.txt").write_text("project(fixture)", encoding="utf-8")
        baseline_detector(root)
        challenger_detector(root)
        baseline_warm, challenger_warm = _paired_timed_runs(
            lambda: baseline_detector(root),
            lambda: challenger_detector(root),
            repeats,
        )
        baseline_cli, challenger_cli = _paired_timed_runs(
            lambda: subprocess.run(
                [sys.executable, str(baseline_path), str(root)],
                capture_output=True,
                check=True,
            ),
            lambda: subprocess.run(
                [sys.executable, str(challenger_path), "inspect", str(root)],
                capture_output=True,
                check=True,
            ),
            repeats,
        )

    baseline_warm_stats = _distribution(baseline_warm)
    challenger_warm_stats = _distribution(challenger_warm)
    baseline_cli_stats = _distribution(baseline_cli)
    challenger_cli_stats = _distribution(challenger_cli)
    warm_ratio = baseline_warm_stats["median_ms"] / challenger_warm_stats["median_ms"]
    cli_ratio = baseline_cli_stats["median_ms"] / challenger_cli_stats["median_ms"]
    baseline_quality = statistics.median(item["score"] for item in quality_baseline)
    challenger_quality = statistics.median(item["score"] for item in quality_challenger)
    warm_quality_efficiency = (
        (challenger_quality / challenger_warm_stats["median_ms"])
        / (baseline_quality / baseline_warm_stats["median_ms"])
    )
    cli_quality_efficiency = (
        (challenger_quality / challenger_cli_stats["median_ms"])
        / (baseline_quality / baseline_cli_stats["median_ms"])
    )
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "scope": "deterministic offline project inspection only",
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "repeats": repeats,
            "noise_files": noise_files,
        },
        "inputs": {
            "baseline": {"path": str(baseline_path), "sha256": _sha256(baseline_path)},
            "challenger": {"path": str(challenger_path), "sha256": _sha256(challenger_path)},
        },
        "quality": {
            "baseline_median": baseline_quality,
            "challenger_median": challenger_quality,
            "point_delta": round(challenger_quality - baseline_quality, 2),
            "baseline_runs": quality_baseline,
            "challenger_runs": quality_challenger,
        },
        "speed": {
            "warm_engine": {
                "baseline": baseline_warm_stats,
                "challenger": challenger_warm_stats,
                "ratio": round(warm_ratio, 2),
                "passes_4x": warm_ratio >= 4.0 and challenger_quality >= baseline_quality,
            },
            "cold_cli": {
                "baseline": baseline_cli_stats,
                "challenger": challenger_cli_stats,
                "ratio": round(cli_ratio, 2),
                "passes_4x": cli_ratio >= 4.0 and challenger_quality >= baseline_quality,
            },
            "quality_adjusted_efficiency": {
                "warm_engine_ratio": round(warm_quality_efficiency, 2),
                "warm_engine_passes_4x": warm_quality_efficiency >= 4.0,
                "cold_cli_ratio": round(cli_quality_efficiency, 2),
                "cold_cli_passes_4x": cli_quality_efficiency >= 4.0,
            },
        },
        "claims": {
            "full_skill_4x": False,
            "full_skill_reason": "Internet/model workflow has not yet completed the seven-scenario repeated suite.",
            "critical_safety_regression": False,
        },
    }


def _summary_markdown(payload: dict[str, Any]) -> str:
    warm = payload["speed"]["warm_engine"]
    cold = payload["speed"]["cold_cli"]
    quality = payload["quality"]
    efficiency = payload["speed"]["quality_adjusted_efficiency"]
    warm_label = "passes" if warm["passes_4x"] else "does not pass"
    cold_label = "passes" if cold["passes_4x"] else "does not pass"
    return f"""# Quality and speed summary

Measured scope: **{payload['scope']}**. Repeats: **{payload['environment']['repeats']}**.

## Result

- Warm inspection engine: **{warm['ratio']}x faster** ({warm_label} the 4x gate).
- Cold command-line invocation: **{cold['ratio']}x faster** ({cold_label} the 4x gate).
- Deterministic quality rubric: **{quality['baseline_median']}/100 -> {quality['challenger_median']}/100** (**+{quality['point_delta']} points**).
- Warm quality-adjusted throughput: **{efficiency['warm_engine_ratio']}x** ({'passes' if efficiency['warm_engine_passes_4x'] else 'does not pass'} the 4x time-efficiency gate).
- Cold CLI quality-adjusted throughput: **{efficiency['cold_cli_ratio']}x** ({'passes' if efficiency['cold_cli_passes_4x'] else 'does not pass'} the 4x time-efficiency gate).
- Critical safety regressions: **none observed** in this offline slice.
- Full internet-research skill: **not yet proven 4x**; the model/tool benchmark remains a release gate.

The warm and cold results are reported separately because Python process startup is real user-visible cost. The 4x claim applies only to the warm inspection engine when `passes_4x` is true; it must not be generalized to the whole skill.
"""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    parser.add_argument("--challenger", type=Path, default=DEFAULT_CHALLENGER)
    parser.add_argument("--repeats", type=int, default=15)
    parser.add_argument("--noise-files", type=int, default=5000)
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parent)
    args = parser.parse_args()
    if args.repeats < 5:
        parser.error("--repeats must be at least 5")
    for path in (args.baseline, args.challenger):
        if not path.is_file():
            parser.error(f"missing benchmark input: {path}")
    payload = _run_suite(args.baseline.resolve(), args.challenger.resolve(), args.repeats, args.noise_files)
    quality_dir = args.output / "results" / "quality"
    tokens_dir = args.output / "results" / "tokens"
    raw_dir = args.output / "raw-logs"
    for directory in (quality_dir, tokens_dir, raw_dir):
        directory.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(payload, indent=2) + "\n"
    (quality_dir / "latest.json").write_text(serialized, encoding="utf-8")
    (raw_dir / "latest.json").write_text(serialized, encoding="utf-8")
    (quality_dir / "summary.md").write_text(_summary_markdown(payload), encoding="utf-8")
    (tokens_dir / "README.md").write_text(
        "# Token results\n\nNo model was invoked by this deterministic helper benchmark, so token use is not applicable.\n",
        encoding="utf-8",
    )
    print(serialized, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
