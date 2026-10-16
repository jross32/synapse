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

### Shipped in v0.1.205 (reserved MCP control lane)

| Date | Endpoint or event | Kind | Notes |
|---|---|---|---|
| 2026-09-04 | `POST /api/v1/review/engine/plan/{project_id}` | additive | Token-free Smart Review planner: bounded diff evidence, deterministic/privacy gates, risk classification, token budget, and targeted reviewer plan. |
| 2026-09-04 | `POST /api/v1/review/engine/queue/{project_id}` | additive | Queues planner-selected existing coder review passes; no second AI execution path. |
| 2026-09-04 | `v1.review.engine_planned` | additive | Safe project/risk/mode/AI-required/queued summary event; no diff content. |
| 2026-08-28 | `POST /mcp/{token}` dispatch | corrective | The 16-thread MCP budget is partitioned into 4 reserved control/read workers and 12 blocking-work workers so long shell/network/downstream-MCP calls cannot consume all recovery/context capacity. |
| 2026-08-28 | MCP response headers | additive | Adds `X-Synapse-MCP-Lane: control|blocking|mixed`. Saturation responses identify which lane is saturated while retaining retryable HTTP 503, JSON-RPC `-32002`, and `Retry-After: 1`. |

Migration: none. JSON-RPC bodies are unchanged. Clients may use the lane header to distinguish control-path latency from blocking-work saturation and should continue treating HTTP 503 as retryable.

### Shipped in v0.1.204 (dedicated bounded MCP dispatch)

| Date | Endpoint or event | Kind | Notes |
|---|---|---|---|
| 2026-08-27 | `POST /mcp/{token}` dispatch | corrective | MCP JSON-RPC work runs on a dedicated 16-worker executor rather than asyncio's process-wide default executor. When all workers are occupied, new calls receive retryable HTTP 503 / JSON-RPC `-32002` immediately instead of joining an invisible queue. |
| 2026-08-27 | MCP response headers | additive | Successful MCP responses expose `X-Synapse-MCP-Queue-Ms`, `X-Synapse-MCP-Execution-Ms`, and `Server-Timing` so queue-vs-execution delay is externally observable. Saturation returns `Retry-After: 1` and `X-Synapse-MCP-Executor: saturated`. |

Migration: none. Existing JSON-RPC request/response bodies are unchanged; clients should treat HTTP 503 as retryable and may use the timing headers for diagnostics.

### Shipped in v0.1.203 (durable ChatGPT workers + thread presence)

| Date | Endpoint or event | Kind | Notes |
|---|---|---|---|
| 2026-08-27 | `PUT /api/v1/projects/{id}/records/canonical-chat-url` | additive | Replaces or clears the one current canonical AI chat/thread pointer for a project; project-record reads now include the pointer + updated timestamp. |
| 2026-08-27 | `GET /api/v1/chatgpt-workers` + `/{id}` | additive | Lists/reads durable ChatGPT UI worker conversations independently of short-lived coordination sessions. |
| 2026-08-27 | `GET /api/v1/chatgpt-workers/readiness` | additive | Reports dedicated profile/project setup readiness without reading the operator's normal browser profile. |
| 2026-08-27 | `POST /api/v1/chatgpt-workers/setup-browser` | additive | Opens the one-time account-owner browser on Synapse's dedicated profile; repeated calls return `already_running` while that profile is already open. |
| 2026-08-27 | `POST /api/v1/chatgpt-workers/{id}/archive|unarchive` | additive | Retires/restores durable worker conversations without deleting their work-item history. |
| 2026-08-27 | `GET /api/v1/thread-presence/overview|groups|threads/{id}/turns` | additive | Reads durable request groups, threads, browser observations, status, and auditable worked-time totals. |
| 2026-08-27 | `POST /api/v1/thread-presence/bootstrap|browser-observe|threads/{id}/begin|heartbeat|finish|state` | additive | Stable thread identity + browser attachment + explicit per-turn accounting protocol. Reusing an external thread key updates the same durable record. |
| 2026-08-27 | `v1.thread_presence.browser_observed|thread_bootstrapped|turn_started|thread_updated|turn_finished` | additive | Streams browser/thread/turn state into the operator surfaces. |
| 2026-08-27 | `GET /api/v1/activity/sessions` / detail representations | additive | Activity/Live View data can include project names and linked durable ChatGPT worker summaries for the selected session. |
| 2026-08-27 | ChatGPT-owned `POST /api/v1/agent-work-items/{id}/launch` | corrective/extended | ChatGPT parent ownership selects the real `chatgpt_web` child path; same-work-item launches reuse the current eligible worker conversation instead of duplicating it. |
| 2026-08-27 | automatic project collaboration | corrective/extended | Same-project root AIs share one auto-managed room; children join that room and peers retain separate catch-up packets. |
| 2026-08-27 | local MCP tools | additive | Adds `synapse_thread_bootstrap`, `synapse_thread_begin_turn`, `synapse_thread_heartbeat`, `synapse_thread_finish_turn`, and `synapse_set_project_chat_url`. |
| 2026-08-27 | `synapse_call_mcp_tool` input | additive compatibility | Accepts normal free-form nested `arguments` plus scalar `arguments_json` for connector hosts that cannot validate arbitrary nested keys. |

