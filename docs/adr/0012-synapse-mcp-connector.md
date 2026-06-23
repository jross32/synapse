# ADR-0012: Synapse as a claude.ai custom connector (MCP server)

- Status: Accepted (v1 = read-only)
- Date: 2026-06-22
- Deciders: Justin (owner), Claude

## Context

The owner wants to add Synapse to claude.ai (and Claude Desktop) as a **custom
connector** — the "Add custom connector" dialog that takes a *Remote MCP
server URL*. That lets Claude (the web/desktop app, not just the CLI) read and
act on Synapse over the Model Context Protocol, in addition to the existing
in-Sessions CLI access.

Constraints discovered:
- claude.ai remote connectors speak MCP over the **Streamable HTTP** transport
  (JSON-RPC 2.0 over a single HTTP endpoint), not stdio.
- The connector needs a **public HTTPS URL**. Synapse already ships
  **Cloudtap** (Cloudflare quick-tunnel) which can expose `127.0.0.1:7878`
  publicly — so no new infra.
- The connector dialog's only auth fields are *optional* OAuth client id/secret;
  there is no bearer-token field. So a personal connector authenticates either
  via OAuth (heavy) or a **secret embedded in the URL**.
- Exposing the daemon publicly is security-sensitive: the daemon can launch
  processes, create projects, run tool actions. We must not expose those by
  default.

No MCP server exists in Synapse today (only REST `/api/v1` + WS). The MCP
Python SDK is **not** a dependency; rather than add one (and the packaging
burden), we hand-roll a minimal, stateless, spec-compliant endpoint inside the
existing FastAPI app.

## Decision

Add an MCP endpoint to the daemon at **`/mcp/{token}`** (token-in-path auth),
hand-rolled, stateless, Streamable-HTTP-compatible.

### Transport (minimal, stateless)
- `POST /mcp/{token}` accepts a JSON-RPC 2.0 request (or notification) and
  returns a JSON-RPC response as `application/json`. Methods:
  `initialize`, `tools/list`, `tools/call`, `ping`. Notifications
  (`notifications/initialized`) return `202 Accepted` with no body.
- `GET /mcp/{token}` → `405` (no server-initiated SSE stream in v1; tools are
  request/response).
- No `Mcp-Session-Id` (stateless) — every request is self-contained.
- `initialize` returns `protocolVersion`, `capabilities: { tools: {} }`,
  `serverInfo: { name: "synapse", version }`.

### Auth (v1)
- The `{token}` path segment must equal the daemon's local auth token
  (`auth.local_token`). Mismatch/absent → `401`. The token IS the secret; the
  Cloudtap URL the user pastes is
  `https://<id>.trycloudflare.com/mcp/<token>`. Documented as "treat this URL
  like a password; it expires when you close the tunnel."
- OAuth is a **future upgrade** (v2) for a non-secret URL.

### Capability scope (v1 = READ-ONLY, safe by default)
Exposed tools wrap existing read paths — **no launch / create / run-action /
delete over the public connector by default**:
- `synapse_get_context` — the `/ai/context` digest (projects, tools, sessions,
  squads, role templates, recent audit).
- `synapse_list_projects` — registered projects.
- `synapse_get_project_records` — a project's ADRs / backlog / versions (ADR-0011).
- `synapse_list_tools` — installed tools + whether runnable.
- `synapse_list_quick_actions` — curated AI workflows.
- `synapse_list_agent_squads` — squads + work items.
- `synapse_list_sessions` — live PTY sessions.

### Write capability (opt-in, v1.1)
A single low-risk write — `synapse_add_project_idea` (capture a quick ADR idea,
ADR-0011) — and any other writes are gated behind an env flag
`SYNAPSE_MCP_ALLOW_WRITES=1` (off by default). Launch/exec stays CLI-only until
OAuth lands. Documented in `docs/security.md`.

### Discoverability
A "Connect to Claude" card in the Network/Phone-access area surfaces: open
Cloudtap → copy the `/mcp/<token>` URL → paste into claude.ai. (UI is a
follow-up; the endpoint + docs ship first.)

## Consequences
- Claude (web/desktop) can introspect Synapse read-only over the internet,
  via the user's own ephemeral Cloudtap tunnel, with the token as the secret.
- Zero new runtime dependency; the endpoint lives beside the REST API and
  reuses the daemon's in-process state.
- The dangerous surface (exec/create) is **not** exposed until the user opts in
  (env flag) and, ultimately, OAuth (v2).

## Alternatives considered
- *MCP Python SDK / FastMCP*: cleaner protocol handling but a heavy new
  dependency + packaging burden for a small, stable surface. Revisit if the
  hand-rolled endpoint proves limiting.
- *OAuth now*: correct but disproportionate for a personal, tunnel-gated
  connector. Deferred to v2.
- *Expose full read+write immediately*: rejected — public exec is the exact
  class of risk Contract #16 (refuse admin) and the security posture avoid.
