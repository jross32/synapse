# Security Posture — Synapse

This document records Synapse's security stance and the reasoning behind each design contract that touches it.

## Threat model (v0.1)

- **Personal machine, trusted home LAN.** Synapse v0.1 assumes a single user on a single PC, with optional access from devices on the same Wi-Fi.
- **Out of scope:** multi-tenant deployments, internet-exposed daemons, defence against a hostile local user.
- **In scope:** preventing accidental privilege escalation, preventing data leaks (no telemetry), making destructive actions explicit.

## Contracts that touch security

### #15 No telemetry by default

The daemon makes zero outbound HTTP calls except:

- When the user explicitly opts in to update checks (off by default; opt-in toggle in `Settings → Updates`).
- When a user-triggered tool action requires it (e.g. Cloudtap shells `cloudflared` which talks to Cloudflare).
- When a managed project makes its own outbound calls (Synapse is not in the data path).

There is no error reporting service, no analytics, no "phone home" beacon. If telemetry is ever added, it must:

1. Be opt-in only.
2. Disclose exactly what is sent, in plain English, in the consent dialog.
3. Land via a new design contract entry (i.e. require explicit lock-in).

### #16 Refuse to run as Administrator

Synapse daemon and Electron app both refuse to start with elevated privileges unless `--allow-admin` is passed. Reason: managed child processes inherit token elevation, so launching `wbscrper` from an elevated Synapse means `wbscrper` (and its Playwright Chromium) all run with admin rights. That is a much larger blast radius than the user signed up for.

If a managed project genuinely needs elevation (rare), the project's manifest can declare `requires_admin: true` and Synapse will request UAC elevation **for that one child process** via a separate launcher, rather than running the whole daemon elevated.

## LAN exposure

The daemon binds `127.0.0.1:7878` (loopback) by default — unreachable from
other devices. Passing `--bind-lan` binds `0.0.0.0:7878` so a phone can reach
it. As of v0.1.11 that is safe to do: every request needs a token (see
**Device authentication** below), so a LAN neighbour who reaches the port
still cannot read or control anything without pairing first.

## Cloudtap caveats

`Cloudtap` exposes a local port to the public internet via Cloudflare. The tool will warn the user before tunnelling any port that:

- Is listening on `127.0.0.1` only (suggests the service was deliberately local-only).
- Has no detected authentication on a quick probe.
- Belongs to a service Synapse is not managing (so the user actually knows what they're sharing).

### Remote recovery helper

`scripts/remote-recovery.ps1` is a local rescue path for the owner of the
machine. It can start or reuse the daemon, open Cloudtap for port `7878`, and
print the WAN `/mobile` URL plus a fresh 6-digit pairing code. This is meant
for cases where Synapse's desktop window is down but the user still has a
trusted automation path to the PC, such as a Codex session.

The helper does not bypass Synapse auth. API routes still require a paired
device token, pairing codes remain single-use and short-lived, and
`/auth/local-token` remains blocked through Cloudflare proxy headers. It does,
however, intentionally publish the mobile shell on the public internet through
Cloudtap, so close the tunnel from Settings -> Phone access when remote
recovery is no longer needed.

## Device authentication (v0.1.11, Milestone H)

So Synapse can be reached from a phone — including off-network via a Cloudflare
tunnel — without anyone bypassing auth.

**Every `/api/v1` data route requires an `X-Synapse-Token` bearer token.** Only
`/health`, `/auth/local-token`, and `/pair` (redeem) are open.

Two token kinds:

- **Local token** — a random secret the daemon writes to `data/auth-token` on
  boot. The desktop app + the dev browser fetch it from
  `GET /api/v1/auth/local-token` and send it on every request.
- **Device token** — minted when a phone redeems a 6-digit pairing code
  (`POST /pair`). Codes are single-use, expire after 10 minutes, and live in
  daemon memory only. The token's SHA-256 is stored in `paired_devices`; the
  raw token is shown to the device exactly once. Revoking a device makes its
  token stop verifying immediately.

**Why not "trust loopback":** a Cloudflare tunnel runs `cloudflared` on this
machine, so a tunnelled request reaches the daemon from `127.0.0.1` — it looks
local. Trusting loopback would let anyone with the tunnel URL through. So the
daemon trusts **no** request by IP. The one exception is the
`/auth/local-token` bootstrap endpoint, gated by `is_trusted_local()` —
loopback **and** no proxy/tunnel headers (`X-Forwarded-For`, `CF-*`). A
tunnelled request always carries those headers, so it cannot reach the local
token; it must pair instead.

WebSocket connections carry the token in the `resume` frame; a non-local
socket without a valid token is closed (code 1008).

v0.2+ roadmap: an account-less device-pairing flow polished for a fixed public
address (same token mechanism, friendlier UX).

## Secrets

No secrets are stored in plaintext by Synapse. Project env vars marked as `secret: true` are stored encrypted at rest (Windows DPAPI on the daemon's user account). The UI never round-trips secret values back to the client after the initial save — only a `(set)` placeholder is shown.

(Secrets are formalised in Round 2 of design contracts — see `v0.1.1.5`.)
