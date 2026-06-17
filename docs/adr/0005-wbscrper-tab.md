# ADR-0005 — wbscrper dedicated tab + AI access

Date: 2026-06-16
Status: Proposed
Supersedes: —
Related: ADR-0001 (tool marketplace), ADR-0002 (AI workbench),
         ADR-0003 (workbench expansion)

## Context

The user runs `wbscrper` (a separate Node + Playwright project) as a
managed Synapse project. wbscrper ships an MCP server with **93 tools
and 26 prompts** across nine categories (scraping, browser sessions,
analysis, security, codegen, scheduling, monitoring, AI, meta). Today
those tools are reachable from a Claude session via MCP — but only if
the user has the MCP client configured outside Synapse.

The user asked for two things on top of that:

1. **A dedicated UI surface inside Synapse** so common wbscrper actions
   (scrape URL, list saves, browser session, scheduled scrape, security
   audit) are a click away rather than a CLI invocation. The intent is
   the wbscrper-equivalent of the Cloudtap tile: every project tile
   shows a tile, every list of saves a card.
2. **AI access** so a Claude / Codex session running in Synapse's
   Sessions tab can call those same actions through `/api/v1/ai/context`
   + a small bridge, without having to set up an out-of-band MCP client.

This ADR scopes both ends, calls out what we will NOT build, and
sequences the work so each half is verifiable on its own.

## Decision

Three phases. Each one is shippable alone; the user can sit on it
between phases without breaking the previous one.

### Phase A — wbscrper detection + dedicated tab (v0.1.35)

A new top-level **Web Scraper** tab in the sidebar that appears **only
when** Synapse detects a running wbscrper instance. Detection rule:
the user has a project with `kind='mcp-server'` whose `expected_port`
is reachable AND `GET /api/mcp-meta` returns the wbscrper schema
fingerprint (`server.name === 'web-scraper'`). No wbscrper -> no
sidebar item, no clutter.

**Tab contents (Phase A only):**
- **Header**: `Connected to wbscrper at localhost:12345 · 93 tools · 26 prompts`.
- **Quick actions row** — 6 curated buttons mirroring the most-used MCP
  tools from `mcp-catalog.js`:
  - **Scrape a URL** — single-URL scrape with default options.
  - **Batch scrape** — paste URLs, run them.
  - **Saves** — list, open, delete (uses `list_saves` / `delete_save`).
  - **Schedules** — list, pause, delete.
  - **Active scrapes** — live status, pause/resume, kill.
  - **Search saved text** — `search_scrape_text` across all saves.
- **Saves panel** — a table of recent saves with click-to-view metadata
  (URL, captured-at, size, screenshot thumbnail).
- **Schedules panel** — cron schedules with next-fire time.

**What is NOT in Phase A:**
- All 93 tools (we surface ~6; the long tail stays MCP-only).
- Tool composition / pipelines.
- Authoring new prompts or schedules from the UI (delegate to the
  existing wbscrper web UI at `:12345`).

**How Synapse talks to wbscrper:**
- Through wbscrper's existing REST endpoints (port 12345) — same
  surface its MCP server uses internally. The daemon proxies to keep
  the token-guarded contract intact:
  ```
  POST /api/v1/integrations/wbscrper/{action}
       (token-guarded)  ->  http://localhost:12345/api/...
                            (no extra auth; loopback only)
  ```
- The proxy is the only Synapse-side wbscrper code; UI handlers call
  the proxy, not 127.0.0.1:12345 directly.

### Phase B — AI access via `/api/v1/ai/context` + tool bridge (v0.1.36)

When wbscrper is detected, `/api/v1/ai/context` gains a new
`integrations.wbscrper` block:

```jsonc
"integrations": {
  "wbscrper": {
    "base_url": "http://localhost:7878/api/v1/integrations/wbscrper",
    "tools_count": 93,
    "prompts_count": 26,
    "fast_path_actions": [
      "scrape_url", "list_saves", "search_scrape_text", "...",
    ],
    "docs_url": "http://localhost:12345/docs"
  }
}
```

So a Claude session inside Synapse Sessions reading `/ai/context` knows:
- The integration is there.
- The base URL to call.
- Which 6 actions are wired through Synapse's token-guarded proxy.
- Where the full 93-tool catalogue lives (its own docs URL).

