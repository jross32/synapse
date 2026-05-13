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

### Pending (later milestones)

| Endpoint or event | Milestone | Notes |
|---|---|---|
| `GET /api/v1/projects` | D | List managed projects |
| `POST /api/v1/projects` | D | Create project |
| `PATCH /api/v1/projects/{id}` | D | Edit project (Contract #1) |
| `DELETE /api/v1/projects/{id}` | D | Soft-delete project |
| `POST /api/v1/projects/{id}/launch` | D | Spawn process |
| `POST /api/v1/projects/{id}/stop` | D | Terminate process |
| `GET /api/v1/projects/{id}/logs` | D | Latest log file content |
| `v1.project.launched` / `v1.project.stopped` / `v1.project.errored` | D | Project lifecycle events |
| `v1.process.heartbeat` | E | Periodic CPU/RAM snapshot per process |
| `GET /api/v1/search?q=...` | F | Universal search (Contract #21) |
| `POST /api/v1/snapshot` / `POST /api/v1/restore` | later | Disaster recovery (Contract #28) |