Migrations 037-040 add project canonical-chat metadata, durable ChatGPT worker/work-item links, work groups,
AI threads/turns, and browser observations. All changes are additive to `/api/v1`; existing clients can ignore the new
fields/routes. Identity is intentionally split: coordination sessions are live leases, worker chats are reusable
conversations, and thread-presence rows are durable request/conversation timing records. Migration 040 additionally enforces one non-empty ChatGPT conversation URL per durable worker row.

### Shipped in v0.1.201 (durable improvement-proposal lifecycle)

| Date | Endpoint or event | Kind | Notes |
|---|---|---|---|
| 2026-08-27 | `GET /api/v1/review/proposals/schema` | additive | Discoverable proposal contract: lifecycle, decision values, kinds, filters, sort fields, linking convention, and operation URLs. |
| 2026-08-27 | `GET /api/v1/review/proposals` | breaking semantics within v1 compatibility surface | Query now uses lifecycle `status=proposed|in_progress|done`, optional `decision=pending|accepted|declined`, `kind`, `project_id`, `sort_by`, and `sort_dir`. |
| 2026-08-27 | `PATCH /api/v1/review/proposals/{id}/lifecycle` | additive | Explicitly Start, Done, or Reopen a proposal; transition evidence is retained. |
| 2026-08-27 | `POST /api/v1/review/proposals/{id}/approve|reject` | corrective semantics | Compatibility URLs now update the independent human decision only; acceptance no longer claims implementation is complete. |
| 2026-08-27 | `POST /api/v1/review/proposals/reconcile` | corrective/extended | Reconciles lifecycle from strong evidence: exact proposal id in active work/session -> in progress; explicit completion claim plus id in commit text -> done; evidence is persisted. |
| 2026-08-27 | proposal representation | additive/breaking semantics | Adds first-class `kind`, `decision`, `lifecycle_source`, `lifecycle_evidence`, `decision_at`, `started_at`, and `done_at`; `status` now means implementation lifecycle. |

Migration: migration `035_proposal_lifecycle.sql` converts legacy `open|approved|rejected` records
to lifecycle `proposed` plus the equivalent decision (`pending|accepted|declined`) and deliberately
does **not** infer that an approved proposal was implemented. Clients that used `status=open` should
move to `status=proposed`/`in_progress`; clients should read `/review/proposals/schema` instead of
hard-coding the vocabulary. Existing approve/reject URLs remain callable.

### Shipped in v0.1.95 (parallel squad launch reliability)

| Date | Endpoint or event | Kind | Notes |
|---|---|---|---|
| 2026-08-01 | `POST /api/v1/agent-work-items/{id}/launch` | corrective | Concurrent launch requests are serialized around PTY startup without holding the daemon's shared SQLite transaction across the await. Successful response shape is unchanged; failed spawn returns the existing ErrorEnvelope, closes pre-registered worker presence, and leaves the item queued for retry. |
| 2026-08-01 | automatic worker failure classification | corrective | A recognized Codex CLI usage-limit exit becomes a concise account-limit blocker directing the operator to Codex Settings → Usage; raw terminal text, URLs, and reset details are not persisted in the reason. |

Migration: existing v1 clients need no changes. Clients may continue launching multiple work items in
parallel; each request now receives a deterministic launch or ErrorEnvelope result instead of sharing a
database transaction with another startup.

### Shipped in v0.1.94 (trustworthy automatic runtime delegation)

