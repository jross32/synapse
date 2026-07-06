# ADR-0025: QA / bug-hunt agent team — per-role MCP binding, a QA bundle, and a launchable Bug-Hunt Squad

- **Status:** accepted
- **Date:** 2026-07-06
- **Deciders:** Justin (owner), Claude
- **Related contracts:** #2 (status enum), #8/#9 (generated types / migrations), #11 (audit log). Builds on ADR-0017 (MCP auto-wiring), ADR-0018 (roles + personalities), ADR-0021 (AI bundles), ADR-0023 (AI Council Review), ADR-0024 (coordination lanes), and the Quality OS (migration 019: ui_contracts / quality_evidence / quality_gates).

## Context

Justin asked for a **token-efficient bug-finding + QA + "act-like-a-real-user" agent team** inside Synapse: agents that actually click buttons and act as mobile/desktop users, hunt UI/UX/accessibility bugs, scale to many concurrent agents, and produce deeper testing while spending **fewer tokens than a non-Synapse single-agent approach** — with a benchmark to pick the best team topology. Three read-only Explore agents + one Plan agent mapped the terrain (Plan 3 in the session plan file): **~80% already exists** (roles/personalities, squad launch + MCP auto-wire, the Quality OS evidence backbone, the benchmark engine). The one strongly-held design finding: **"many many roles" is a token/duplication anti-pattern** — every role is a parallel PTY worker that re-reads a full role prompt, and near-duplicate roles produce near-duplicate findings, which lowers `quality_per_1k_tokens`. Justin agreed (chose the lean option).

## Decision

Ship the QA / bug-hunt team **reuse-first**, in committed increments:

1. **Per-role MCP binding (migration 021).** A role scopes which MCP servers its workers receive via `agent_role_templates.mcp_server_ids`: `null` → all enabled (backward-compatible), `[]` → none, `[ids]` → only those. Fixes a real bug (every Claude worker previously received *every* enabled server — a token cost + attack surface). Browser roles get only Playwright; coordination roles get none.
2. **The `qa-bug-hunt-squad` AI bundle.** A lean roster — **9 roles** (browser hunters `user-simulator` / `edge-case-hunter` / `state-corruptor` / `ux-critic` / `a11y-auditor`; coordination `qa-lead` / `triage-steward` / `bug-report-synthesist` / `token-steward`) — plus **12 user personas** and a viewport parameter (mobile/tablet/desktop). Diversity lives in **personalities × viewports**, not role count: ~9 roles × ~12 personas × 3 viewports = dozens of distinct behaviors on a token-lean role set.
3. **A launchable `bug-hunt-squad` quick-action.** Modeled on `autonomous-boss` (ADR-0013): it drives Synapse's own REST API to assemble the squad, claim a **coordination lane per surface** (ADR-0024) so no two hunters overlap, launch lane-separated browser hunters that drive the app via the Playwright MCP as their persona, and record findings as **Quality OS evidence** (`POST /ui-contracts/{id}/run`, a FAIL auto-opens a blocking gate). The daemon stays thin (the agent drives the browser via MCP; the daemon records) — matching ADR-0003.
4. **Default topology: a narrow two-pass supervised tree** — `qa-lead` → parallel lane-separated hunters → `triage-steward` (dedupe) → `bug-report-synthesist` (file gates once). Two-pass already beat the non-Synapse baseline on all six dimensions at ≤ its tokens (makeup-business-demo). The topology benchmark will validate/tune this.
5. **Browser driver = Playwright MCP now; a lower-token custom driver later, benchmark-gated** (candidate: the web-scraper MCP's structured extraction vs Playwright's token-heavy snapshots) — adopt only if it wins.

Token discipline is **structural**: hunters run at `minimal` context with only the browser MCP; coordination roles carry no MCP; findings are deduped once and filed in a single batched pass instead of every worker opening gates.

## Maturity (be honest)

**Shipped + tested (this ADR):** per-role MCP binding (migration 021, `v0.1.36.14`, 8 tests) · the `qa-bug-hunt-squad` bundle (`v0.1.36.15`, 4 tests) · the launchable `bug-hunt-squad` quick-action (`v0.1.36.16`, validated by the 19 quick-action tests). The quick-action is a **launchable prompt** (the same class of artifact as `autonomous-boss`), not a bespoke daemon engine.

**Not yet (next phases — Plan 3 Phases 2–3, tracked on the roadmap):**
- **Per-worker token accounting** — the load-bearing gap; PTY workers report zero tokens today, so "fewer tokens than a non-Synapse agent" is not yet *proven*.
- **A bug-hunt fixture + topology benchmark** — a fixed buggy app + answer key to rank flat vs supervisor-tree vs solo-baseline by bugs-per-1k-tokens.
- **Auto-spawn supervised children + a concurrency cap + token budgets** (the `delegate` endpoint creates a child but doesn't launch it; nothing bounds concurrency today).
- **SUPERVISED_IDEATION + a proposal inbox** (agents brainstorm improvements for approval).
- **A live browser-driving E2E** — proving a hunter opens a real gate with a real screenshot needs an interactive session with a Playwright MCP installed and real Claude workers spawned. Until that runs, this team is **launchable + individually-tested, not end-to-end-proven**.

## Consequences

- **Positive:** a real, reusable, token-lean bug-finding team; a genuine security/token fix (scoped MCP); evidence-backed findings via the Quality OS; no breaking changes (nullable column + additive bundle + additive quick-action).
- **Limits:** the token-efficiency claim is a *target pursued honestly via benchmark*, not yet measured; the team depends on a Playwright MCP being installed; the full loop is unproven until the live E2E runs.

This ADR was hand-authored for bootstrap (like ADR-0023/0024), since it defines a capability spanning roles, bundles, coordination, and the Quality OS rather than one project's records.
