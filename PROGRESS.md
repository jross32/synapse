# Progress — Synapse

**Always read this file first** if you're an AI coding session resuming work. It's the single source of truth for "where are we right now."

---

## Current version

`0.1.10`

## Current milestone

**Milestone F in progress — the real UI.** Shell (v0.1.8) + auto-discovery (v0.1.8.5) + audit hardening (v0.1.8.6) + plugin system & Cloudtap (v0.1.9) + multi-tunnel Cloudtap (v0.1.9.5) + Home slideshow (v0.1.10) done. Tools are manifest plugins; Cloudtap holds many tunnels at once. Home now leads with a featured-projects slideshow. 210 tests pass. Next: v0.1.10.5 (snapshot/restore) → finishes Milestone F.

| Version | Phase | Status |
|---|---|---|
| `0.1.0-alpha.1` | Milestone A — scaffolding | ✅ done |
| `0.1.0.5` | Design contracts round 1 (docs) | ✅ done |
| `0.1.1` | Round 1 contract scaffolding (code) | ✅ done |
| `0.1.1.5` | Design contracts round 2 (docs) | ✅ done |
| `0.1.2` | Round 2 contract scaffolding (code) | ✅ done |
| `0.1.2.5` | README + docs sync; commit-rule hardening | ✅ done |
| `0.1.3` | Milestone B — daemon skeleton (FastAPI + WS + migrations + reconciler) | ✅ done |
| `0.1.4` | Milestone C — Electron skeleton (window, tray, daemon spawn, WS connect) | ✅ done |
| `0.1.5` | Milestone D — Project registry + launcher (CRUD + tiles + click-to-launch) | ✅ done |
| `0.1.5.5` | Hotfix: ASCII-only `.ps1` scripts + daemon log strings (PS 5.1 cp1252 parse fix) | ✅ done |
| `0.1.6` | Clickable `synapse.cmd` launcher + desktop shortcut + Electron CDP inspector + CSP/orphan fixes | ✅ done |
| `0.1.7` | Milestone E — Live process monitor (watcher + heartbeat + auto-restart + logs + "+ Add Project") | ✅ done |
| `0.1.8` | Milestone F (shell) — shadcn/ui sidebar + 5 pages + daemon context + log viewer | ✅ done |
| `0.1.8.1` | Hotfix: Vite IPv4 bind so synapse.cmd's health poll matches | ✅ done |
| `0.1.8.5` | Project auto-discovery (multi-stack detector) + migration 003 (tags/pinned) + groups | ✅ done |
| `0.1.8.6` | UI/UX audit fixes — WS replay-envelope bug, responsive overflow, version/path polish | ✅ done |
| `0.1.9` | Milestone F — tool plugin system (manifest + curated handlers) + Cloudtap | ✅ done |
| `0.1.9.5` | Milestone F — multi-instance tool model + multi-tunnel Cloudtap + app labeling | ✅ done |
| `0.1.10` | Milestone F — Home featured slideshow + page restructure | ✅ done |
| `0.1.10.5` | Milestone F — snapshot / restore (Contract #28) wired to Settings | ⚪ next |

## What's done

### v0.1.0-alpha.1 — Milestone A scaffolding
- Folder structure, all config files, CI workflow, docs, placeholder code, first plugin manifest

### v0.1.0.5 — Round 1 contracts (docs)
- All 16 design contracts written into `AGENTS.md`

### v0.1.1 — Round 1 contracts (scaffolding)
- Daemon: `api_versions.py`, `errors.py`, `models.py` (`BaseEntity` + status enums), `migrations/001_initial.sql`, `audit.py`, `process_log.py`, `security.py`
- Renderer: `error-types.ts`, `api-client.ts`, `ws-client.ts` (with reconnect + replay), `theme-tokens.css`, `generated-types.ts`
- Tests: 6 new test files covering Contracts #2, #3, #4, #7, #8, #9, #10, #11, #16
- Docs: `api-changes.md`, `security.md`, `adr/README.md`
- `version-bump.ps1` now supports `-Kind design` + updates `__init__.py`

### v0.1.1.5 — Round 2 contracts (docs)
- AGENTS.md expanded from 16 → 28 contracts (#17 health, #18 restart, #19 resources, #20 deps, #21 search, #22 notifications, #23 a11y, #24 utc/local, #25 secrets, #26 hot reload, #27 CLI, #28 snapshot)

### v0.1.2 — Round 2 contracts (scaffolding)
- Daemon modules: `time_utils.py`, `health.py`, `restart_policy.py`, `resources.py`, `dependencies.py`, `search.py`, `notifications.py`, `secrets.py` (DPAPI + Fernet), `manifest_watcher.py` (watchdog), `cli.py`, `snapshot.py`
- Migration `002_round2_schema.sql`: project_dependencies, search_index, notification_preferences, project_secrets + extended projects columns
- Renderer: `format-time.ts`, `search-client.ts`, full Round 2 types in `generated-types.ts`
- 10 new test files; HealthResponse now reports contracts 1–28
- pyproject: added `watchdog` + `cryptography` deps, registered `synapse` console script
- **85 tests passing, 1 platform-conditional skip**

### v0.1.3 — Milestone B (daemon skeleton)
- `storage.py` (single SQLite connection, WAL + FK, autocommit, `transaction()` ctx mgr, `migrate()`)
- `migrations/_runner.py` (atomic per-migration apply, `BEGIN IMMEDIATE` + `COMMIT`, idempotent)
- `ws.py` (`EventBus` with monotonic IDs + 1 000-event ring buffer + async-locked subscribe/publish; `WsHub` with resume + ping + replay-window-exceeded protocol)
- `orphan_reconciler.py` (`reconcile()` classifies managed processes into `re-attached` / `pid-recycled` / `daemon-restart` via psutil)
- `app.py` (FastAPI factory, CORS, error envelope handler, `/api/v1/health`, `WS /api/v1/ws`, lifespan that runs reconciler + publishes boot events)
- `__main__.py` rewritten (argparse, refuse-admin, migrate, build app, uvicorn boot)
- `scripts/dev.ps1` actually orchestrates daemon + Vite + Electron with health polling
- 32 new tests across `test_storage.py`, `test_ws.py`, `test_orphan_reconciler.py`, `test_app.py` — total 117 passing
- **Smoke-tested:** real boot, `curl /api/v1/health` returns contract shape, WS replay handshake delivers `v1.daemon.started`, ping/pong works

### v0.1.4 — Milestone C (Electron skeleton)
- `scripts/gen-icon.py` (pure-stdlib PNG generator, no Pillow) → checked-in `synapse.png` (32×32) + `synapse-256.png` (256×256)
- `electron/main.ts` rewritten — single-instance lock, spawns daemon child, polls `/api/v1/health` for up to 15 s, opens window only when daemon is ready, tray with Show / health-page / Quit, hide-to-tray on window close, kills daemon on `will-quit`
- `electron/preload.ts` exposes typed `window.synapse.*` (version, daemonBase, daemonWsBase, platform)
- `renderer/App.tsx` rewritten — calls `setDaemonBase`, fetches `/api/v1/health`, renders daemon + WS cards with conn-state badge using `--synapse-status-*` tokens, shows last 5 events via `formatLocal()` (Contract #24)
- Compiles cleanly (`npm run build:electron` → `dist-electron/main.js` + `preload.js`)
- All 117 daemon tests still pass

### v0.1.5 — Milestone D (Project registry + launcher)
- daemon `projects.py` (Project + ProjectUpdate Pydantic, kebab-case validator, full CRUD with monotonic timestamps, secret redaction)
- daemon `process_manager.py` (detached spawn, log capture, terminate→kill, audit + WS events for every transition)
- daemon `seed.py` (idempotent first-run wbscrper insert, preserves user edits)
- daemon `routes_projects.py` (GET/POST/PATCH/DELETE /api/v1/projects + launch/stop)
- daemon `app.py` mounts the projects router; `__main__.py` calls seed before lifespan + instantiates the PM
- renderer `projects-client.ts` (typed wrappers per endpoint); `generated-types.ts` gains Project + ProjectUpdate
- renderer components: `StatusBadge` (pulse animation during transitions, aria-live), `ProjectTile` (live status + cmd/port metadata + Launch/Stop/Edit/Delete + error banner), `ProjectEditDialog` (modal form, focus trap, Esc to close)
- renderer page `Apps.tsx` (tile grid, WS-driven refresh, empty state, confirm-before-destructive delete)
- renderer `styles.css` keyframes for badge pulse
- 32 new tests across `test_projects.py`, `test_process_manager.py`, `test_seed.py`, `test_routes_projects.py` — total 149 passing
- **Smoke path:** `.\scripts\dev.ps1` → daemon seeds wbscrper → window shows wbscrper tile → click Launch → npm start runs → click Stop → tile returns to stopped

### v0.1.6 — Clickable launcher + Electron inspection
- `synapse.cmd` (cmd-only launcher, no PowerShell) + `install-shortcut.cmd` (Desktop `.lnk` via cscript)
- `scripts/inspect-electron.js` — generic Electron CDP inspector (screenshot/console/snapshot/html/click/eval/title)
- `electron/main.ts` `--inspect-renderer` flag exposes a CDP port
- `playwright` devDependency added
- `gen-icon.py` now emits multi-res `synapse.ico` + `renderer/public/favicon.ico`
- AGENTS.md Rule #6: E2E pass required on every code version bump
- Fixes: CSP/preload host mismatch (Electron "Failed to fetch"), orphan process tree on Stop, React shorthand-style warning, favicon 404, Base URL fallback

### v0.1.7 — Milestone E (live process monitor)
- daemon: background watcher (crash detection), ~2s heartbeat broadcaster (CPU% + RSS, tree-summed), auto-restart per `RestartPolicy`, `GET /projects/{id}/logs`
- renderer: `ProcessMonitor` live table, `ProjectFormDialog` (create + edit), "+ Add Project" button, per-tile CPU/RAM
- fixes: `DETACHED_PROCESS` killed all log capture (now `CREATE_NO_WINDOW`); `update()` corrupted nested Pydantic models (now re-validates)

### v0.1.8 — Milestone F (shell)
- shadcn/ui + Tailwind wired (`components.json`, `cn()`, HSL colour vars, `tailwindcss-animate`)
- hand-vendored UI kit in `renderer/components/ui/` (button, card, badge, input, separator, modal)
- `Sidebar` icon rail + `nav.ts` + `DaemonProvider` context (one shared WS)
- 5 pages: Home (HUD), Apps, Tools (placeholder), Processes, Settings
- `LogViewer` (Contract #3) + tile quick-actions (Open folder / Open in browser via new `synapse:open-external` IPC)
- every renderer component rebuilt on shadcn/Tailwind
- 158 tests still passing; E2E verified browser + Electron

### v0.1.8.5 — Project auto-discovery + groups/pinning
- `daemon/synapse_daemon/discovery.py` — multi-stack project detector (Node / Python / Rust / Go / .NET / Java / Ruby / PHP / Docker / static / Makefile / git), confidence + alternative candidates
- `scan_directory(root)` — walks a workspace root, skips junk (node_modules, venv, hidden, system dirs)
- `migration 003_discovery_groups.sql` — `discovered`, `pinned`, `group_name`, `tags_json` columns on `projects`
- REST: `GET /api/v1/discovery/scan`, `POST /api/v1/discovery/import`
- UI: `DiscoveryDialog` "Scan for projects" flow on Apps; tile pinning + groups
- 183 tests passing

### v0.1.8.6 — UI/UX audit fixes
- Full audit: Playwright browser walk + Electron CDP inspector + os-bridge native capture, every page × every viewport
- **Fixed** WS replay-envelope bug — `ws-client.ts` `parse()` dropped the daemon's `{type:"replay",events:[...]}` frame, so events before connect / during reconnect never reached the UI (Recent activity stayed empty). Now unwraps the envelope.
- **Fixed** responsive overflow below ~700px — `Apps.tsx` tile grid `minmax(320px,1fr)` → `minmax(min(100%,320px),1fr)`
- Polish: responsive shell padding, `break-words` paths, daemon-derived UI version, human-readable connection label
- 183 tests passing; typecheck green

### v0.1.9 — Tool plugin system + Cloudtap
- **Plugin model (hybrid):** a tool = a folder under `tools/` with a `manifest.json` (pure data). The daemon NEVER imports code from a tool folder — actions run via *curated built-in handlers* compiled into the daemon. New built-in tool = drop a manifest folder + one entry in `_BUILTIN_HANDLER_FACTORIES`.
- Daemon: `tools_registry.py` (`ToolRegistry` — scan/validate/bind), `tools/` package (`ToolHandler` base + `cloudtap.py`), `routes_tools.py` (list / get / run-action, all audited), `Tool*` Pydantic models, `--tools-dir` flag
- Cloudtap: spawns `cloudflared` quick tunnel, parses the `*.trycloudflare.com` URL, one tunnel at a time, killed on daemon shutdown; honest error states (bad port / not installed / no-URL timeout / early exit / dropped)
- Renderer: `tools-client.ts`, `ToolCard.tsx` (one generic manifest-driven card — no tool-specific UI), `Tools.tsx` page; `Tool*` types
- Audit fixes: state-aware action buttons (manifest `available_in`); Tools page refetches on `v1.tool.*` WS events
- 206 tests passing (+23); typecheck green; E2E verified a real tunnel served traffic over the public internet

### v0.1.9.5 — Multi-tunnel Cloudtap + multi-instance tool model
- **Generic multi-instance model:** `ToolState.items` (list of `ToolItem`) + `ToolAction.scope` (`tool` vs `item`). Any tool can now own multiple live instances, each with its own row + per-instance action buttons. Reusable by future tools (terminal sessions, etc.).
- Cloudtap rewritten around a `dict` of `_Tunnel`s — open many tunnels, `close` (item-scoped) terminates exactly one and leaves the rest running. No more misleading global "Close tunnel" button.
- Cloudtap auto-labels each tunnel with the registered project whose `expected_port` matches (handler gets `storage`); falls back to `localhost:<port>`.
- Renderer: `ToolCard` renders an "Active (N)" instance list; `runToolAction` takes an optional `itemId`.
- 210 tests passing (+4); typecheck green; E2E opened two real tunnels at once, closed one, the other kept serving.

### v0.1.10 — Home featured slideshow
- `components/FeaturedSlideshow.tsx` — Microsoft-Store-style hero: rotates featured projects (pinned first, then most-recently-active), auto-advances + pauses on hover, prev/next arrows + dot nav, **Launch straight from the hero**.
- `pages/Home.tsx` restructured — hero, heartbeat HUD, then "Recent activity" beside "Jump in". Fixes the top-heavy empty space the audits flagged. Welcome empty state when no projects.
- 210 tests pass; typecheck green; E2E verified in browser + Electron, no overflow at 400px.

## What's next (immediate)

**v0.1.10.5 — snapshot / restore (Contract #28).** Finishes Milestone F:
- REST endpoints to export the registry (projects + tools + settings) as one JSON file and restore it (`snapshot.py` is already scaffolded)
- Settings page UI to download a snapshot + upload one to restore
- Then Milestone G is already done (Cloudtap shipped v0.1.9) → Milestone H (mobile Web UI)

## Known issues / broken state

None — toolchain is green:
- `npm install` ✅
- `pip install -e ".[dev]"` ✅
- `npm run typecheck` ✅
- `pytest` (all suites) ✅

## How to verify the current state

```powershell
cd C:\Users\justi\synapse
npm install
pip install -e ./daemon
npm run typecheck      # should exit 0
pytest daemon/tests    # should pass 1 smoke test
```

## Architectural reminders (don't forget)

- **Daemon owns state.** Desktop + mobile UIs are dumb clients.
- **Daemon port = 7878.** Never 12345 (that's wbscrper's REST).
- **New tools = new folder + manifest.** No UI surgery.
- **Detached spawn** for managed processes (so they outlive Synapse UI).
- **Two version files** must stay in sync: `package.json` and `pyproject.toml`. `scripts/version-bump.ps1` handles both.

## Design contracts (28 total — full spec in AGENTS.md)

Every milestone must honour all 28. Quick list:

**Round 1 (locked v0.1.0.5, scaffolded v0.1.1):**
1. Everything editable from the UI
2. Live status feedback on every action
3. Log capture per managed process
4. Single error envelope (`{code, message, details, retryable}`)
5. WebSocket reconnect protocol (event IDs + ring buffer)
6. Daemon orphan reconciliation on startup
7. Versioned API (`/api/v1/...`, `v1.entity.event`)
8. Single schema source of truth (Pydantic → TS)
9. DB migrations from day 1
10. Naming conventions (kebab/snake/camel/noun.verb)
11. Audit log
12. Confirm-before-destructive
13. Empty states everywhere
14. Theming via CSS tokens
15. No telemetry by default
16. Refuse Administrator unless `--allow-admin`

**Round 2 (locked v0.1.1.5, scaffolded v0.1.2):**
17. Health-check protocol per project (separate `health` field, `http | tcp | command | none` probe)
18. Restart policy per project (`never | on-failure | always`)
19. Resource observability (CPU% + RSS MB per process on heartbeat)
20. Project dependencies (`requires`, topological launch, cycle detection)
21. Universal search / `Ctrl+K` command palette
22. Native system notifications (with per-event opt-out)
23. Accessibility minimums (WCAG AA, focus rings, ARIA, keyboard nav)
24. Timestamps UTC in DB, local in UI (shared `formatLocal()` helper)
25. Secrets management (DPAPI-encrypted, never logged, never round-tripped)
26. Hot manifest reload (`watchdog` watcher + `v1.manifest.reloaded`)
27. CLI surface (`synapse list | start | stop | logs | snapshot | restore | doctor`)
28. Snapshot / restore (JSON dump; secrets excluded)

---

_Last updated by Milestone A scaffolding._
