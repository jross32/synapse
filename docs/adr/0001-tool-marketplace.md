# ADR-0001: Tool marketplace

- **Status:** proposed
- **Date:** 2026-05-20
- **Deciders:** Justin (owner), Claude (drafter)
- **Related contracts:** #8 (Pydantic-as-schema), #15 (no third-party network without opt-in), #25 (secrets), Plugin contract in AGENTS.md

## Context

Synapse v0.1.9 shipped a real plugin system: a tool is a folder under `tools/` with a `manifest.json`, and behaviour comes from curated handlers compiled into the daemon. That's the right *internal* model — drop-in manifests can never run untrusted code, because the daemon doesn't import from tool folders at all.

But it gives no story for **distribution**. Today the only way to install a tool is to drop a manifest folder into the repo and (for behaviour) ship a handler in the daemon binary. We want:

1. **Third-party authors** to be able to publish a tool that other users can install — like VS Code extensions, Raycast scripts, Linear apps.
2. **The WhatIf Company** to publish first-party tools (Cloudtap, future ones) through the same channel. They're "auto-installed" today because they ship in-repo; long-term they should flow through the marketplace just like third-party tools.
3. **Users** to **discover and install** tools from the UI without dropping folders into `tools/`. Probably "Browse tools → install" + "Add from URL".
4. **Hot install/uninstall** — install or remove without restarting the daemon, ideally.

The hard constraint: **never run untrusted code as a side effect of "install"**. The hybrid model in v0.1.9 only ran built-in handlers; the marketplace has to preserve that property.

## Decision

A two-tier tool model:

### Tier 1: Declarative tools (open, sandboxed)

A *declarative* tool's `manifest.json` describes everything the daemon needs to run it — no Python handler required. The daemon executes such tools through a small library of vetted *primitives* that the manifest invokes by name. Initial primitives:

- `process.spawn` — run a shell command with a templated argv. (Backs the future Terminal runner.)
- `url.open` — open a URL in the user's browser.
- `http.request` — issue an HTTP request, render the response.
- `text.transform` — pure-string transformations (regex extract, format).

Anyone can write a declarative tool. The marketplace can auto-install them. The trust model: the user sees exactly what the tool will do (the manifest is human-readable), and the daemon enforces it (the primitive set is the only attack surface).

### Tier 2: Handler tools (curated, audited)

A *handler* tool needs Python that the daemon imports. The same curated table from v0.1.9 (`_BUILTIN_HANDLER_FACTORIES` in `tools_registry.py`) governs which handler refs are bindable. The marketplace **never installs a handler tool implicitly** — a handler tool's manifest can sit in `tools/<id>/manifest.json` but its `actions` stay inert (`runnable: false`) until a daemon build ships that bound handler.

This keeps Cloudtap-class tools (process spawn, output parsing) honest — they ship in The WhatIf Company's signed daemon builds, not through arbitrary upload.

### Registry

A central JSON index at a stable URL — initially `https://synapse.whatif.dev/tools/index.json` — describes available tools:

```json
{
  "version": 1,
  "tools": [
    {
      "id": "cloudtap",
      "name": "Cloudtap",
      "publisher": "The WhatIf Company",
      "tier": "handler",
      "manifest_url": "https://synapse.whatif.dev/tools/cloudtap/1.0.0/manifest.json",
      "version": "1.0.0",
      "verified": true,
      "homepage": "...",
      "description": "..."
    },
    { "id": "open-in-vscode", "tier": "declarative", ... }
  ]
}
```

Anyone can submit a tool by opening a PR against the index repo. **Verified** is a flag set only on tools we've reviewed.

### Install flow (UI)

A new **Tools → Browse** page fetches the registry, shows the list (with verified / tier badges), and offers an Install button:

- **Declarative** → fetches the manifest, schema-validates it, writes it to `tools/<id>/manifest.json`, and triggers a hot reload of `ToolRegistry`. Live in seconds, no daemon restart.
- **Handler** → if the daemon already has a handler bound for that id (built-in), Install just writes the manifest. If not, the UI shows "This tool requires a Synapse build that ships its handler — coming in v0.X.Y."

