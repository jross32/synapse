# ADR-0038: Native ChatGPT UI fleet controller

Status: Proposed
Date: 2026-10-17

## Context
Ten ChatGPT UI workers were orchestrated manually through a shared registered Playwright MCP browser. Repeated supervisor model calls are expensive because they re-read a large conversation. The existing scripts under scripts/chatgpt-fleet prove dispatch and inspection, but cannot provide durable restart recovery.

## Decision
Introduce a daemon-owned, opt-in fleet controller with MCP start, status, nudge and stop operations. Persist fleet configuration, owned browser conversation IDs, and per-lane status atomically in a daemon data directory, not in the live repository. Each lane owns a separately created git worktree and branch. Worktrees are created sequentially before dispatch. All repository and browser actions use existing registered Synapse tool paths; never spawn other AI CLIs or add another scheduler.

The start contract accepts project_url, repo, base_ref, either workers=N or explicit lanes (name/task/files), interval_minutes (default 15), and connector labels (plugins). Validate URLs, lane names, distinct file ownership, repo boundaries, branch collisions, and connector availability before mutation. Connector labels must be resolved against the ChatGPT composer menu; every requested connector must be attached, otherwise stop dispatch and raise an actionable blocker.

Each dispatch creates a fresh ChatGPT chat, sends the bounded worker preamble, and records the /c/ conversation URL from a verified tab list rather than a premature dispatch result. Close only controller-owned tabs after approximately 20 seconds; ChatGPT continues processing server-side. Never act on unowned tabs. Do not follow up into old chats because existing URLs can render minimized floating chats without message history.

## Lane protocol and reconciliation
Worker writes `working <UTC timestamp>` before action and `idle <full commit SHA> <next|DONE>` on completion. The daemon checks that the idle SHA is reachable on the lane branch before marking a round complete. An idle lane with unfinished next work gets a *fresh* chat. Working states older than 120 minutes are treated as stale and re-dispatched with an explicit recovery prompt. Status is a compact one-line record per lane including busy/idle/done, branch HEAD and latest status. Never mistake missing status or an unverified HANDOFF for completion.

Once idle status and SHA have been verified, archive only the controller-owned completed round chat through its options menu. Archive is reversible; never delete. If archiving fails, retain the chat ID and retry safely; do not block status reporting. Integrator lane performs --no-ff merges and tests one completed branch at a time, with separate file ownership and an explicit approval/milestone signal.

## Scheduling and safety
Use one opt-in timer within the existing daemon lifecycle (no Windows scheduled tasks and no separate scheduler), at most one nudge pass per configured interval, with a persisted lease to prevent overlapping passes. Stop disables timer and future dispatch; it does not kill workers, destroy worktrees, or delete chats. Resume reconciles git/status/browser state before any new dispatch. Emit operator-attention events only for signed-out browser, missing connector, browser lock, conflicts and integrator milestones. Polling and deterministic nudge logic require zero model tokens; worker execution still uses ChatGPT.

Do not touch the running Synapse daemon checkout, credentials, protected branches, unrelated browser tabs, or other worktrees. No implicit push or merge to protected branches. Use async/poll for potentially slow MCP operations. Validate all external input and redact sensitive data from logs.

## Tests and rollout
Mock registered Playwright MCP calls and git operations. Test validation, sequential worktree creation, multi-connector attachment failure, owned-tab-only actions, fresh-chat redispatch, status/branch SHA reconciliation, 120-minute stale threshold, archive-only cleanup, timer opt-in and idempotent stop/restart. Keep native mode disabled until browser integration is verified end to end in an isolated test repository. Existing scripts remain the fallback.

## Alternatives
Repeated AI-driven check-ins: rejected due to measured context-read cost. New independent scheduler: rejected due to ownership and lifecycle duplication. Reusing old conversations: rejected due to floating-chat UI behavior. Deleting chats: rejected as irreversible.


## Implementation checkpoint (2026-10-17, version 0.2.223)

The controller foundation, REST and MCP endpoints, AI context discovery,
daemon timer and browser-mocked tests have landed on feat/chatgpt-ui-fleet.
This is not live acceptance. The next round must implement shared-Chrome
CDP lifecycle and safe orphan cleanup, device readiness, runtime fallbacks,
integrator branch-change gating, and a nonblocking dispatch queue, then
perform the isolated two-worker real-UI acceptance. Long synchronous
multi-lane dispatch remains a risk under the MCP 90-second bound.
