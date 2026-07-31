#!/usr/bin/env python3
"""Deterministic helpers for the Super Internet Digger skill.

The script never accesses the network, downloads artifacts, installs dependencies,
or executes discovered projects. It plans bounded research, validates/ranks candidate
records, performs a single-pass local project inspection, and evaluates benchmark
claims from already measured summaries.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import statistics
import sys
from collections import defaultdict
from collections.abc import Iterable
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

ARTIFACT_KINDS = {
    "source-code",
    "binary-build",
    "web-playable",
    "documentation",
    "sdk-or-tooling",
    "community-project",
}
SOURCE_TYPES = {
    "official-public",
    "authorized-private",
    "public-mirror",
    "community-remake",
    "web-build",
    "tooling-sdk",
    "leaked-source",
    "unknown",
}
ACCESS_MODES = {
    "public-web",
    "public-git",
    "authenticated-git",
    "authenticated-web",
    "artifact-download",
    "manual-only",
}
PLAYABLE_VALUES = {"ready", "likely", "unclear", "unlikely"}
MAX_SCAN_DEPTH = 4


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"File does not exist: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in {path}: {exc}") from exc


def _write_json(payload: Any) -> None:
    json.dump(payload, sys.stdout, indent=2, sort_keys=False)
    sys.stdout.write("\n")


def _canonical_url(value: str | None) -> str:
    if not value:
        return ""
    try:
        parts = urlsplit(value.strip())
    except ValueError:
        return value.strip().lower()
    host = parts.netloc.lower()
    path = re.sub(r"/+", "/", parts.path).rstrip("/")
    return urlunsplit((parts.scheme.lower(), host, path, parts.query, ""))


def _csv_set(value: str) -> set[str]:
    return {item.strip().lower() for item in value.split(",") if item.strip()}


def build_plan(target: str, goal: str, tools: set[str], authorized_path: str | None) -> dict[str, Any]:
    has_github = bool(tools & {"github", "gh", "git"})
    has_scraper = bool(tools & {"web-scraper", "wbscrper"})
    has_browser = bool(tools & {"browser", "chrome", "playwright"})
    has_web = bool(tools & {"web", "search", "web-search"})
    warden = "warden" in tools

    lanes = [
        {
            "id": "official",
            "objective": "Verify owner identity, official domains, releases/tags, dates, license, docs, and stores.",
            "preferred_tools": [
                *( ["github"] if has_github else [] ),
                *( ["web-scraper"] if has_scraper else [] ),
                *( ["web"] if has_web else [] ),
            ] or ["available direct web or browser tool"],
            "parallel_group": 1,
            "stop_when": "Primary evidence establishes owner, artifact, version/date, and license/access basis.",
        },
        {
            "id": "code",
            "objective": "Find canonical source/release artifacts and immutable version pins; classify mirrors separately.",
            "preferred_tools": [
                *( ["github"] if has_github else [] ),
                *( ["web-scraper"] if has_scraper else [] ),
                *( ["browser"] if has_browser else [] ),
            ] or ["available repository or web tool"],
            "parallel_group": 1,
            "stop_when": "One canonical candidate and one independent version/date signal are recorded.",
        },
        {
            "id": "alternatives",
            "objective": "Find official SDK/docs/playable builds or clearly licensed community equivalents when source is unavailable.",
            "preferred_tools": [
                *( ["web-scraper"] if has_scraper else [] ),
                *( ["web"] if has_web else [] ),
                *( ["browser"] if has_browser else [] ),
            ] or ["available direct web or browser tool"],
            "parallel_group": 1,
            "stop_when": "The best legal fallback for every missing requested artifact kind is evidenced.",
        },
    ]
    if authorized_path:
        lanes.insert(
            1,
            {
                "id": "authorized-private",
                "objective": "Validate the supplied authorized access path as metadata only; do not retrieve before confirmation.",
                "preferred_tools": ["existing authenticated connector or browser session"],
                "parallel_group": 1,
                "stop_when": "Access path, authorization basis, and confirmation requirement are recorded without credentials.",
            },
        )

    return {
        "target": target,
        "goal": goal,
        "generated_at": datetime.now(UTC).isoformat(),
        "strategy": "parallel-primary-first",
        "lanes": lanes,
        "global_stop_conditions": [
            "High-confidence primary candidate exists for each requested artifact kind.",
            "Version/tag and date have a second independent signal.",
            "License or authorized-access basis is explicit.",
            "No unresolved safety or provenance blocker remains.",
        ],
        "tool_policy": {
            "direct_tools_remain_available": True,
            "warden_available": warden,
            "warden_role": "optional-router" if warden else "not-installed-or-not-selected",
            "identical_retry_allowed": False,
        },
        "permission_gates": ["discovery", "acquisition", "execution"],
    }


def _parse_date(value: Any) -> date | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return date.fromisoformat(value.strip()[:10])
    except ValueError:
        return None


def _candidate_errors(candidate: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    artifact_kind = candidate.get("artifact_kind")
    source_type = candidate.get("source_type")
    access_mode = candidate.get("access_mode")
    playable = candidate.get("playable_potential")
    if artifact_kind not in ARTIFACT_KINDS:
        errors.append(f"invalid artifact_kind: {artifact_kind!r}")
    if source_type not in SOURCE_TYPES:
        errors.append(f"invalid source_type: {source_type!r}")
    if access_mode not in ACCESS_MODES:
        errors.append(f"invalid access_mode: {access_mode!r}")
    if playable not in PLAYABLE_VALUES:
        errors.append(f"invalid playable_potential: {playable!r}")
    if not candidate.get("upstream_url"):
        errors.append("missing upstream_url")
    if source_type == "leaked-source" and candidate.get("acquisition_allowed") is True:
        errors.append("leaked-source cannot be acquirable")
    if source_type == "authorized-private":
        if not candidate.get("authorized_access_path"):
            errors.append("authorized-private requires authorized_access_path")
        if candidate.get("confirmation_required") is not True:
            errors.append("authorized-private requires confirmation")
    if candidate.get("confirmation_required") and candidate.get("user_confirmed") is not True:
        candidate["ready_for_acquisition"] = False
    else:
        candidate["ready_for_acquisition"] = bool(candidate.get("acquisition_allowed"))
    if candidate.get("acquisition_allowed") and not candidate.get("acquisition_reason"):
        errors.append("acquirable candidate requires acquisition_reason")
    return errors


def _score_candidate(candidate: dict[str, Any], today: date) -> dict[str, Any]:
    source_type = candidate.get("source_type", "unknown")
    provenance_scores = {
        "official-public": 30,
        "authorized-private": 28,
        "tooling-sdk": 26,
        "web-build": 24,
        "community-remake": 19,
        "public-mirror": 10,
        "unknown": 0,
        "leaked-source": -100,
    }
    provenance = provenance_scores.get(str(source_type), 0)
    confidence = {"high": 4, "medium": 2, "low": 0}.get(candidate.get("provenance_confidence"), 0)

    release_date = _parse_date(candidate.get("release_date"))
    freshness = 0
    if release_date is not None:
        age_days = max(0, (today - release_date).days)
        freshness = 20 if age_days <= 365 else 16 if age_days <= 730 else 10 if age_days <= 1825 else 5

    version = 15 if candidate.get("checksum") else 12 if candidate.get("version_label") else 0
    license_label = str(candidate.get("license") or "").strip().lower()
    license_score = 0 if not license_label or license_label == "unknown" else 15
    playable = {"ready": 10, "likely": 7, "unclear": 2, "unlikely": 0}.get(
        candidate.get("playable_potential"), 0
    )
    reproducible = 10 if candidate.get("reproduction_steps") else 3 if candidate.get("version_label") else 0
    evidence_count = len(candidate.get("evidence_ids") or [])
    evidence = min(6, evidence_count * 2)
    total = provenance + confidence + freshness + version + license_score + playable + reproducible + evidence

    blockers: list[str] = []
    if source_type == "leaked-source":
        blockers.append("unauthorized-provenance")
    if not candidate.get("acquisition_allowed"):
        blockers.append("acquisition-not-allowed")
    if candidate.get("confirmation_required") and not candidate.get("user_confirmed"):
        blockers.append("confirmation-required")
    if license_score == 0 and candidate.get("artifact_kind") in {"source-code", "community-project"}:
        blockers.append("license-unclear")

    return {
        "total": max(0, min(110, total)),
        "dimensions": {
            "provenance": provenance + confidence,
            "freshness": freshness,
            "version_pin": version,
            "license_access": license_score,
            "playability": playable,
            "reproducibility": reproducible,
            "evidence": evidence,
        },
        "blockers": blockers,
        "eligible": not any(item in blockers for item in {"unauthorized-provenance", "license-unclear"}),
    }


def rank_candidates(payload: Any) -> dict[str, Any]:
    raw_candidates = payload.get("candidates", []) if isinstance(payload, dict) else payload
    if not isinstance(raw_candidates, list):
        raise ValueError("Input must be a candidate array or an object with a candidates array.")

    deduped: dict[tuple[str, str, str], dict[str, Any]] = {}
    duplicates: list[dict[str, Any]] = []
    invalid: list[dict[str, Any]] = []
    today = datetime.now(UTC).date()

    for index, raw in enumerate(raw_candidates):
        if not isinstance(raw, dict):
            invalid.append({"index": index, "errors": ["candidate must be an object"]})
            continue
        candidate = dict(raw)
        errors = _candidate_errors(candidate)
        if errors:
            invalid.append({"index": index, "id": candidate.get("id"), "errors": errors})
        score = _score_candidate(candidate, today)
        candidate["ranking"] = score
        key = (
            _canonical_url(candidate.get("upstream_url")),
            str(candidate.get("artifact_kind") or ""),
            str(candidate.get("version_label") or ""),
        )
        current = deduped.get(key)
        if current is None or score["total"] > current["ranking"]["total"]:
            if current is not None:
                duplicates.append(current)
            deduped[key] = candidate
        else:
            duplicates.append(candidate)

    candidates = sorted(
        deduped.values(),
        key=lambda item: (
            not item["ranking"]["eligible"],
            -item["ranking"]["total"],
            str(item.get("name", "")).lower(),
        ),
    )
    by_kind: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for candidate in candidates:
        by_kind[str(candidate.get("artifact_kind"))].append(candidate)

    selected: dict[str, dict[str, Any]] = {}
    for kind, items in by_kind.items():
        eligible = [item for item in items if item["ranking"]["eligible"]]
        if eligible:
            selected[kind] = eligible[0]

    return {
        "candidate_count": len(raw_candidates),
        "deduplicated_count": len(candidates),
        "selected": selected,
        "candidates": candidates,
        "invalid": invalid,
        "duplicates": duplicates,
        "policy": {
            "safety_overrides_score": True,
            "confirmation_does_not_override_block": True,
        },
    }


def _bounded_inventory(root: Path) -> tuple[int | None, list[str], str]:
    """Scan once while retaining only detector-relevant paths.

    Keeping every path made large, mostly-irrelevant repositories slower than
    the v1 multi-scan baseline. A scandir stack plus a tiny relevant-path set
    preserves all detector evidence without allocating thousands of Path
    objects, statting irrelevant files twice, or serializing an inventory the
    caller never needs.
    """

    ignored = {".git", "node_modules", ".venv", "venv", "dist", "build", "target"}
    exact_names = {
        "projectversion.txt",
        "project.godot",
        "package.json",
        "pnpm-lock.yaml",
        "yarn.lock",
        "bun.lock",
        "bun.lockb",
        "package-lock.json",
        "pyproject.toml",
        "requirements.txt",
        "main.py",
        "manage.py",
        "cargo.toml",
        "cargo.lock",
        "cmakelists.txt",
        "index.html",
    }
    interesting_suffixes = (".uproject", ".csproj")
    relevant: list[str] = []
    stack: list[tuple[str, int]] = [(str(root), 0)]
    root_text = str(root)
    relative_offset = len(root_text.rstrip("\\/")) + 1
    while stack:
        current, depth = stack.pop()
        try:
            entries = os.scandir(current)
        except OSError:
            continue
        with entries:
            for entry in entries:
                try:
                    if entry.is_dir(follow_symlinks=False):
                        if depth < MAX_SCAN_DEPTH and entry.name not in ignored:
                            stack.append((entry.path, depth + 1))
                        continue
                except OSError:
                    continue
                lower_name = entry.name.lower()
                if lower_name in exact_names or lower_name.endswith(interesting_suffixes):
                    try:
                        if entry.is_file(follow_symlinks=False):
                            relevant.append(entry.path[relative_offset:].replace("\\", "/"))
                    except OSError:
                        continue
    return None, relevant, "single-pass-scandir"


def inspect_project(root: Path) -> dict[str, Any]:
    if not root.exists() or not root.is_dir():
        raise ValueError(f"Project directory does not exist: {root}")
    inventory_count, files, inventory_mode = _bounded_inventory(root)
    file_set = set(files)
    lower_files = {item.lower(): item for item in files}
    detections: list[dict[str, Any]] = []

    def add(kind: str, confidence: str, evidence: Iterable[str], install: list[str], run: list[str], notes: list[str]) -> None:
        detections.append(
            {
                "type": kind,
                "confidence": confidence,
                "evidence": list(evidence),
                "install_commands": install,
                "run_commands": run,
                "notes": notes,
            }
        )

    if "ProjectSettings/ProjectVersion.txt" in file_set:
        version_path = root / "ProjectSettings" / "ProjectVersion.txt"
        version = ""
        try:
            match = re.search(r"m_EditorVersion:\s*(.+)", version_path.read_text(encoding="utf-8", errors="ignore"))
            version = match.group(1).strip() if match else ""
        except OSError:
            version = ""
        add("unity", "high", ["ProjectSettings/ProjectVersion.txt"], [], [], [f"Unity Editor {version}" if version else "Unity Editor required"])
    if "project.godot" in file_set:
        add("godot", "high", ["project.godot"], [], ["godot --path ."], ["Review project.godot before launch."])
    uprojects = [item for item in files if item.lower().endswith(".uproject")]
    if uprojects:
        add("unreal", "high", [uprojects[0]], [], [], ["Unreal Editor required."])

    if "package.json" in file_set:
        manager = "pnpm" if "pnpm-lock.yaml" in file_set else "yarn" if "yarn.lock" in file_set else "bun" if {"bun.lock", "bun.lockb"} & file_set else "npm"
        install = {"pnpm": "pnpm install --frozen-lockfile", "yarn": "yarn install --immutable", "bun": "bun install --frozen-lockfile", "npm": "npm ci" if "package-lock.json" in file_set else "npm install"}[manager]
        scripts: dict[str, Any] = {}
        dependencies: dict[str, Any] = {}
        try:
            package = json.loads((root / "package.json").read_text(encoding="utf-8"))
            scripts = package.get("scripts", {}) if isinstance(package, dict) else {}
            dependencies = {**package.get("dependencies", {}), **package.get("devDependencies", {})} if isinstance(package, dict) else {}
        except (OSError, json.JSONDecodeError, TypeError):
            pass
        run = [f"{manager} run {name}" for name in ("dev", "start", "serve", "preview") if name in scripts]
        kind = "electron" if "electron" in dependencies else "node-web" if dependencies.keys() & {"react", "vue", "svelte", "vite", "next"} else "node-app"
        add(kind, "high", ["package.json"], [install], run, [f"Package manager: {manager}."])

    python_evidence = [item for item in ("pyproject.toml", "requirements.txt", "main.py", "manage.py") if item in file_set]
    if python_evidence:
        install = ["python -m pip install -e ."] if "pyproject.toml" in file_set else ["python -m pip install -r requirements.txt"] if "requirements.txt" in file_set else []
        run = ["python main.py"] if "main.py" in file_set else ["python manage.py runserver"] if "manage.py" in file_set else []
        add("python-app", "high" if "pyproject.toml" in file_set else "medium", python_evidence, install, run, ["Use a disposable virtual environment."])

    if "Cargo.toml" in file_set:
        add("rust", "high", ["Cargo.toml"], ["cargo build --locked" if "Cargo.lock" in file_set else "cargo build"], ["cargo run --locked" if "Cargo.lock" in file_set else "cargo run"], [])
    csproj = next((original for lower, original in lower_files.items() if lower.endswith(".csproj")), None)
    if csproj:
        add("dotnet", "high", [csproj], ["dotnet restore"], [f'dotnet run --project "{csproj}"'], [])
    if "CMakeLists.txt" in file_set:
        add("cmake", "medium", ["CMakeLists.txt"], ["cmake -S . -B build", "cmake --build build"], [], ["Inspect generated targets before execution."])
    if "index.html" in file_set and not any(item["type"] == "node-web" for item in detections):
        add("static-web", "high", ["index.html"], [], ["python -m http.server 8000"], ["Open http://127.0.0.1:8000/."])

    confidence_order = {"high": 0, "medium": 1, "low": 2}
    detections.sort(key=lambda item: (confidence_order.get(item["confidence"], 3), item["type"]))
    return {
        "project_root": str(root.resolve()),
        "inventory_count": inventory_count,
        "inventory_mode": inventory_mode,
        "relevant_files_scanned": len(files),
        "inventory_depth": MAX_SCAN_DEPTH,
        "detections": detections,
        "primary": detections[0] if detections else {"type": "unknown", "confidence": "low"},
        "polyglot": len(detections) > 1,
        "execution_performed": False,
        "warnings": [
            "Commands are proposals only; inspect project instructions and obtain execution authorization first."
        ],
    }


def _median_metric(payload: dict[str, Any], key: str) -> float | None:
    value = payload.get(key)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    values = payload.get("attempts")
    if isinstance(values, list):
        numeric = [float(item[key]) for item in values if isinstance(item, dict) and isinstance(item.get(key), (int, float))]
        if numeric:
            return statistics.median(numeric)
    return None


def _ratio(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator is None or denominator <= 0:
        return None
    return numerator / denominator


def compare_metrics(baseline: dict[str, Any], challenger: dict[str, Any]) -> dict[str, Any]:
    b_quality = _median_metric(baseline, "quality_score_100")
    c_quality = _median_metric(challenger, "quality_score_100")
    b_elapsed = _median_metric(baseline, "elapsed_seconds")
    c_elapsed = _median_metric(challenger, "elapsed_seconds")
    b_tokens = _median_metric(baseline, "total_tokens")
    c_tokens = _median_metric(challenger, "total_tokens")
    b_calls = _median_metric(baseline, "tool_calls")
    c_calls = _median_metric(challenger, "tool_calls")
    b_critical = _median_metric(baseline, "critical_errors") or 0.0
    c_critical = _median_metric(challenger, "critical_errors") or 0.0

    speed = _ratio(b_elapsed, c_elapsed)
    token_reduction = _ratio(b_tokens, c_tokens)
    call_reduction = _ratio(b_calls, c_calls)
    b_qpm = _ratio(b_quality, _ratio(b_elapsed, 60.0)) if b_elapsed else None
    c_qpm = _ratio(c_quality, _ratio(c_elapsed, 60.0)) if c_elapsed else None
    time_efficiency = _ratio(c_qpm, b_qpm)
    b_qpt = _ratio(b_quality, _ratio(b_tokens, 1000.0)) if b_tokens else None
    c_qpt = _ratio(c_quality, _ratio(c_tokens, 1000.0)) if c_tokens else None
    token_efficiency = _ratio(c_qpt, b_qpt)
    quality_delta = c_quality - b_quality if c_quality is not None and b_quality is not None else None
    safety_regression = c_critical > b_critical or c_critical > 0
    non_inferior_quality = quality_delta is not None and quality_delta >= 0

    claims = {
        "four_x_faster": bool(speed is not None and speed >= 4.0 and non_inferior_quality and not safety_regression),
        "four_x_time_efficient": bool(time_efficiency is not None and time_efficiency >= 4.0 and non_inferior_quality and not safety_regression),
        "four_x_token_efficient": bool(token_efficiency is not None and token_efficiency >= 4.0 and non_inferior_quality and not safety_regression),
        "higher_quality": bool(quality_delta is not None and quality_delta > 0 and not safety_regression),
        "no_safety_regression": not safety_regression,
    }
    return {
        "baseline": baseline.get("name", "baseline"),
        "challenger": challenger.get("name", "challenger"),
        "medians": {
            "baseline_quality_score_100": b_quality,
            "challenger_quality_score_100": c_quality,
            "baseline_elapsed_seconds": b_elapsed,
            "challenger_elapsed_seconds": c_elapsed,
            "baseline_total_tokens": b_tokens,
            "challenger_total_tokens": c_tokens,
            "baseline_tool_calls": b_calls,
            "challenger_tool_calls": c_calls,
        },
        "multipliers": {
            "speed": speed,
            "time_efficiency": time_efficiency,
            "token_efficiency": token_efficiency,
            "token_reduction": token_reduction,
            "tool_call_reduction": call_reduction,
        },
        "quality_delta_points": quality_delta,
        "claims": claims,
        "eligible_winner": non_inferior_quality and not safety_regression,
        "honesty_note": "Only true claim fields are supported by the supplied measurements; validate repeat count and comparability separately.",
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Plan, rank, inspect, and benchmark Super Internet Digger work.")
    sub = parser.add_subparsers(dest="command", required=True)

    plan = sub.add_parser("plan", help="Create a bounded parallel research plan.")
    plan.add_argument("--target", required=True)
    plan.add_argument("--goal", choices=["source", "playable", "both", "docs", "sdk"], default="both")
    plan.add_argument("--tools", default="")
    plan.add_argument("--authorized-path")

    rank = sub.add_parser("rank", help="Validate, deduplicate, and rank candidate JSON.")
    rank.add_argument("path", type=Path)

    inspect = sub.add_parser("inspect", help="Inspect a local project in one bounded pass.")
    inspect.add_argument("path", type=Path)

    compare = sub.add_parser("compare", help="Evaluate honest performance claims from measured summaries.")
    compare.add_argument("baseline", type=Path)
    compare.add_argument("challenger", type=Path)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        if args.command == "plan":
            result = build_plan(args.target, args.goal, _csv_set(args.tools), args.authorized_path)
        elif args.command == "rank":
            result = rank_candidates(_read_json(args.path))
        elif args.command == "inspect":
            result = inspect_project(args.path.expanduser())
        elif args.command == "compare":
            baseline = _read_json(args.baseline)
            challenger = _read_json(args.challenger)
            if not isinstance(baseline, dict) or not isinstance(challenger, dict):
                raise ValueError("Benchmark summaries must be JSON objects.")
            result = compare_metrics(baseline, challenger)
        else:
            raise ValueError(f"Unsupported command: {args.command}")
    except ValueError as exc:
        _write_json({"error": str(exc)})
        return 2
    _write_json(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
