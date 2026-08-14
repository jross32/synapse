"""Gate each Phase C change on attempts-to-first-success, not on it sounding right.

Every variant is a config of one code version, so a whole sweep runs unattended without
anyone editing source between arms - which would silently make the arms incomparable.

Usage:
    python phase_c_batch.py <variant> [runs]

The unit is attempts-to-first-success. The local tier passes a large stateful module about
one run in five, which makes a per-attempt pass rate close to meaningless and the number of
attempts the thing that actually costs something.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "daemon"))

from synapse_daemon.blueprints import get_blueprint  # noqa: E402
from synapse_daemon.coder_runtimes import CoderRuntime  # noqa: E402
from synapse_daemon.scaffold.runner import build_blueprint  # noqa: E402

LOCAL = (CoderRuntime.LOCAL,)

VARIANTS: dict[str, dict] = {
    # The state before Phase C: whole-file repairs, the model's own test as a gate.
    "baseline": dict(blueprint="webapp-auth-crud", targeted_repair=False,
                     advisory_model_test=False, model="qwen2.5-coder:7b"),
    "targeted": dict(blueprint="webapp-auth-crud", targeted_repair=True,
                     advisory_model_test=False, model="qwen2.5-coder:7b"),
    "advisory": dict(blueprint="webapp-auth-crud", targeted_repair=False,
                     advisory_model_test=True, model="qwen2.5-coder:7b"),
    "both": dict(blueprint="webapp-auth-crud", targeted_repair=True,
                 advisory_model_test=True, model="qwen2.5-coder:7b"),
    # Same two switches, but the nine-function module split into three of three.
    "split": dict(blueprint="webapp-auth-crud-split", targeted_repair=True,
                  advisory_model_test=True, model="qwen2.5-coder:7b"),
    # The split with the other two switches OFF, so its contribution can be separated from
    # theirs. Without this, "split passed 4/4" is a claim about three changes at once.
    "split-plain": dict(blueprint="webapp-auth-crud-split", targeted_repair=False,
                        advisory_model_test=False, model="qwen2.5-coder:7b"),
    # A different model of the same size class, never tried on this task.
    "deepseek": dict(blueprint="webapp-auth-crud", targeted_repair=True,
                     advisory_model_test=True, model="deepseek-coder:6.7b"),
}

STORAGE_PIECES = {"storage", "store_users", "store_sessions", "store_records"}


async def one_run(variant: str, cfg: dict, ws: Path) -> dict:
    """Build only the storage-shaped pieces - they are where the failures live."""
    blueprint = get_blueprint(cfg["blueprint"])
    blueprint = blueprint.model_copy(update={
        "pieces": [p for p in blueprint.pieces if p.name in STORAGE_PIECES]})

    if ws.exists():
        shutil.rmtree(ws)
    ws.mkdir(parents=True)

    started = time.time()
    result = await build_blueprint(
        blueprint, workspace=ws, coder_model=cfg["model"], max_repairs=10, ladder=LOCAL,
        targeted_repair=cfg["targeted_repair"],
        advisory_model_test=cfg["advisory_model_test"],
    )
    # Judged on the pieces this actually built. `result.passed` also requires the assembled
    # app to start, and this deliberately builds a subset - so `app.py` imports an `api`
    # that was never generated and the whole-app check fails for a reason that has nothing
    # to do with what is being measured. Reported here rather than silently using the
    # convenient number.
    pieces_passed = bool(result.pieces) and all(p.passed for p in result.pieces)
    return {
        "variant": variant,
        "seconds": round(time.time() - started, 1),
        "passed": pieces_passed,
        "whole_app_passed": result.passed,
        "assembly_note": ("only the storage pieces are built here, so the assembled-app "
                          "check cannot pass and is not what this measures"),
        "pieces": [{"name": p.name, "passed": p.passed, "verified": p.verified,
                    "repairs": p.repairs, "seconds": p.seconds,
                    "stop_reason": p.stop_reason[:160]} for p in result.pieces],
    }


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("variant", choices=sorted(VARIANTS))
    ap.add_argument("runs", nargs="?", type=int, default=4)
    args = ap.parse_args()

    cfg = VARIANTS[args.variant]
    out = Path(__file__).resolve().parent / f"phase_c_{args.variant}.json"
    ws = Path(__file__).resolve().parent / f"phase-c-{args.variant}"

    print(f"=== {args.variant} === {json.dumps(cfg)}", flush=True)
    runs = []
    for i in range(1, args.runs + 1):
        record = await one_run(args.variant, cfg, ws)
        runs.append(record)
        flags = " ".join(f"{p['name']}={'ok' if p['passed'] else 'no'}"
                         for p in record["pieces"])
        print(f"  run {i}: passed={record['passed']} {record['seconds']:.0f}s  {flags}",
              flush=True)
        out.write_text(json.dumps({"variant": args.variant, "config": cfg, "runs": runs},
                                  indent=1), encoding="utf-8")

    wins = [i for i, r in enumerate(runs, 1) if r["passed"]]
    print()
    print(f"passed {len(wins)}/{len(runs)} runs" + (f" (first on attempt {wins[0]})"
                                                    if wins else ""))
    # The headline. Never a per-attempt rate on its own - it reads as a quality score and
    # is really a coin flip you are allowed to repeat for free.
    print("attempts to first success:",
          wins[0] if wins else f">{len(runs)} (never succeeded)")
    print(f"total wall clock: {sum(r['seconds'] for r in runs) / 60:.0f} min")


asyncio.run(main())
