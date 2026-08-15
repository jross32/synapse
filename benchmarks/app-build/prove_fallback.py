"""Prove the ladder falls through, using a tier that is genuinely out of credits.

Copilot on this machine really has exceeded its monthly quota. That is the exact condition
the ladder was built for, available for once as a fact rather than a simulation - so the
fallback is tested against the real thing instead of a mocked failure.

Ladder: copilot (exhausted) -> codex. A pass means the build noticed, dropped a rung, and
finished, and that the piece records which tier actually wrote it.
"""
from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "daemon"))

from synapse_daemon import coder_runtimes  # noqa: E402
from synapse_daemon.blueprints import get_blueprint  # noqa: E402
from synapse_daemon.scaffold.runner import build_blueprint  # noqa: E402

ROOT = Path(__file__).resolve().parent
LADDER = (coder_runtimes.CoderRuntime.COPILOT, coder_runtimes.CoderRuntime.CODEX)


async def main() -> None:
    for runtime in LADDER:
        coder_runtimes.clear_exhausted(runtime)

    blueprint = get_blueprint("cli-csv-report")
    blueprint.pieces = [p for p in blueprint.pieces if p.name == "reader"]

    started = time.time()

    def log(event: dict) -> None:
        if event.get("type") in {"runtime_selected", "runtime_exhausted", "runtime_failed",
                                 "piece_finished"}:
            rest = {k: v for k, v in event.items() if k not in {"type", "blueprint"}}
            print(f"  [{time.time()-started:5.0f}s] {event['type']}: {rest}", flush=True)

    ws = ROOT / "ladder-fallback"
    result = await build_blueprint(blueprint, workspace=ws, ladder=LADDER,
                                   max_repairs=2, on_event=log)

    piece = result.pieces[0]
    print()
    print(f"  tier that wrote it : {piece.runtime}")
    print(f"  passed / verified  : {piece.passed} / {piece.verified}")
    print(f"  copilot cooling    : {coder_runtimes.cooling_down(LADDER[0]):.0f}s")

    ok = piece.passed and piece.runtime == coder_runtimes.CoderRuntime.CODEX.value
    print("\n" + ("FALLBACK WORKS: exhausted rung skipped, next rung finished the piece"
                  if ok else "FALLBACK FAILED - see above"))


asyncio.run(main())
