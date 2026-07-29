# ADR-0027: Make Synapse fully AI-drivable — API discovery, a driver guide, and a drive-capable MCP

- **Status:** accepted (rolling — shipped in increments)
- **Date:** 2026-07-29
- **Deciders:** Justin (owner), Claude
- **Related:** ADR-0012 (the read-only `/mcp/<token>` connector), ADR-0026 (WAN auto-start — makes the connector reachable remotely), ADR-0024 (coordination), the `GET /api/v1/ai/context` capability digest, AGENTS.md (the REST-first "everything is an endpoint" rule).

## Context

Justin wants to drive Synapse **from another AI chat** — another Claude Code session (same machine) or a remote AI over the WAN tunnel — to debug, build a backend, and evaluate an app for a team. Synapse already exposes **235 REST endpoints** (squads, work items, quick-actions/workflows, projects, review inbox, Quality OS eval, benchmarks, coordination), the web-scraper MCP is auto-wired into agents, and there's a `GET /api/v1/ai/context` digest. The gaps that made this hard:

1. **No API discovery.** `openapi_url`/`docs_url` were disabled, so an AI couldn't enumerate the endpoint surface or schemas — it had to be told every path by hand.
2. **No single "how to drive Synapse" guide.** The knowledge was scattered across AGENTS.md, ADRs, and code.
3. **The `/mcp/<token>` connector is read-only.** A remote AI (claude.ai connector, or any MCP client over the WAN tunnel) can introspect Synapse but can't *do* anything (create/launch a squad, run a workflow).

## Decision

Make Synapse drivable by an AI along two complementary paths, shipped in increments:

1. **API discovery ON (v0.1.72).** `openapi_url=/api/v1/openapi.json`, `docs_url=/api/v1/docs`, `redoc_url=/api/v1/redoc`. The schema is the API **contract** only — every data read / action still requires `X-Synapse-Token`, so exposing the shape (even over the tunnel) carries no data/action risk. This is the fastest, safest unblock for a same-machine Claude Code driving Synapse over `localhost:7878`.
2. **A driver guide** (`docs/DRIVE-SYNAPSE-FROM-AI.md`) — the exact token-auth + the canonical flows (create a squad → add work items → launch → monitor/kill; run a quick-action/workflow; drive the web-scraper; register + evaluate a project via Quality OS/benchmarks; coordinate via the lanes API), with copy-paste examples. Linked from AGENTS.md + README.
3. **A drive-capable MCP (increment).** Extend the `/mcp/<token>` connector beyond read-only with a bounded set of high-value **drive** tools (create squad, add + launch work item, run quick-action, capture), behind the existing `SYNAPSE_MCP_ALLOW_WRITES` gate, so a remote AI can drive Synapse over the WAN tunnel — the "public WAN MCP" Justin asked for.

## Security posture

- REST + the MCP connector are guarded by the daemon's `X-Synapse-Token` (the connector's path token). WAN auto-start (ADR-0026) makes them reachable publicly, so the token is the trust boundary.
- API **discovery** exposes only the contract, not data or actions — safe to leave open.
- Enabling **writes** on the WAN-exposed MCP is a real escalation (a caller with the token can run AI workers). It stays behind an explicit flag, is audited, and the guide documents the risk. A future hardening step (rotating/scoped tokens per remote client) is tracked.

## Consequences

- A same-machine Claude Code can enumerate the API (`/api/v1/openapi.json`) + follow the guide to drive squads/workflows/scraper/eval today.
- Over the (now auto-on) WAN tunnel, a remote AI can introspect now and, once the drive tools land, fully drive Synapse.
- Each increment ships verified (dogfooded against the live API) + docs-synced.
