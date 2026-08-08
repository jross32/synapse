"""How many local agents should a squad have, and which model in each seat?

The intuition that "more agents = better" is worth distrusting with small models. Every
extra seat costs a full model turn (seconds to minutes on a 6 GB card) and every handoff
is a chance for a weak model to garble the previous one's work. This measures whether the
extra seats actually buy correctness.

Topologies compared, all on the same tasks with the same workspace contract:

  solo              one agent does everything
  coder_reviewer    a coder writes, a reviewer runs the tests and repairs
  planner_coder_rev a planner writes a spec first, then coder, then reviewer
  two_coders_rev    two coders attempt independently, reviewer picks and fixes the better

Scoring is machine-checked: the produced file is executed against assertions the agents
never see. Wall-clock and per-seat token counts are recorded, because a squad that is
right slightly more often but takes five times as long is usually the wrong trade.

    python squad_bench.py
    python squad_bench.py --repeat 2
"""

from __future__ import annotations

import argparse
import asyncio
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "daemon"))

from synapse_daemon.local_agent import PermissionMode, run_agent  # noqa: E402

HERE = Path(__file__).parent
RESULTS = HERE / "squad_results.json"
REPORT = HERE / "SQUAD_REPORT.md"
WORKROOT = HERE / ".squad_work"

# Measured in REPORT.md on this machine. The agent seat needs tool-calling, which the
# coder-tuned variants cannot do at all, so they are deliberately not used as agents.
AGENT_MODEL = "qwen2.5:1.5b"     # 100% tool-calling, 24.8 tok/s, fits VRAM
REVIEW_MODEL = "llama3.2:3b"     # 100% on diff reasoning, 14.7 tok/s, fits VRAM


# ---------------------------------------------------------------- tasks


TASKS = [
    {
        "id": "fizzbuzz",
        "brief": (
            "Create a file solution.py containing a function fizzbuzz(n) that returns a "
            "list of length n. For each number 1..n the entry is 'Fizz' if divisible by 3, "
            "'Buzz' if divisible by 5, 'FizzBuzz' if divisible by both, otherwise the "
            "number as a string."
        ),
        "check": (
            "from solution import fizzbuzz\n"
            "r = fizzbuzz(15)\n"
            "assert len(r) == 15, r\n"
            "assert r[0] == '1', r[0]\n"
            "assert r[2] == 'Fizz', r[2]\n"
            "assert r[4] == 'Buzz', r[4]\n"
            "assert r[14] == 'FizzBuzz', r[14]\n"
        ),
    },
    {
        "id": "roman",
        "brief": (
            "Create a file solution.py containing a function to_roman(n) that converts an "
            "integer between 1 and 3999 into a Roman numeral string. Use standard "
            "subtractive notation, so 4 is IV and 9 is IX."
        ),
        "check": (
            "from solution import to_roman\n"
            "assert to_roman(4) == 'IV'\n"
            "assert to_roman(9) == 'IX'\n"
            "assert to_roman(14) == 'XIV'\n"
            "assert to_roman(1987) == 'MCMLXXXVII'\n"
        ),
    },
    {
        "id": "wordcount",
        "brief": (
            "Create a file solution.py containing a function word_count(text) that returns "
            "a dict mapping each lowercased word to how many times it appears. Split on "
            "whitespace and strip surrounding punctuation from each word."
        ),
        "check": (
            "from solution import word_count\n"
            "r = word_count('The cat, the CAT; a dog.')\n"
            "assert r.get('the') == 2, r\n"
            "assert r.get('cat') == 2, r\n"
            "assert r.get('dog') == 1, r\n"
        ),
    },
]


def score(workspace: Path, check: str) -> tuple[bool, str]:
    """Run the hidden assertions against whatever the squad produced."""
    sol = workspace / "solution.py"
    if not sol.exists():
        return False, "no solution.py was produced"
    runner = workspace / "_check.py"
    runner.write_text(check, encoding="utf-8")
    try:
        proc = subprocess.run([sys.executable, str(runner)], capture_output=True, text=True,
                              timeout=30, cwd=str(workspace))
        return proc.returncode == 0, "" if proc.returncode == 0 else (
            (proc.stderr or proc.stdout)[-220:])
    except subprocess.TimeoutExpired:
        return False, "the produced code hung"
    finally:
        runner.unlink(missing_ok=True)


# ---------------------------------------------------------------- topologies


