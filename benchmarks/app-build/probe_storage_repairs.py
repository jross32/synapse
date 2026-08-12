"""Build the `storage` piece alone and record what every repair attempt actually changed.

The question this answers: when a piece burns its whole repair budget, is the model *stuck*
(same failure, no idea what to do) or *thrashing* (fixing one assertion while breaking an
earlier one)? Those look identical in the build summary - both end in an escalation - and
they need opposite fixes. Stuck wants a better error message. Thrashing wants the model to
stop rewriting the entire file to fix one function.

Writes a JSON trail so the answer is data rather than an impression.
"""
from __future__ import annotations

import asyncio
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "daemon"))

from synapse_daemon.blueprints import get_blueprint  # noqa: E402
from synapse_daemon.local_pipeline import error_fingerprint, run_pipeline  # noqa: E402
from synapse_daemon.scaffold import contracts as contracts_mod  # noqa: E402

WS = Path(__file__).resolve().parent / "probe-storage"
TRAIL = Path(__file__).resolve().parent / "storage_repair_trail.json"
if "--with-contract" in sys.argv:
    WS = WS.with_name("probe-storage-contract")
    TRAIL = TRAIL.with_name("storage_repair_trail_contract.json")

# Which assertion in the scenario failed, so consecutive attempts can be compared by
# *position in the scenario* rather than by message text.
ASSERT_RE = re.compile(r"AssertionError: (.{0,120})", re.S)


def scenario_position(error: str, scenario: str) -> int:
    """Roughly where in the scenario the run died. -1 if it did not reach an assertion."""
    m = ASSERT_RE.search(error or "")
    if not m:
        return -1
    needle = m.group(1).strip().split("\n")[0][:60]
    for i, line in enumerate(scenario.splitlines()):
        if needle and needle[:40] in line:
            return i
    return -1


async def main() -> None:
    # .instantiate() resolves the {{records}} / {{title_field}} placeholders. Without it the
    # model is handed a spec containing literal `{{title_field}}` and asked to implement it,
    # which measures the probe rather than the pipeline.
    bp = get_blueprint("webapp-auth-crud").instantiate()
    piece = next(p for p in bp.pieces if p.name == "storage")
    WS.mkdir(parents=True, exist_ok=True)
    for stale in WS.glob("*.db"):
        stale.unlink()

    expected = contracts_mod.ModuleContract(
        module="storage",
        functions=[contracts_mod.FunctionSpec(name=f["name"], args=f.get("args", []))
                   for f in piece.contract["functions"]])
    extra = (contracts_mod.contract_test_source("storage", expected).rstrip()
             + "\n\n" + piece.tests.strip())

    # A/B: the same piece, with and without the signatures it will be graded against being
    # stated up front. The baseline is what every build did until now - held to a contract
    # it was never shown.
    with_contract = "--with-contract" in sys.argv
    spec = piece.spec
    if with_contract:
        spec += ("\n\nThe module MUST expose exactly these, with these parameter names in "
                 "this order - callers are already written against them:\n\n"
                 + expected.as_prompt())

    trail: list[dict] = []
    started = time.time()

    def log(event: dict) -> None:
        if event.get("type") == "repairing":
            err = str(event.get("error", ""))
            pos = scenario_position(err, piece.tests)
            trail.append({"attempt": event.get("attempt"),
                          "seconds": round(time.time() - started),
                          "fingerprint": error_fingerprint(err),
                          "scenario_line": pos,
                          "error": err[:400]})
            print(f"  repair {event.get('attempt'):>2}  "
                  f"[{time.time()-started:6.0f}s]  scenario_line={pos:>3}  "
                  f"{error_fingerprint(err)[:90]}", flush=True)

    print(f"building `storage` alone, max_repairs=10, "
          f"contract_in_prompt={with_contract} ...", flush=True)
    result = await run_pipeline(spec, workspace=WS, path="storage.py",
                               coder_model="qwen2.5-coder:7b", max_repairs=10,
                               extra_test=extra, on_event=log)

    print(f"\npassed={result.passed}  attempts={len(result.attempts)}  "
          f"{result.total_seconds:.0f}s\nstop_reason: {result.stop_reason}")

    positions = [t["scenario_line"] for t in trail if t["scenario_line"] >= 0]
    prints = {
        "contract_in_prompt": with_contract,
        "passed": result.passed,
        "attempts": len(result.attempts),
        "seconds": result.total_seconds,
        "stop_reason": result.stop_reason,
        "distinct_fingerprints": len({t["fingerprint"] for t in trail}),
        "scenario_positions": positions,
        "monotonic_progress": positions == sorted(positions),
        "trail": trail,
    }
    TRAIL.write_text(json.dumps(prints, indent=1), encoding="utf-8")

    print(f"\ndistinct failures: {prints['distinct_fingerprints']} across {len(trail)} repairs")
    print(f"scenario positions reached: {positions}")
    # `passed` first. Without it this reported a successful build as "PROGRESSING - ran out
    # of budget", which is the same class of mistake as everything else this probe found:
    # a summary that never consults the one field that settles the question.
    if result.passed:
        verdict = f"PASSED - every scenario assertion, after {len(trail)} repairs"
    elif positions and not prints["monotonic_progress"]:
        verdict = "THRASHING - it went backwards"
    elif len(set(positions)) <= 1:
        verdict = "STUCK - same place every time"
    else:
        verdict = "PROGRESSING - ran out of budget, not ideas"
    print("verdict:", verdict)


asyncio.run(main())
