"""Turn results.json into a human-readable report with real numbers.

Everything here is derived from measured runs - pass rates come from executing generated
code against assertions and validating tool-call shapes, throughput comes from Ollama's own
eval counters. Nothing is estimated.

    python report.py
"""

from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).parent
RESULTS = HERE / "results.json"
REPORT = HERE / "REPORT.md"

CATEGORIES = ["tool-calling", "coding", "structured-output", "control", "review", "vision"]

TASK_LABELS = {
    "tool_call_simple": "Emit a tool call",
    "tool_call_select": "Pick the right tool",
    "json_output": "Valid JSON on demand",
    "code_generate": "Write working code",
    "code_repair": "Fix broken code",
    "instruction_adherence": "Follow exact instructions",
    "diff_reasoning": "Reason about a diff",
    "vision_color": "Identify colour in an image",
    "vision_count": "Count objects in an image",
}


def category_scores(tasks: dict) -> dict[str, float | None]:
    out: dict[str, float | None] = {}
    for cat in CATEGORIES:
        vals = [t["pass_rate"] for t in tasks.values() if t.get("category") == cat]
        out[cat] = round(sum(vals) / len(vals), 3) if vals else None
    return out


def main() -> int:
    if not RESULTS.exists():
        print("no results.json - run bench.py first")
        return 1
    data = json.loads(RESULTS.read_text(encoding="utf-8"))
    runs = data.get("runs", {})
    if not runs:
        print("results.json has no runs")
        return 1

    rows = []
    for name, run in runs.items():
        tasks = run.get("tasks", {})
        vram = run.get("vram", {})
        cats = category_scores(tasks)
        pass_rate = run.get("overall_pass_rate") or 0.0
        speed = run.get("median_tok_per_s") or 0.0
        rows.append({
            "name": name,
            "pass": pass_rate,
            "speed": speed,
            "load": run.get("load_s"),
            "size_gb": vram.get("size_gb"),
            "vram_gb": vram.get("vram_gb"),
            "on_gpu": vram.get("fully_on_gpu"),
            "cats": cats,
            "tasks": tasks,
            # Useful work per unit time: a model that is right 86% of the time at 25 tok/s
            # delivers far more than one that is right 86% of the time at 6 tok/s.
            "efficiency": round(pass_rate * speed, 1),
        })

    by_eff = sorted(rows, key=lambda r: -r["efficiency"])
    by_pass = sorted(rows, key=lambda r: (-r["pass"], -r["speed"]))

    L: list[str] = []
    L.append("# Local model benchmark results\n")
    L.append("Measured on this machine, not estimated. Code tasks are scored by executing the")
    L.append("generated code against assertions; tool-calling is scored by validating the shape")
    L.append("of the emitted call; throughput comes from Ollama's own eval counters.\n")

    hw = data.get("hardware") or {}
    L.append("## Machine\n")
    L.append("| | |")
    L.append("|---|---|")
    L.append(f"| GPU | {hw.get('gpu', 'NVIDIA GeForce GTX 1660 Ti with Max-Q Design')} |")
    L.append(f"| VRAM | {hw.get('vram_gb', 6.0)} GB |")
    L.append(f"| RAM | {hw.get('ram_gb', 15.8)} GB |")
    L.append(f"| CPU | {hw.get('cpu', 'AMD Ryzen 7 3750H')} |")
    L.append("")

    L.append("## Efficiency ranking\n")
    L.append("Ranked by **useful work per unit time** (pass rate x median tokens/sec). Two models")
    L.append("with the same accuracy are not equally useful if one is four times faster.\n")
    L.append("| # | Model | Efficiency | Pass rate | Speed (tok/s) | Fits in VRAM |")
    L.append("|---|-------|-----------:|----------:|--------------:|--------------|")
    for i, r in enumerate(by_eff, 1):
        fit = "yes" if r["on_gpu"] else "**no - spills to CPU**"
        L.append(f"| {i} | `{r['name']}` | **{r['efficiency']}** | {r['pass']:.1%} | "
                 f"{r['speed']} | {fit} |")
    L.append("")

    L.append("## Accuracy by category\n")
    L.append("| Model | Overall | Tool-calling | Coding | Structured | Control | Review |")
    L.append("|-------|--------:|-------------:|-------:|-----------:|--------:|-------:|")
    for r in by_pass:
        c = r["cats"]

        def pct(v: float | None) -> str:
            return "-" if v is None else f"{v:.0%}"

        L.append(f"| `{r['name']}` | **{r['pass']:.1%}** | {pct(c['tool-calling'])} | "
                 f"{pct(c['coding'])} | {pct(c['structured-output'])} | "
                 f"{pct(c['control'])} | {pct(c['review'])} |")
    L.append("")

    L.append("## Resource cost\n")
    L.append("| Model | On disk | Resident in VRAM | Fully on GPU | Cold load |")
    L.append("|-------|--------:|-----------------:|--------------|----------:|")
    for r in sorted(rows, key=lambda x: -(x["size_gb"] or 0)):
        L.append(f"| `{r['name']}` | {r['size_gb']} GB | {r['vram_gb']} GB | "
                 f"{'yes' if r['on_gpu'] else 'NO'} | {r['load']}s |")
    L.append("")

    L.append("## Per-task detail\n")
    all_tasks = sorted({t for r in rows for t in r["tasks"]})
    header = "| Model | " + " | ".join(TASK_LABELS.get(t, t) for t in all_tasks) + " |"
    L.append(header)
    L.append("|" + "---|" * (len(all_tasks) + 1))
    for r in by_pass:
        cells = []
        for t in all_tasks:
            task = r["tasks"].get(t)
            cells.append("-" if task is None else ("PASS" if task["pass_rate"] >= 0.5 else "FAIL"))
        L.append(f"| `{r['name']}` | " + " | ".join(cells) + " |")
    L.append("")

    REPORT.write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"wrote {REPORT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
