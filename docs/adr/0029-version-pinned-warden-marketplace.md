# ADR-0029: Version-pinned Warden as an optional MCP marketplace tool

- **Status:** accepted — shipped in v0.1.90
- **Date:** 2026-07-31
- **Deciders:** Justin (owner), Codex
- **Related:** ADR-0017 (Marketplace + MCP servers), ADR-0027 (AI-drivable Synapse), Contracts #2, #4, #11, #15, #25

## Context

[Warden](https://github.com/chris-asmussen/warden) is Chris Asmussen's MIT-licensed MCP server that places
five compact tools (`search`, `call_tool`, `use_skill`, `admin`, and `route`) in front of many downstream
MCP servers and skill directories. It can reduce tool-schema context cost and help an AI find the right
capability, but it is not a replacement for Synapse's daemon, project memory, coordination, audit, UI, or
direct MCP integrations.

The upstream repository currently publishes package version `0.2.1`, but it has no GitHub release or tag.
Installing from a moving branch would make Synapse builds non-reproducible. Upstream Warden also fronts
stdio MCP servers; Synapse has both stdio and HTTP MCP servers.

## Decision

1. **Warden is optional and additive.** It appears in the existing MCP marketplace and, when enabled, is
   wired into AI workers beside every other enabled MCP server. Installing it never hides or disables
   GitHub, Playwright, Web Scraper, or any other direct Synapse resource.
2. **Pin immutable upstream source.** Synapse v0.1.90 installs Warden `0.2.1` from commit
   `29cb1355c33f19e8c9c6c6d48ba3136234eeaf2c`. The installer checks out that exact commit, verifies Git
   HEAD, installs into an isolated virtual environment, verifies the imported version and CLI, and only
   then registers the MCP server.
3. **Keep releases side by side.** Verified releases live under
   `data/vendor/mcp/warden/releases/<version>-<commit>/`. A future catalog pin installs separately and is
   activated only after verification. Older verified releases remain available to the rollback endpoint.
4. **Synapse owns the managed registry.** Enabled stdio MCP servers are mirrored automatically into
   Warden's registry; Warden itself is excluded to prevent recursion. Disabled servers are excluded. HTTP
   MCP servers remain directly available and are reported as direct-only because upstream Warden does not
   currently front them.
5. **Do not duplicate Synapse secrets into Warden JSON.** Managed registry entries omit `env`. Synapse
   supplies the required values to the Warden process from the existing redacted MCP credential store, and
   downstream children inherit that environment. A server with a conflicting environment-variable value
   is skipped from Warden and remains directly available. Warden-admin entries not owned by Synapse are
   preserved across synchronization.
6. **Make the lifecycle AI-discoverable and auditable.** Status, sync, pinned update, and rollback are REST
   endpoints, advertised by `GET /api/v1/ai/context`, documented in `docs/api-finds.md`, broadcast through
   `v1.mcp_server.updated`, and recorded in the audit log.

## Consequences

- An AI may use Warden's compact search/router when that saves context, or call any direct MCP tool normally.
- A fresh marketplace installation requires Git and Python 3.10+; packaged Synapse reports a clear retryable
  error if a suitable Python interpreter is not installed.
- Warden starts one instance of each configured stdio server while building its catalog and opens a fresh
  downstream connection for each proxied call. This is upstream behavior and should be benchmarked before
  adding pooling.
- Warden's `admin` and `call_tool` capabilities remain subject to the calling AI host's normal MCP tool
  approvals. Synapse does not claim that upstream mutations are covered by Synapse's own confirmation UI.
- A future Synapse-native skill marketplace (including Justin's enhanced internet-digger idea) is deliberately
  separate from this decision and can later feed Warden skill directories without changing this install model.
