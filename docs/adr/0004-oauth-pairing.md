# ADR-0004 — Sign in with Apple / Google (OAuth pairing)

Date: 2026-06-16
Status: **Proposed — deferred** (no implementation work until user gives go)
Supersedes: —
Related: ADR-0002 (workbench), ADR-0003 (workbench expansion Phase G),
         Contract #15 (no third-party network calls without opt-in)

## Context

The user has asked twice (once in ADR-0002, again in ADR-0003) for
"Sign in with Apple / Google" as an alternative to the current pairing
flow. Today's pairing is:

- Desktop generates a 6-digit code (`POST /api/v1/auth/pair/code`).
- Phone hits `http://<LAN-IP>:7878/mobile`, enters the code.
- Daemon swaps the code for a long-lived device token, stored
  per-device in `paired_devices` (migration 004).

That works, but only on the same LAN, requires the user to find their
LAN IP, and breaks if `SYNAPSE_HOST` is loopback-only. OAuth would let
a paired device authenticate by signing in with an Apple ID / Google
account instead of typing a code.

This ADR is a **stub**: it documents the decision space so the
dangling cross-refs in PROGRESS, CHANGELOG, AGENTS, and ADR-0003 land
somewhere real. **No code lands until the user explicitly approves
Phase A below.**

## Decision

Four-phase plan. Each phase has its own user gate.

### Phase A — provider setup + redirect handling

- Register OAuth clients on Apple (Sign in with Apple) and Google
  (OAuth 2.0 + OIDC). This is real paperwork — Apple wants a verified
  developer account; Google wants a configured OAuth consent screen.
- Decide the redirect URI strategy:
  - **Desktop:** `synapse://auth/callback` via a registered Electron
    custom protocol, so the OS returns the user to the desktop app
    after the provider auth.
  - **Mobile UI:** `http://<LAN-IP>:7878/auth/oauth/callback` --
    requires the LAN-exposure toggle to be on (per the AUDIT punch
    list) so the redirect is reachable.
- Persist provider client IDs + secrets in the daemon's secret store
  (DPAPI-encrypted; Contract #25).

### Phase B — daemon-side OAuth flow

- `routes_auth.py` gains `/api/v1/auth/oauth/start/{provider}` and
  `/api/v1/auth/oauth/callback`. The start route returns a provider
  URL; the callback consumes the authorisation code, exchanges for an
  ID token, verifies signature against the provider's JWKS, and pulls
  the user's subject claim.
- Sign-in maps to the existing `paired_devices` row -- a successful
  OAuth round trip yields the same long-lived device token the
  pair-code flow already produces. Downstream code does NOT care
  which path created the token.
- JWKS keys cached for the JWT verification window the provider
  declares (Apple ~24 h, Google ~6 h). Cache live in-memory only --
  cold start re-fetches.

### Phase C — UI surfaces

- Mobile UI gets a "Sign in with Apple" + "Sign in with Google" button
  next to the existing 6-digit pair-code input.
- Desktop Settings → Paired devices gets the same two buttons on the
  "+ Pair a new device" flow.
- Pair-code flow remains supported -- offline-LAN setup is still a
  legitimate path. OAuth is additive, not replacement.

### Phase D — account migration + device-list reconciliation

- Existing paired devices (created via pair-code) get a "claim with
  Apple / Google" upgrade path so their token gets associated with
  the OAuth subject claim. Downstream this lets us deduplicate "same
  user, three phones" reliably.
- A revoke-by-account API for the case where a user loses their
  phone -- sign in to a new device, hit revoke, every prior device
  token bound to that account dies.

## Honest trade-offs (deliberate non-decisions)

- **No social login providers beyond Apple + Google.** Adding GitHub
  / Microsoft / X would just dilute attention; the two requested are
  enough for the foreseeable users.
- **No "magic-link by email."** Out of scope; needs an SMTP relay,
  which violates Contract #15 (third-party network) without opt-in.
- **No server-side session for desktop.** Desktop already trusts
  loopback for `/auth/local-token`. OAuth is a mobile / off-LAN
  convenience, not a desktop one.
- **No federation across multiple Synapse installs.** A device paired
  with `Synapse-A` does NOT carry over to `Synapse-B` just because
  both are signed in with the same Apple ID. Synapse instances are
  intentionally independent.

## Why this is deferred

- Real provisioning work (Apple developer account, Google OAuth
  console) is real money + real time. The pair-code flow works.
- The LAN-exposure toggle (AUDIT punch list) is a prerequisite for
  the mobile callback URL -- needs to ship first.
- The user has not signalled an immediate need; the 6-digit code path
  is the production path today and isn't reported broken.

This ADR's purpose is to make sure the *decision space* is captured.
When the user wants to start, Phase A is the entrypoint and the gates
above structure the work.

## Status

Proposed — deferred. Implementation does NOT start until the user
explicitly approves Phase A AND the LAN-exposure toggle has shipped.
