"""Which runtime, at which effort, for which kind of work.

The point is to stop guessing. Every combination below builds a REAL blueprint piece and is
graded by that piece's own contract and acceptance scenario - so "it worked" means the same
thing here as it does in a build, rather than being a human reading the output and nodding.

Cost is read from what each CLI reports about itself (`runtime_usage`), not estimated.

    python bench.py codex:low,codex:medium,codex:high reader
    python bench.py local:- reader,summary
"""
from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "daemon"))

from synapse_daemon import coder_runtimes as cr  # noqa: E402
from synapse_daemon.blueprints import get_blueprint  # noqa: E402
from synapse_daemon.scaffold.runner import build_blueprint  # noqa: E402

ROOT = Path(__file__).resolve().parent
BLUEPRINT = __import__("os").environ.get("BENCH_BLUEPRINT", "cli-csv-report")


async def run_one(runtime: str, effort: str, piece: str) -> dict:
    """Build one piece with one setting, and let the blueprint decide whether it worked."""
    blueprint = get_blueprint(BLUEPRINT)
    blueprint.pieces = [p for p in blueprint.pieces if p.name == piece]

    rt = cr.CoderRuntime(runtime)
    cr.clear_exhausted(rt)
    profile = cr.RuntimeProfile(effort=effort) if effort and effort != "-" else None
    if rt is cr.CoderRuntime.GEMINI:  # keep the free tier on the model that has one
        profile = cr.RuntimeProfile(model="gemini-2.5-flash", effort=effort or "")

    ws = ROOT / f"ws-{runtime}-{effort or 'default'}-{piece}"
    started = time.time()
    result = await build_blueprint(
        blueprint, workspace=ws, ladder=(rt,), max_repairs=3,
        runtime_profiles={rt: profile} if profile else None,
    )
    outcome = result.pieces[0]
    usage = outcome.usage or {}
    return {
        "runtime": runtime,
        "effort": effort or "default",
        "piece": piece,
        "passed": outcome.passed,
        "verified": outcome.verified,
        "repairs": outcome.repairs,
        "seconds": round(time.time() - started, 1),
        "cost_usd": round(float(usage.get("cost_usd", 0.0) or 0.0), 4),
        "total_tokens": int(usage.get("total_tokens", 0) or 0),
        "stop_reason": outcome.stop_reason[:160],
    }


async def main() -> None:
    combos = (sys.argv[1] if len(sys.argv) > 1 else "codex:low,codex:medium,codex:high")
    pieces = (sys.argv[2] if len(sys.argv) > 2 else "reader").split(",")

    rows: list[dict] = []
    for combo in combos.split(","):
        runtime, _, effort = combo.partition(":")
        for piece in pieces:
            print(f"--- {runtime}:{effort or 'default'} / {piece}", flush=True)
            try:
                row = await run_one(runtime, effort, piece)
            except Exception as exc:  # noqa: BLE001 -- one bad combo must not end the sweep
                row = {"runtime": runtime, "effort": effort or "default", "piece": piece,
                       "passed": False, "verified": False, "error": f"{type(exc).__name__}: {exc}"[:200]}
            rows.append(row)
            print(f"    {json.dumps({k: v for k, v in row.items() if k != 'stop_reason'})}",
                  flush=True)

    out = ROOT / "results.json"
    prior = json.loads(out.read_text(encoding="utf-8")) if out.exists() else []
    out.write_text(json.dumps(prior + rows, indent=1), encoding="utf-8")

    print("\n| runtime | effort | piece | verified | repairs | seconds | tokens | cost |")
    print("|---|---|---|---|---|---|---|---|")
    for r in rows:
        print(f"| {r['runtime']} | {r['effort']} | {r['piece']} | "
              f"{'yes' if r.get('verified') else 'NO'} | {r.get('repairs','-')} | "
              f"{r.get('seconds','-')} | {r.get('total_tokens','-')} | "
              f"${r.get('cost_usd', 0)} |")


asyncio.run(main())
