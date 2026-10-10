# Railway for Synapse: Cloud Architecture and Cost Guard
Status: source implemented 2026-10-09; live daemon reload, browser E2E and ongoing notification delivery NOT yet verified.

## Observed baseline (read from connected Railway account, 2026-10-09 UTC)

Workspace: `jross32's Projects`. Railway projects: Synapse Accounts; SYNAPS-OS Clinic OS Staging. One production service is active: `accounts-api` in Synapse Accounts, region `sfo`, one replica, from `jross32/synapse` using `cloud/accounts/Dockerfile`, 500 MB persistent volume mounted at `/data`. Latest deployment success at 2026-10-09T16:45:27Z. Staging project had zero services.

Fresh sample (after deployment): CPU ~0.00105 vCPU, memory 0.05681152 GB, used disk 0.032874496 GB. Last hour contained 2 HTTP requests, 0 errors. Do not treat this sample as a fully representative monthly average: the service was just deployed.

Reference 30-day pricing (Railway documentation, October 2026):
- CPU: $20 per *sustained* vCPU-month
- RAM: $10 per sustained GB-month
- Used volume storage: $0.15 per GB-month
- Outgoing network: $0.05 per GB
- Estimate at measured sample + used volume storage = ~$0.59/month CPU/RAM/volume before traffic, subscription floor, other projects, agent usage, taxes.
- This is NOT billed usage, invoice total, or a forecast with strong confidence.
- Hobby includes $5 of consumption in $5 subscription; Pro includes $20 in $20 subscription; Free gives $1 credit. Current workspace subscription tier was not returned by the connector.

Official docs: https://docs.railway.com/pricing/plans
Official cost controls: https://docs.railway.com/pricing/cost-control
Billing summary: https://docs.railway.com/projects/project-usage

## Implemented inside Synapse

Location: Watchdogs -> Railway cost monitor panel (no separate hosted app).
- `daemon/synapse_daemon/railway_cost_monitor.py`: source-aware monthly *steady-state* estimate, out-of-plan excluded-cost disclosure, stale/incomplete states, $3/$5 default warning/critical thresholds, optional read-only Railway GraphQL metrics.
- `daemon/synapse_daemon/routes_railway_costs.py`: authenticated read endpoint and threshold edit.
- Mounted inside existing `routes_watchdogs.py`, to reuse Synapse token guard in `app.py`.
- `renderer/components/RailwayCostPanel.tsx`: per-service CPU/RAM/used volume storage/outbound sample, stale status, editable thresholds, billing link.
- `renderer/pages/Watchdogs.tsx`: integrates panel.
- `data/railway-costs/observation.json`: observed seed from connected Railway tool, a point-in-time sample, NOT secret. No API token written.
- `daemon/tests/test_railway_cost_monitor.py`: regression tests.

To connect direct, automatic local Railway metrics, provide a read-authorized Railway **account/workspace** API token as `RAILWAY_API_TOKEN` in the Synapse daemon process environment, not via frontend, repo, logs, or ChatGPT text. Project tokens need different auth headers; the collector currently supports bearer account/workspace tokens only. Source must restart/reload in a safe maintenance window to activate modified endpoints; do NOT restart the current busy daemon without coordination.

The GET `/api/v1/system/railway-costs` endpoint returns latest reading; it refreshes from Railway GraphQL when token exists and cached observation >5 min old. GET `?refresh=true` requests read-only refresh. POST `/api/v1/system/railway-costs/budget` accepts `{warning_usd,critical_usd}` and persists JSON settings. Route inherits X-Synapse-Token auth. The observation store is under Synapse data dir, not synced across machines on its own. Metrics refresh is **on request**, not a daemon timer; a scheduled watcher is still needed for unattended notification.

Railway account connection inside ChatGPT is not automatically an accessible API credential for the Windows Synapse daemon. Never copy or extract app credentials. If no token is set, source shows a saved observation and labels stale data. **It does not pretend the cloud is connected.**

