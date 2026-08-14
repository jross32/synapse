"""Phase D: build a second, differently-shaped blueprint through the ladder.

The question this exists to answer is the one the whole scaffold was justified by: does it
*amortise*? `webapp-auth-crud` cost two days, almost all of it spent building the machinery
rather than the app. If that machinery is worth having, a blueprint that shares none of its
subject matter - no HTTP, no HTML, no browser - should be cheap.

Reports what each piece cost and which tier wrote it, because "it worked" is not the claim
under test.
"""
from __future__ import annotations

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

WS = Path(__file__).resolve().parent / "phase-d-cli"
OUT = Path(__file__).resolve().parent / "phase_d_result.json"


async def main() -> None:
    ladder = (CoderRuntime.CLAUDE, CoderRuntime.CODEX, CoderRuntime.COPILOT,
              CoderRuntime.LOCAL)
    blueprint = get_blueprint("cli-csv-report")
    if blueprint is None:
        raise SystemExit("cli-csv-report is not in the catalog")

    if WS.exists():
        shutil.rmtree(WS)
    WS.mkdir(parents=True)

    started = time.time()

    def log(event: dict) -> None:
        kind = event.get("type")
        if kind in ("piece_started", "piece_finished"):
            print(f"  [{time.time() - started:5.0f}s] {kind}: {event.get('piece')} "
                  f"{'ok' if event.get('passed') else ''}", flush=True)
        elif kind == "repairing":
            print(f"      repair {event.get('attempt')}: "
                  f"{str(event.get('error'))[:100]}", flush=True)
        elif kind == "targeted_repair":
            print(f"      -> rewriting only `{event.get('function')}`", flush=True)
        elif kind == "runtime_exhausted":
            print(f"      !! {event.get('runtime')} out of room: "
                  f"{event.get('detail')}", flush=True)

    result = await build_blueprint(blueprint, workspace=WS, max_repairs=10, ladder=ladder,
                                   max_attempts=2, on_event=log)

    print()
    print(result.summary())
    for piece in result.pieces:
        print(f"  {piece.name:<10} {'PASS' if piece.passed else 'ESCALATE':9s} "
              f"runtime={piece.runtime:<8} repairs={piece.repairs} "
              f"verified={piece.verified} {piece.seconds:5.0f}s")
        if piece.checks:
            print(f"             checks={piece.checks}")
        if not piece.passed:
            print(f"             {piece.stop_reason[:160]}")

    OUT.write_text(result.model_dump_json(indent=1), encoding="utf-8")
    print(f"\nwritten to {OUT.name}")


asyncio.run(main())
