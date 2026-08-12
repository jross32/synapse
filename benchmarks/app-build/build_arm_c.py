"""Arm C: build the same app from the blueprint, through the scaffold."""
from __future__ import annotations
import asyncio, json, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "daemon"))

from synapse_daemon.blueprints import get_blueprint
from synapse_daemon.scaffold.runner import build_blueprint

WS = Path(__file__).resolve().parent / "arm-c-blueprint"

async def main() -> None:
    bp = get_blueprint("webapp-auth-crud")
    started = time.time()
    def log(e):
        t = e.get("type")
        if t in ("piece_started", "piece_finished"):
            print(f"  [{time.time()-started:6.0f}s] {t}: {e.get('piece')} "
                  f"{'ok' if e.get('passed') else ''}", flush=True)
        elif t == "repairing":
            # The last line of a traceback is the assertion message, and the assertion
            # messages are the entire point of the scenarios - truncating the head of the
            # traceback threw away the diagnosis and kept the boilerplate.
            err = str(e.get("error") or "").strip().splitlines()
            tail = next((ln.strip() for ln in reversed(err) if ln.strip()), "")
            print(f"      repair {e.get('attempt')}: {tail[:220]}", flush=True)
    result = await build_blueprint(bp, workspace=WS, coder_model="qwen2.5-coder:7b",
                                   max_repairs=10, on_event=log)
    print("\n" + result.summary())
    for p in result.pieces:
        mark = "VERIFIED" if p.verified else ("passed" if p.passed else "ESCALATE")
        print(f"  {p.name:10s} {mark:9s} repairs={p.repairs} "
              f"{p.seconds:6.0f}s  checks={p.checks} {p.stop_reason[:60]}")
    (WS / "build_result.json").write_text(result.model_dump_json(indent=1), encoding="utf-8")

asyncio.run(main())
