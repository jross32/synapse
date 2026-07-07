# Bug-Hunt Fixture — token-efficiency benchmark (Plan 3 Phase 2)

A fixed, deliberately-buggy static site (`app/`) plus a machine-checkable `answer-key.json`.
Point a bug-hunt run at it, collect the findings + the tokens spent, and `grade.py` scores the
run mechanically. This is the fixture that lets us prove the core Plan 3 claim honestly:

> **A Synapse bug-hunt squad finds more true bugs per 1k tokens than a single non-Synapse agent.**

Nothing here depends on the live site being pretty — `app/` exists only to *contain* the 12 bugs
in the answer key. Every bug is genuinely present in the source and independently detectable.

## The app
`app/` is a 3-file static site (`index.html`, `style.css`, `script.js`) — a small bakery landing
page with a newsletter form, a contact form, a gallery, and a nav bar. Serve it with any static
server (e.g. `python -m http.server` from `app/`) and open it in a browser. Two of the bugs (the
mobile-nav overlap and the low-contrast success text) only show up when you actually render it, so
a browser-driving arm should catch bugs a source-only arm misses — that difference is part of what
the benchmark measures.

## The answer key
`answer-key.json` lists **12 bugs** across 7 categories (functional, state, ui, performance,
accessibility, edge-case, security) and 4 severities. Each bug has:
- `surface` — where it lives (contact form, header/nav, gallery, …)
- `detect` — how to reproduce it
- `match` — keyword phrases a grader uses to link a reported finding to this bug

## Scoring (mechanical, via `grade.py`)
A run produces a **findings file**: a JSON array of objects, each with at least a `text` field
(the finding description) and optionally a `surface`:

```json
[
  { "surface": "contact form", "text": "Empty submit still shows success — no validation" },
  { "surface": "header", "text": "Mobile nav overlaps the logo and can't be tapped" }
]
```

Grade it:

```bash
python grade.py --findings run-findings.json --tokens 14200
```

- **true positive** — a finding whose text contains any of a bug's `match` phrases (each bug is
  claimed at most once; duplicate findings for the same bug are counted as `duplicate`, not TP).
- **false positive** — a finding matching no bug in the key.
- **miss** — a key bug no finding matched.
- **`bugs_per_1k_tokens`** = `true_positives / (tokens / 1000)` — the headline efficiency number.
- **`false_positive_rate`** = `false_positives / (true_positives + false_positives)`.
- **`recall`** = `true_positives / 12`.

## Benchmark arms
Run the **same** fixture through each arm, **same token-source class** for every arm (self-reported
CLI usage — `runtime_self_report` / `reported`, matching `benchmarks.py`'s provenance rules so a
harness counter is never compared against a CLI counter), ≥3 repeats, then compare `bugs_per_1k_tokens`:

| Arm | What it is |
|-----|-----------|
| `solo-baseline` | one non-Synapse agent, no coordination — the number to beat |
| `flat-5-pros` | 5 parallel Synapse hunters, no supervisor |
| `supervisor-tree` | `qa-lead` → lane-separated hunters → `triage-steward` → `bug-report-synthesist` (the seeded default) |
| `many-small-tasks` | many single-surface micro-tasks |

The winning topology (highest `bugs_per_1k_tokens` at an acceptable `false_positive_rate`) becomes
the seeded default for the `qa-bug-hunt-squad` bundle. Publish results under `results/` like
`makeup-business-demo/results/` (a `tokens/` and a `quality/` folder + a `summary.md`), and keep
every raw run in `raw-logs/` for transparency.

## Honesty rules (inherited from Plan 3 + `AGENTS.md`)
- Same fixture + same answer key for every arm; no arm-specific tweaks.
- Same token-source class across arms; exclude `unknown`-provenance counts from comparison.
- ≥3 repeats + a confidence label (a single run is noisy).
- The answer key only lists bugs that are actually in `app/`; if you add a bug to the key, add it
  to the source in the same commit (and vice-versa).