An **Install from URL** field lets a user paste a `manifest.json` URL directly (for unlisted / private tools).

### Update flow

The browser tracks installed versions vs. registry versions, surfaces "Update" buttons. Auto-update is opt-in per tool. Updates are diffed against the previously-installed manifest and shown to the user before applying.

### Uninstall flow

Removes `tools/<id>/`, triggers a hot reload. Built-in tools (cloudtap shipped in-repo) are not uninstallable from the UI — they show a "Built-in" badge instead.

### Hot reload

`ToolRegistry` already loads once at boot. Add a watcher (`watchdog`, already a daemon dependency) on `tools/` so adding/removing/changing a manifest triggers a registry reload + a `v1.tool.reloaded` WS event. The Tools page subscribes and refreshes its cards.

### Authoring story

A "Create a tool" link in **Tools → Browse** opens a small scaffolder: pick a primitive, fill in fields/actions, save to `tools/<id>/manifest.json`. That's the "easy for a user to deploy a new tool" piece — no folders, no JSON by hand.

## Consequences

### Positive

- **One distribution channel** for first-party and third-party alike — same UI, same registry, same install flow.
- **Trust model stays explicit:** declarative tools = open (sandboxed primitives); handler tools = curated by us. The user sees the tier on every install.
- **Hot reload** removes the existing "restart the daemon to pick up a manifest" papercut.
- **Cloudtap doesn't need to change** to fit — it ships handler-tier as today; once it's in the registry it can also be auto-installed by users on older Synapse builds (as a declarative no-op manifest with a "needs Synapse ≥ X.Y.Z" hint).

### Negative / trade-offs

- **Primitive library is now a real surface.** Each new primitive (`process.spawn`, `http.request`, …) needs the same care as a daemon endpoint — audited, escaped, scoped. Starts small, grows deliberately.
- **Registry is a single point of failure / trust.** Mitigated by allowing **Install from URL** and by publishing the index on GitHub for transparency.
- **Versioning and updates introduce state** the daemon previously didn't have. Installed-version tracking lives in a new SQLite column on a `tool_installs` table (Migration 006+).
- **More UI surface** (Browse, Install, Update flows) → more polish work before v1.

### Follow-ups

Code changes required (in rough version order):

1. **`v0.1.20`** — hot manifest reload (`watchdog` on `tools/`, `v1.tool.reloaded` event, registry refresh). Lays the groundwork.
2. **`v0.1.21`** — declarative primitives: implement `process.spawn` and `url.open`; let manifests invoke them. Migrate the "Terminal runner" and "Open-in-VS Code" tools onto primitives so we eat our own dogfood.
3. **`v0.1.22`** — registry fetch + Tools → Browse page. Read-only at first (no Install button), just to validate the index format.
4. **`v0.1.23`** — Install / Uninstall for declarative tools, with manifest schema validation + diff confirmation.
5. **`v0.1.24`** — Install from URL.
6. **`v0.1.25+`** — handler-tier flow + verified-publisher badges + scaffolder.

Docs to update when each lands:

- `AGENTS.md` plugin contract — extend with the two-tier model, primitives table, and install rules.
- `README.md` — add a "Install tools from the marketplace" line under v0.1 features.
- `PROGRESS.md` — version table + What's done sections.

Migration plan (if breaks contract):

- No contract breaks. Plugin contract in AGENTS.md is *extended*, not replaced. The existing v0.1.9 curated-handler tools remain valid and continue to work.

## Open questions

- **Where does the registry live?** `synapse.whatif.dev` or a GitHub-hosted JSON in a `synapse-tools` repo? GitHub gives us free PR-based moderation; a domain we control gives us a stable URL and CDN.
- **Code signing for handler tools.** Once handlers ship outside the in-repo build (an installer add-on?), we need Authenticode / similar. Defer until handler-tier flow is on the table.
- **Sandboxing primitive execution.** `process.spawn` is the dangerous one — it can do anything the user can. Mitigations: a per-tool argv allowlist in the manifest; user confirmation on first run; no shell expansion unless explicitly opted in. Worth its own ADR when it lands.
