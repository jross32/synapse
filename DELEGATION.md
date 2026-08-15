# Delegation: which runtime, at what effort, for what work

Written for whoever picks this up next — including a future me. Everything below is
measured on this machine, with the numbers and the date, so it can be checked rather than
believed. Where something is a guess it says so.

**The one-line version:** delegate any piece that arrives with a contract and an acceptance
scenario; keep for yourself only the work that decides what the shape should be.

---

## The ladder

```
claude  ->  codex  ->  copilot  ->  gemini  ->  local
```

Best first, free last. A rung is skipped when it is not installed or has reported being out
of room; the cooldown is remembered so an empty tier is not retried all afternoon.

| Rung | Cost | Speed | Use it for |
|---|---|---|---|
| `claude` | paid, metered in USD | fast | work needing judgement, or when the others fail |
| `codex` | paid | ~90 s a piece | **the default delegate.** Strongest quality-per-token measured |
| `copilot` | paid, monthly credits | ~40 s | untested end-to-end — quota was empty when tried |
| `gemini` | free, per-day | ~100–190 s | good fallback. Free tier is **per-model** — see below |
| `local` | free, unlimited | 4–50 min a piece | overnight only. ~1 pass in 5 |

## Measured: effort mode on codex (2026-08-15)

Eight builds, three real blueprint pieces, graded by each piece's own contract and
acceptance scenario — not by reading the output and nodding.

| Piece | Effort | Verified | Seconds | Tokens |
|---|---|---|---|---|
| reader | low | yes | 108 | 52,631 |
| reader | medium | yes | 100 | 25,099 |
| reader | high | yes | 152 | 30,342 |
| summary | low | yes | 63 | 21,268 |
| summary | medium | yes | 82 | 42,734 |
| summary | high | yes | 89 | 26,366 |
| **storage** (9 functions) | **low** | **yes** | **89** | 44,275 |
| storage (9 functions) | high | yes | 168 | 58,673 |

**8 of 8 verified, zero repairs, at every effort level.**

Three things follow:

1. **Use `low`.** Effort bought nothing measurable in quality. It cost real time — high
   averaged 136 s against low's 86 s. This reverses the `medium` default shipped in
   v0.1.151, which was reasoning rather than measurement.
2. **Token counts do not order by effort.** Low was cheapest on `summary` and dearest on
   `reader`. Run-to-run variance is larger than the effect, so anyone quoting a
   tokens-per-effort figure from a single run is quoting noise.
3. **The hard piece was not hard for codex.** `storage` is nine coupled functions across
   users, sessions and records — the piece the local tier failed 0/4 in every configuration
   across 441 minutes. codex:low verified it in 89 seconds, first try.

Why low is enough here is structural, not luck: a blueprint piece arrives with a declared
contract and an executable scenario, so the model is **filling in a known shape** rather
than deciding what the shape should be. Raise effort for work that must design something,
and let the loop escalate when low genuinely fails.

## What delegates well

The shape that worked, every time:

- **Small.** One module, a handful of functions. Nine coupled functions defeated the local
  tier entirely; three did not.
- **Contract-first.** The signatures are stated up front. Withholding them cost 10 repairs
  against 3 — see `benchmarks/app-build/CONTRACT_AB.md`.
- **Independently checkable.** An acceptance scenario written from the caller's side, which
  the delegate never sees. Without one, `passed` only means the model agrees with itself.

Two real examples, both written by Gemini on the free tier, both passing every test first
time: `runtime_usage.py` (105 s) and `runtime_ledger.py` (96 s). Roughly 700 lines that cost
nothing.

## What does not delegate

- Work where the contract is the thing being decided. Writing the spec costs about as much
  as writing the code, and you cannot check what you have not specified.
- Surgical edits inside a large file with a lot of surrounding context.
- Anything where you cannot state, in advance, what would prove it wrong.

## Free-tier facts worth knowing

- **Gemini's allowance is per-model and lopsided.** Flash and Flash-Lite get ~1,500
  requests/day; Pro gets 25–50 and is largely behind billing since May 2026. Always name a
  Flash model. Two delegated modules exhausted the daily quota.
- **Copilot** is monthly, and reports `You have exceeded your monthly quota`.
- **Qwen Code's** free OAuth tier closed on 15 April 2026. Do not plan around it.
- Every other free CLI agent (Cline, Aider, Goose, Continue) is bring-your-own-key: it
  spends credits you already have, through a different interface. No new capacity.

## Reading a result honestly

`passed` means the tests in the workspace went green, and most of those were written by the
same model that wrote the code — so it means **the model agrees with itself**. `verified`
means the blueprint's own scenario ran and passed. Checks that could not run report
`not_run`, never a pass.

If a scenario fails on something the model seemingly cannot fix, **suspect the scenario
first.** On this project that has been the cause more often than the model has: scenarios
that never executed, a scenario that deleted three guessed database filenames while the
model used a fourth, a contract checker that could not see a re-export, and a parser
verified only against imagined input.

## Spending

Every call records what it consumed — Claude reports exact `total_cost_usd`, gemini and
codex report tokens, copilot reports credits — into `data/runtime-ledger.jsonl`.

```python
from synapse_daemon import coder_runtimes as cr
for rung in cr.preflight():
    print(rung.runtime, rung.usable_now, rung.cost_usd_today, rung.note)
```

Run that before committing to a long build, rather than discovering mid-run that the rung
driving it is empty.

## Re-running the benchmark

```
python benchmarks/delegation/bench.py "codex:low,codex:high" reader,summary
BENCH_BLUEPRINT=webapp-auth-crud python benchmarks/delegation/bench.py "codex:low" storage
```

Results append to `benchmarks/delegation/results.json`. Numbers above are one machine, one
day, n=1 per cell — enough to choose a default, not enough to defend a ranking. If a result
here matters to a decision you are making, run it again.