| Date | Endpoint or event | Kind | Notes |
|---|---|---|---|
| 2026-08-01 | `POST /api/v1/agent-work-items/{id}/launch` (extended) | additive | Body accepts optional `execution_mode` (`interactive` default or `automatic`), `authority` (`observe`, `workspace`, `full`), and `timeout_seconds` (30–86,400; default 1,800). Response and `v1.agent_run.started` include the resolved values. Automatic launches use runtime-native non-interactive commands and require an explicit handoff. Daemon-owned `SYNAPSE_API`, token, project, prompt, and worker identity env values cannot be overridden by caller env. |
| 2026-08-01 | `POST /api/v1/agent-squads/{id}/stop` (extended) | additive | Response adds the resulting paused squad `status`. Running work items are blocked before their PTYs close so asynchronous finalization cannot report false completion. |
| 2026-08-01 | worker finalization semantics | corrective | Exit zero without an explicit handoff now becomes `handoff` with transcript-inspection guidance, not `completed`; nonzero exit becomes `blocked`, with safe classified guidance for known authentication/runtime failures. |
| 2026-08-01 | `GET/POST /api/v1/activity/sessions/{id}/goals`; `PATCH/DELETE .../goals/{goal_id}` | additive | Adds an audited, ordered session milestone list with `pending`, `active`, `completed`, and `blocked` states. `GET /activity/sessions/{id}` now includes `goals[]`. |
| 2026-08-01 | `v1.activity.goals_updated` | additive | Streams `{session_id, goals}` after a goal is created, renamed, completed, blocked, reordered, or removed. |
| 2026-08-01 | `X-Synapse-Session` request header (extended) | corrective | A declared authenticated Synapse action refreshes/reactivates its coordination session after daemon/app restart while preserving the safe receipt behavior. Squad worker/MCP/handoff journal receipts inherit the squad owner's session id for parent roll-up. |
| 2026-08-01 | `PATCH /api/v1/coordination/sessions/{id}` | additive | Audited correction for a worker that registered before reading its injected project/runtime/PTY identity. Recalculates the connection grade and emits `v1.coordination.session_heartbeat`; no direct database edit is required. |
| 2026-08-01 | `GET /api/v1/agent-squads/{id}/work-items` | additive | Returns `{work_items:[...]}` for focused, AI-discoverable sibling inspection. The richer squad-detail endpoint remains available. |
| 2026-08-01 | `POST /api/v1/coordination/sessions` (extended) | additive | Response adds a one-time `session_key`. New attributed calls pair `X-Synapse-Session` with `X-Synapse-Session-Key`; only the hash is stored. Existing fields remain unchanged. |
| 2026-08-01 | worker authentication + `POST /api/v1/agent-work-items/{id}/launch` (extended) | corrective | Workers are pre-registered and receive a short-lived identity/authority-bound token rather than the desktop local token. Launch response adds `coordination_session_id`; env adds `SYNAPSE_SESSION_ID`/`SYNAPSE_SESSION_KEY`. Cross-session/work-item writes and out-of-authority global mutations return `403 auth.worker_scope_denied`. |
| 2026-08-01 | restart-stage aggregation | corrective | The first error is terminal for an operation; later delayed success rows remain audited but cannot replace the error or produce `status: complete`. |
| 2026-08-01 | `v1.coordination.session_heartbeat` for automatic workers | corrective | Synapse refreshes the pre-registered worker session every 30 seconds while its PTY is alive. Long tool calls no longer cause false stale/gone state or mid-task credential revocation; finalization, timeout, stop, and shutdown cancel the owned loop. |

Migration: existing v1 clients need no changes because omitted launch fields preserve interactive behavior. Clients
requesting automatic execution should always show the resolved authority and timeout and retain an operator stop path.

### Shipped in v0.1.93 (deep AI operator journal)

