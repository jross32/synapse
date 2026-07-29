# ADR-0026: WAN auto-start — open the Cloudtap tunnel on daemon boot by default

- **Status:** accepted
- **Date:** 2026-07-29
- **Deciders:** Justin (owner), Claude
- **Related contracts:** #6 (orphan reconciliation / restart safety), #11 (audit log). Builds on the Cloudtap WAN tool (v0.1.36), `boot_config` (v0.1.35), and ADR-0012 (the `/mcp/<token>` connector exposed over the tunnel).

## Context

Synapse already had everything needed to reach it from off-LAN: the **Cloudtap tool** (wraps `cloudflared`) opens a quick tunnel at a public `*.trycloudflare.com` URL pointing at the daemon port, `GET /remote-access` reports the tunnel + verifies it, and `NetworkPanel` drives open/close. But it was **manual** — the user had to click "Expose to WAN via Cloudtap" every time. Justin's goal is to drive Synapse (and, over ADR-0012's `/mcp/<token>` connector, an AI) **from anywhere**, so the tunnel should come up on its own.

Justin's requirements:
- **On by default** — a fresh install exposes over Cloudtap automatically; the tunnel follows the daemon lifecycle, not a UI click.
- **User-overridable** — a toggle in Settings → Network turns it off; the choice persists.
- **Also surfaced in onboarding** so a new user makes an informed choice.

## Decision

1. **A persisted `wan_auto_start` boot setting (default `true`)** in `boot_config.json`, next to `bind_lan`. Degrades to the default on a missing/garbage/wrong-typed file — never crashes the daemon.
2. **A daemon `on_startup` hook (`_autostart_wan_tunnel`)** that, when `wan_auto_start` is on, opens the Cloudtap tunnel on the bound port. It mirrors `_autostart_mcp_servers`:
   - **Best-effort** — wrapped so a tunnel failure NEVER aborts daemon startup.
   - **Idempotent** — if a tunnel is already open for the bound port, it's left alone (a reconnect/restart doesn't stack tunnels).
   - **Graceful** — a missing Cloudtap tool just logs + skips.
   - **Gated by `allow_wan_autostart`** (default `false`; only `__main__` sets it `true`) so TestClient app-builds never spawn a real `cloudflared` — the same opt-in shape as `allow_web_scraper_download_bootstrap`.
3. **`GET/PATCH /api/v1/system/network` carry `wan_auto_start`** so the Settings toggle (and the API) can flip it; both `NetworkPatch` knobs are optional so a caller can change just one, and each change is audited under its own `network.<knob>.set` action.

## Security note

Auto-opening a public tunnel means the daemon is reachable on the internet whenever it runs. This is an explicit, owner-chosen default; the exposure is guarded by the daemon's `X-Synapse-Token` (and ADR-0012's path token for the MCP connector). The Settings/onboarding toggle lets any user opt out. A future hardening step (rotating tokens / per-tunnel auth) is tracked separately.

## Consequences

- A fresh install is WAN-reachable out of the box; the ADR-0012 MCP connector is therefore reachable remotely, enabling "drive Synapse from anywhere."
- Verified live: on daemon restart the tunnel auto-opened at a public URL with no manual action; `/remote-access` reported `wan.active=true` immediately (status `warming` during cloudflared's edge propagation, per the existing warmup grace).
- The toggle UI (Settings + onboarding) ships as the follow-up increment.
