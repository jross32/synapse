# Topology run — turnkey checklist (Plan 3 Phase 2)

Everything needed to actually *run* the bug-hunt topology benchmark and rank the arms by
`bugs_per_1k_tokens`. It ties together the pieces already shipped: the fixture (`app/`), the
`answer-key.json`, the grader (`grade.py`), the daemon scoring endpoint
(`POST /benchmarks/score-bug-hunt`), per-worker token accounting (`work_item_token_usage` +
handoff self-report), and coordination lanes (ADR-0024) that keep hunters off each other's surfaces.

This needs a **hands-on session** — it launches real agents. It is not something the autonomous
improvement loop runs on its own.

## 0. Serve the fixture
```bash
cd benchmarks/bug-hunt-fixture/app && python -m http.server 8123
# fixture now at http://127.0.0.1:8123
```
Keep this running for every arm. All arms hunt the **same** URL so the comparison is fair.

## 1. The arms (same fixture, same token-source class for all)
| Arm | Setup |
|-----|-------|
| `solo-baseline` | one non-Synapse agent (plain `claude`), no coordination, Playwright MCP — the number to beat |
| `flat-5-pros` | 5 parallel Synapse hunters, no supervisor |
| `supervisor-tree` | `qa-lead` → lane-separated browser hunters → `triage-steward` → `bug-report-synthesist` (seeded default) |
| `many-small-tasks` | many single-surface micro-tasks |

For the Synapse arms, install the roster once (`POST /ai-bundles/install/qa-bug-hunt-squad`) and
create the squad (`POST /agent-squads`), then launch work items against `http://127.0.0.1:8123`.
Assign each hunter a distinct surface via a coordination lane (`POST /coordination/lanes`) so no two
workers test the same thing.

## 2. Collect findings + tokens (per arm, ≥3 repeats)
- **Findings** — each hunter reports `{surface, text}` bugs; the `bug-report-synthesist` dedupes
  them into one findings array per run. (For the solo arm, the single agent's report is the array.)
- **Tokens** — every worker self-reports its CLI usage line on **handoff**
  (`POST /agent-work-items/{id}/handoff` with `total_tokens`), recorded in `work_item_token_usage`.
  Roll up the arm's total with `sum_squad_tokens(squad_id)`. Same token-source class
  (`runtime_self_report` / `reported`) for every arm — never compare a harness counter to a CLI one.

## 3. Score each run
```bash
# via the daemon (what a squad synthesist would call):
curl -s -X POST "$SYNAPSE_API/benchmarks/score-bug-hunt" \
  -H "X-Synapse-Token: $SYNAPSE_TOKEN" -H "Content-Type: application/json" \
  -d "{\"answer_key\": $(cat answer-key.json), \"findings\": $(cat run-findings.json), \"total_tokens\": 14200}"

# or offline:
python grade.py --findings run-findings.json --tokens 14200
```
Record `true_positives`, `false_positive_rate`, and the headline `bugs_per_1k_tokens` for each run.

## 4. Rank + publish
- ≥3 repeats per arm; attach the benchmark engine's confidence label (a single run is noisy).
- The winning topology = highest median `bugs_per_1k_tokens` at an acceptable `false_positive_rate`
  (a fast arm that hallucinates bugs is not a win).
- Publish under `benchmarks/bug-hunt-fixture/results/` like `makeup-business-demo/results/`
  (a `tokens/` folder, a `quality/` folder, a `summary.md`); keep every raw run in `raw-logs/`.
- Seed the winner as the `qa-bug-hunt-squad` bundle's default topology.

## 5. Honesty gates (inherited)
Same fixture + same answer key for every arm; no arm-specific tweaks; same token-source class;
exclude `unknown`-provenance token counts; keep the raw runs visible. If the winner only wins on
speed while missing bugs the baseline caught, say so — the claim is *more bugs per 1k tokens*, not
*fastest*.
