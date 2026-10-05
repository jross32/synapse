# Repair Arena

Use Repair Arena when a Synapse project needs diagnosis, repair planning, reliability improvement, regression-risk review, or a second opinion on what to fix next.

## Preferred entrypoint

Call the native Synapse MCP tool:

`synapse_repair_arena(project_id, rounds=2, mode="demo", prepare_candidates=false)`

Use the registered Synapse project id. Do not ask the user for a filesystem path when Synapse already knows the project.

## What the tool guarantees

The default Repair Arena pass is a **planning and evidence-selection stage**:

1. App Doctor scans the target repository read-only.
2. It returns a scored baseline, prioritized findings, redacted evidence, and bounded test-plan discovery.
3. Agent Arcade runs distinct repair strategies: architecture/boundaries, test-first implementation, and failure/false-positive critique.
4. The tournament is persisted and returns a traceable tournament id, scoreboard, champion, and winning plan.
5. The target repository is not modified, target tests are not executed, target project code is not executed, and nothing is auto-merged by this stage.

## Isolated candidate staging

When the next step is worth implementing, call the same tool with `prepare_candidates=true` and optionally `candidate_count=1..3`. Repair Arena will:

1. take the highest-ranked final-round plans;
2. create one Git branch/worktree per candidate from the same committed base;
3. place the orchestration brief outside each worktree so every candidate starts clean;
4. report the branch, worktree path, base commit, and whether the primary working-tree status stayed unchanged; and
5. leave all candidates unmerged and unexecuted.

Staging **does mutate Git metadata** by creating branches/worktrees. It does not copy uncommitted primary-tree changes into the candidates, and it must never claim the primary tree was preserved if its before/after status changed during staging.

A staged candidate is still only a workspace plus plan. A separate implementation worker must inspect the evidence and make the actual change inside that worktree.

## Read-only candidate evaluation

After a worker has changed a staged worktree, call `synapse_repair_candidate_evaluate(project_id, tournament_id, candidate)` from any connector, including the read-only connector. Use the tournament id from the staging receipt and an agent id/name or rank.

The evaluator:
- resolves the staged worktree from Repair Arena metadata instead of asking for a filesystem path;
- inspects the Git diff against the common base commit;
- re-runs App Doctor read-only;
- reports fixed/persisted/new finding ids, score delta, changed files, and new high/critical findings;
- never executes target tests or project code; and
- always keeps promotion closed until the remaining verification gates are supplied.

Treat `static_improvement_detected` as provisional evidence, not a winner. A clean candidate may mean either "not started" or a deliberate abstention, so inspect its rationale before ranking it below a code-changing candidate.

## Never confuse ranking with proof

A Repair Arena champion is the **best-scoring proposal in that tournament**, not a verified repair.

Do not say a defect is fixed because:
- a plan won;
- a score is high;
- App Doctor's static score improved without inspecting the finding;
- multiple simulated agents agree.

Treat scanner findings as hypotheses until the cited evidence is inspected. Test fixtures, generated verification helpers, deliberate debug tooling, and non-production files can create false positives.

## Promotion protocol

After the planning tournament, promote a candidate only when all applicable evidence gates are satisfied:

1. Inspect the winning plan against the actual cited files/evidence.
2. Preserve unrelated dirty work.
3. When implementation is justified, prefer `prepare_candidates=true` so the finalists get isolated branches/worktrees from the same base, then implement only inside a candidate worktree.
4. Add or tighten a regression test that fails for the real defect rather than merely encoding the scanner heuristic.
5. Run proportionate tests.
6. If behavior is user-visible, run desktop/mobile browser or runtime proof.
7. Re-run App Doctor and compare before/after findings, not just the aggregate score.
8. Reject or roll back the repair if it broadens scope, introduces a higher-severity finding, breaks tests, worsens browser behavior, or cannot be verified.

## Mode selection

### `demo`
Use by default for a fast, deterministic, local competition. It is useful for structure, critique, and reproducible workflow testing. It does **not** represent independent live-model consensus.

### `gemini`
Use only when live-model reasoning is materially useful and the runtime is available. It may consume external quota and can fail due to provider availability. The same promotion gates still apply.

## Rounds

- 1 round: fast second opinion.
- 2 rounds: default; enough for critique/refinement.
- 3 rounds: use for complicated or higher-risk repair planning.

More rounds are not automatically more trustworthy. Evidence quality matters more than tournament length.

## How to report results

Surface these items clearly:
- project id/name;
- App Doctor baseline score/grade;
- highest-severity findings and whether they are verified or heuristic;
- discovered verification/test plans;
- tournament id;
- champion and scoreboard;
- winning plan summary;
- explicit statement that the planning pass did or did not modify/run the target project;
- next evidence required before promotion.

## When not to use Repair Arena

Skip it when:
- the user only wants a simple factual explanation;
- there is no project/repository to diagnose;
- a known deterministic fix is already fully specified and Repair Arena would add ceremony without reducing risk.

For release-critical, security-sensitive, data-loss-prone, or high-blast-radius changes, Repair Arena should complement—not replace—specialized review/security tooling and human approval where required.
