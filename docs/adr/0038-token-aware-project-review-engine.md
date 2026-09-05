# ADR-0038 — Token-Aware Project Review Engine

**Status:** proposed / implemented in first increment  
**Date:** 2026-09-04

## Context

Synapse already has three pieces that should not be duplicated:

1. coder review passes that can run sidecar reviewers through the configured coder runtimes,
2. quality gates and structured review verdicts,
3. human review/proposal surfaces plus token/runtime accounting.

What was missing was the decision layer in front of those systems. A tiny documentation edit and a high-risk auth/payment/trading change were equally capable of being handed to an expensive model with a large context. Project-specific invariants also tended to live in a worker prompt instead of a durable repository contract.

A recent Stock Hunter pull-request review illustrated the value of independent review: a behavioral contract change could be sound while release/version metadata remained stale. The useful lesson is not “send every repository to several models.” It is “cheap checks first, then the smallest independent review justified by the changed risk surface.”

## Decision

Add a project-wide Smart Review Engine under the existing `/api/v1/review` surface.

### Review funnel

For each requested change:

1. **Observe the change only.** Use an explicitly supplied PR/coder diff or a local `git status` + `git diff HEAD`. Do not ingest the repository by default.
2. **Run deterministic guards first.** Secret-bearing files, source-without-test signals, migration evidence, release-document checks, and git-inspection health cost no model tokens.
3. **Classify risk.** Auth/security/payments/migrations/deployment/trading/execution paths are high risk; backend/API/data-contract changes are medium risk; small ordinary changes are low risk.
4. **Select review depth automatically.**
   - `economy`: 8k-token budget, at most 1 AI pass
   - `standard`: 30k, at most 2 passes
   - `thorough`: 60k, at most 3 passes
   - `release`: 100k, at most 4 passes
5. **Skip AI when it adds little value.** Docs-only changes skip AI by default. Empty changes and deterministic secret blockers also spend zero AI tokens.
6. **Use independent reviewers when practical.** If Codex is the primary coder, prefer Claude/Copilot before Codex for review; equivalent rotation applies to the other primary runtimes.
7. **Reuse the existing coder review-pass runtime.** The engine queues review passes; the established launch route owns sandboxing, runtime execution, verdicts, quality gates, and exact usage accounting.

### API

`POST /api/v1/review/engine/plan/{project_id}`

Returns the risk, effective policy, deterministic findings, estimated context size, remaining budget, and recommended specialist passes. It does not invoke an AI.

`POST /api/v1/review/engine/queue/{project_id}`

Runs the same plan and creates only the justified coder review passes. It returns the existing coder-review launch URLs, so a Synapse AI coder, CLI integration, UI, or GitHub event handler can continue through the normal runtime path.

The request may carry an exact external diff and changed-file list. That permits future GitHub webhook integration without giving GitHub-specific code ownership of the review logic.

## Project-specific review contracts

Every Synapse-managed project receives useful defaults automatically. A project can specialize them by committing:

`.synapse/review-policy.json`

Example:

```json
{
  "mode": "standard",
  "token_budget": 30000,
  "max_ai_passes": 2,
  "max_diff_chars": 60000,
  "focus_points": [
    "Point-in-time evidence must never use future data.",
    "A confidence score must not be described as a guaranteed return."
  ]
}
```

The file is data only; Synapse never executes project code to load the policy. Values are bounded so a repository cannot silently request an unlimited review budget.

This is the preferred way to encode Stock Hunter evidence/execution invariants, WhatIf Pulse health-state truthfulness, UI human-pass expectations, game mobile/desktop checks, MCP tool safety classifications, and future project-specific contracts without hard-coding project names into Synapse.

## Security and cost boundaries

- A changed `.env`, `.env.local`, `.env.production`, `credentials.json`, or `secrets.json` is a deterministic blocker. The diff is withheld from queued AI review context.
- Supplied diffs are capped at 500k characters and reviewer context is separately bounded by the selected policy.
- AI passes are capped at four even when a project policy asks for more.
- Project token budgets are clamped to 4k–120k.
- Review prompts explicitly constrain the reviewer to the supplied change and prohibit speculative repo-wide cleanup.
- A second opinion is a risk-based escalation, not a default tax on every edit.

## Follow-up increments

1. Add a Review UI panel showing risk, selected mode, estimated/actual tokens, findings, and one-click launch/verify.
2. Add GitHub webhook/event ingestion: PR opened/pushed -> plan -> queue -> publish findings; rerun only affected findings after updates.
3. Feed exact completed-run token/cost telemetry back into review-plan calibration so budget estimates learn from observed runtimes.
4. Add content-hash caching for durable architecture/project-contract context.
5. Add deterministic project adapters (release metadata/version alignment, lockfile/manifest pairing, migration/test contracts) without increasing model spend.

## Consequences

The useful part of automated review becomes available to every managed project immediately, while token spend scales primarily with changed risk rather than repository size. Synapse remains the orchestration and policy layer; coder runtimes remain execution providers; quality gates remain the blocking-verdict authority; humans retain the final approval surface for consequential actions.
