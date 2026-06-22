# ADR-0011: Per-project decision records, backlog, and version history

- Status: Accepted
- Date: 2026-06-22
- Deciders: Justin (owner), Claude

## Context

Synapse itself keeps ADRs (`docs/adr/`), a `CHANGELOG.md`, and a backlog in
`PROGRESS.md`. But the **projects a user manages inside Synapse** had no
equivalent: no place to record why a decision was made, what's on the
backlog, or how the project's versions evolved. The owner wants every
managed project/app to carry its own:

- **ADRs** — architecture/decision records, scoped to that project.
- **Quick ADRs / ideas** — a lightweight inbox you can drop a thought into
  ("we should probably switch to X") that is *not yet* a formal decision, and
  later **promote** into an officially numbered ADR.
- **Backlog** — durable planning items (distinct from Agent-Squad work items,
  which are execution-time and ephemeral).
- **Version history** — a per-project changelog: versions + what changed.

This must be editable from the UI (Contract #1), live in the daemon's SQLite
(single source of truth, Contract #8), and be **AI-callable** so an
agent/worker can append an idea or record a decision while it works
(Contract: AI-facing surfaces).

## Decision

Three new daemon-owned tables (migration `012_project_records.sql`), each
scoped by `project_id`, with REST CRUD and a renderer surface in the project
detail modal.

### `project_adrs`
`id, project_id, number (nullable), title, status, body_md, tags_json,
supersedes_id (nullable), source, created_at, updated_at, decided_at`.

**Lifecycle (the "quick idea -> official ADR" flow):**
```
idea  ->  draft  ->  proposed  ->  accepted
                                     └─ superseded (by a later ADR)
                  └─ rejected
```
- A **quick ADR / idea** is just a row created with `status='idea'` and no
  `number`. Frictionless capture (title only is enough).
- **Promote** (`POST .../promote`) moves an idea/draft/proposed row to
  `accepted`, assigns the **next per-project ADR number**, and stamps
  `decided_at`. That is "officially written in".
- `supersedes_id` lets a new accepted ADR mark an older one `superseded`
  (history is preserved, never deleted).

### `project_backlog`
`id, project_id, title, body_md, status (todo|in_progress|done|wontfix),
priority (low|medium|high), order_index, source, created_at, updated_at,
completed_at`. Durable planning list; reorderable.

### `project_versions`
`id, project_id, version, released_at (nullable), changes_md, source,
created_at, updated_at`. A per-project changelog the user or an AI maintains
explicitly (not auto-derived from git — managed projects are not always git
repos, and Contract #1 wants it editable).

### REST surface (all under `/api/v1`, token-guarded)
- `GET /projects/{id}/records` — one bundle (adrs + backlog + versions) for
  the detail view.
- ADRs: `GET|POST /projects/{id}/adrs`, `GET|PATCH|DELETE /project-adrs/{adr_id}`,
  `POST /project-adrs/{adr_id}/promote`.
- Backlog: `GET|POST /projects/{id}/backlog`, `PATCH|DELETE /project-backlog/{item_id}`.
- Versions: `GET|POST /projects/{id}/versions`, `PATCH|DELETE /project-versions/{version_id}`.

Every mutation writes an `audit_log` row. Models are added to
`model_registry()` so `gen-types` exports them to the renderer.

### AI-callable
The endpoints are listed in `GET /api/v1/ai/context` -> `endpoints_for_ai`
so a Claude/Codex/Copilot worker inside a Sessions tab can: read the
project's records, drop a quick idea, record an ADR, add a backlog item, or
append a version entry as it works.

### UI
A tabbed section in `ProjectDetailModal.tsx`: **Decisions** (ADR list with
status chips + a one-field "quick idea" capture + a "Promote to ADR"
action + full editor), **Backlog** (list with status/priority + quick add),
and **History** (version list + quick add).

## Consequences

- Per-project knowledge now lives with the project, survives restarts, and
  is portable via snapshot/restore (Contract #28) once those models are
  added to the snapshot payload (follow-up).
- Agent-Squad work items stay separate (execution-time); backlog is the
  durable plane. A future enhancement can "send a backlog item to a squad".
- Numbers are **per-project** (each project has its own ADR-0001, 0002, ...),
  not global.

## Alternatives considered

- *Reuse the unbuilt ADR-0006 "objectives" tree* — objectives were never
  implemented and conflate planning with execution. Backlog here is simpler
  and decisions/versions are genuinely new shapes.
- *Markdown files in the project folder* — rejected: not all managed projects
  have a writable repo, harder to query, and breaks the "edit from the UI /
  DB is source of truth" contracts.
