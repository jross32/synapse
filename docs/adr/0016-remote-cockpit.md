# ADR-0016: Mobile remote cockpit — Needs-Review inbox first

- Status: Accepted (Phase R1 shipping: Needs-Review / approval inbox)
- Date: 2026-06-23
- Deciders: Justin (owner), Claude

## Context

The owner's headline goal is "control all and do all from my phone" — a remote
AI workforce you steer from anywhere. The squads, records, processes, and
pairing already exist; Phase R adds the **command / approve / capture / inspect**
layer on top of them. The roadmap flags one feature as highest value: an
**approval inbox** so you can clear the AI's handoffs while away.

## Decision (R1 — the approval inbox)

A **Needs-Review inbox** aggregates, across *every* squad and project, the work
the AI has handed back:

- **`handoff`** items — a worker finished a chunk and wants sign-off.
- **`blocked`** items — the AI is stuck and is effectively asking you a question.

This reuses the existing `agent_work_items` model (no new table): the inbox is a
cross-squad *view* over those two statuses, enriched with squad + project names.

### Daemon — `review.py` + `routes_review.py`
- `GET /review/inbox` → the queue (sorted most-recently-touched first, count).
- `POST /review/items/{id}/approve` → mark **completed** (accept).
- `POST /review/items/{id}/revise` `{note}` → back to **queued** with the note
  appended to the work item's instructions, so the AI sees the feedback next run.
- `POST /review/items/{id}/reject` `{note}` → **blocked** with the reason recorded.
- Each action audits + emits `v1.review.resolved` so an open inbox (desktop *or*
  phone) clears live.

### Renderer (R2)
A **"Review" surface** (nav tab + a Home card with the pending count) listing
each item with its summary / blockers / files and **Approve · Revise · Reject**
actions; revise/reject prompt for a note. Subscribes to `v1.review.resolved`.
Built mobile-first — this is a phone feature.

## Later in Phase R (own increments)
- **Capture button** — note / voice / screenshot → a project's records,
  `.synapse-ai-context.md`, or the active session (tagged `source=mobile`).
- **Project Control Room (mobile)** — overview + launch/stop + logs + records +
  "start Claude/Codex here" on one page.
- **Logs → "ask AI what this error means"** — package an error + context into a
  quick-action / session.
- **Web Push** — a service worker + VAPID + push-subscription routes, wiring the
  existing `v1.notification` events (crash, tunnel, **handoff ready / needs
  approval**) to real phone notifications.
- **Permission modes + panic-lock** — per-device access level (view / operator /
  developer / admin) + one-tap "lock all remote access."
- **QR scan-to-pair (new device)** — extend the claim flow to mint a *new-device*
  pair claim in the QR (no 6-digit code).

## Consequences
- The single most useful remote action — approve/redirect the AI's work — lands
  first, on top of data we already have, with zero schema change.
- "Revise" routing feedback into `instructions_md` means the AI actually acts on
  your note; "reject" preserves the reason on the blocked item.
- The rest of the cockpit layers onto the same squads/records/notifications.

## Alternatives considered
- *A dedicated "questions" table for the AI-asks-me queue* — deferred; `blocked`
  items with `blockers_md` already capture "stuck / needs input," so a new table
  isn't needed for R1. Revisit if free-form questions outgrow that.
