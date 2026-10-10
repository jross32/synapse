# Fail-Early Supervisory Development Loop

Use this loop for every meaningful Localization Studio change and reuse it across Synapse projects where applicable.

1. **Inspect** — read current project AI context, records, git status/diff, architecture, tests, runtime/tool status, and relevant evidence. Establish whether the baseline is already failing.
2. **Reconsider** — ask whether the requested/proposed implementation is still the highest-value next step. Prefer fixing a blocking foundation over adding downstream features.
3. **Reuse before inventing** — discover applicable Synapse tools, skill packs, quick actions, playbooks, blueprints, MCP tools, project helpers, and existing libraries.
4. **Pre-mortem** — before edits, enumerate plausible failures: contracts/API shape, migration/data loss, concurrency, security/privacy, stale caches, locale fallback, grammatical edge cases, Unicode, RTL, interpolation, missing keys, performance, accessibility, mobile overflow, test nondeterminism, concurrent repo edits, and rollback.
5. **Define proof first** — state machine-checkable acceptance criteria and the smallest tests/evidence that would falsify the implementation.
6. **Change narrowly** — make the smallest reversible scoped change. Preserve unrelated dirty/concurrent work.
7. **Fast verification** — syntax/type/static checks plus targeted unit/contract tests immediately.
8. **Repair + regressions** — fix failures at the cause and add a regression test when practical. Repeated failures should improve the harness, linter, fixture, skill, or preflight.
9. **Broader verification** — integration tests, browser/mobile flows, accessibility/human-view evidence, performance measurements, benchmark comparisons, and Quality OS gates as appropriate.
10. **Diff/evidence review** — inspect the final diff and receipts. Separate verified facts from assumptions. Tests reduce risk; they do not prove absence of defects.
11. **Durable handoff** — record decisions, failures, measurements, remaining risks, and exact next step in shared project context.
12. **Re-plan** — repeat from step 1 before advancing. Do not continue merely because the original plan said to.

## Stop / rollback rules
Stop and reassess on baseline failures, ambiguous destructive changes, unexpected broad diffs, conflicting concurrent edits, unverifiable quality claims, security/privacy uncertainty, or a newly discovered higher-priority blocker.

## Localization-specific rule
Never optimize speed before measuring correctness. Never expand locale count while the locale-pack contract is unstable. Never personalize a base locale with one person's language behavior. Never publish competitor superiority without blinded comparable evidence.
