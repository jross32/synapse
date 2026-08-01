# ADR-0034: Trustworthy automatic runtime delegation

- **Status:** accepted — shipping in v0.1.94
- **Date:** 2026-08-01
- **Deciders:** Justin (owner), Codex
- **Related:** ADR-0023 (AI Council), ADR-0024 (coordination), ADR-0030 (runtime-neutral MCP injection), ADR-0033 (operator journal), Contracts #2, #3, #4, #7, #11, #12, #22, #23, #25

## Context

Synapse could launch Claude, Codex, and GitHub Copilot workers, but the shared endpoint always opened an interactive terminal UI. A worker could therefore look “running” while waiting for a human prompt, and a clean process exit could be mistaken for completed work even when no evidence-backed handoff existed. Stop and timeout paths also raced the asynchronous PTY finalizer, allowing a terminated worker to become falsely completed.

Runtime permission models differ. A single generic “automatic” flag would either remain interactive on one CLI or silently grant too much authority on another. MCP injection also has to remain isolated per worker, and an automatic run must never wait forever at a tool prompt.

## Decision

1. **Keep interactive as the default.** `POST /api/v1/agent-work-items/{id}/launch` accepts `execution_mode: interactive | automatic`; omitted remains `interactive`.
2. **Name the authority boundary.** Automatic runs accept `authority: observe | workspace | full` plus a required bounded timeout (30 seconds to 24 hours, default 30 minutes). The desktop offers interactive or workspace automatic execution and always exposes Pause/Stop controls.
3. **Translate automatic execution per runtime.** Claude uses print mode and policy-aware permission modes, Codex uses `exec`, and Copilot uses prompt mode. Every runtime receives the same daemon-authored absolute role-prompt path and must finish through the explicit work-item handoff endpoint.
4. **Use policy-aware Claude automation.** Observe uses plan mode, workspace uses Claude's non-interactive `auto` permission mode, and full uses the explicit dangerous bypass. `acceptEdits` is not used for automatic runs because MCP calls can still strand it at an interactive prompt.
5. **Reserve Codex rule bypass for full authority.** Workspace mode keeps project execution rules and the workspace sandbox. Only an explicitly full run adds both the sandbox/approval bypass and `--ignore-rules`.
6. **Treat process exit as transport evidence, not completion.** Exit zero without an explicit handoff becomes `handoff` with an inspect-transcript warning. Nonzero exits become blocked. Known stable failure signatures are converted into safe actionable blockers without copying terminal output or secrets.
7. **Block before terminating.** Stop and timeout paths first atomically mark a running work item blocked, then close its PTY. The later finalizer cannot overwrite that operator decision. A handoff preserves its evidence-backed work status but does not bypass the process deadline: a still-live PTY is closed. Stopping a squad leaves it paused.
8. **Sanitize operator-visible worker text.** Handoff and journal fields remove terminal control characters while preserving normal newlines and tabs.
9. **Make the reason visible.** Deep Live View shows a compact `Now` plus `Why this step` summary, while the complete structured receipt remains in the inner scrolling timeline.
10. **Keep MCP processes isolated.** Automatic mode reuses ADR-0030's role-scoped, per-worker MCP translation; it does not start one shared Reflex process or mutate an already-running worker.
11. **Give workers a protected, scoped handoff context.** Synapse pre-registers every worker with its exact project, runtime, role, work item, squad, and PTY. It receives a short-lived session credential—not the desktop local token—through daemon-owned `SYNAPSE_API`, `SYNAPSE_TOKEN`, `SYNAPSE_SESSION_ID`, `SYNAPSE_SESSION_KEY`, project, prompt, and identity variables. Only the credential hash is stored. Caller-supplied environment values cannot override those fields. Deadline tasks are owned and cancelled on finalization, operator stop, or daemon shutdown.
12. **Redact credential echoes at capture time.** PTY output treats non-trivial values from token, secret, password, API-key, private-key, and credential environment fields as protected. A streaming redactor removes them before WebSocket publication, scrollback, or transcript persistence, including values split across read chunks or cut off when the process exits.
13. **Finalize PTYs once and in order.** EOF and operator shutdown share one single-flight finalizer. It observes and drains every pending output publication before emitting `session_exited`, persisting the transcript, and emitting `session_finalized`, so the last redaction marker cannot arrive after consumers close the session.
14. **Keep external sessions present across restart boundaries without allowing impersonation.** Registration returns a one-time `session_key`; later calls pair `X-Synapse-Session` with `X-Synapse-Session-Key`. The key hash binds receipts to that session and a valid declared call refreshes/reactivates its lease. Pre-release rows remain compatible only until they end. Live automatically selects newly registered root sessions while worker connections stay in the parent roll-up.
15. **Roll worker evidence into the parent and expose editable milestones.** The session that creates a squad becomes its durable Live owner; later worker starts, MCP attachments, and reviewer handoffs inherit that parent link. Each session also owns an API-editable Goals list stored with its session metadata and rendered in a collapsed `[completed/total]` side inspector.
16. **Enforce worker API scope as well as runtime flags.** Worker credentials may only identify their own coordination session. Cross-session identity/goal mutation and cross-work-item handoff/status writes are rejected. Observe authority permits reads plus self-reporting; workspace authority also blocks Synapse-wide lifecycle/security changes such as restart, auth, pairing, settings, snapshot/restore, and MCP/marketplace installation. Full authority remains explicit but still cannot impersonate another session.
17. **Make restart failures sticky.** Once any restart stage reports an error, later delayed health/readiness callbacks cannot overwrite the stage or repaint the operation all-green. A new operation is required for a fresh attempt.
18. **Require real interaction proof for Live controls.** The Goals inspector's client uses the shared API client's structured-body contract, announces appended timeline activity, includes squad-worker plans in “Why this step,” labels the goal list, and lets Escape cancel a rename.
19. **Make worker presence daemon-owned.** An automatic worker cannot reliably interrupt a long browser, MCP, or model call to heartbeat itself. While its PTY remains live, Synapse refreshes the pre-registered coordination session every 30 seconds. Finalization, timeout, operator stop, and daemon shutdown cancel that loop before the session is released and its scoped credential is revoked.

