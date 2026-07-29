# Security policy

Synapse is a local-first developer engine (a FastAPI daemon + Electron/React app) that can launch processes,
run AI workers, and — optionally — expose itself over a public tunnel. This document describes its trust model
and how to report issues.

## Trust model

- **Local token.** The daemon (`127.0.0.1:7878`) is guarded by a per-install token in `data/auth-token`, sent
  as the `X-Synapse-Token` header. Every data read and every action requires it. **Treat the token like a
  password.** It is gitignored and must never be committed.
- **WAN exposure (Cloudtap / ADR-0026).** WAN auto-start opens a public `*.trycloudflare.com` tunnel to the
  daemon on boot **by default**. When the tunnel is up, the daemon is reachable from the internet, and the
  token is the whole trust boundary — anyone holding the token + URL can drive Synapse. Turn WAN off in
  **Settings → Network** (or `PATCH /api/v1/system/network {"wan_auto_start": false}`) if you don't want remote
  exposure.
- **API discovery (ADR-0027).** `/api/v1/openapi.json` / `/docs` are open (no token) — they expose only the API
  **contract** (endpoint shapes), never data or actions.
- **MCP connector (ADR-0012 / ADR-0027).** `/mcp/<token>` uses the token as a path secret. It is **read-only by
  default**; drive tools are gated behind `SYNAPSE_MCP_ALLOW_WRITES=1`. Enable writes only if you accept that a
  remote MCP client with the token can create/assign work.

## Handling secrets

- Never commit `data/auth-token`, `.env`, account credentials, or connector tokens. The pre-commit / autosave
  secret scan (see `AGENTS.md`) flags obvious leaks, but treat it as a backstop, not a guarantee.
- Rotate the local token (delete `data/auth-token`; the daemon regenerates it on next boot) if you suspect
  exposure, especially after sharing a WAN URL.

## Reporting a vulnerability

This is an early-development, owner-operated project. If you find a security issue, please **open a private
report** rather than a public issue: email the maintainer (see the repository owner on GitHub) with steps to
reproduce and impact. Please do not disclose publicly until it's addressed.
