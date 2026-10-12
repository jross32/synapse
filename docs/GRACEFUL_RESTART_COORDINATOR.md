# Graceful Restart Manager: coordinated maintenance protocol (experimental)

The existing Synapse Restart Manager now exposes a durable maintenance coordinator in routes_system.py, backed by maintenance_coordinator.py.

- POST /api/v1/system/restart/maintenance: prepare with nonempty worker roster and capabilities checkpoint, drain, non_pausable; defaults to 120s grace, configurable 5-900.
- GET /api/v1/system/restart/maintenance: durable status, worker ACKs and checkpoint references.
- POST /api/v1/system/restart/maintenance/{id}/ack: record paused with durable checkpoint reference, drained, or unsafe.
- POST /api/v1/system/restart/maintenance/{id}/cancel: cancel.
- POST /api/v1/system/restart/maintenance/{id}/commit: reuse existing audited restart operation only if roster ACKs are safe.

State is atomically persisted under data/maintenance/restart.json. Expired windows postpone, never kill workers.

## Not production ready
This implements an initial safety state-machine and REST integration, NOT uninterrupted worker execution. Roster is caller-supplied and ACK uses normal daemon authorization, not verified worker identities. The existing legacy /system/restart and Electron restart buttons do NOT yet route through the new safety coordinator. No live restart or install has been performed.

Before enabling it for user-facing automatic restart:
1. Discover all active workers from the real registries, freeze dispatch, notify, and authenticate per-worker ACKs. Include external AI sessions, browser workers, PTY jobs, scheduler and MCP requests.
2. Persist actual checkpoints and validate resumability per runtime; nonpausable workers defer the restart.
3. Complete independent Windows restart supervisor, rollback and health checks without changing the user's MCP URL.
4. Route all restart entry points through the barrier, integrate worker-status indicators in the existing Electron Restart Manager, and recover after daemon crashes.
5. Verify real cross-version upgrades and two-computer E2E, including old active jobs, reconnect, 120s deadline and failure rollback.
6. Resolve observed dev frontend 0.2.218 and Python backend 0.1.209 skew and dual port-7878 listeners.

The guarded commit consumes ready state exactly once and rejects repeated commits. A user-supplied roster is NOT proof of complete worker discovery; the route remains experimental until server-side worker identification and authenticated worker ACKs are implemented.