### Notifications / hard limits

The user already has five active ChatGPT scheduled tasks; creating a separate recurring Railway alert failed with `too_many_active_automations`. No background ChatGPT alert is active and no unrelated task was disabled. Separately, native Railway Usage -> Set Usage Limits can configure email soft alerts and a hard compute stop. A hard stop takes workloads offline, including authentication, and should be used only after an explicit user-approved threshold. Do not claim that the in-app $3/$5 state acts as an off-hours notification or shuts down spend.

## Cloud readiness matrix

1. Accounts/auth: Already on Railway. Confirm real Google OAuth flow, callback/domain, secure session cookies, user/device auth, DB migrations, rate limiting, restore and backup.
2. Cross-machine registry: Railway small coordinator service can store device IDs and health, last sync, opt-in discovery; never expose desktop root tokens.
3. Worker orchestration: Keep local code execution and browser-UI workloads local. Cloud coordinator may store durable queues, idempotency keys, leases and resumable checkpoints, but verify single-worker fencing and offline recovery.
4. Remote observability and notification dispatch: Strong candidate for small always-on container and email/webhook provider with idempotent dedup and bounded retry.
5. Product backends: Evaluate independently per product. Deploy only when there is actual external/user traffic, need for always-on public APIs, and staged rollback plan.
6. Sandbox/preview environments: Eligible for short-lived smoke-test containers with TTL, quota/owner tags, full clean-up proof. Avoid 24/7 preview replicas.
7. Heavy CPU workers / model inference / continuous Playwright: Prefer local now. Railway VM/sandbox compute can be much more expensive than idle containers. Price test first.
8. User image/photos and business documents: Use private object storage for needed data with signed access, quotas, encryption, clear deletion and backup policies; do not expose local paths/sessions publicly.
9. Shared research cache, small worker receipts, sync metadata: reasonable in a metered persistent service after privacy and retention design.
10. 95 registered Synapse projects are NOT 95 Railway deployments. Never mass-deploy projects or give unbounded workers automatic deployment permission.

### Gate before ANY new Railway service
- Why does this workload need always-on availability?
- What data would leave the Windows machine, and is user authorization established?
- What is its expected CPU/RAM/storage/egress monthly upper bound?
- Can traffic be batched, scaled to zero, or handled over a tunnel from local?
- Are service quotas, auth, idempotency, healthchecks, backups, rollback and retention in place?
- What is the fail-safe action at warning/hard budget threshold?
- Can the service be demonstrated end-to-end, including multi-device behavior and recovery?

## Verification limits
Focused backend/watchdogs suite: 17 passed (2026-10-09). Global TypeScript typecheck exceeded Synapse command timeout (80s), not a pass or diagnosed TS failure. Need isolated long-running typecheck with captured result, live daemon reload coordinated with concurrent writers, authenticated API E2E, and real mobile/desktop UI proof. Current live UI may still be serving old source.


## Approved expansion roadmap — 2026-10-09
Owner approved all nine additional capabilities and execution. This is a staged build, not blanket authorization to deploy chargeable services or disable essential ones. Existing Always-On Cloud Control Plane squad ce64ad400c34 owns overlapping identity/worker/cost tasks: extend it, DO NOT launch duplicate squads.

### Ordered deliverables and acceptance gates

**P0 — Cloud Spending Guardian:** extend Railway cost monitor to include sourced (not fabricated) actual billed usage when authorized, CPU/RAM/egress/storage time series, project attribution, $3 warning / $5 critical *configurable* thresholds, anomaly alerts, notification dedup, history, stale-source indicators, and optional approval-gated new deployment policy. Native Railway soft notifications and hard limits are separate; don't claim billing control from estimate-only warnings. Test missing data, price changes, double-counting, stale metrics, overage, disconnected PC.