| Date | Endpoint or event | Kind | Notes |
|---|---|---|---|
| 2026-08-01 | `POST /api/v1/activity/sessions/{session_id}/events` | additive | Persists a bounded plan/reasoning-summary/decision/search/action/evidence/blocker/squad/MCP/tool/result receipt with real identity links and authority. Rejects unknown sessions and mismatched squad/work-item/MCP references. |
| 2026-08-01 | `GET /api/v1/activity/sessions/{session_id}` | additive | Adds `journal[]`, enriched squad `worker_profiles[]`, and daemon-authored `connection_help`; journal rows include related project-squad lifecycle events. |
| 2026-08-01 | `v1.activity.journaled` | additive | Streams one structured journal event. Payload `{event}`. |
| 2026-08-01 | `v1.coordination.session_heartbeat` | additive | Payload now carries the complete session view, including task and `last_intent`, rather than only id/status. Existing fields remain. |
| 2026-08-01 | `v1.agent_run.started` | additive | Adds the exact role-scoped `mcp_server_ids` attached to the worker. |
| 2026-08-01 | `v1.agent_mcp.attached` | additive | Emits the worker/squad/runtime and enabled MCP ids after launch; the activity projector persists a receipt. |
| 2026-08-01 | `X-Synapse-Session` request header | additive | Opts an authenticated AI call into automatic Synapse method/result/authority receipts. Bodies, auth headers, responses, and secret values are never copied. |
| 2026-08-01 | `GET /api/v1/search?q={query}&limit={n}` | additive | Mounts the advertised universal search route over live projects, Synapse tools, MCP servers, actions, and settings. Returns scored typed hits and timing; newly enabled MCPs appear without a stale secondary index. |

Migration: existing v1 clients need no changes. Clients that want automatic receipts add the returned
coordination session id as `X-Synapse-Session`; Deep View reporting is otherwise opt-in through the new POST.

### Shipped in v0.1.92 (portable benchmarked skill packs)

| Date | Endpoint or event | Kind | Notes |
|---|---|---|---|
| 2026-07-31 | `GET /api/v1/ai-bundles/skills` | additive | Lists bundled portable skill packages and installed immutable versions. |
| 2026-07-31 | `GET /api/v1/ai-bundles/skills/{skill_id}` | additive | Returns an installed skill manifest, resource inventory, and `SKILL.md` instructions. |
| 2026-07-31 | `GET /api/v1/ai-bundles/skills/{skill_id}/resources/{resource_path}` | additive | Reads one path-confined UTF-8 skill resource without importing or executing package code. |
| 2026-07-31 | Synapse local MCP | additive | Adds `synapse_list_skill_packs` and `synapse_get_skill_pack`, and advertises the skill surface through `/api/v1/ai/context`. |

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
| 2026-08-01 | `GET /api/v1/agent-squads/{id}/work-items` | additive | Returns only the squad's ordered work-item collection for lightweight worker/sibling inspection. |
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

### Shipped in v0.1.36-dev (Installed Pages + Web Scraper)

| Date | Endpoint or event | Kind | Notes |
|---|---|---|---|
| 2026-06-28 | `GET /api/v1/installed-pages` | additive | Returns the curated dedicated-page registry currently available to the user. v1 ships only the `web-scraper` page, surfaced when an installed HTTP MCP server is recognized as the owner's scraper. |
| 2026-06-28 | `GET /api/v1/installed-pages/web-scraper` | additive | Returns `WebScraperOverview`: install/runtime status, source id, UI/docs URLs, and scraper capability counts when connected. |
| 2026-06-28 | `GET /api/v1/installed-pages/web-scraper/saves` | additive | Daemon-side proxy to the installed scraper's saves feed. The renderer never talks to the MCP origin directly. |
| 2026-06-28 | `GET /api/v1/installed-pages/web-scraper/schedules` | additive | Daemon-side proxy to the installed scraper's schedules feed. |
| 2026-06-28 | `GET /api/v1/installed-pages/web-scraper/active` | additive | Daemon-side proxy to the installed scraper's active-job feed. |
| 2026-06-28 | `POST /api/v1/installed-pages/web-scraper/scrape-url` | additive | Daemon-side proxy to the installed scraper's quick-scrape action. Body is passed through as JSON. |
| 2026-07-05 | `GET /api/v1/installed-pages/web-scraper/harvest-capabilities` | additive | Returns the curated design-harvest action catalog plus supported provenance/adaptation modes for the dedicated harvest workspace. |
| 2026-07-05 | `POST /api/v1/installed-pages/web-scraper/actions/{action}` | additive | Curated design-harvest proxy for `capture`, `research_url`, `to_markdown`, `extract_styles`, `extract_structure`, `generate_react`, `generate_css`, and `infer_schema`. Rejects unsupported actions with `422 web_scraper.unsupported_action`. |
| 2026-07-05 | `POST /api/v1/installed-pages/web-scraper/save-artifacts` | additive | Saves harvest outputs into normal project files, writes a `design-harvest-manifest.json`, and optionally links saved artifacts to a benchmark attempt. |
| 2026-06-28 | `v1.mcp_server.updated` | additive | Broadcast on install/update/start/stop/uninstall so desktop surfaces such as Installed Pages and MCP management can refresh without polling. |