async def _seat(model: str, task: str, ws: Path, mode: PermissionMode, steps: int) -> dict:
    run = await run_agent(model=model, task=task, workspace=ws, mode=mode,
                          allow_web=False, max_steps=steps)
    return {"model": model, "tokens": run.total_tokens_out, "seconds": run.total_duration_s,
            "steps": len(run.steps), "answer": (run.answer or "")[:300]}


async def topo_solo(t: dict, ws: Path) -> list[dict]:
    return [await _seat(AGENT_MODEL,
                        f"{t['brief']}\n\nWrite the file, then stop.", ws,
                        PermissionMode.ACCEPT_EDITS, 8)]


async def topo_coder_reviewer(t: dict, ws: Path) -> list[dict]:
    seats = [await _seat(AGENT_MODEL,
                         f"{t['brief']}\n\nWrite the file, then stop.", ws,
                         PermissionMode.ACCEPT_EDITS, 8)]
    seats.append(await _seat(
        REVIEW_MODEL,
        "Read solution.py in the workspace. Check it satisfies this requirement:\n"
        f"{t['brief']}\n"
        "If anything is wrong or missing, rewrite solution.py so it is correct. "
        "If it is already correct, say so and change nothing.",
        ws, PermissionMode.ACCEPT_EDITS, 8))
    return seats


async def topo_planner_coder_reviewer(t: dict, ws: Path) -> list[dict]:
    seats = [await _seat(
        AGENT_MODEL,
        f"{t['brief']}\n\nDo NOT write the solution. Write a short plan to plan.md: the "
        "function signature and the edge cases that matter. Keep it under 10 lines.",
        ws, PermissionMode.ACCEPT_EDITS, 6)]
    seats.append(await _seat(
        AGENT_MODEL,
        f"{t['brief']}\n\nRead plan.md first if it exists, then write solution.py and stop.",
        ws, PermissionMode.ACCEPT_EDITS, 8))
    seats.append(await _seat(
        REVIEW_MODEL,
        "Read solution.py. Check it satisfies this requirement:\n"
        f"{t['brief']}\nIf anything is wrong, rewrite solution.py correctly.",
        ws, PermissionMode.ACCEPT_EDITS, 8))
    return seats


async def topo_two_coders_reviewer(t: dict, ws: Path) -> list[dict]:
    """Two independent attempts, then a reviewer keeps the better one.

    Attempts run in parallel in wall-clock terms only if the GPU can hold both; on a 6 GB
    card it serialises, which is itself part of what this measures.
    """
    a, b = ws / "a", ws / "b"
    a.mkdir(exist_ok=True)
    b.mkdir(exist_ok=True)
    seats = list(await asyncio.gather(
        _seat(AGENT_MODEL, f"{t['brief']}\n\nWrite solution.py, then stop.", a,
              PermissionMode.ACCEPT_EDITS, 8),
        _seat(AGENT_MODEL, f"{t['brief']}\n\nWrite solution.py, then stop.", b,
              PermissionMode.ACCEPT_EDITS, 8),
    ))
    # Hand both attempts to the reviewer in the top-level workspace.
    for tag, sub in (("attempt_a.py", a), ("attempt_b.py", b)):
        src = sub / "solution.py"
        if src.exists():
            shutil.copy(src, ws / tag)
    seats.append(await _seat(
        REVIEW_MODEL,
        "Two attempts at the same task are in the workspace: attempt_a.py and attempt_b.py.\n"
        f"The requirement is:\n{t['brief']}\n"
        "Read both, decide which is more correct, and write the better version (fixed if "
        "needed) to solution.py.",
        ws, PermissionMode.ACCEPT_EDITS, 10))
    return seats


async def topo_self_verify(t: dict, ws: Path) -> list[dict]:
    """Write, then actually run it, then fix what the error says.

    The hypothesis worth testing is that a weak model's problem is not knowledge but the
    absence of feedback. It never finds out its code is wrong, so it cannot fix it. Giving
    it the shell and telling it to exercise its own function turns guesswork into a loop
    that terminates on evidence - the same reason a human catches their own bug in seconds
    once they run the thing.

    The hidden assertions stay hidden: the agent writes its own checks.
    """
    return [await _seat(
        AGENT_MODEL,
        f"{t['brief']}\n\n"
        "Then VERIFY it actually works before you finish:\n"
        "1. Write solution.py.\n"
        "2. Run it with run_command, calling the function on an example and printing the "
        "result — for example: python -c \"from solution import *; print(...)\"\n"
        "3. Look at the output. If it is wrong or errors, fix solution.py and run it again.\n"
        "Only give your final answer once you have seen correct output.",
        ws, PermissionMode.AUTO, 14)]


