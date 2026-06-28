# API Changes — Synapse

This file is the source of truth for changes to the daemon's REST and WebSocket surface (Contract #7).

The daemon API is **versioned by prefix**: REST endpoints live under `/api/v1/...` and WebSocket event names are namespaced as `v1.entity.verb`. Any breaking change requires a new prefix (e.g. `v2`) and parallel availability of v1 for at least one minor release after deprecation.

## Versioning rules

- **Additive change** (new endpoint, new optional field, new event): no version bump.
- **Breaking change** (removed/renamed endpoint, removed/renamed field, changed type, changed semantics): new prefix.
- **Deprecation:** mark the old endpoint with `Deprecation:` header + `Sunset:` date. Keep alive for one minor release minimum.
- **Event names** follow `noun.verb` (`project.launched`, `tool.errored`). Past tense for completed actions, present-continuous for in-flight (`project.launching`).

Every entry below must include: the date, the new version added, what changed, and a migration note for clients still on the older version.

## v1 — initial surface

### Shipped in v0.1.3 (Milestone B)

| Date | Endpoint or event | Kind | Notes |
|---|---|---|---|
| 2026-05-13 | `GET /api/v1/health` | additive | Returns `HealthResponse` — `{ok, version, started_at, contracts: [1..28]}`. Unversioned `GET /health` 404s by design. |
| 2026-05-13 | `WS /api/v1/ws` | additive | Bidirectional event stream. Client sends `{type:"resume", since: <int>}` on connect; daemon replies with `{type:"replay", events:[...], last_event_id, buffer_min_id}` then streams live events. Client sends `{type:"ping"}` → daemon replies `{type:"pong"}`. If `since` falls outside the 1 000-event ring buffer, daemon emits `{type:"error", name:"v1.ws.replay_window_exceeded", payload:{since, buffer_min_id}}` per Contract #5. |
| 2026-05-13 | `v1.daemon.started` | additive | Broadcast once at boot. Payload: `{version, schema_migration, started_at, contracts}`. |
| 2026-05-13 | `v1.process.reconciled` | additive | Emitted once per non-trivial orphan reconciliation outcome. Payload: `{process_id, entity_type, entity_id, pid, outcome}` where outcome ∈ `pid-recycled | daemon-restart`. Re-attached rows are silent. |
| 2026-05-13 | `v1.daemon.reconciliation_complete` | additive | Summary event after reconciliation, only emitted if any rows were inspected. Payload: `ReconciliationReport`. |

### Shipped in v0.1.5 (Milestone D)

