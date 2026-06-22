# ADR-0010 — Agent Squad hierarchy + autonomous boss

- **Status:** Partially accepted. Hierarchy + roster + kill switch **shipped**
  in v0.1.36-dev (2026-06-22). The autonomous boss is **Proposed** and gated on
  user "go".
- **Date:** 2026-06-22
- **Supersedes / builds on:** the first-pass Agent Squads (migration
  `008_agent_squads.sql`).

## Context

Agent Squads launched as a flat model: 4 roles, one lead per squad, a
two-level work-item tree, and four raw forms shown at once. Justin asked for
(1) a guided, non-overwhelming way to assemble a team, (2) many more roles in a
real **boss -> supervisor -> worker** hierarchy, (3) two bosses able to
collaborate on one project, and eventually (4) an **autonomous AI boss** that
plans a team, picks workers, creates projects, leverages/installs tools, and
learns over time — with a kill switch as the safety backstop (full autonomy +
"Stop all").

## Decision

### Shipped this round (the substrate)

- **`role_tier`** (`boss` / `supervisor` / `worker`) on `agent_role_templates`
  via migration `011_squad_hierarchy.sql`. Delegation intent: boss ->
  supervisors + workers; supervisor -> workers; worker executes. The
  work-item `parent_id` tree already supports N levels; tiers give the UI a
  way to group + reason about the chain.
- **Expanded roster** (4 -> 11 seeded roles): boss, planner, supervisor,
  implementer, reviewer, researcher, tester, designer, docs-writer, devops,
  security. Roles remain fully data-driven (CRUD), so users add their own.
- **Team Builder wizard** (`renderer/components/SquadWizard.tsx`): goal &
  project -> preset team -> roster -> review. Presets (*Ship a feature*,
  *Research & plan*, *Bug hunt*, *Full build*, *Solo lead*, *Custom*) make the
  common cases one click; the raw forms stay behind an Advanced disclosure.
- **Kill switch** (`POST /api/v1/agent-squads/{id}/stop`): closes a squad's
  live PTY sessions and finalizes its work items. This is the non-negotiable
  safety primitive the autonomous boss depends on.
- **Two-boss collaboration (lightweight):** multiple boss-tier work items are
  allowed, and two squads on one project already share that project's
  `.synapse-ai-context.md`, so two bosses coordinate through shared memory. A
  richer co-lead UX is deferred.

### Proposed next round (the autonomous boss)

Default autonomy level (per the owner): **full autonomy + kill switch.** The
boss runs without per-step approval; the user can "Stop all" at any moment.

Loop sketch (all built on existing REST, no new contracts required):

1. **Sense** — read `GET /api/v1/ai/context` (projects, tools, quick-actions,
   sessions, squads, audit tail).
2. **Plan** — draft a roster (role_tier-aware) + a work-item DAG for the goal.
3. **Provision** — create a project if needed (`POST /api/v1/projects`),
   install useful tools (`POST /api/v1/marketplace/install/{id}`), or author a
   quick-action template.
4. **Execute** — spawn workers (existing launch endpoint), prefer existing
   tools/workflows over writing from scratch.
5. **Learn** — append decisions to `.synapse-ai-context.md` and record usage in
   `catalog_preferences` so later runs reuse what worked.

Guardrails: the kill switch (shipped); the daemon's existing audit log
(Contract #11) records every autonomous action with `source`; refuse
Administrator (Contract #16); no outbound calls except user-triggered
(Contract #15).

## Consequences

- The hierarchy + wizard make squads approachable now without committing to the
  autonomous loop. Migrations are additive (`011`), so existing installs gain
  tiers without a reset.
- The autonomous boss reuses today's REST surface, so it can be built behind a
  feature flag without new daemon contracts. It stays Proposed until the owner
  greenlights it; the kill switch + audit log are the agreed preconditions.
- Related deferred ADR: **Synapse as a claude.ai connector** (a remote MCP
  server wrapping the REST API, exposed via Cloudtap) — the same REST surface
  the boss uses could be fronted as MCP for external Claude/Codex clients.