async def topo_verify_then_review(t: dict, ws: Path) -> list[dict]:
    """Self-verification first, then a reviewer with the shell as a second pair of eyes."""
    seats = await topo_self_verify(t, ws)
    seats.append(await _seat(
        REVIEW_MODEL,
        "Read solution.py, then run it with run_command to check it against this "
        f"requirement:\n{t['brief']}\n"
        "If the output is wrong, fix solution.py and run it again until it is right.",
        ws, PermissionMode.AUTO, 12))
    return seats


async def topo_pipeline_repair(t: dict, ws: Path) -> list[dict]:
    """No agent at all: Python orchestrates, the model only ever writes code.

    This exists because of the most important measurement in this file. Called directly
    with the brief, `qwen2.5-coder:3b` solves every one of these tasks. Wrapped in an agent
    loop driven by a 1.5B model, the same coder drops to roughly a third. The scaffolding,
    not the model, is the bottleneck: the small model has to choose a tool, format the call,
    relay the spec, and interpret the result, and each of those is a chance to fail.

    So the orchestration moves into ordinary code, which never mis-formats a tool call or
    paraphrases a requirement:

        generate implementation  ->  generate a test from the same brief
        ->  run the test  ->  on failure, hand back the real traceback  ->  repeat

    The model does the one thing it is measurably good at. Everything requiring reliability
    is done by the program. Costs no API tokens, because every call is local.
    """
    import synapse_daemon.local_agent as la  # noqa: PLC0415

    seats: list[dict] = []
    t0 = time.time()
    tokens = 0

    code = await asyncio.to_thread(la.generate_code, t["brief"], la.DEFAULT_CODER_MODEL)
    (ws / "solution.py").write_text(code, encoding="utf-8")

    # A test written from the same brief, by the same model, but independently of the
    # implementation - so it encodes the requirement rather than the code's behaviour.
    test_spec = (
        f"{t['brief']}\n\n"
        "Write a pytest-free self-test for that function. Import it from solution, call it "
        "on a few representative inputs including edge cases, and assert the results. Print "
        "'OK' at the end. Output only the test code."
    )
    test_code = await asyncio.to_thread(la.generate_code, test_spec, la.DEFAULT_CODER_MODEL)
    (ws / "selftest.py").write_text(test_code, encoding="utf-8")

    for attempt in range(3):
        proc = subprocess.run([sys.executable, "selftest.py"], capture_output=True, text=True,
                              timeout=40, cwd=str(ws))
        if proc.returncode == 0:
            break
        error = (proc.stderr or proc.stdout)[-900:]
        repair = (
            f"This code was written for the following requirement:\n{t['brief']}\n\n"
            f"```python\n{(ws / 'solution.py').read_text(encoding='utf-8')}```\n\n"
            f"Running it produced this error:\n```\n{error}\n```\n\n"
            "Fix the implementation so it satisfies the requirement. Output only the "
            "corrected code."
        )
        code = await asyncio.to_thread(la.generate_code, repair, la.DEFAULT_CODER_MODEL)
        (ws / "solution.py").write_text(code, encoding="utf-8")
        seats.append({"model": la.DEFAULT_CODER_MODEL, "tokens": 0, "seconds": 0,
                      "steps": 1, "answer": f"repair attempt {attempt + 1}"})

    seats.insert(0, {"model": la.DEFAULT_CODER_MODEL, "tokens": tokens,
                     "seconds": round(time.time() - t0, 1), "steps": 2,
                     "answer": "generate + self-test"})
    return seats


TOPOLOGIES = {
    "solo": topo_solo,
    "self_verify": topo_self_verify,
    "verify_then_review": topo_verify_then_review,
    "pipeline_repair": topo_pipeline_repair,
    "coder_reviewer": topo_coder_reviewer,
    "planner_coder_reviewer": topo_planner_coder_reviewer,
    "two_coders_reviewer": topo_two_coders_reviewer,
}


