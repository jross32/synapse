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

_To be populated as Milestone B and beyond ship endpoints. The contracts in `AGENTS.md` define the shape; this file records the concrete additions._

| Date | Endpoint or event | Kind | Notes |
|---|---|---|---|
| _pending_ | `GET /api/v1/health` | additive | Returns `HealthResponse` from `models.py` |
| _pending_ | `GET /api/v1/projects` | additive | List managed projects |
| _pending_ | `POST /api/v1/projects` | additive | Create project |
| _pending_ | `PATCH /api/v1/projects/{id}` | additive | Edit project (Contract #1) |
| _pending_ | `DELETE /api/v1/projects/{id}` | additive | Soft-delete project |
| _pending_ | `POST /api/v1/projects/{id}/launch` | additive | Spawn process |
| _pending_ | `POST /api/v1/projects/{id}/stop` | additive | Terminate process |
| _pending_ | `GET /api/v1/projects/{id}/logs` | additive | Latest log file content |
| _pending_ | `WS /api/v1/ws` | additive | Live event stream; supports `{type: "resume", since: N}` (Contract #5) |
| _pending_ | `v1.project.launched` | additive | Broadcast when a process is spawned |
| _pending_ | `v1.project.errored` | additive | Broadcast when a project transitions to error |
| _pending_ | `v1.process.heartbeat` | additive | Periodic CPU/RAM snapshot per process |
