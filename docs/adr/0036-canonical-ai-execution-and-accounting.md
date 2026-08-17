# ADR-0036 — Canonical AI execution, readiness, and accounting

**Status:** Accepted (foundation shipping incrementally)  
**Date:** 2026-08-17

## Context

Synapse had two incompatible truths. Blueprint/scaffold calls optionally appended parsed
usage to `data/runtime-ledger.jsonl`; Agent Squad and PTY launches used a separate
self-reported token table and did not update runtime exhaustion. A provider could return a
monthly quota error while Synapse continued to advertise it as ready, and an observed Codex
usage footer could coexist with an empty work-item ledger. The in-memory one-hour cooldown
in ADR-0035 also disappeared on restart and cannot represent a monthly reset window.

Process exit, worker handoff, accepted work, and measured usage are separate facts. None may
stand in for another.

## Decision

1. SQLite is the canonical source of truth for AI executions, usage observations, and
   provider capacity. JSONL remains compatibility history/export only.
2. Every launch receives one durable `execution_id` before it can be considered running.
   Source identity and PTY identity are unique, making retries and duplicate EOF events
   idempotent.
3. Runtime capacity is evidence-backed state, not a Boolean:
   `unknown | available | degraded | cooldown | quota_exhausted | auth_required |
   not_installed | offline | disabled`.
4. Missing token, cost, credit, or request measurements remain SQL `NULL` and API `null`.
   Zero is used only when a provider actually reports zero.
5. Usage observations name their provenance and source. Comparisons are valid only across
   compatible measurements; Synapse must include failed attempts and orchestration overhead.
6. PTY finalization updates the execution, usage observation, and provider capacity exactly
   once. Exit zero without a handoff remains a handoff-needing-review work outcome.
7. Explicitly requested unavailable runtimes fail locally with evidence. Policy-ordered
   launches may select the next installed, usable provider. Provider/privacy/cost boundary
   changes require an explicit policy or human approval.
8. REST is the complete control plane. `/ai/context` advertises runtime readiness/accounting
   endpoints. MCP tools call the same scoped application services; they do not create a
   parallel privileged implementation.
9. Public/WAN drive will use expiring, revocable, project-scoped capability credentials with
   authority, spend, duration, concurrency, and action scopes. The desktop root token is not
   the public automation credential.

## Incremental migration

The first green unit wires Agent Squad automatic PTY launches/finalization and read-only REST.
Subsequent complete units migrate Coder Workspace, Blueprints, AI Cases, quick actions, local
agents, and scheduled routines through the same service; add reservations/probes; then add
scoped MCP writes and public REST. Existing paths remain labeled partial until migrated.

## Consent and authority

Authority is project-, task-, and time-scoped and defaults to the least privilege. Standing
grants are visible, revocable, and receipt-producing. Spend limits fail closed. A fallback
may not silently cross a provider, privacy, or authority boundary not present in the launch
policy. Full authority is never inherited by a schedule or public client.

## Acceptance

- Copilot monthly exhaustion survives daemon restart and prevents another launch.
- Codex PTY usage is attributed exactly once even when finalization repeats.
- Unknown usage renders as unknown, never zero.
- Timeout/stop/blocked states remain sticky after late exit or handoff.
- REST exposes execution identity, capacity evidence, provenance, and measured usage.
- Every migrated path passes launch → output → durable result → reload/restart tests.

