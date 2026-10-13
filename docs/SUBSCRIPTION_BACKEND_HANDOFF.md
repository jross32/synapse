# Synapse subscription backend handoff

Status: backend preview, not a live paid billing product.

## UI contract
- `GET /v1/plans`: public Free/Plus/Pro/Unlimited catalog. Prices are null and purchase is disabled.
- `GET /v1/subscription`: authenticated account plan, billing status, feature flags and current limits.
- `GET /v1/subscription/usage`: authenticated current UTC calendar-month usage.
- `POST /v1/subscription/preview-usage`: authenticated demo-only counter; request `{"metric":"preview_actions","units":1,"event_key":"stable-operation-id"}`. Returns 429 when over quota, 409 for reused keys with different payloads. **Do not call this from production actions yet.**

All endpoints derive account identity from the bearer token; no account ID is accepted from clients. Unknown/expired paid states fail closed to Free.

## Internal-only trusted transitions
`set_plan_trusted(db, account_id=..., plan_id=..., billing_status=..., provider="stripe"|"admin")` is a Python service function and is NOT exposed as an HTTP route. Future billing webhook integration must verify provider signatures, subscription/customer ownership, event ordering and replay protection before invoking it. Current tests exercise the state machine using this trusted entry point.

## Production gates
1. Agree on actual pricing, feature matrix and usage quotas. The `preview_actions` values are illustrative and do not gate existing daemon behavior.
2. Add billing provider customer mapping, signed webhooks, webhook replay/event-order handling, checkout and portal flows, cancellation and prorations. Do not trust a client-submitted plan ID to grant paid access.
3. Integrate metering into actual AI actions with reserve/commit or compensating release on failed actions, not up-front charges.
4. Add production migrations and concurrency tests on Railway's real database. `create_all` creates new tables but does not migrate existing columns.
5. Run full backend suite and smoke tests on a staging deployment before promoting production. Verify Railway's persistent database backups and recovery plan.
6. Once backend is approved, wire the premium UI account menu to `GET /v1/subscription` and usage panel to `GET /v1/subscription/usage`; only enable upgrade buttons after live billing is verified.

## Operational safety
No existing local projects, files, AI agents, or watchdogs are moved into the cloud. No frontend changes are required by this branch. Existing Railway account service remains untouched until explicit deployment.
