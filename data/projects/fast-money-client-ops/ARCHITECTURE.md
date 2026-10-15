# Architecture

## Runtime

- `server.py` uses Python's standard-library threaded HTTP server so the starter
  is runnable anywhere Synapse itself can run Python.
- `fast_money.config.json` controls app name, enabled surfaces, billing
  placeholders, and the expected port.
- `seed-data.json` provides deterministic bootstrap records.
- `server.py` owns a workspace-scoped local workflow store. The first mutation
  creates `workspace-state.json` with atomic replacement, a schema version,
  workspace metadata, mutable business records, and an audit log.
- Workspace schema version 2 covers the delivery-to-cash workflow.
- `local_auth.py` owns process-local opaque session tokens with fixed 8-hour
  expiry, role-switch revocation, and independent per-session CSRF tokens. The
  browser receives only an HttpOnly, SameSite=Strict session cookie.
- `static/auth.js` starts/switches local role sessions, displays the active role,
  holds the non-cookie CSRF token in memory, and signs out without exposing the
  opaque session token to JavaScript.
- `static/app.js` reads shared state through `/api/workspace-state` and sends
  workflow transitions through the local API instead of browser localStorage.
- Dynamic workflow values are HTML-escaped before browser rendering so persisted
  operator-entered fields do not become stored markup.

## Session and authorization invariants

- `/portal` requires a customer session; `/ops` and `/catalog` require an
  operator session. A role mismatch redirects the page request to `/signin`.
- Workspace API reads require a session.
- Customer workspace responses are filtered to the session's lead and linked
  quote/job/invoice records. Catalog and operator audit history are omitted.
- Quote approval is a customer action and is rejected if the quote is linked to a
  different lead.
- Job scheduling/completion and invoice send/mark-paid transitions are
  operator-only.
- Authenticated POST mutations, including logout, require the current session's
  `X-CSRF-Token`; missing or forged tokens are rejected.
- Local sessions expire after 8 hours. Starting a different local role revokes the
  previous cookie-backed session before issuing a new one.
- Logout deletes the current server-side session and expires the browser cookie.
- Sessions are intentionally process-local and disappear on server restart.

## Workflow invariants

- Quote approval is idempotent: it advances the linked lead, creates at most one
  kickoff job, and records one `quote.approved` audit event.
- A job must be scheduled before it can be completed.
- Repeating the exact same schedule is a no-op; changing it records
  `job.rescheduled`.
- Job completion is idempotent and creates at most one linked draft invoice.
- Invoice state moves `draft -> sent -> paid`.
- Paying an invoice marks the linked lead `active-client` and the invoice renewal
  handoff `ready`.
- Every real lifecycle transition records a linked audit event.

## Surfaces

- `/` landing page
- `/pricing` pricing and packaging
- `/signin` local role-session chooser
- `/portal` customer portal
- `/ops` operator console with job/invoice actions and workflow audit history
- `/catalog` optional operator catalog editor shell
- `/health` launcher-friendly health endpoint
- `GET /api/session`
- `POST /api/session/login`
- `POST /api/session/logout`
- `GET /api/workspace-state`
- `POST /api/quotes/{quote_id}/approve`
- `POST /api/jobs/{job_id}/schedule`
- `POST /api/jobs/{job_id}/complete`
- `POST /api/invoices/{invoice_id}/send`
- `POST /api/invoices/{invoice_id}/mark-paid`

## Boundaries

- The reference server remains bound to `127.0.0.1`; workflow data does not leave
  the machine.
- The local role chooser is not production authentication. It exists to prove and
  test authorization boundaries without hardcoding credentials or claiming hosted
  identity assurance.
- Do not expose the reference server to a LAN/public host until login is replaced
  with real identity verification, session lifecycle/revocation is backed by an
  appropriate production store/policy, and HTTPS + Secure cookies are enabled.
  The local fixed-expiry/revocation/CSRF controls prove the policy seam only.
- Billing and invoice-delivery integrations remain explicit adapter seams.
- `workspace-state.json` is runtime data rather than seed/config source.
- "Send invoice" is a local lifecycle transition only; no external email or
  payment-provider call is made yet.

## Next upgrades

- Replace the localhost role chooser with a real identity provider before any
  hosted or multi-device pilot.
- Replace process-local sessions with a production session store/lifecycle and
  HTTPS-only Secure cookies as part of the hosted-auth layer.
- Add invoice delivery/payment adapters behind the current local transition seam.
- Add renewal tasks and reminder scheduling from the ready renewal handoff.
- Add real billing and subscription state behind the pricing page.
