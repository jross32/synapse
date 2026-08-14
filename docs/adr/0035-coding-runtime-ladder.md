# ADR-0035: Coding runtime ladder — paid runtimes first, local models as the overnight tier

- **Status:** accepted — shipping in v0.1.144
- **Date:** 2026-08-13
- **Deciders:** Justin (owner), Claude
- **Related:** ADR-0034 (automatic runtime delegation), ADR-0028 (AI activity), Contracts #2, #22, #25

## Context

The blueprint scaffold was built local-first: grind on free Ollama models for as many
attempts as it takes, and escalate to a frontier model only when the local loop is stuck.
The stated goal was saving tokens.

Two days of measurement did not support it.

| Measured | |
|---|---|
| Local pass rate, one nine-function stateful module | **1 in 5** runs |
| Local inference spent | 4.9 hours |
| Usable local output | ~101 lines — one correct module |
| Frontier tokens spent | **increased**, entirely on fixing the harness around the models |
| Same module via `claude --print` | correct first time, **12.9 seconds** |

Eight harness defects were found in the process, every one of which made the local models
look *worse* than they are — stale bytecode grading the previous attempt's code, acceptance
scenarios that never executed, a scenario that failed every attempt after the first on a
leftover database. Fixing them was worth doing, and the scaffold is better for it. None of
it changed the conclusion that a 7B on a 6 GB card is the wrong default for a piece this
size.

The owner's requirement is explicit: use Codex / Claude / Copilot while their credits last,
and fall to local models when they run out or when the work can be left running overnight.

## Decision

1. **Invert the ladder.** A build picks the best available runtime and falls to the free one
   only when forced: `claude → codex → copilot → local`. Local is the floor, and is always
   reachable so that a build can never be blocked purely by exhausted credit.

2. **Choose per piece, not per build.** A build routinely spans tiers when a paid runtime
   runs out of room halfway through. `PieceOutcome.runtime` and `.ladder_note` record which
   tier wrote each piece and what was skipped to get there; a build-level label would
   attribute the whole app to whoever started it.

3. **Share everything downstream of "who writes the code".** Contract assertions, the
   blueprint acceptance scenario, the repair loop and the `passed` / `verified` split are
   worth exactly as much when Claude wrote a piece as when a 7B did. `run_pipeline` takes an
   injectable `generate`; the tier is the only thing that varies. This is what makes the
   ladder cheap to add, and it is the durable return on the scaffold work.

4. **One definition of how to invoke a CLI.** The per-runtime headless flags move to
   `coder_runtimes.headless_argv`, and `routes_agent_squads` calls it rather than keeping a
   second copy. Each flag was learned from a real failure — a worker that sat forever at an
   interactive prompt, another that finished its review and refused to file it — and that
   knowledge should exist once.

5. **Be reluctant to declare a tier exhausted.** `looks_exhausted` inspects only the stderr
   of a *failed* invocation, skips traceback lines, matches English phrasing (`rate limit`)
   but not identifiers (`rate_limit`), and ignores `429` after `line ` or before
   `tests passed`. A false positive silently demotes a paid runtime to the free tier for an
   hour with nothing announcing it, so the eager direction is the expensive one and is
   pinned by nine cases. Cooldown is one hour, held in memory so a restart re-probes rather
   than inheriting a stale belief.

6. **Bound paid repairs harder than free ones.** `max_repairs` stays generous for local,
   where another attempt costs only time nobody is waiting on, and is capped at 3 for paid
   tiers, where every repair is a fresh billed session and a runtime that has failed three
   times with the contract, the scenario and the real error in front of it wants a human.

7. **Report the free tier in attempts, not pass rates.** `max_attempts` retries a failing
   piece from a genuinely clean slate — cleared bytecode, no leftover database, no leftover
   module — and records `attempts_to_first_success`. One run in five is a poor interactive
   tool and a serviceable overnight one; the metric has to say which is being claimed.

## Consequences

- The scaffold's value is restated honestly: it is what makes **any** runtime's output
  verifiable, not a way to make small models competitive. That claim is supported by the
  measurements; the earlier one was not.
- Builds now cost money by default. This is the owner's explicit preference, and (6) exists
  to keep it bounded.
- Local models retain a real job — overnight and credit-exhausted work — where their
  economics genuinely hold.
- Tests that stub the local generator must pin `ladder=(CoderRuntime.LOCAL,)`. Three
  existing cases were shelling out to the real Claude CLI before this was noticed, which is
  precisely the waste the ladder exists to avoid.

## Follow-ups

- Gate each local-reliability change on a 4-run batch measuring attempts-to-first-success;
  keep only what moves it. Kill criterion: if it does not reach ≤3, stop investing and let
  local remain best-effort overnight.
- Build a second blueprint of a different shape through the ladder to measure whether the
  scaffold amortises. That is the only thing that answers "did this save tokens".
