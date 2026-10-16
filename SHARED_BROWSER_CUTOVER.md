# Authenticated shared Playwright cutover (fail closed)

The integration branch is a candidate, **not** proof that the live supervisor
has switched transports. Do not merge it over the dirty Synapse checkout or
restart the daemon without an agreed maintenance window.

## Before cutover

1. Stop scheduling **new** `chatgpt_web` work, without terminating existing
   leases or closing browser tabs. Reconcile active sessions and record their
   durable work-item IDs. Wait for in-flight work to reach terminal states.
2. Save the base commit, full `git status --porcelain=v1 -uall` manifest, and
   a binary-safe `git diff --binary HEAD` of the main checkout. **Untracked
   files need their own verified backup**; a Git patch does not preserve them.
   Record the backup location and SHA-256. Preserve Synapse's SQLite database
   using its consistent-backup procedure, not a live file copy.
3. Confirm there is one registered, authenticated `playwright` MCP session,
   that its ChatGPT project composer is signed in, and that **all clients**
   using its globally selected-tab tool have stopped. Merely observing a
   signed-in page or taking an in-process asyncio lock does not establish
   cross-client exclusivity. Require an external exclusive lease/gateway that
   rejects independent calls until the worker releases it.
4. Verify the integration changes against current dirty-main modifications in
   an isolated worktree. Run focused and full tests. Never overwrite concurrent
   edits in `app.py`, `chatgpt_child_agents.py`, or worker routes.
5. Only after all checks, deploy a reviewed build with explicit rollback
   pointer and a maintenance-window restart. Never start a second scheduler.

## Acceptance and rollback

- Submit one bounded coding task via the existing Foreman REST dispatch path.
- Confirm the worker uses the authenticated shared Playwright session (not the
  dedicated Chrome profile), owns its tab, and records a durable conversation.
- Independently verify actual changed source, passing tests, Git commit hash,
  and saved Synapse AI-context handoff **before** marking success.
- On failed login, tab ownership, completion reconciliation, or test proof,
  stop **new** dispatch, preserve evidence, restore the previous reviewed build,
  and restart only under the same maintenance controls. Do not close other
  clients' tabs, discard work, or fabricate terminal success.

Status 2026-10-16: main had 516 dirty entries and 1,201 untracked paths.
Tracked patch and manifest: `D:\synapse-cutover-safety-20261016`.
The patch alone does **not** preserve those untracked paths.
The Playwright server had multiple live ChatGPT conversations and no proven
cross-client exclusive tool lane; production cutover is therefore blocked.
