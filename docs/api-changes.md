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