### Shipped in v0.1.36-dev (Self-improvement + review-loop foundation)

| Date | Endpoint or event | Kind | Notes |
|---|---|---|---|
| 2026-07-05 | `GET /api/v1/ai/health-report` | additive | Returns a compact self-improver diagnostic report: version, uptime, schema migration, contracts, project counts, audit tail, cached test summary, and git summary. Intended for Synapse-native AI workbenches. |
| 2026-07-05 | `POST /api/v1/synapse-dev/test/full` | additive | First guarded ADR-0007 developer-loop endpoint. Requires `SYNAPSE_DEV_ENABLED=1`; runs the full daemon/frontend typecheck + test loop and returns structured pytest/TypeScript results plus a cached summary for `ai/health-report`. |
| 2026-07-05 | `POST /api/v1/synapse-dev/test/file` | additive | Guarded targeted-test endpoint. Requires `SYNAPSE_DEV_ENABLED=1` and only accepts paths under `daemon/tests/`; rejects out-of-repo or non-test paths with a structured error. |
| 2026-07-05 | `GET /api/v1/quick-actions` (extended) | additive | Quick-action payloads now optionally expose `project_id`, `launch_mode`, `thread_title`, and `prompt_filename`, enabling project-targeted launches and coder-thread quick actions such as `improve-synapse`. |
| 2026-07-05 | `POST /api/v1/quick-actions/{id}/launch` (extended) | additive | Launch now supports `launch_mode="coder-thread"`, may lazy-create the bundled `synapse-self` project, and returns `thread_id` + `coder_run_id` when a quick action launches as a real coder thread rather than a plain PTY. |
| 2026-07-05 | `POST /api/v1/coder-threads/{id}/review-passes` / `POST /api/v1/coder-review-passes/{id}/launch` (metadata extended) | additive | Review-pass metadata may now carry `review_kind`, `preset_label`, `reason`, `focus_points`, and `escalation_policy`, which the coder workspace surfaces as explicit "why this pass ran" context for UX/QA/token-efficiency/judge loops. |

### Shipped in v0.1.73 (AI operator trust + attention, first slice)

| Date | Endpoint or event | Kind | Notes |
|---|---|---|---|
| 2026-07-29 | `GET /api/v1/ai/health-report` (extended) | additive | Adds `quality.latest_browser_proof` / `quality.failing_contracts` to the compact trust payload and a new `review.latest_successful_pass` summary (`id`, `thread_id`, `thread_title`, `project_id`, `title`, `summary_md`, `updated_at`). This lets lightweight operator surfaces answer "what was last actually proven?" without pulling the full `ai/context` digest. |

### Shipped in v0.1.90 (optional Warden marketplace integration)

| Date | Endpoint or event | Kind | Notes |
|---|---|---|---|
| 2026-07-31 | `GET /api/v1/mcp-servers/warden/status` | additive | Returns the installed/cached/verified state, immutable catalog pin, active release, registry coverage, and rollback availability. |
| 2026-07-31 | `POST /api/v1/mcp-servers/warden/sync` | additive | Mirrors enabled stdio MCP servers into Warden without disabling direct MCP access. Warden, HTTP servers, disabled servers, and conflicting-secret servers are excluded and reported. |
| 2026-07-31 | `POST /api/v1/mcp-servers/warden/update` | additive | Downloads the catalog-pinned commit into a versioned isolated environment, verifies it, then activates it. Existing verified releases are retained. |
| 2026-07-31 | `POST /api/v1/mcp-servers/warden/rollback` | additive | Atomically points the installed Warden MCP record at the newest previous verified release and resynchronizes its registry. |
| 2026-07-31 | `v1.mcp_server.updated` (extended reasons) | additive | May now carry `installing`, `warden_registry_synced`, `warden_updated`, or `warden_rolled_back` reasons. Existing clients may ignore unknown reasons. |

### Shipped in v0.1.91 (runtime-neutral MCP injection + observable restart)