| Date | Endpoint or event | Kind | Notes |
|---|---|---|---|
| 2026-05-13 | `GET /api/v1/projects` | additive | `{projects: Project[]}` — live registry, excludes soft-deleted rows. Secrets in `env` are redacted to `"(set)"` (Contract #25). |
| 2026-05-13 | `GET /api/v1/projects/{id}` | additive | Single `Project`; 404 with `{code:"project.not_found"}` on miss. |
| 2026-05-13 | `POST /api/v1/projects` | additive | Body: full `Project`. 201 on success; 409 `{code:"project.conflict"}` on duplicate id. Validates kebab-case id (Contract #10). |
| 2026-05-13 | `PATCH /api/v1/projects/{id}` | additive | Body: `ProjectUpdate` (any subset of editable fields). 200 with updated record; 422 `{code:"project.invalid"}` if body is empty. |
| 2026-05-13 | `DELETE /api/v1/projects/{id}` | additive | Soft-delete. 204 on success; 409 `{code:"project.conflict"}` if project is currently running. |
| 2026-05-13 | `POST /api/v1/projects/{id}/launch` | additive | Body: `{source: "desktop"|"mobile"|"tray"|"cli"|"auto"}` (defaults `"desktop"`). Spawns the project's `launch_cmd` detached (Windows: `CREATE_NEW_PROCESS_GROUP \| DETACHED_PROCESS`), captures stdout/stderr to `data/logs/<id>/<ts>.log`, emits `v1.project.launching` then `v1.project.launched`. |
| 2026-05-13 | `POST /api/v1/projects/{id}/stop` | additive | Sends `terminate()`, falls back to `kill()` after 5 s grace; updates `managed_processes.stopped_at` + `stop_reason='user'`; emits `v1.project.stopping` then `v1.project.stopped`. |
| 2026-05-13 | `v1.project.launching` | additive | Payload: `{id, source}`. |
| 2026-05-13 | `v1.project.launched` | additive | Payload: `{id, pid, log_path}`. |
| 2026-05-13 | `v1.project.stopping` | additive | Payload: `{id, source}`. |
| 2026-05-13 | `v1.project.stopped` | additive | Payload: `{id, reason}`. |
| 2026-05-13 | `v1.project.errored` | additive | Payload: `{id, error: ErrorRef}`. |

### Shipped in v0.1.7 (Milestone E)

| Date | Endpoint or event | Kind | Notes |
|---|---|---|---|
| 2026-05-15 | `GET /api/v1/projects/{id}/logs?lines=N` | additive | Returns `{project_id, log_path, lines[], total_lines}` — the tail of the project's most recent per-spawn log file (Contract #3). `lines` capped 1–2000. |
| 2026-05-15 | `v1.process.heartbeat` | additive | Broadcast every ~2s while any project runs. Payload: `{processes: ResourceSnapshot[], over_budget: [{id, breached[]}]}`. Each snapshot sums CPU% + RSS MB across the project's whole process tree. |
| 2026-05-15 | `v1.project.errored` (crash path) | additive | Now also emitted when the watcher detects an unexpected non-zero exit. Payload gains `exit_code` + `error`. |
| 2026-05-15 | `v1.project.stopped` (clean-exit path) | additive | Emitted when a process exits 0 on its own (not via Stop). Payload `reason: "exited"`. |
| 2026-05-15 | `v1.project.restart_scheduled` | additive | Contract #18 — emitted when an auto-restart is queued. Payload `{id, attempt, delay_seconds, max_retries}`. |
| 2026-05-15 | `v1.project.restart_exhausted` | additive | Emitted when a crashing project hits `max_retries`. Payload `{id, attempts, max_retries}`. |

### Pending (later milestones)

| Endpoint or event | Milestone | Notes |
|---|---|---|
| `GET /api/v1/search?q=...` | F | Universal search (Contract #21) |
| `POST /api/v1/snapshot` / `POST /api/v1/restore` | later | Disaster recovery (Contract #28) |

### Shipped in v0.1.36-dev (Sessions-centric AI squads)

| Date | Endpoint or event | Kind | Notes |
|---|---|---|---|
| 2026-06-20 | `GET /api/v1/agent-role-templates` | additive | Lists the daemon-owned role templates used by Agent Squads (`planner`, `implementer`, `reviewer`, `researcher` by default). |
| 2026-06-20 | `POST /api/v1/agent-role-templates` | additive | Creates a role template with `preferred_runtimes`, `default_visibility`, `context_mode`, delegation rules, and prompt preamble markdown. |
| 2026-06-20 | `PATCH /api/v1/agent-role-templates/{id}` / `DELETE /api/v1/agent-role-templates/{id}` | additive | Updates or removes a role template. Existing squads keep stored role ids; clients should handle missing templates defensively. |
| 2026-06-20 | `GET /api/v1/agent-squads` | additive | Returns the durable squad list ordered by `last_activity_at DESC`. |
| 2026-06-20 | `POST /api/v1/agent-squads` | additive | Creates a new squad for a real project. Body: `{project_id, name, goal_md?, status?, lead_role_id?}`. |
| 2026-06-20 | `GET /api/v1/agent-squads/{id}` | additive | Returns `AgentSquadDetail` (`squad`, `role_templates`, `work_items`) for the Sessions cockpit. |
| 2026-06-20 | `PATCH /api/v1/agent-squads/{id}` / `DELETE /api/v1/agent-squads/{id}` | additive | Updates squad metadata/status or deletes the squad tree. |
| 2026-06-20 | `POST /api/v1/agent-squads/{id}/work-items` | additive | Creates a queued work item. Body: `{title, instructions_md?, assigned_role_id?, preferred_runtime?, parent_id?}`. |
| 2026-06-20 | `POST /api/v1/agent-work-items/{id}/launch` | additive | Launches a work item as a normal PTY session in the project cwd. Response includes PTY summary fields plus `squad_id`, `work_item_id`, `role_id`, `runtime`, `role_prompt_file`, `project_id`, and `project_name`. Injects `SYNAPSE_SQUAD_ID`, `SYNAPSE_WORK_ITEM_ID`, `SYNAPSE_ROLE_ID`, `SYNAPSE_LEAD_SESSION_ID`, `SYNAPSE_ROLE_PROMPT_FILE`, `SYNAPSE_AI_CONTEXT`, and `SYNAPSE_AI_CONTEXT_DIRECTION_PROMPT` into the PTY env. |
| 2026-06-20 | `POST /api/v1/agent-work-items/{id}/delegate` | additive | Creates a child work item linked by `parent_id`, preserving the existing Sessions model of “helpers are real PTYs, not hidden jobs.” |
| 2026-06-20 | `POST /api/v1/agent-work-items/{id}/handoff` | additive | Explicit handoff capture. Body: `{status, summary_md, blockers_md?, files_touched[], suggested_next_role?}`. Also appends a structured entry to `data/projects/<project_id>/.synapse-ai-context.md`. |
| 2026-06-20 | `POST /api/v1/agent-work-items/{id}/status` | additive | Lightweight status transition helper for the cockpit. Body: `{status}`. |
| 2026-06-20 | `v1.agent_squad.created` / `v1.agent_squad.updated` | additive | Broadcast when squads are created or updated so the Sessions cockpit refreshes without polling. |
| 2026-06-20 | `v1.agent_work_item.created` / `v1.agent_work_item.updated` / `v1.agent_work_item.handoff` | additive | Broadcast when work items are created, updated, or handed off. |
| 2026-06-20 | `v1.agent_run.started` / `v1.agent_run.ended` | additive | Broadcast when a squad work item enters/exits a PTY session. `v1.agent_run.ended` fires after transcript persistence so clients can safely rely on `transcript_file_id` when present. |
| 2026-06-20 | `GET /api/v1/ai/context` (extended) | additive | Gains per-project `ai_context` metadata plus top-level `agent_squads` and `agent_role_templates` so an AI session can inspect squad/work-item state before taking action. |

### Shipped in v0.1.36-dev (Profile hub + synced catalog state)

| Date | Endpoint or event | Kind | Notes |
|---|---|---|---|
| 2026-06-21 | `GET /api/v1/profile` | additive | Returns the local-first `ProfileSummary`: Synapse Accounts sign-in state, sync backend, linked identities, portable preferences summary, and the current host record. |
| 2026-06-21 | `PATCH /api/v1/profile` | additive | Updates daemon-owned profile config such as `sync_enabled`. Supabase-specific config fields were removed; the daemon now talks to the built-in Synapse Accounts service directly. |
| 2026-06-21 | `GET /api/v1/profile/preferences` / `PATCH /api/v1/profile/preferences` | additive | Reads and updates portable setup preferences such as theme, sidebar layout, Discover recents, and Sessions quick-action collapse state. |
| 2026-06-21 | `POST /api/v1/profile/signup` / `POST /api/v1/profile/signin` / `POST /api/v1/profile/signout` | additive | Native Synapse account lifecycle. Signup uses username + email + password, signin accepts username or email, and both routes persist rotating Synapse Accounts sessions locally through the daemon. |
| 2026-06-21 | `POST /api/v1/profile/auth/start/{provider}` / `GET /api/v1/profile/auth/callback` | additive | OAuth handoff for external identities such as Google. The daemon now delegates to the first-party Synapse Accounts service and completes the browser flow through a short-lived handoff token. |
| 2026-06-21 | `DELETE /api/v1/profile/providers/{provider}` | additive | Unlinks a linked external identity such as Google from the current Synapse account. |
| 2026-06-21 | `GET /api/v1/profile/catalog-state` | additive | Returns `CatalogPreferenceState`: synced favorites/history/install-memory for Discover and Installed views, keyed by `tool:<id>` and `quick-action:<id>`. |
| 2026-06-21 | `POST /api/v1/profile/favorites/{kind}/{id}` | additive | Sets or toggles the favorite flag for a tool or quick action. `kind` is `tool` or `quick-action`. |
| 2026-06-21 | `GET /api/v1/profile/service-connections` | additive | Returns `ServiceConnection[]` for portable official connections (GitHub/Google account identities) plus local-detected runtimes such as Claude Code, Codex, ChatGPT/OpenAI session cache, and Copilot CLI. |
| 2026-06-21 | `POST /api/v1/profile/service-connections/{provider}/connect` / `POST /api/v1/profile/service-connections/{provider}/verify` / `DELETE /api/v1/profile/service-connections/{id}` | additive | Creates or refreshes a saved service-connection status record, or clears the stored status. Local-detected providers are re-scanned on each verify. |
| 2026-06-21 | `GET /api/v1/profile/hosts` | additive | Returns the host inventory Synapse tracks for this profile, including the current machine and the last-seen timestamps used by the Profile hub. |
| 2026-06-21 | `v1.profile.updated` | additive | Broadcast when profile/account or catalog state changes so the shell can refresh account badges and Profile hub data without a hard reload. |
| 2026-06-21 | `v1.profile.sync.updated` | additive | Broadcast when the daemon's account sync status changes. Payload includes `signed_in`, `sync_status`, `last_sync_at`, and `last_sync_error`. |
| 2026-06-21 | `v1.service_connection.updated` | additive | Broadcast when a connected-service record changes so Sessions and the Profile hub can refresh their readiness cards. |

### Shipped in v0.1.36-dev (Synapse Accounts service)

| Date | Endpoint or event | Kind | Notes |
|---|---|---|---|
| 2026-06-21 | `POST /v1/auth/signup` / `POST /v1/auth/signin` / `POST /v1/auth/refresh` / `POST /v1/auth/signout` | additive | First-party Synapse Accounts auth service endpoints. Production is intended to run against Postgres; local dev can use SQLite. Access tokens are short-lived and refresh tokens rotate. |
| 2026-06-21 | `GET /v1/me` | additive | Returns the signed-in Synapse account summary, including linked identities and provider metadata. |
| 2026-06-21 | `GET /v1/public/config` | additive | Returns auth-provider availability so the daemon and renderer can show native-only or Google-enabled flows without manual user config. |
| 2026-06-21 | `GET /v1/sync/document` / `PUT /v1/sync/document` | additive | Fetches and updates the cloud-backed portable sync document for preferences, favorites/history/install memory, and host inventory. Files/logs/transcripts/uploads remain out of scope. |
| 2026-06-21 | `POST /v1/oauth/start` / `POST /v1/oauth/exchange` / `GET /v1/oauth/google/callback` | additive | Starts external OAuth, exchanges the completion handoff for a Synapse session, and completes the Google callback on the hosted service. |
| 2026-06-21 | `DELETE /v1/providers/{provider}` | additive | Unlinks an external identity from the current Synapse account. |

### Shipped in v0.1.36-dev (Agent Squads hierarchy + kill switch, Profile reachability)

| Date | Endpoint or event | Kind | Notes |
|---|---|---|---|
| 2026-06-22 | `POST /api/v1/agent-squads/{id}/stop` | additive | Kill switch: closes every live PTY session owned by the squad's work items and finalizes those work items. Returns `{squad_id, stopped_sessions, work_item_ids}`. |
| 2026-06-22 | `AgentRoleTemplate.role_tier` | additive | New field on role templates: `boss` / `supervisor` / `worker`. Drives the Team Builder hierarchy. Existing installs gain it via migration `011_squad_hierarchy.sql` (default `worker`; the original seeds are re-tiered). |
| 2026-06-22 | `ProfileSummary.account_backend_reachable` | additive | New boolean on the profile summary. `false` when no Synapse Accounts service is reachable, so the UI hides native sign-in and shows a "sync is optional / not configured" state instead of forms that always error. |

### Shipped in v0.1.36-dev (AI Factory + advanced case engine foundation)

| Date | Endpoint or event | Kind | Notes |
|---|---|---|---|
| 2026-06-27 | `GET /api/v1/ai-cases/meta` | additive | Returns AI Factory-facing metadata: supported `case_modes`, `generation_modes`, seeded `mission_profiles`, `write_policies`, starter recipes, component families, and available AI bundle install state. |
| 2026-06-27 | `POST /api/v1/ai-cases` | additive | Creates a durable AI case from a structured contract: `intent`, `targets`, `directives`, and `policies`. Legacy flat fields (`primary_project_id`, `neighbor_project_ids`, `goal_md`, `case_mode`) are still accepted and normalized into the new shape. |
| 2026-06-27 | `GET /api/v1/ai-cases` / `GET /api/v1/ai-cases/{id}` / `GET /api/v1/ai-cases/{id}/graph` | additive | Lists cases, returns one case detail, or returns parent/root/comparison lineage. Case detail now includes typed targets, case-owned jobs, active workers, bundle summary, branch/worktree metadata, and the structured intent/directives/policies payload. |
| 2026-06-27 | `POST /api/v1/ai-cases/{id}/spawn` | additive | Creates a child case from a parent case, preserving root/lineage metadata for future bakeoffs, portfolio sweeps, and alternate-path runs. |
| 2026-06-27 | `POST /api/v1/ai-cases/{id}/run` / `POST /api/v1/ai-cases/{id}/stop` | additive | Starts or stops the case loop. `run` allocates an isolated git worktree/branch for the primary repo, builds a case-owned squad/work-item tree, records a persisted `ai_case_job`, and launches the lead worker inside the worktree. `stop` hard-stops owned PTY workers, finalizes their job rows, and leaves the case in a clean non-running state. |
| 2026-06-27 | `POST /api/v1/ai-cases/{id}/run` (extended) | additive | Mode-specific preparation now happens before the lead run launches. `benchmark` spawns candidate child cases, `portfolio` spawns ordered repo-slice children, `challenge` spawns a minority-path child, `harvest` promotes reference URLs into attached sources, and `repair` / `migrate` / `audit` seed their own ledgers or scorecard scaffolding. |
| 2026-06-27 | `GET /api/v1/ai-cases/{id}/bundle` | additive | Returns the structured case bundle, now including similarity, scorecard, ledger, leaderboard, promotion, and failure-matrix scaffolding alongside the original verdict/handoff artifacts. |
| 2026-06-27 | `POST /api/v1/ai-cases/{id}/export/{adr|backlog|memory|preset|recipe|scorecard|benchmark}` | additive | Converts a case into Synapse-native artifacts or export files, including AI memory notes, quick-action presets, recipe exports, scorecards, and benchmark summaries. |
| 2026-06-27 | `GET /api/v1/ai-factory/catalog` | additive | Returns the seeded AI Factory catalog (`components`, `recipes`, `sources`) plus aggregate counts for the native Synapse AI Factory page. |
| 2026-06-27 | `GET /api/v1/ai-factory/catalog` (extended) | additive | Response now also includes Marketplace-grade AI bundle metadata plus `counts.installed_bundles` so the AI Factory can surface bundle install state natively. |
| 2026-06-27 | `GET|POST|PATCH|DELETE /api/v1/ai-components` / `/ai-recipes` / `/ai-sources` | additive | CRUD surface for AI Factory assets. `POST /api/v1/ai-sources/{id}/promote` promotes harvested source material into reusable catalog entries. |
| 2026-06-27 | `GET /api/v1/ai-bundles` / `POST|DELETE /api/v1/ai-bundles/install/{id}` | additive | Lists AI bundle catalog entries and installs/uninstalls AI-first packs of roles, personalities, quick actions, recipes, and sources. Installed bundle ownership is persisted so uninstall can cleanly remove only bundle-owned assets. |
| 2026-06-27 | `POST /api/v1/projects/{id}/open-ai-os` | additive | Ensures the separate local AI Operating System app is registered as a managed Synapse project, launches it if needed, and returns a deep link URL pre-filled with the chosen primary project plus an optional `case_id`. |
| 2026-06-27 | `v1.ai_case.created` / `v1.ai_case.updated` | additive | Broadcast when AI cases are created or when case/job status changes. The AI Factory page uses these events to keep run state in sync without polling. |
| 2026-06-27 | `POST /api/v1/agent-work-items/{id}/launch` (extended) | additive | Body now also accepts `cwd_override` and `env` so case-owned workers can execute inside an isolated worktree while keeping their original project/squad ownership and transcript linkage. |
| 2026-06-27 | `GET /api/v1/ai/context` (extended) | additive | Gains top-level `ai_cases`, `ai_factory` counts, installed AI bundles, and the AI Factory / AI-case / AI-bundle endpoint list so autonomous workers can discover and operate the new substrate directly from Synapse. |
| 2026-06-27 | `GET /api/v1/quick-actions` (extended) | additive | Quick-action listing and launch now merge installed bundle-owned templates from the daemon data directory with the bundled template catalog. |
