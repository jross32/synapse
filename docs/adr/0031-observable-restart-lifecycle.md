# ADR-0031: Observable, resumable Synapse restart lifecycle

- **Status:** accepted — targeted for v0.1.91
- **Date:** 2026-07-31
- **Deciders:** Justin (owner), Codex
- **Related:** ADR-0027 (AI-drivable Synapse), ADR-0028 (AI activity), Contracts #2, #4, #7, #11, #13, #22

## Context

The tray's **Restart Synapse** action previously exited and relaunched with no visible progress. A clean restart
can span two different owners: packaged Electron stops and relaunches its daemon directly, while development
Electron exits with code 75 so `scripts/dev.ps1` can replace the daemon, Vite, and Electron together. The old UI
could disappear for several seconds, could not resume progress in the new process, and exposed failures only in
console output or a tray tooltip.

## Decision

1. **Show startup state, not a blank gap.** Every desktop start opens a small Synapse progress window before the
   main renderer. Restart adds explicit stages for request accepted, old services stopped, desktop relaunched,
   daemon health, and interface readiness.
2. **Carry restart state across processes.** Electron writes a short-lived `restart-progress.json` marker in the
   runtime data directory. The replacement process resumes it; records older than ten minutes fail visibly as
   `SYN-BOOT-301` instead of causing a restart loop. The marker is removed after all checks pass.
3. **Use measured checks.** Green checks appear only after the corresponding fact is known: process handoff,
   `/api/v1/health`, and Electron `ready-to-show`. Pending and active stages remain visibly distinct.
4. **Give failures stable diagnostic codes.** Restart and boot failures use the `SYN-RST-*` and `SYN-BOOT-*`
   catalog. The window shows the code, plain-language meaning, technical detail, and a Copy diagnostics action.
5. **Make restart AI-drivable.** `POST /api/v1/system/restart` creates an audited operation. Electron polls the
   daemon for requested operations, executes the same path as the tray, and reports stages through
   `POST /api/v1/system/restart/{id}/stage`. `GET /api/v1/system/restart` returns the latest state and error catalog.
6. **Broadcast and audit lifecycle state.** The daemon emits `v1.system.restart_requested` and
   `v1.system.restart_progress`; every request and stage is appended to the audit log.
7. **Prevent duplicate/stale loops.** One live operation is allowed at a time. Duplicate requests return a
   structured conflict containing `SYN-RST-001`; incomplete operations age out after ten minutes.

## Consequences

- Tray, renderer, and AI-triggered restarts share one observable path.
- Users can distinguish a slow healthy restart from a failed stage and can copy enough context to diagnose it.
- Development and packaged builds keep different process owners without presenting different UX.
- The transient marker is a cross-process handoff, while the daemon audit log remains the durable operation
  history and API source of truth.
