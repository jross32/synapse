# ADR-0024: Native multi-AI coordination — shared presence, advisory file lanes, and a real pre-commit gate

- **Status:** accepted
- **Date:** 2026-07-05
- **Deciders:** Justin (owner), Claude
- **Related contracts:** #2 (status enum), #4 (error envelope), #5 (WS events), #8/#9 (generated types / migrations), #11 (audit log), #24 (timestamps). Relates to ADR-0006 (per-project `.synapse-ai-context.md`), ADR-0011 (project records), ADR-0022 (unified cockpit + shared Plan), ADR-0023 (AI Council Review); makes `docs/MULTI-AI-WORKFLOW.md` machine-checkable.

## Context

Justin runs more than one AI coder against the Synapse repo **at the same time** (e.g. Claude Code committing while Codex edits the coder workspace). Today that coordination is entirely **manual and document-based**: `docs/MULTI-AI-WORKFLOW.md` tells each agent to run the 3 gates before committing, "pick a lane," not race the same file, and leave a handoff note in the per-project `.synapse-ai-context.md`. It works only because a human — or a diligent agent — reads the markdown and *hand-notices* overlaps.

That failure mode happened during this very session: Codex had a large uncommitted wave touching `routes_coder_workspace.py` + `CoderWorkspace.tsx`, and Claude's planned Phase A touched the **same two files**. Claude had to manually read the channel, manually spot the overlap, and manually hold — and the hand-written channel even carried a **stale migration number** (it said `019` was free after Codex had already taken it). Justin asked for this to be unified **through Synapse**: the app itself should hold one live picture of *who is working what, on which files*, share it, and surface collisions — so agents stop hand-parsing markdown.

## Decision

Ship **native multi-AI coordination** as a daemon-owned substrate plus an enforceable pre-commit gate, reusing existing Synapse patterns rather than inventing parallel ones. Six decisions:

1. **Two-layer substrate.** The **DB is authoritative** for machine-coordinatable facts: `agent_sessions` (presence: runtime, task, status, heartbeat) and `file_lanes` (advisory claims of path globs). The existing `.synapse-ai-context.md` remains a **human/CLI-readable projection** so a cold-started CLI that never calls the API still inherits state from the file it is already told to read. One channel, no second file, no fourth plan table.

2. **Advise, don't enforce, for external processes.** Claude Code CLI and Codex CLI are **external OS processes the daemon never spawned** — it cannot intercept their file writes. Therefore lanes are **advisory soft-locks**: an overlapping claim returns `200` with a `conflicts[]` array (never `423`). The **one enforceable choke point** is the pre-commit overlap check in `scripts/coordination-preflight.ps1`, which agents opt into exactly as they already opt into the 3 gates. A **git-working-tree collision detector** (`detect_collisions`) is the after-the-fact backstop for raw edits. Synapse's **own** in-app coder dispatch is the only place it can hard-gate. Shipping this as "lane enforcement" would sell false safety; the value is *live visibility + one real gate at commit*.

3. **Presence + file lanes are the primitives; the shared Plan layers on next.** This ADR delivers presence and lanes. The shared per-project Plan (ADR-0022 Part E, `.synapse/plan.md`) promotes onto the same substrate in a follow-up, reusing the `project_records` shape — not a new plan schema.

4. **Disk-truth numbering.** `next_migration_number` / `next_adr_number` scan the filesystem (including untracked files) — never a cached doc — so the "which number is free" answer is always correct. The preflight prints it. This directly fixes the stale-`019` bug above.

5. **Reuse over reinvention.** Presence status reuses the enum discipline of `agent_squads`; file I/O for the projection reuses `ai_context_memory`'s atomic write; errors/audit/WS/time reuse `errors.py` / `audit.py` / `ws.py` / `time_utils`; path resolution reuses `runtime_paths.repo_root()`. **File lanes are the only genuinely new primitive.**

6. **Strict phasing under an active concurrent lane.** The MVP shipped as **new files only** while a second agent (Codex) held a large uncommitted wave; wiring into shared files (`app.py`) waited until that wave was committed — the feature **dogfooded the very protocol it automates**.

## Enforce vs advise — the honest boundary

| Edit path | Can Synapse block it? |
|---|---|
| External CLI (Claude Code, Codex) editing disk directly | **No** — advise + surface only |
| An agent **committing** (opts into preflight) | **Yes** — preflight exits non-zero on cross-owner overlap |
| Synapse's own in-app `coder_run` dispatch | **Yes** — it owns that process (follow-up) |
| Raw edits already on disk | Detected after the fact by the git-status scanner |

## Consequences

### Positive
- The "Claude had to manually notice and hold" problem becomes an API call + a gate: claim a lane → conflicts returned immediately; stage over another agent's lane → preflight fails.
- One live, per-project picture of presence + lanes, ready to render in the cockpit and broadcast over the existing WS bus (phone included).
- Numbering advice is always correct (disk truth), killing a real class of collision.

### Negative / limits
- Lanes are advisory for external processes — a determined agent can ignore them. Mitigated by loud presence + the commit gate, not by false locks.
- Presence relies on heartbeats; a crashed CLI leaves a phantom row until the 90s TTL sweep marks it `gone` and releases its lanes.
- Cross-scope semantics are deliberately simple: `project_id = NULL` is the repo-level scope two CLIs on the Synapse repo share; project-scoped lanes don't conflict with repo-level ones.

### Follow-ups (roadmap)
- Mount is done; next: a **CoordinationBoard** cockpit panel (presence strip + lane map + collision banner) fed by `v1.coordination.*` events; the git-status detector on a slow timer; promote `.synapse/plan.md` to first-class (ADR-0022 Part E); auto-create/release a lane when an in-app `coder_run` starts/ends.

## Status of this slice (be honest)

**Shipped (MVP):** migration `020_coordination.sql` (`agent_sessions`, `file_lanes`), `coordination.py` (presence, lanes, overlap, git collision detector, disk-truth numbering), `routes_coordination.py` (mounted at `/api/v1/coordination`), `test_coordination.py` (16 tests green), `scripts/coordination-preflight.ps1`. **Not yet:** the cockpit panel, WS-driven live UI, the shared-Plan promotion, and in-app auto-lanes — tracked on `docs/roadmap.json`.

This ADR was hand-authored for bootstrap (like ADR-0023), since it defines coordination discipline that spans every AI coder, not one project's records.
