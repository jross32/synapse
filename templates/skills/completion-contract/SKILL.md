---
name: completion-contract
description: Default Synapse completion discipline for any nontrivial development or fix request, combining autonomous continuation, bounded retries, real desktop/mobile browser interaction checks, Quality OS gates and durable verified handoffs.
---

# Synapse Completion Contract — default for development

**Apply automatically** when an AI using Synapse receives a build, repair, redesign, deployment, install, verification or end-to-end development task. This is a *discipline* layered over the installed Autonomous Dev Loop, Repair Arena, UI Forge, Browser UI Audit and Quality OS; **do not build competing schedulers**.

## Mandatory first actions

1. Load project AI context, records, current git status, active sessions, owners and any open Quality OS blockers. Inspect the *actual* existing tool/skill implementation before coding.
2. Write an acceptance checklist from the user's request: full feature inventory, routes/screens/buttons/forms, data lifecycle, existing behavior and security, desktop/mobile, backend/REST, install/update/deploy if requested. Map every acceptance item to executable evidence.
3. Assign one writer per file/worktree, reuse previously running workers, keep recovery checkpoints outside disposable chats, and use the installed `autonomous-dev-loop` continuity contract.

## Autonomous execution contract

- Execute a bounded batch, then automatically choose the next pending acceptance criterion; persist checkpoint with exact next action and previous tests. A 30–60-minute project run requires daemon-owned worker supervision across individual model/tool turn boundaries; an AI chat turn alone **cannot** promise to run for that duration.
- On errors: classify (code, environment, permissions, network, credentials, external dependency), seek root cause, make smallest reversible repair, add regression test, rerun. Use Repair Arena when diagnostic alternatives are useful. Retry with bounded exponential backoff, changing hypothesis after repeated identical failures. Do not loop without progressing.
- Use available local runtime only if viable; check before launching. Installing ordinary dependencies is permitted after checking provenance, compatibility, licensing, disk usage and rollback; do not silently install privileged, unsafe or unrelated software.
- Never bypass login challenges, authorization requirements, security policy or access boundaries. If real sign-in, payments, destructive migration or privileged access needs the owner, flag a narrowly described intervention and preserve runnable state.
- Never overwrite another worker's dirty work, discard user data, modify unrelated applications or expose secrets in logs.

## Independent proof gate — fail closed

- Run static checks and focused tests, then integration/regression tests. Changes affecting user journeys require real Chromium/Playwright or Reflex click-through, not just screenshots or DOM inspection.
- Enumerate all visible routes, navigational links, actionable buttons, forms, dialogs, keyboard paths and error states; prove each user-visible interaction or record explicit tested exceptions. Inspect network/console errors, responsiveness on desktop and narrow mobile, touch target usability, accessibility basics, persistence across reload and restart.
- For backend/API use real authenticated read/write and permission-negative tests; prove concurrency/idempotency, migrations and rollback where relevant.
- For deployments and installers validate actual installed/running artifact, version/hash and real destination. Distinguish build success from running app proof.
- Check Synapse Quality OS open blockers; do not mark `verified_complete` with relevant blocking gates open. A reviewer independent of the implementer must inspect evidence, not just an AI's summary.
- Classify outcomes: `working`, `blocked_requires_owner`, `blocked_external`, `verification_failed`, `verified_complete`. Only the last means done.

## Mandatory durable checkpoint

Persist project, branch/worktree, commit, precise acceptance checklist pass/fail/untested, tests and logs, open gates, blocking permission or credential, recovery attempts, known risks, next exact command/worker, timestamp, and status into Synapse's project AI context / durable Autonomous Dev Loop checkpoint before a context boundary. Resume rather than asking the user to say "keep going."

## Scope and visibility

This installed skill is discoverable by *Synapse-connected AIs that retrieve Synapse skills/context*. It cannot force unrelated disconnected ChatGPT chats to read it, eliminate platform turn limits, guarantee full autonomy, or override a human authorization requirement. Completion claims must accurately describe what was actually executed.