# ---------------------------------------------------------------- runner


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repeat", type=int, default=1)
    ap.add_argument("--topologies", default="")
    args = ap.parse_args()

    names = ([n.strip() for n in args.topologies.split(",") if n.strip()]
             if args.topologies else list(TOPOLOGIES))

    results: dict = {"runs": {}}
    if RESULTS.exists():
        results = json.loads(RESULTS.read_text(encoding="utf-8"))
        results.setdefault("runs", {})

    for topo in names:
        entry = results["runs"].setdefault(topo, {"tasks": {}})
        print(f"\n=== {topo} ===")
        for t in TASKS:
            passes, times, tokens, seatcounts, details = 0, [], [], [], []
            for rep in range(args.repeat):
                ws = WORKROOT / f"{topo}_{t['id']}_{rep}"
                if ws.exists():
                    shutil.rmtree(ws, ignore_errors=True)
                ws.mkdir(parents=True)
                t0 = time.time()
                try:
                    seats = await TOPOLOGIES[topo](t, ws)
                except Exception as exc:  # noqa: BLE001 -- a crash is a data point
                    seats = [{"error": f"{type(exc).__name__}: {exc}"}]
                elapsed = round(time.time() - t0, 1)
                ok, why = score(ws, t["check"])
                passes += 1 if ok else 0
                times.append(elapsed)
                tokens.append(sum(s.get("tokens", 0) for s in seats))
                seatcounts.append(len(seats))
                details.append({"passed": ok, "why": why, "seats": seats,
                                "seconds": elapsed})
                print(f"  {t['id']:10s} rep{rep} {'PASS' if ok else 'FAIL'} "
                      f"{elapsed:6.1f}s {sum(s.get('tokens', 0) for s in seats):5d} tok"
                      f"{'  ' + why[:60] if why else ''}")
            entry["tasks"][t["id"]] = {
                "pass_rate": passes / args.repeat,
                "avg_seconds": round(sum(times) / len(times), 1),
                "avg_tokens": int(sum(tokens) / len(tokens)),
                "seats": seatcounts[0] if seatcounts else 0,
                "details": details,
            }
            RESULTS.write_text(json.dumps(results, indent=1), encoding="utf-8")

        tasks = entry["tasks"]
        entry["overall_pass_rate"] = round(
            sum(x["pass_rate"] for x in tasks.values()) / len(tasks), 3)
        entry["avg_seconds"] = round(sum(x["avg_seconds"] for x in tasks.values()) / len(tasks), 1)
        entry["avg_tokens"] = int(sum(x["avg_tokens"] for x in tasks.values()) / len(tasks))
        RESULTS.write_text(json.dumps(results, indent=1), encoding="utf-8")
        print(f"  => {entry['overall_pass_rate']:.0%} pass, {entry['avg_seconds']}s avg, "
              f"{entry['avg_tokens']} tok avg")

    write_report(results)
    print(f"\nresults -> {RESULTS}\nreport  -> {REPORT}")
    return 0


def write_report(results: dict) -> None:
    runs = results.get("runs", {})
    rows = sorted(runs.items(), key=lambda kv: -(kv[1].get("overall_pass_rate") or 0))

    L = ["# Local-model squads: how many agents actually help?\n",
         "Every seat costs a full model turn, and every handoff is a chance for a small model",
         "to garble the previous one's work. These runs test whether the extra seats buy",
         "correctness. Scoring is machine-checked: the produced file is executed against",
         "assertions the agents never see.\n",
         f"Agent seat: `{AGENT_MODEL}` · Reviewer seat: `{REVIEW_MODEL}` "
         "(both chosen from the measurements in REPORT.md).\n",
         "| Topology | Seats | Pass rate | Avg time | Avg tokens |",
         "|---|---:|---:|---:|---:|"]
    for name, r in rows:
        seats = next(iter(r.get("tasks", {}).values()), {}).get("seats", "-")
        L.append(f"| `{name}` | {seats} | **{(r.get('overall_pass_rate') or 0):.0%}** | "
                 f"{r.get('avg_seconds')}s | {r.get('avg_tokens')} |")
    L.append("")

    L.append("## Per task\n")
    task_ids = [t["id"] for t in TASKS]
    L.append("| Topology | " + " | ".join(task_ids) + " |")
    L.append("|---" * (len(task_ids) + 1) + "|")
    for name, r in rows:
        cells = []
        for tid in task_ids:
            t = r.get("tasks", {}).get(tid)
            cells.append("-" if not t else f"{t['pass_rate']:.0%} ({t['avg_seconds']}s)")
        L.append(f"| `{name}` | " + " | ".join(cells) + " |")
    L.append("")
    REPORT.write_text("\n".join(L) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
