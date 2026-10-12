# Maya Growth Director — measured experiment planner (October 10, 2026)

## What was implemented
A safe internal experiment planning layer was added to Synapse's existing Maya profile while her dedicated ChatGPT worker login remains blocked.

- `daemon/synapse_daemon/maya_experiments.py`: read-only generation of exactly one reversible internal first-value test, source-linked project prioritization with a 24-hour health-probe freshness gate, a measurable numerator/denominator, explicit unknown baselines, steps, required dated evidence, guardrails, and next action. Fresh healthy candidates are prioritized over stale healthy registry entries. No invented customer, conversion, or revenue numbers.
- `record_experiment_plan`: stores a durable draft-only staff event in the existing staff_events schema; idempotent on an identical source/plan; a meaningful readiness change gets a new version. Never invokes a worker or performs any external action.
- `daemon/synapse_daemon/routes_staff.py`: new `GET /api/v1/staff/maya/experiment-plan` preview and `POST /api/v1/staff/maya/experiment-plan` draft-only record. Same authenticated route surface as existing staff APIs.
- `renderer/lib/staff-client.ts`, `renderer/components/MayaGrowthReviewPanel.tsx`: display the proposed experiment steps, readiness and unknown metrics, and explicit Save draft button. Not a Launch button.
- `daemon/synapse_daemon/maya_growth.py`: Maya's prompt now requires one falsifiable, reversible experiment with metric denominator, evidence and approval boundaries.
- `daemon/tests/test_maya_experiments.py`: 11 detailed integration/route/receipt cases; the full migrated test fixture did not finish under tool timeout on the low-memory host.
- `tools/maya_experiments_smoke.py`: fast, independent in-memory validation of first-value planning, privacy checks, stale/future health handling, and idempotent event persistence.

## Verified
- 14/14 lightweight isolated logic-and-receipt checks passed with system Python on October 10.
- Python compilation of changed backend modules passed.
- TypeScript syntax parse for MayaGrowthReviewPanel.tsx and staff-client.ts passed.
- Full `npm run typecheck` timed out at 80 seconds (no success claim).
- Full migrated pytest test module timed out during slow database initialization (no success claim).
- Live daemon `GET /api/v1/staff/maya/experiment-plan` returned 404, because the daemon was deliberately **not restarted** to protect other active workers.
- Global git diff --check had preexisting whitespace warnings in unrelated download-site/app.js and download-site/style.css; Maya-owned source syntax checks passed.

## Current release blocker
The AI Staff foundation and Maya UI are partially untracked in the current working tree alongside other agents' substantial changes. Do NOT blindly stage, reset, commit or push unrelated files. First coordinate one safe integrated Git publication lane, run the full tests on a memory-available machine, then safely reload the daemon and verify authenticated API plus mobile/desktop browser behavior. Live Maya work item `faa2ad60d1e9` is blocked by dedicated ChatGPT worker profile not signed in. This implementation does **not** change that blocker.

## Next acceptance gate
1. Confirm staff source ownership and Git scope.
2. Pass 11 integration tests, full TS typecheck and authenticated GET/POST on the reloaded daemon.
3. Open AI Staff > Maya > Growth Review and verify the draft is previewed/saved on desktop and mobile.
4. Sign in to Synapse's separate ChatGPT worker browser manually, then retry existing blocked work item once, with no duplicate squad.
5. Execute a real consented ResellTogether first-value walkthrough, store pass/fail receipts and the actual attempted/completed counts. Never label a proposal as measured success.
