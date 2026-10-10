# Maya — Growth Director operating contract (pilot)

## Real status at creation (2026-10-09)
Maya is a persistent named staff identity with a role, persona, project work permission, approval-first authority, KPIs, and disabled recurring trigger. The first deterministic portfolio preflight was persisted as staff event `event-613f129f22`, created after inspecting the live project registry. This is **not** a completed AI worker assignment, autonomous activity, experiment, market research result, or revenue finding. Runtime health must be rechecked before claiming an active worker. The daemon has **not** been restarted/reloaded as part of this pilot.

## What shipped in source
- `daemon/synapse_daemon/maya_growth.py`: read-only commercial project and backlog evidence shortlist, operational readiness assessment, conservative next-step suggestion, and fingerprinted, idempotent review event.
- `GET /api/v1/staff/maya/growth-review`: preview without writing, training, model inference, or running external actions.
- `POST /api/v1/staff/maya/growth-review`: record an evidence receipt; deduplicates unchanged source snapshots. No spending, publication, or work item launch.
- Maya's actual chat prompt receives a compact project-health snapshot and explicit unknown metrics, while unrelated staff chat remains unchanged.
- AI Staff > Maya > Profile: Growth Review UI preview, source caveats, and explicit Record button.
- `daemon/tests/test_maya_growth.py`: 9 focused tests spanning source truth, safety, deduplication, preview, prompt, and routes.

## Growth Director's decision discipline
1. Start with an evidence ledger: observation, authoritative source, observation timestamp, uncertainty, proposed verification.
2. Separate operational readiness, user demand, actual funnel conversion, profit, and predicted growth. An app being healthy does not establish sales.
3. Pick ONE reversible, low-cost experiment with a measure, denominator, and stop condition. Do not produce ten vague ideas.
4. Use a first-value customer journey: visit -> sign up -> upload/add item -> create/publish listing where applicable. Define transitions *from the actual app*, not assumptions.
5. Independently verify reproducibility, browser behavior, and data integrity. Record failure screenshots, not just green logs.
6. Be explicit about owner approval for external outreach, paid promotion, account changes, spending, or irreversible operations.
7. Capture measured outcomes and compare to the pre-registered baseline. Unknown metrics stay unknown, not zero.
8. Ask specialists only for bounded missing expertise and preserve the lead's accountability.
9. Every review and experiment should produce a durable evidence receipt; score Maya on accepted recommendations, real improvements, cost and error rate—not messages or token volume.

## Pilot recommendation / next measured experiment
**ResellTogether — first-item-to-first-value baseline.** The recorded Synapse status is launched/healthy (a registry fact, not device/browser acceptance). Use a consented test account and check a bounded real user flow: sign in -> upload garment photos -> create closet item -> obtain a complete listing -> reach the intended publication workflow. Capture step completion, error states, time per step, account isolation, and screenshots on mobile and desktop. Record attempted/completed counts; *no baseline currently exists*. Do not publish externally without explicit approval. Escalate a reproduction of any upload/auth blocker before acquisition experiments.

## Next milestones (not complete)
- **P1 — prove a worker run:** Maya-linked staff work item, ChatGPT UI execution where available, heartbeat, exact finish/handoff and verifiable evidence; guard stale sessions; no duplicate launch.
- **P2 — measured experiment ledger:** per-project hypothesis, baseline, metric numerator/denominator, source URL/file/receipt, owner approval status, execution dates, cost, outcome, reversible rollback.
- **P3 — freshness-aware intelligence:** GitHub releases, app HTTP health, screenshot/browser checks, analytics & funnel source when authorized; rank sources by freshness/confidence. No fabricated customer numbers.
- **P4 — daily autonomous scans:** only enable a scheduler when runtime and resume/retry are proven; no duplicate sends, quiet notifications unless actionable.
- **P5 — expert council:** ask Sofia (marketing), Marcus (product), Jordan (sales), Adrian (finance) for domain-specific evidence, with Maya as accountable synthesis lead.
- **P6 — eval harness:** repeated blind trials, precision of recommendations, verified task completion rate, erroneous claims, approval safety, and measured business outcome; iterate on failure cases.

## Safe rollout gate
Before claiming live UI or autonomous behavior: pass focused tests and staff regression tests, TypeScript check, demonstrate authenticated GET/POST after a safe daemon reload, complete real browser UI inspection and a complete staff-linked worker lifecycle. Preserve unrelated dirty files. Never restart the daemon while other workers are active without coordinated quiescence. No claim of 100% success from a partial test.


## 2026-10-09 supervised worker attempt and execution-truth upgrade

A real Maya-owned assignment was created **once** via Synapse's existing staff summon path:
- Squad `81f0d68b1b8b`; work item `faa2ad60d1e9`; project `reselltogether`.
- Purpose: evidence-only first-value journey audit with zero production modification.
- Preferred runtime `chatgpt_web`, `observe` authority, 600s timeout, initially fresh ChatGPT conversation.
- Authenticated local Synapse CLI helper successfully POSTed the standard launch route. Execution `6ed4b23e9b37823b`, coordination session `698e5fcdab5c`.
- Worker **started but did not complete**. Its result is `blocked` with exact handoff blocker: *ChatGPT browser profile is not signed in. Open the dedicated Synapse ChatGPT profile once, sign in manually, then retry.*
- Setup endpoint `POST /chatgpt-workers/setup-browser` reported `already_running=true`, so the dedicated setup browser is already open for the owner to sign in. Do not copy normal Chrome cookies/passwords to this profile.
- Crucially, the worker was marked **blocked**, not active/successful. Do not call this a completed autonomous growth analysis.

New implementation:
- `daemon/synapse_daemon/staff_execution.py`: read-only effective work state based on linked staff assignment, actual session status, heartbeat recency and handoff evidence. Flags running rows with stale/missing/ended sessions as reconciliation-needed; never silently resumes or forks worker.
- `GET /api/v1/staff/{staff_id}/execution`: observe work queue, confirmed activity, stale sessions, blockers and handoffs.
- `renderer/components/MayaExecutionPanel.tsx`: shows Maya's confirmed working/queued/stale/finished counts, exact blockers, opens the official ChatGPT setup browser, and allows owner-click retry of the *same work item* with observe authority.
- `daemon/tests/test_staff_execution.py`: 11 lifecycle and route tests, including stale-active, missing session, completed-without-handoff, blocked reason, identity isolation, future timestamp.
- Combined focused tests: **21 passed** across staff-execution and Maya growth tests. `npm run typecheck` **exit 0** after UI updates; `py_compile` and Git diff whitespace check passed.
- Isolated FastAPI TestClient against actual Synapse DB: `GET /staff/maya/execution` HTTP 200, `observed_state=blocked`, correct work item. Main daemon still returns 404 for this new route, since the daemon was deliberately not restarted/reloaded.

Blocking requirements for end-to-end acceptance:
1. Account owner signs in *inside the already-open dedicated Synapse ChatGPT worker browser* and **closes that browser** afterward.
2. Coordinated safe daemon reload when other workers have checkpointed, to activate new routes/UI. Do not casually restart.
3. Retry **existing** work item `faa2ad60d1e9` (no duplicate), verify fresh heartbeat, successful response/hand-off with independent evidence, then measure first-value baseline.
4. Git cannot be pushed blindly: AI Staff foundation source files and much of UI are still untracked on main while unrelated workers hold dirty changes. Coordinate ownership and commit a coherent reviewed change set.
