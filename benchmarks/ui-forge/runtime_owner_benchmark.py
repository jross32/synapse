#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import statistics
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
STATIC_LOCATOR = REPO_ROOT / "templates" / "skills" / "ui-forge" / "scripts" / "source_locator.py"
RUNTIME_LOCATOR = REPO_ROOT / "templates" / "skills" / "ui-forge" / "scripts" / "runtime_owner_locator.py"


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _fixture(root: Path, count: int) -> list[tuple[str, str, str]]:
    html = ["<!doctype html><html><body>"]
    expected: list[tuple[str, str, str]] = []
    for index in range(count):
        element_id = f"phaseTitle{index:03d}"
        initial = f"Initial title {index:03d}"
        runtime = f"Runtime title {index:03d}"
        html.append(f'<h1 id="{element_id}">{initial}</h1>')
        script = root / "src" / f"controller{index:03d}.js"
        script.parent.mkdir(parents=True, exist_ok=True)
        script.write_text(
            "const elements = {\n"
            f'  {element_id}: document.getElementById("{element_id}"),\n'
            "};\n"
            "export function render(){\n"
            f'  elements.{element_id}.textContent = "{runtime}";\n'
            "}\n",
            encoding="utf-8",
        )
        expected.append((element_id, runtime, script.relative_to(root).as_posix()))
    html.append("</body></html>\n")
    (root / "index.html").write_text("\n".join(html), encoding="utf-8")
    # Decoy script with many unrelated mutations in a selector-linked file pattern.
    decoy = root / "src" / "decoy.js"
    decoy.write_text(
        'const saveStatus=document.getElementById("saveStatus");\n'
        + "\n".join(f'saveStatus.textContent="Noise {i}";' for i in range(count * 2))
        + "\n",
        encoding="utf-8",
    )
    return expected


def _stats(values: list[float]) -> dict[str, float]:
    ordered = sorted(values)
    idx = min(len(ordered) - 1, max(0, int((len(ordered) - 1) * 0.9 + 0.999999)))
    return {
        "median_ms": round(statistics.median(values) * 1000, 4),
        "p90_ms": round(ordered[idx] * 1000, 4),
        "min_ms": round(min(values) * 1000, 4),
        "max_ms": round(max(values) * 1000, 4),
    }


def run(count: int = 30) -> dict[str, Any]:
    static = _load(STATIC_LOCATOR, "ui_forge_static_locator_runtime_bench")
    runtime = _load(RUNTIME_LOCATOR, "ui_forge_runtime_owner_bench")
    static_hits = 0
    runtime_hits = 0
    runtime_writer_flags = 0
    static_times: list[float] = []
    runtime_times: list[float] = []

    with tempfile.TemporaryDirectory(prefix="ui-forge-runtime-owner-") as temp:
        root = Path(temp)
        cases = _fixture(root, count)
        for element_id, rendered_text, expected_file in cases:
            probe = {"tag": "h1", "id": element_id, "text": rendered_text}

            started = time.perf_counter()
            static_result = static.locate_source(root, probe, limit=1)
            static_times.append(time.perf_counter() - started)
            if static_result and static_result[0].get("file") == expected_file:
                static_hits += 1

            started = time.perf_counter()
            runtime_result = runtime.locate_runtime_owner(root, probe, limit=1)
            runtime_times.append(time.perf_counter() - started)
            if runtime_result and runtime_result[0].get("file") == expected_file:
                runtime_hits += 1
            if runtime_result and runtime_result[0].get("likely_runtime_writer") is True:
                runtime_writer_flags += 1

    static_accuracy = static_hits / count
    runtime_accuracy = runtime_hits / count
    payload = {
        "schema": "ui-forge-runtime-owner-benchmark-v1",
        "generated_at": datetime.now(UTC).isoformat(),
        "scope": "distinguish static DOM declaration from JavaScript runtime writer",
        "cases": count,
        "baseline": {
            "treatment": "static JSX/HTML source locator only",
            "runtime_writer_top1_accuracy": round(static_accuracy, 4),
            "timing": _stats(static_times),
        },
        "challenger": {
            "treatment": "UI Forge runtime owner locator",
            "runtime_writer_top1_accuracy": round(runtime_accuracy, 4),
            "likely_writer_flag_rate": round(runtime_writer_flags / count, 4),
            "timing": _stats(runtime_times),
        },
        "delta": {"accuracy_points": round((runtime_accuracy - static_accuracy) * 100, 2)},
        "overall_pass": runtime_accuracy == 1.0 and runtime_writer_flags == count,
        "claims": {
            "runtime_owner_precision_pass": runtime_accuracy == 1.0,
            "beats_static_locator_for_runtime_writer_task": runtime_accuracy > static_accuracy,
            "not_a_full_ui_forge_or_lovable_claim": True,
        },
    }
    return payload


def main() -> int:
    payload = run()
    result_dir = Path(__file__).resolve().parent / "results"
    result_dir.mkdir(parents=True, exist_ok=True)
    (result_dir / "runtime-owner-latest.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))
    return 0 if payload["overall_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
