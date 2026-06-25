# ADR-0017: Marketplace hub + MCP-server pillar (+ publishing)

- Status: Accepted (MW1 hub + MW2 MCP shipping; publishing = MW6, follows)
- Date: 2026-06-24
- Deciders: Justin (owner), Claude

## Context

The owner wants Synapse to feel like an app store for the AI workforce — install
tools, models, **MCP servers**, AI workers, and ready-made squads from one
visual place — and to download MCP servers their AI uses automatically. Today
these are scattered (tool marketplace in the Tools tab, models in the Assistant
tab) and there is **no way to consume external MCP servers** (`mcp_connector.py`
only *exposes* Synapse to claude.ai).

## Decision

### MW1 — Marketplace hub
A new **"Marketplace" nav tab** (`pages/Marketplace.tsx`) with section pills:
Tools, Models, MCP Servers, Workers, Squad Presets. Tools + Models reuse the
existing `MarketplaceBrowser` / `ModelBrowser` (additive — the Tools tab +
Assistant's Models view are untouched); the rest fill in over MW2–MW4. One
visual home, each card showing installed/running status.

### MW2 — MCP-server pillar (the new capability)
Two transports, because they behave differently:
- **stdio** (most servers): the AI launches the command on demand. Synapse just
  stores the command and reports a static "Ready" state.
- **http** (e.g. the owner's web-scraper): a standalone server that must be
  *running*. Synapse health-checks it (is the port listening?), can **launch**
  it (if a launch command is set), **autoruns** it on boot if enabled, and shows
  honest states (Connected / Not running / Starting / Trouble connecting).

- `mcp_servers.py` — Pydantic models + CRUD + `McpServerManager` (spawns +
  health-checks http servers, mirroring `ollama_client.start_server` +
  `process_manager`) + `build_mcp_config()`.
- migration `014_mcp_servers.sql`; curated `docs/mcp-servers-sample.json`
  (filesystem, memory, sequential-thinking, github, playwright, fetch, a custom
  http template).
- `routes_mcp_servers.py` — registry / install (catalog or custom) / list+status
  / start / stop / patch (enable + autorun) / delete.
- **Wire into AI (the headline):** at `routes_agent_squads.launch_work_item`,
  a Claude worker's argv gains `--mcp-config <generated file>` built from the
  user's **enabled** servers. `--mcp-config` *merges*, so a project's own
  `.mcp.json` is never clobbered, and the file lives in the data dir.

### MW6 — Publishing (follows)
Package the owner's own MCP server / tool / role / preset into a shareable
manifest + a submit path. The public index is static JSON, so "publish" =
export a valid entry + a clear path to the community index.

## Consequences
- One discoverable, visual home for everything installable.
- The owner's AI workers automatically gain the MCP servers the owner enabled —
  including their own running web-scraper — with honest running-status + a launch
  button when a server isn't up.
- stdio vs http is modelled explicitly, so "is it running?" only applies where it
  makes sense.

## Alternatives considered
- *Write a project `.mcp.json`* — rejected: would clobber the user's own config.
  `--mcp-config` merges additively and stays in Synapse's data dir.
- *Model MCP servers as tool manifests* — the tool registry is for one-shot
  primitives; long-running, health-checked servers need their own state + a
  manager, so they get a dedicated module.