The AI uses the same token (`$SYNAPSE_TOKEN`) it already has — no new
auth path. It can `curl $SYNAPSE_API/integrations/wbscrper/scrape_url
-d '{"url": "..."}'` from inside its PTY.

This is **not** a re-implementation of the MCP protocol. The MCP path
stays first-class for users who configure Claude Code's MCP block. The
proxy is a convenience for Synapse-internal sessions that want one
auth surface.

### Phase C — Quick-action templates referring to wbscrper (v0.1.37)

Two new entries in `templates/quick-actions/`:

- **`scrape-and-summarise.json`** — pre-loads the prompt *"Scrape the URL
  the user supplies, extract entities, then summarise the page."* The
  session has `$SYNAPSE_TOKEN` and the wbscrper integration metadata in
  context so the AI can call the right action.
- **`audit-site-security.json`** — *"Run the wbscrper security audit
  flow on this URL: TLS, security headers, robots, JWT decoding..."*

Same Phase F infrastructure; only the templates ship.

## Consequences

### Positive
- The wbscrper-Synapse boundary stays explicit: one proxy module, one
  detection rule, one ai-context block. Adding a second integration
  (Ollama, a database tool, anything) follows the same template.
- The user gets the buttons they asked for **and** the AI gets a
  first-class way to call them, without re-implementing MCP.
- Sidebar visibility is event-driven (detected or not), so a user
  without wbscrper sees zero clutter.

### Negative / honest trade-offs
- The tab is **wbscrper-specific** by design. A future Synapse fork or
  a new MCP server won't get a tab for free; the next integration is
  another ADR. We're not building a generic "render any MCP server as
  a tab" framework — that lives on the long list of *too generic to
  build well*.
- We surface 6 of 93 tools. Power users will still want the wbscrper
  web UI for the long tail; the docs link from the header takes them
  there.
- Cross-origin: wbscrper at `:12345` has its own CORS; Synapse's proxy
  side-steps that by being same-origin to the renderer (port 7878). If
  the user runs wbscrper on a non-loopback host, the proxy will need
  to be re-scoped — out of Phase A.

## Detailed design (Phase A, locked at acceptance)

### Detection (`daemon/synapse_daemon/integrations_wbscrper.py`)

```python
async def detect_wbscrper(storage: Storage) -> WbscrperState | None:
    """Returns a non-None state when an MCP-kind project answers the
    wbscrper fingerprint on its expected_port within ~250 ms."""
```

- Caches the answer for 30 s so the sidebar doesn't poll on every render.
- Fingerprint: `GET /api/mcp-meta` returns `{"server": {"name":
  "web-scraper"}}` AND `server_info` returns a known `tools_count`.

### Proxy route (`routes_integrations.py`)

```
POST /api/v1/integrations/wbscrper/scrape_url
POST /api/v1/integrations/wbscrper/batch_scrape
GET  /api/v1/integrations/wbscrper/saves
DELETE /api/v1/integrations/wbscrper/saves/{id}      [D]
GET  /api/v1/integrations/wbscrper/schedules
GET  /api/v1/integrations/wbscrper/active
POST /api/v1/integrations/wbscrper/search
```

Each forwards to the wbscrper REST endpoint of the same shape.
Token-guarded; the destructive `[D]` actions get the same confirm-before
treatment as `delete_project`.

### AI-context integration (Phase B step)

A `_detect_integrations(storage)` helper in `routes_ai.py` returns the
`integrations.wbscrper` block when detection passes. Inert in the
no-wbscrper case (does not appear in the JSON at all -- keeps Context
small).

### Renderer

- `lib/wbscrper-client.ts` -- thin functions over the proxy.
- `pages/WebScraper.tsx` -- the tab; mirrors the Apps page layout
  conventions.
- `nav.ts` -- adds the conditional sidebar item; hidden when
  `integrations.wbscrper` is falsy in the daemon-context snapshot.

## Status

Proposed. Implementation does NOT start until the user approves Phase
A. Phases B and C have their own explicit gates -- each is enough work
that the user should re-confirm.