| Date | Endpoint or event | Kind | Notes |
|---|---|---|---|
| 2026-07-31 | `POST /api/v1/agent-work-items/{id}/launch` (extended) | additive | Enabled, role-scoped MCP servers are now translated for every built-in CLI runtime: Claude `--mcp-config`, Codex one-launch `mcp_servers.*` overrides, and GitHub Copilot CLI `--additional-mcp-config`. Codex/Copilot secret values remain only in the worker environment. |
| 2026-07-31 | `GET /api/v1/system/restart` | additive | Returns the latest audited whole-Synapse restart operation, ordered stages, overall status, and stable error catalog. |
| 2026-07-31 | `GET /api/v1/system/restart/errors` | additive | Returns plain-language meanings for `SYN-RST-*` and `SYN-BOOT-*` diagnostics. |
| 2026-07-31 | `POST /api/v1/system/restart` | additive | Requests an audited visible restart (`202`). A second live operation returns the normal conflict envelope with diagnostic `SYN-RST-001`. |
| 2026-07-31 | `POST /api/v1/system/restart/{operation_id}/stage` | additive | Electron records measured `request`, `stop`, `desktop`, `daemon`, and `interface` stage state. |
| 2026-07-31 | `v1.system.restart_requested` | additive | Payload `{operation_id, source}`; the desktop process observes this and runs the same restart path as the tray. |
| 2026-07-31 | `v1.system.restart_progress` | additive | Payload `{operation}` after each audited stage report. |

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

### Shipped in v0.1.36-dev (Coder Workspace + benchmark foundation)

| Date | Endpoint or event | Kind | Notes |
|---|---|---|---|
| 2026-06-28 | `GET|POST /api/v1/projects/{id}/coder-threads` | additive | Durable thread-first workspace surface for the new chat-style coder experience. Threads are project-scoped, carry active runtime provenance, and survive UI changes. |
| 2026-06-28 | `GET|PATCH|DELETE /api/v1/coder-threads/{id}` | additive | Returns one thread plus its messages, runtime switches, review passes, and linked runs; updates title/runtime/archive state; deletes the thread and its children. |
| 2026-06-28 | `GET|POST /api/v1/coder-threads/{id}/messages` / `POST /api/v1/coder-threads/{id}/runtime` / `POST /api/v1/coder-threads/{id}/review-passes` / `GET /api/v1/coder-threads/{id}/context` | additive | Adds durable message history, explicit runtime-switch events, structured review-pass records, and a project-aware context bundle (files, records, linked runs, workspace preferences). |
| 2026-06-28 | `GET /api/v1/ai/context` (extended) | additive | Now also includes top-level `coder_threads` and `benchmark_runs`, plus the new coder-thread and benchmark endpoint discovery entries. |
| 2026-06-28 | `v1.pty.session_input` | additive | PTY write-side lifecycle event. Used to determine whether a linked coder run was ever interacted with, not just launched. |
| 2026-06-28 | `GET|POST /api/v1/benchmarks/specs` / `GET|POST /api/v1/benchmarks/runs` / `GET /api/v1/benchmarks/runs/{id}` | additive | Benchmark spec catalog plus durable runs and materialized attempts for `direct_cli`, `synapse_coder_thread`, `synapse_workbench`, and `synapse_raw_pty`. A default mixed mini-suite is seeded automatically. |
| 2026-06-28 | `POST /api/v1/benchmarks/runs/{id}/launch` / `POST /api/v1/benchmarks/ingest-direct` / `POST /api/v1/benchmarks/runs/{id}/rescore` / `POST /api/v1/benchmarks/runs/{id}/export` | additive | Launches the next benchmark attempt through the selected Synapse surface, ingests direct/no-Synapse runs, recomputes derived metrics, and exports `BENCHMARK.json`, `BENCHMARK.md`, and `BENCHMARK_LESSONS.json`. |
| 2026-06-28 | `POST /api/v1/projects/{id}/open-ai-os` (extended) | additive | Body now also accepts `benchmark_run_id`, so AI OS can open directly on a benchmark leaderboard/report without depending on an AI case id. |
| 2026-08-17 | `GET /api/v1/ai/runtimes`, `GET /api/v1/ai/executions/{execution_id}`, `POST /api/v1/ai/runtimes/{runtime_id}/recheck`, `POST /api/v1/ai/runtimes/{runtime_id}/capacity` | additive | Canonical SQLite-backed runtime capacity, execution identity, outcome, and nullable provenance-tagged usage. Agent Squad launches return `execution_id`; PTY finalization is idempotent and persists quota evidence. Recheck returns stale quota state to unknown; local capacity attestation records user-known exhausted/disabled/unknown evidence without spending a provider call. |
