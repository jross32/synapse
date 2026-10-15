# Fast Money Client Ops

Fast Money created this local-first client-ops SaaS starter as a proof app
that Synapse can generate and then hand to an AI runtime for refinement.

## What it includes

- Landing page and pricing page
- Local role sign-in for customer and operator sessions
- Customer portal scoped to one customer's lead, quote, job, and invoice records
- Operator console with protected workflow actions
- Optional catalog editor shell
- Workspace-scoped quote approval that advances the linked lead and creates a kickoff job
- Audited job scheduling, rescheduling, and completion
- Automatic draft-invoice creation when delivery completes
- Audited invoice send / mark-paid transitions with renewal-handoff state
- Local audit history for workflow changes, visible only to the operator session
- Demo data and billing/provider adapter placeholders

## Run locally

```powershell
python server.py
```

Then open `http://127.0.0.1:8740/`. Protected surfaces redirect to
`/signin`, where the localhost reference app can start either a customer or
operator session.

Workflow changes are stored in `workspace-state.json` beside the app, so they
persist across browsers and server restarts while staying on the local machine.
Session tokens are opaque, HttpOnly, SameSite=Strict cookies backed by process
memory. Local sessions expire after 8 hours, switching roles revokes the previous
session, and authenticated mutations require a per-session CSRF token delivered
through the session API and echoed in the `X-CSRF-Token` header. Signing in again
is expected after a server restart. The server binds only to `127.0.0.1` by
default.

Run the workflow and authorization tests with:

```powershell
python -m unittest -v test_workflow.py test_auth.py
```

## Local session / workflow API

- `GET /api/session`
- `POST /api/session/login` with JSON `role`: `customer` or `operator`
- `POST /api/session/logout` requires the current session CSRF token
- `GET /api/workspace-state` requires a session; customer responses are scoped
  to the current customer lead
- `POST /api/quotes/{quote_id}/approve` requires the matching customer session
- `POST /api/jobs/{job_id}/schedule` with JSON `owner` + `scheduled_for`
  requires operator access
- `POST /api/jobs/{job_id}/complete` requires operator access
- `POST /api/invoices/{invoice_id}/send` requires operator access
- `POST /api/invoices/{invoice_id}/mark-paid` requires operator access

Authenticated mutations require `X-CSRF-Token` with the token returned for the
current session. Mutations remain idempotent where repeating the same completed
action should be safe. Each real lifecycle transition records an audit event in
workspace state.

## Security boundary

The role chooser is intentionally a **local demo convenience**, not production
identity verification. Because anyone with localhost access can choose either
role, do not expose this reference server to a LAN or public host as-is. Before
any hosted or multi-device pilot, replace the local login endpoint with real
identity verification, move sessions into a production lifecycle/store with
appropriate revocation policy, and use Secure cookies behind HTTPS. The local
reference implementation now proves fixed expiry, role-switch revocation, and
CSRF enforcement, but those controls do not turn the open localhost role chooser
into production authentication.

## Files to know

- `FAST_MONEY_BRIEF.md` -- the latest product brief passed by the launcher
- `PROMPT.md` -- the current AI build/refinement prompt
- `ARCHITECTURE.md` -- structure and boundaries
- `MONETIZATION.md` -- pricing and packaging notes
- `seed-data.json` -- deterministic seed records
- `local_auth.py` -- process-local opaque sessions and role profiles
- `workspace-state.json` -- generated local workspace state after the first mutation
## Release preflight

Run python release_preflight.py from this directory. It prints a JSON report without exposing secrets and exits nonzero until all gates pass. Current demo configuration must fail closed.

Checks include real identity instead of the local role chooser, HTTPS and Secure sessions, Stripe test checkout, live billing, approved outbound messages, and deployment rollback. Configuration booleans are operator attestations, NOT technical proof. Only set them after independent verification. The preflight does not send messages, process payments, or deploy.

Run python -m unittest discover -p test_*.py -q and separately run discovery in the files directory. Browser verification uses the isolated harness documented in docs/REMOTE_EXECUTION_BROWSER_RECOVERY.md at the repository root.

A passing test alone does not authorize public deployment or live payment processing.
