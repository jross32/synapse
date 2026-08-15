"""Exercise the middle rungs of the ladder, which have never produced a piece.

`claude` has built 3 pieces and `local` has been measured for 441 minutes. `codex` and
`copilot` have built nothing, ever - and they are exactly the rungs that engage when Claude
credits run out, which is the whole reason the ladder exists. An argv mistake in either
would surface at the moment the user is already blocked.

Builds ONE small piece per runtime, so the credit cost is a single generation each.

    python prove_ladder_rungs.py codex
    python prove_ladder_rungs.py copilot
"""
from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "daemon"))

from synapse_daemon import coder_runtimes  # noqa: E402
from synapse_daemon.blueprints import get_blueprint  # noqa: E402
from synapse_daemon.scaffold.runner import build_blueprint  # noqa: E402

# The smallest real piece in the catalog: pure functions, a declared contract, and an
# acceptance scenario written from the caller's side.
PIECE = "reader"
ROOT = Path(__file__).resolve().parent


async def main() -> None:
    name = (sys.argv[1] if len(sys.argv) > 1 else "codex").lower()
    runtime = coder_runtimes.CoderRuntime(name)

    print(f"runtime  : {runtime.value}")
    print(f"available: {coder_runtimes.available(runtime)}")
    if not coder_runtimes.available(runtime):
        raise SystemExit(f"{runtime.value} is not usable on this machine")
    # A cooldown left over from an earlier experiment would silently skip the rung this
    # script exists to exercise.
    coder_runtimes.clear_exhausted(runtime)

    blueprint = get_blueprint("cli-csv-report")
    blueprint.pieces = [p for p in blueprint.pieces if p.name == PIECE]

    ws = ROOT / f"ladder-{runtime.value}"
    started = time.time()

    def log(event: dict) -> None:
        kind = event.get("type")
        if kind in {"piece_started", "piece_finished", "runtime_selected",
                    "runtime_exhausted", "runtime_failed"}:
            print(f"  [{time.time()-started:5.0f}s] {kind}: "
                  f"{ {k: v for k, v in event.items() if k != 'type'} }", flush=True)

    result = await build_blueprint(blueprint, workspace=ws, ladder=(runtime,),
                                   max_repairs=3, on_event=log)

    print()
    for p in result.pieces:
        print(f"  {p.name:<10} tier={p.runtime or '?':<10} passed={p.passed} "
              f"verified={p.verified} repairs={p.repairs}")
        print(f"      checks: {p.checks}")
        if not p.passed:
            print(f"      stop  : {p.stop_reason[:300]}")

    out = ROOT / f"ladder_{runtime.value}.json"
    out.write_text(result.model_dump_json(indent=1), encoding="utf-8")
    print(f"\n{result.summary()}\nwrote {out.name}")


asyncio.run(main())
