# ADR-0020: AI Factory + Advanced AI Case Engine

- **Status:** accepted
- **Date:** 2026-06-27
- **Deciders:** Justin Ross, Codex
- **Related contracts:** #1, #2, #5, #8, #9, #11

## Context

Synapse already had strong low-level AI primitives: workbench PTYs, project
files/transcripts, Agent Squads, quick-actions, project decision records, and a
marketplace path for tools and workers. What it lacked was a first-class product
shape for higher-order AI work:

- reusable app recipes, packs, profiles, and source intake
- structured multi-step AI cases instead of ad-hoc chats
- isolated implementation space for case-owned execution
- a dedicated run board that can show contradictions, evidence, verdicts, and
  handoff artifacts without forcing all of that into the main Synapse shell

At the same time, we do not want to split truth across multiple runtimes. The
daemon must remain the single source of truth for projects, cases, jobs,
workers, transcripts, files, and exports.

## Decision

We split the product into two tightly linked surfaces:

1. **AI Factory** lives inside Synapse as the authoring and operating surface
   for reusable AI intelligence:
   - recipes
   - nav/layout/interaction/visual/data/testing/profile policy assets
   - source intake and promotion
   - case setup and mission selection

2. **AI Operating System (AI OS)** stays a separate local web app opened from
   Synapse. It focuses on live execution, evidence, contradiction handling,
   verdicts, implementation progress, and handoff/export views.

The daemon owns both through an advanced case engine with these rules:

- `case_mode` describes engine behavior (`research`, `generate`, `hybrid`,
  `audit`, `repair`, `migrate`, `replicate`, `benchmark`, `harvest`,
  `portfolio`, `challenge`)
- `mission_profile_id` packages a reusable workflow preset without exploding
  the API into a giant enum
- case creation is grouped into `intent`, `targets`, `directives`, and
  `policies`
- cases can form a graph through parent/root/comparison relationships
- execution slices keep a **single automatic write target**; broader work is
  modeled through child cases
- runnable cases get an isolated branch/worktree rather than mutating the
  user's active checkout
- case-owned jobs are explicit persisted records, even when their visible
  execution surface is still a PTY-backed worker

The AI Factory catalog is stored in daemon-owned SQLite tables and seeded with
starter assets so the system can work on day 1 without manual library authoring.

## Consequences

### Positive
- Synapse keeps one runtime and one audit trail while gaining a much more
  productized AI workflow.
- Reusable intelligence becomes tangible data instead of scattered prompts.
- AI work can be launched from projects directly (`Open in AI OS`) without
  burying the user in raw terminal/session concepts.
- The system gains a durable backbone for future bakeoffs, harvest flows, and
  child-case orchestration.

### Negative / trade-offs
- The v1.2 foundation adds substantial schema and API surface area quickly.
- Some advanced mode-specific behaviors still share the same core execution
  loop and will need deeper specialization in later passes.
- A separate AI OS app introduces one more packaged surface to keep aligned
  with the daemon contract.

### Follow-ups
- Deepen per-mode behavior for `benchmark`, `harvest`, `portfolio`, and
  `challenge`.
- Promote browser/scraper intake into first-class case evidence and asset
  promotion flows.
- Evolve case-owned jobs from PTY-backed orchestration toward a richer
  headless job runner where that improves determinism.
