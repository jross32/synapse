# ADR-0028: AI Activity (connections, notifications, Live View), the one-window UI standard, and docs-sync enforcement

- **Status:** accepted — Phases 0-6 shipped (v0.1.78-v0.1.88)
- **Date:** 2026-07-29
- **Deciders:** Justin (owner), Claude
- **Related:** ADR-0024 (coordination sessions — the "connection" signal), ADR-0025 (review inbox — where AIs file bugs/ideas), ADR-0026 (WAN auto-start), ADR-0027 (AI-drivable Synapse), Contract #5 (durable WS replay), Contract #11 (audit log), the token ledger (per-work-item tokens).

> **For any AI (Claude / Codex / Copilot) working on Synapse:** this ADR + `docs/roadmap.json` + `PROGRESS.md` are the durable, in-repo home of the current plan. Read them first — the plan lives here, not only in one AI's local notes, so every AI codes to the same plan (per `AGENTS.md`). The full task-level breakdown Claude authored is mirrored here at decision level.

## Context

Justin can run Synapse and have an AI drive it over the API, but he has **no visibility** into when an AI connects, what it's doing, or whether it fully loaded. He wants: connection detection with a **green/yellow/red** status + error codes; a growing **session number** (#001, #025 …) per AI run; an app-wide **Notification Center** (persistent bell → dismissible list → rich, truthful detail popups with token usage, team hierarchy, and working jump-to links); a dedicated **Live View** tab to watch each AI work live (its output/thoughts, real loading states, and a **preview** of the app being built). Almost all the *data* already exists (every AI action emits a replayable WS event; coordination `agent_sessions`; audit log; review inbox; token ledger) — the work is surfacing it + the net-new connection/session/status layer and UI.

He also set two **standing directives** that this ADR codifies repo-wide:
- **One-window UI standard.** New surfaces are a fixed-height shell whose *inner panels* scroll independently (open/close panels like Plan / Files / Preview), never the whole page, with styled professional scrollbars — not the OS default. Model on Claude / Claude-Code's split layout. Apps and AI Coding are the messy, over-scrolling offenders to converge first.
- **Docs + GitHub stay 100% in sync on every commit.** No release lags its docs.

## Decision

1. **Build the AI Activity feature in phases** (Claude's PLAN 5): (0) WAN Settings toggle [shipped v0.1.78]; (1) session + connection lifecycle (seq #, green/yellow/red + a `connection_code` catalog, `v1.agent_session.connected/updated/ended` events); (2) a persisted activity/notifications API (event→notification projector over the existing events/audit/inbox/tokens); (3) the global Notification Center UI; (4) the **Live View** tab (its own top-level sidebar hub) — **this is the pilot of the one-window standard**; (5) app **preview** (research-informed: primary = iframe the live running project — Synapse runs real dev servers on real ports, which beats a sandboxed artifact for real apps; optional = a sandboxed `srcdoc` renderer for self-contained snippets); (6) expose sessions/activity to AIs (REST + `ai/context` + MCP).
2. **One-window UI standard** is a binding frontend convention (recorded in `AGENTS.md` + `CLAUDE.md`): fixed-height shell, `min-h-0 overflow-y-auto` inner panes, a shared `.scrollbar-thin` utility (theme-var `::-webkit-scrollbar` + Firefox `scrollbar-*`), page body never scrolls. New UI is built this way; Apps + AI Coding are refactored to it.
3. **Docs-sync is a hard gate.** `scripts/docs_sync_check.py` verifies the three version files agree, a `## [<version>]` CHANGELOG entry exists, and README names the current version. It runs in CI (mirrored as pytest tests) and is a required pre-commit step in `AGENTS.md`. Subjective freshness (README reflects *capabilities*, PROGRESS/roadmap narrative) stays in the PR-template checklist + the AGENTS.md docs-sync rule.

## What shipped (Phases 0–6, v0.1.78 → v0.1.88)

| Phase | Version | What landed |
|---|---|---|
| 0 | `0.1.78` | WAN auto-start toggle in Settings (finished ADR-0026). |
| 1 | `0.1.82`–`0.1.83` | `connection_codes.py` (green/`ok`, yellow/`degraded.*`, red/`failed.*` + explanation + remedy); migration `027` adding `seq` (#001…) + `connection_level`/`connection_code` to `agent_sessions`; register grades the connection (MCP probed best-effort) and emits an enriched `session_registered` event. |
| 2 | `0.1.84` | Migration `028` + `activity.py` — an event→notification **projector** over the daemon's own bus (session connected, squad created, work created/handed off, idea filed, project launched/errored, tool ran) writing truthful rows with token rollups + jump-to links; `routes_activity.py` (`/activity/notifications`, read, read-all, `/activity/sessions`, session detail). |
| 3 | `0.1.85` | **Notification Center** — global bell + unread badge, dismissible list with status dots, detail with token usage + working jump-to links; `.scrollbar-thin` utility. |
| 4 | `0.1.86` | **Live View** top-level hub — session rail + live timeline (persisted milestones + live events incl. the AI's terminal output); the reference implementation of the one-window standard. |
| 5 | `0.1.87` | **Live app preview** — iframes the real running project (device widths, reload, logs, open-in-browser); **CSP `frame-src` fix** (see below). |
| 6 | `0.1.88` | AI-facing: `ai_activity` block in `GET /ai/context`; sessions in `/coordination/snapshot` carry `seq` + grade; read-only MCP tools `synapse_list_sessions` + `synapse_recent_activity`; driver-guide section. |

**Notable finding (Phase 5):** the preview iframe rendered *nothing* because the app's CSP (`default-src 'self'`, no `frame-src`) made Chrome refuse to frame the project. Types and tests passed; only driving the real UI caught it. Fixed with a **loopback-scoped** `frame-src` (Synapse-launched projects only). This is why the ADR's E2E-before-complete rule exists.

## Consequences

- Every AI that opens the repo finds the plan here → Codex/Copilot code to the same plan as Claude.
- The Live View establishes the one-window look the rest of the app converges to.
- A version bump can't silently ship without a CHANGELOG entry + a current README (CI + the pre-commit gate catch it).
- Reuse-first: the feature is mostly wiring existing events/sessions/audit/inbox/tokens into new endpoints + UI; connection status + session numbering + the UI are the net-new parts.