**P0 — Cloud Decision Journal:** durable records for proposed/approved deployments: owner, workload, projected cost range, data classification, rationale, alternatives (local/Railway/hybrid), service/environment IDs, TTL, billable dimensions, 7-day/30-day follow-ups, actual usage, continue/optimize/migrate/retire decision. Immutable audit trail for rollout, rollback, and human approvals. Never auto-deploy expensive services merely because of a recommendation.

**P0 — Persistent AI Job Queue:** extend existing cloud_outbox/agent_squads/restart coordinator, don't duplicate. Cloud stores encrypted task metadata, lease epoch, heartbeat/TTL, idempotency, checkpoint pointers, bounded retry, reconnect adoption, failed/stale lease recovery, execution allowed only by authenticated designated workers. Test at-least-once message delivery and at-most-one effective execution under crashes, split-brain, out-of-order ACK, duplicate reconnect, offline device.

**P1 — Remote iPhone Control Center:** connected mobile dashboard for online/offline computers and last seen, active/stale workers, project state, Railway expenses, alerts, owner approvals with scoped credentials; cloud remains read-only/queued when Windows offline. Verify on narrow phone browser, native Safari where actually available; include no sensitive daemon root tokens or user-private file contents.

**P1 — Backups and Restore Center:** encrypted/retention-limited database backups, restore-drill receipts, coverage and last-success, RPO/RTO target, integrity and audit trail, priority Synapse Accounts. Differentiate backup configured from restore proven, no destructive restore to production.

**P1 — Intelligent Cloud Placement:** deterministic recommendation model scoring availability, measured local/cloud resource load, sensitivity, compliance, reliability, performance, network, hard caps, and actual/forecast monthly cost. Modes local/Railway/hybrid; must justify decisions and handle incomplete input as unknown. No autonomous paid provisioning without approved service policy.

**P1 — Unified Infrastructure Health:** combine daemon/watchdogs, tunnel, Windows machine, cloud Accounts, Railway metric freshness, AI sessions/agents, cross-device coordination; root-cause grouping, offline-vs-unhealthy semantics, dependency tree and recovery receipts, no invented green health.

**P2 — Ephemeral Cloud QA Environments:** requested PR/demo preview environments tagged with owner and cost budget, TTL, secrets isolation, deploy/health/accessibility/UX test receipts, stop/delete confirmation, watchdog expiration enforcement and cleanup audit, fail-closed on missing budget.

**P2 — SaaS Unit Economics:** per-product infra/AI/model/tool spend and revenue, cost per customer/action, gross margin and payback, unknown revenue explicitly not zero, linked to Cloud Decision Journal; do not co-mingle Synapse core infrastructure with hosted customer products.

### Platform safeguards / roadmap dependencies
- Synapse cloud authentication is a dependency, not a substitute for scoped device identity. Complete and validate Google OAuth, account reset, cross-device authorization and DB migration safety.
- Keep heavy Ollama, continuous Chrome/Playwright and local code builds on Windows unless measured alternatives support migration.
- Each stage includes tests, independent browser and API evidence, accurate unknown-state reporting, README/CHANGELOG, isolated Git commits and rollback procedure. Never sweep coworkers' dirty changes.
- No live daemon restarts without coordinated quiescence; no credentials stored in Git or responses; no automatic production Railway deploy or hard spending cutoff without explicit approved budget and downtime policy.

### Execution lanes (existing squad ce64ad400c34)
A. Extend existing Railway monitor + cost ledger and decision journal (first build).
B. Worker cloud heartbeat/checkpoint/outbox and security-fenced recovery (existing workers).
C. Browser/mobile control-center + backed-up account state after A/B contracts stabilize.
D. Unified observability, cloud-placement scoring, ephemeral QA and unit economics in sequence.

Definition of done: test proof and live UI evidence, actual source-linked metrics, alert delivery proof (or clearly blocked), data retention/security review, controlled rollout and no regression. Any unimplemented item stays planned, not complete.
