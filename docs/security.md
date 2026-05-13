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

The daemon binds `0.0.0.0:7878` so the mobile Web UI can reach it from the user's phone. This means **anyone on the same network can reach the daemon**. Acceptable for trusted home Wi-Fi; not acceptable for cafes, hotels, or shared offices.

v0.1 mitigation: the daemon will log every connection it accepts (audit log, source = `mobile`).

v0.2+ roadmap:
- Per-device pairing PIN (one-time code displayed on the desktop UI).
- Network ACL (default allow only RFC1918 addresses).
- Optional Cloudflare tunnel + authenticated origin if the user wants off-LAN access.

## Cloudtap caveats

`Cloudtap` exposes a local port to the public internet via Cloudflare. The tool will warn the user before tunnelling any port that:

- Is listening on `127.0.0.1` only (suggests the service was deliberately local-only).
- Has no detected authentication on a quick probe.
- Belongs to a service Synapse is not managing (so the user actually knows what they're sharing).

## Secrets

No secrets are stored in plaintext by Synapse. Project env vars marked as `secret: true` are stored encrypted at rest (Windows DPAPI on the daemon's user account). The UI never round-trips secret values back to the client after the initial save — only a `(set)` placeholder is shown.

(Secrets are formalised in Round 2 of design contracts — see `v0.1.1.5`.)