## Consequences

- A launched worker either stays visibly interactive, runs automatically within a named boundary, hands off evidence, or reports a truthful blocker.
- A compromised or confused worker no longer possesses the desktop root token and cannot claim another AI's Live identity, goals, or handoff. The human desktop retains the trusted-local authority documented in `docs/security.md`.
- Claude, Codex, and Copilot can be acceptance-tested without typing into their terminals.
- Full authority is powerful and intentionally explicit. A future boss-to-worker escalation flow may approve it automatically only inside authority already delegated to that boss, with scope, reason, timeout, audit receipt, and operator stop controls; v0.1.94 does not silently infer boss authority.
- A worker may still use credentials it was explicitly given, but echoing them does not turn PTY history into a secret store. Exact matching happens before every durable or live output sink.
- Duplicate EOF callbacks or an EOF/shutdown race cannot duplicate lifecycle receipts or reorder final output behind session completion.
- An external AI cannot be observed while it makes no Synapse calls at all, but its first declared call after a restart restores presence automatically; meaningful worker/reviewer receipts remain attached to the parent session that launched the squad.
- Goals are concise operator milestones, not a hidden-reasoning channel. Human and AI edits use the same audited daemon API.
- A shown restart error remains part of the operation's durable truth, even if a late callback observes eventual recovery.
- A healthy automatic worker stays green through long tool calls without receiving broader authority; PTY death still ends presence and revokes its scoped credential promptly.
- Existing launch clients remain compatible because all new request fields are optional and preserve the previous interactive behavior.
