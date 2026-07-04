# Progress — Synapse

**Always read this file first** if you're an AI coding session resuming work. It's the single source of truth for "where are we right now."

---

## Current version

`0.1.36.11`

## Current milestone

**v0.1.36 Phase A polish wave shipped + phone parity / WAN reliability follow-up verified + first-party accounts landed + the AI Factory / AI OS advanced case engine is live.** Milestones A–I done; ADR-0002 (workbench) shipped through v0.1.29; ADR-0003 (workbench expansion) shipped through v0.1.34. v0.1.35–0.1.36 ship a wave of UX wins: status simplification, port clarification, disk-size badge, editable sidebar, GitHub Copilot quick-launch, collapsible AI Quick-actions, clickable project + tool detail modals, WAN exposure via Cloudtap, color themes (hacker green + surfer blue), dark native dropdowns, Phase B preview card, plus the new daemon route `GET /projects/{id}/disk-usage`. Follow-up on 2026-06-19..20: `/mobile` now serves the full React shell (Home / Apps / Tools / Sessions / Processes / Settings), supports paired-device auth in-browser, recovers cleanly from stale mobile tokens, and carries the same phone session from LAN -> Cloudtap WAN via durable paired-device identity, short-lived handoff claims, and the new daemon-owned `GET /api/v1/remote-access` aggregate. Settings now hosts a merged `Phone Access` hub with LAN, pairing, paired-device reconnect, WAN verification, and diagnostics in one place. Mobile nav is now a 2-row touch grid so all tabs stay visible on a 390px-wide phone. `scripts/remote-recovery.ps1` now gives Codex/local automation a rescue path: start or reuse the daemon, open Cloudtap on `7878`, wait for the WAN `/mobile` URL, and print a fresh pairing code. `synapse.cmd` / `scripts/dev.ps1` now clear `ELECTRON_RUN_AS_NODE` before launching Electron, avoid `EPIPE` main-process popups, launch Vite/Electron through directly owned child processes, and honor in-app restart by cycling the full daemon + Vite + Electron dev stack instead of only relaunching Electron. The daemon also installs a Windows-only asyncio accept-reset workaround so transient WinError 64 socket drops do not silently kill new LAN/WAN accepts on port 7878. Desktop auth now self-heals after daemon/token drift: renderer REST calls retry once after refreshing `/auth/local-token`, the desktop WS client retries after a 1008 auth close, the Tools page clears stale 401 banners after a later success, and Electron main-process tray requests bootstrap the token from the daemon instead of reading `data/auth-token` directly. On 2026-06-20 the remaining WAN reconnect bug was traced to the WS hub's 0.5 s resume-frame timeout, which caused false `1008` closes over Cloudflare and made the phone shell wipe its token a few seconds after a successful handoff; the timeout is now widened, remote/mobile shells no longer attempt desktop-only local-token bootstrap, and live Playwright retesting confirmed the phone stays inside the full shell over both LAN and Cloudtap WAN after a full Synapse restart. Packaging bootstrap is also now wired end to end: `installer/build-daemon.ps1` produces `installer/daemon-dist/synapse-daemon.exe`, Electron knows how to spawn the bundled daemon, and the daemon resolves bundled tools/templates/docs/mobile assets from packaged resources instead of source-tree-only paths. Sessions now also has a first-pass **Agent Squads** mode: durable role templates (`planner`, `implementer`, `reviewer`, `researcher`), daemon-owned squad/work-item tables via migration `008_agent_squads.sql`, explicit handoff capture that appends to `.synapse-ai-context.md`, PTY launches tagged with `SYNAPSE_SQUAD_ID` / `SYNAPSE_WORK_ITEM_ID` / `SYNAPSE_ROLE_PROMPT_FILE`, and a three-pane Sessions cockpit that keeps helper workers as real reopenable PTY sessions instead of hidden background jobs. On 2026-06-21 the daemon also gained a local-first **Profile hub** surface, then replaced the Supabase dependency with a new in-repo **Synapse Accounts** service (`daemon/synapse_accounts`) backed by native username/email/password auth, Google OAuth plumbing, rotating refresh tokens, synced portable preferences, and local encrypted session storage. The renderer now routes signed-out users into a polished native auth flow, signed-in users into the full Profile hub, and no longer blocks account creation behind slow connected-service probes. Live Playwright retesting confirmed browser signup now completes end to end and lands directly in the signed-in Profile hub. On 2026-06-22 the Profile sign-in became reachability-aware (an honest "sync is optional / not configured" panel when no Synapse Accounts service is reachable, via `ProfileSummary.account_backend_reachable`), Agent Squads gained a guided **Team Builder wizard** (goal -> preset team -> roster -> review), a `boss` / `supervisor` / `worker` role hierarchy (migration `011_squad_hierarchy.sql`, 11 seeded roles), and a **kill switch** (`POST /api/v1/agent-squads/{id}/stop`); the PTY launch path was also hardened so a missing project cwd returns a clean 422 instead of crashing the daemon. On 2026-06-22..23: shipped per-project **decision records** (ADRs + backlog + version history with a quick-idea -> promote-to-numbered lifecycle; migration `012_project_records.sql`, ADR-0011) in the project detail modal and AI-callable; a Sessions/Squads UX pass (cockpit gated on a selected squad, delegate/handoff gated on a selected work item, work-item form behind a disclosure, single Set-status control, larger labeled mode toggle) plus an app-wide fix for white native `<select>` dropdowns in dark mode; **Synapse as a claude.ai connector** -- a read-only MCP server at `/mcp/{token}` exposed over Cloudtap (ADR-0012); and the **autonomous AI boss** as a launchable `autonomous-boss` quick-action that plans, staffs, and runs a squad with full autonomy bounded by the kill switch (ADR-0013). 448 tests pass + 11 skipped. 15 bundled marketplace tools. ADRs 0011/0012/0013 shipped; 0009 (launcher splash) + 0010 (squad hierarchy/autonomy) authored; still gated on user "go": 0004 OAuth, 0005 wbscrper tab, 0006 project objectives, 0007 AI-improves-Synapse REST, 0008 marketplace reorg + sidebar promotion. On 2026-06-24..25 the **Marketplace & Workforce** wave landed: a visual **Marketplace hub** (ADR-0017 MW1); an **MCP-server pillar** that installs/launches MCP servers and auto-wires enabled ones into spawned Claude sessions via `--mcp-config` (ADR-0017 MW2, hardened for secret redaction + process-tree kill + zombie reaping); an in-app **What's New + Roadmap** path fed by `CHANGELOG.md` + `docs/roadmap.json` (ADR-0019 MW8); animated **synapse launch artwork** (MW9); and **AI personalities** — a worker = role + personality, so two same-role workers differ and collaborate/debate (ADR-0018 MW3, migration `015_personalities.sql`, REST `/personalities`, layered into the worker prompt). On 2026-06-27 the first-pass **AI Factory + AI Operating System** foundation landed: new daemon-backed AI Factory catalogs (components / recipes / sources), structured AI cases with `intent` / `targets` / `directives` / `policies`, mission profiles, richer case modes, case-owned jobs, AI-case lineage/graph support, isolated worktrees/branches, a native `AI Factory` page in the main shell, project-tile `Open in AI OS`, and a separate packaged AI OS board for live case execution. Later on 2026-06-27 the system grew a first Marketplace-grade **AI Bundles** layer (migration `017_ai_bundles.sql`, ADR-0021): installable AI-first packs of roles, personalities, quick actions, recipes, sources, and policy references published by **The WhatIf Company**; bundle-aware Marketplace + AI Factory views; bundle-owned quick-action installs; catalog install tracking in the profile layer; and installer-time bundle preselection via a bootstrap file consumed on first launch. The case runner also now applies a first real specialization pass for `benchmark`, `harvest`, `portfolio`, `challenge`, `repair`, `migrate`, and `audit`: benchmark candidate children, portfolio slices, minority-path challenge children, harvest source promotion scaffolding, and bundle-aware role/personality selection during squad synthesis. On 2026-06-28 those bundled AI packs were pressure-tested against isolated live AI-case installs and then tightened: role/personality/quick-action wording now avoids repeating labels the worker prompt already carries, trimming prompt overhead without changing the specialist squad coverage. Live verification on an isolated daemon + browser/API pair confirmed bundle install still works, updated bundle-owned quick actions reload, and a fresh `challenge` case still spawns its minority-path child with the expected contradiction-first council roles. On 2026-06-29 Fast Money shipped as a built-in launcher plus bundled AI pack: `tools/fast-money/manifest.json`, `synapse_daemon/tools/fast_money.py`, bundled marketplace + AI bundle catalog entries, focused daemon tests, and a first-run proof app registered at `data/projects/fast-money-client-ops`. Live verification confirmed the proof app serves its landing page, customer portal shell, and operator console shell on port `8740`. Packaging now produces a working installed app (frozen daemon bundles migrations + uvicorn; all catalogs shipped). 528 tests pass + 12 skipped. On 2026-07-03 (`0.1.36.5`, docs-only) the **README was rewritten extensively** (AI-first framing, non-technical + developer explainers, drift/memory comparison, Web Scraper MCP usage guide, "how any AI connects" section) and a **real benchmark** was added at `benchmarks/makeup-business-demo/` comparing a real Synapse-built app against a memory-less single-shot baseline across tokens, time, and six independently-judged quality dimensions (with-Synapse won 4/6 dimensions — UI/UX, design, code quality, accessibility — but lost backend-correctness and bug-hunt to two real, live-reproduced bugs in an unreviewed single pass; see the benchmark's `results/quality/summary.md` for the honest breakdown). Dogfooding that benchmark also surfaced a **real, still-open bug**: Agent Squads' `claude` work-item launch fails on Windows whenever any MCP server is enabled, because a multi-element `argv` (the auto-appended `--mcp-config` flag) isn't reaching the spawned `.CMD` child correctly (see `benchmarks/makeup-business-demo/methodology.md`). Next: fix that PTY multi-arg spawn bug, then deepen browser/scraper-backed intake, bundle authoring/publishing, and the case-native headless job runner. (See the 2026-07-04 decision-coverage audit below.)

## 2026-07-04 — decision-coverage audit (point-in-time; not a source of truth)

A one-time audit checked whether any product decision from the **origin build session** (the 21.7k-line thread where Synapse was named + scoped) was ever made verbally but never written into the durable docs. Method: extracted the 237 real user turns + all 7 AskUserQuestion picks, ran a product-noun recall sweep, read the decision-dense regions, did a bare-approval pass over the upper (14k–21k) region, and reverse-cross-checked 11 highest-signal + negative + foundational decisions against `AGENTS.md` / `PROGRESS.md` / `CHANGELOG.md` / `README.md` / `docs/roadmap.json` / `docs/adr/*`.

**Result: no gaps, no reversals.** Every material decision — including the negative/foundational ones (projects-stay-local, don't-automate-the-ChatGPT-web-UI, ONE-Synapse/retire-`ai_os`, built-for-AI, run-via-clickable-`.exe`) — is already captured. The origin session ended with a clean handoff ("everything committed + pushed; nothing half-saved; resume Z2 — fold `ai_os` into the cockpit"), so no work was left dangling. This is a **point-in-time recall sample as of 2026-07-04**, not a permanent guarantee; the detailed evidence (extracted turns, AskUserQuestion map, cross-check) lives in the session plan file `~/.claude/plans/okay-i-did-the-floofy-sketch.md` (Phase 0 record).

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
| `0.1.10.5` | Milestone F — snapshot / restore (Contract #28) wired to Settings | ✅ done |
| `0.1.11` | Milestone H — device auth + pairing foundation (token on every request) | ✅ done |
| `0.1.12` | Milestone H — mobile Web UI (responsive `/mobile`, pair screen, full control) | ✅ done |
| `0.1.13` | Milestone I — auto-start on login + tray polish + daemon attach-or-spawn | ✅ done |
| `0.1.14` | Polish — universal `Ctrl+K` command palette (Contract #21) | ✅ done |
| `0.1.15` | Polish — Apps page filter (name / path / tags / group / launch_cmd) | ✅ done |
| `0.1.16` | Polish — Open-in-VS Code tile quick-action | ✅ done |
| `0.1.17` | Polish — Audit log viewer in Settings (Contract #11 surfaced) | ✅ done |
| `0.1.18` | Polish — Light / Dark / System theme (Contract #14) | ✅ done |
| `0.1.19` | Project kinds + Apps filter chips + MCP-server auto-detect; ADR-0001 tool marketplace | ✅ done |
| `0.1.20` | Open-in-Terminal tile button + responsive sidebar (collapses to 56px at < 640px) | ✅ done |
| `0.1.21` | Hot tool-manifest reload via watchdog (ADR-0001 step 1, Contract #26) | ✅ done |
| `0.1.22` | Declarative tool primitives — `url.open` + `process.spawn` (ADR-0001 step 2) | ✅ done |
| `0.1.23` | Tools → Browse page (read-only marketplace catalogue) (ADR-0001 step 3) | ✅ done |
| `0.1.24` | Marketplace Install / Uninstall — loop closed via hot reload + primitives (ADR-0001 step 4) | ✅ done |
| `0.1.25` | ADR-0002 + PTY session foundation (`pty.spawn` primitive + REST control plane) | ✅ done |
| `0.1.26` | xterm.js + Sessions tab — live AI / shell sessions in the dashboard (ADR-0002 Phase A step 2) | ✅ done |
| `0.1.27` | Marketplace ships Claude + Codex + Tools → Sessions deep link (ADR-0002 Phase A complete) | ✅ done |
| `0.1.28` | Sessions install dialog + Help panel + `/pty/probe` | ✅ done |
| `0.1.29` | Apps tile "Open in workbench" + `/ai/context` digest + "Built for AI" Home callout (ADR-0002 Phase B) | ✅ done |
| `0.1.30` | Project files REST surface + migration 006 (ADR-0003 Phase A) | ✅ done |
| `0.1.30.5` | Workbench transcripts + `/ai/context` files inline (ADR-0003 Phase D + step 6) | ✅ done |
| `0.1.31` | Renderer `<FilesPanel>` + `files-client` (ADR-0003 Phase A complete) | ✅ done |
| `0.1.31.5` | Pre-upload inspection dialog with magic-byte detection (ADR-0003 Phase B) | ✅ done |
| `0.1.32` | Always-on AV scanning via Defender (Windows) / ClamAV (POSIX) (ADR-0003 Phase C) | ✅ done |
| `0.1.33` | ChatGPT export.zip importer + auto-created `imported-chatgpt` project (ADR-0003 Phase E) | ✅ done |
| `0.1.34` | AI quick-action templates + Sessions rail (ADR-0003 Phase F) | ✅ done |
| `0.1.35` | Polish + LAN exposure: status legend, port doc, sidebar editable, tray Exit/Restart, mobile QR, file preview, terminal search, PTY default cwd → ~, Modal/StatusLegend focus traps, Stop-all on Processes, NetworkPanel | ✅ done |
| `0.1.36-dev` | UX wishlist: collapsible AI Quick-actions, Copilot quick-launch, status UI merge (idle+stopped -> not running), disk-size badge, editable sidebar (reorder + hide/show), tile detail modals (Project + Tool), WAN via Cloudtap, color themes (hacker green, surfer blue), dark native dropdowns, full mobile shell parity + LAN/WAN handoff, Sessions-centric Agent Squads mode, ADRs 0006/0007/0008 drafted | ⏳ in progress |
| `0.1.36.5` | Docs-only: README rewrite (AI-first framing, drift/memory, Web Scraper MCP guide), `benchmarks/makeup-business-demo/` real Synapse-vs-baseline benchmark, AGENTS.md doc-sync rule for benchmarks + any-AI note | ✅ done |
| `0.1.36.6` | Docs-only: README squad worked example (Skeptic vs. Pragmatist reviewer) + autonomous "AI boss" self-improvement bullet | ✅ done |
| `0.1.36.7` | Docs/config: AGENTS.md commit-before-limit rule + commit-rule #11 (commit+push per logical change) + gitignore daemon/auth-token | ✅ done |
| `0.1.36.8` | Docs: `docs/screenshots/` UI gallery (Home + cockpit, live-captured) + AGENTS.md screenshot-refresh rule; verified cockpit is project-scoped-only (no project-free New chat) | ✅ done |
| `0.1.36.9` | AI Council Review workflow (ADR-0023): `ai-council-review` quick-action + MULTI-AI-WORKFLOW/AGENTS/roadmap docs — pre/post multi-reviewer gate, adaptive 2–10, prompt-pass mechanism (no squad-workers on Windows yet) | ✅ done |
| `0.1.36.10` | **Fix:** Windows PTY multi-arg `.cmd`/`.bat` squad-launch bug (`claude.CMD --mcp-config` dropped args → every squad claude worker silently failed) — PowerShell-`&` wrap + 6 tests incl. hostile-path E2E + live repro. **Squad launch now works on Windows.** | ✅ done |

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

### v0.1.10.5 — Snapshot / restore (Contract #28)
- `snapshot.py` — `build_snapshot()` (registry → `SnapshotPayload`) + `restore_snapshot()` (merge by id; create new, update existing, never delete; restored projects come back idle with secret values blanked).
- `routes_snapshot.py` — `GET /api/v1/snapshot`, `POST /api/v1/restore` (compatibility-checked + audited).
- Renderer: `snapshot-client.ts`, `components/SnapshotPanel.tsx` (Settings "Backup & restore" card — download a snapshot, restore one from file, see the report).
- 216 tests pass (+6); typecheck green; E2E downloaded a 21-project snapshot and restored it → "0 created, 21 updated".

### v0.1.11 — Device auth + pairing foundation (Milestone H, part 1)
- **Token on every request.** `migration 004` (`paired_devices`), `auth.py` (`AuthManager` — local token in `data/auth-token`, device tokens via 6-digit pairing codes, `is_trusted_local()`, `require_token()` dependency), `routes_auth.py` (`/auth/local-token`, `/pair/code`, `/pair`, `/pair/devices`).
- Why not "trust localhost": a Cloudflare tunnel makes tunnelled requests look loopback — so nothing is trusted by IP; only the one bootstrap endpoint uses the trusted-local check (loopback + no proxy headers).
- `app.py` guards projects/discovery/tools/snapshot routers with `X-Synapse-Token`; `ws.py` accepts a token in the resume frame. CORS allows the header.
- Renderer: `bootstrapLocalToken()` at startup; `api-client`/`ws-client` send the token; `PairedDevicesPanel` in Settings (generate code with countdown, list/revoke devices).
- 230 tests pass (+14); typecheck green; E2E verified token bootstrap, 401 without token, pairing-code generation.

### v0.1.12 — Mobile Web UI (Milestone H complete)
- `mobile/index.html` — a self-contained responsive Web UI (HTML + CSS + vanilla JS, one file, no external resources). Pair screen (6-digit code → device token in `localStorage`) → dashboard: every project as a card with live status + Launch/Stop, `:port` links, a Cloudtap section (open/close tunnels), live WebSocket updates, "Unpair this device".
- `app.py` — mounts `mobile/` as static files at `/mobile` (open, so a phone can load the page before pairing).
- 231 tests pass (+1); typecheck green; E2E at a 390×844 phone viewport — paired, listed 21 projects, opened + closed a real Cloudflare tunnel from the phone, 0 console errors.

### v0.1.13 — Auto-start + tray polish (Milestone I)
- `electron/main.ts` — `synapse:get-autostart` / `synapse:set-autostart` IPC over `setLoginItemSettings`; richer tray menu (Projects submenu with launch + running checkmarks, Open-mobile-UI, Start-with-Windows checkbox), refreshed every 20s via authenticated daemon calls (main process reads the local token off disk).
- **Probe-before-spawn:** Electron checks `/health` on launch — attaches to an already-running daemon instead of spawning a second one; only kills a daemon it spawned itself.
- Renderer: `StartupPanel` in Settings (start-with-Windows toggle; degrades to "Desktop app only" in a browser).
- 231 tests pass; typecheck green; E2E — Electron rebooted clean, attached to the running daemon (one `:7878` holder), Startup toggle present, 0 console errors.

### v0.1.30 → v0.1.34 — ADR-0003 (workbench expansion)

A single coherent arc. The `project_files` table generalises: file uploads, transcripts, ChatGPT-import conversations, and quick-action prompt records all share one storage / audit / download surface.

- **v0.1.30** -- migration 006 (`project_files` with `scan_result` / `scan_engine` / `duplicate_of`), `files_storage.py` (write / move / soft-delete / hash; pure functions), `routes_files.py` (multipart POST, list, download, delete; per-project AND shared via `project_id IS NULL`; 100 files / req and 256 MiB / file caps via env; after-write dedup reconciliation under transaction).
- **v0.1.30.5** -- workbench-tagged PTY exits persist scrollback to `project_files` (`source='transcript'`); `/api/v1/projects/{id}/transcripts` lists them; `/api/v1/ai/context` inlines the current project's files (and shared scope).
- **v0.1.31** -- `lib/files-client.ts` (multipart, list, download, soft-delete; XHR for progress); `<FilesPanel>` in the workbench (drag-drop, multi-file picker, per-row metadata, delete confirm).
- **v0.1.31.5** -- Phase B pre-upload inspection: in-browser magic-byte detection (`application/pdf`, plain text, common images, JSON, ZIP, PE / ELF / Mach-O); the executable red banner; bulk-select review dialog.
- **v0.1.32** -- Phase C AV scanning. `files_av.py` with Defender (`MpCmdRun.exe`; stdout `Threat :` regex because exit codes drift) + ClamAV (`clamscan`; stable exit codes); 30s timeout; RTP-vanished-file fall-through. Upload pipeline scans quarantine bytes BEFORE finalize; blocked uploads insert a row with `scan_result='blocked'` + `deleted_at=now` for the audit trail.
- **v0.1.33** -- Phase E ChatGPT import. `chatgpt_import.py` walks each conversation's `mapping` tree from root to `current_node` so forked retries render the branch the user kept. `routes_imports.py` POST takes a multipart zip, lazy-creates the `imported-chatgpt` project, writes one Markdown file per conversation tagged `source='chatgpt-import'`. Honest scope (Contract #15): the official export, not browser scraping, not a live API.
- **v0.1.34** -- Phase F AI quick-actions. `quick_actions.py` loads `templates/quick-actions/*.json`; `routes_quick_actions.py` lazy-creates the `scratch` project, writes the templated prompt to `PROMPT.md` + `PROMPT-<id>.md` inside its cwd, spawns the workbench PTY with `SYNAPSE_QUICK_ACTION_{ID,PROMPT,PROMPT_FILE}` injected so the Claude / Codex session sees the prompt on prompt 1. Two bundled templates ship: `new-mcp-server`, `new-synapse-tool`. The button ships the shortcut; the AI does the work.
- **368 tests pass + 9 skipped.** Suite hygiene during v0.1.33: fixed `_BUNDLED_SAMPLE` + mobile-UI cwd-relative paths and the `BaseEntity` `default_factory` timestamp drift.

### v0.1.36-dev — Mobile parity + WAN handoff follow-up
- `/mobile` now prefers the built React renderer instead of the older standalone HTML page, while still falling back to `mobile/index.html` if `dist/` is absent.
- New renderer runtime bootstrap path:
  - paired-device token in `localStorage` for phone/browser sessions
  - local daemon token for Electron + same-machine browser sessions
  - stale/expired mobile token auto-clears back to the pair screen instead of leaving the phone in an empty shell
- Mobile shell now exposes the same primary pages as desktop: `Home`, `Apps`, `Tools`, `Sessions`, `Processes`, `Settings`, with dedicated phone chrome (`Synapse Mobile` header + bottom nav).
- Browser/mobile cleanup:
  - project browser links use the current LAN host instead of hardcoded `localhost`
  - tunnel-origin project links no longer pretend `localhost:<port>` is reachable over WAN
  - desktop-only quick actions (open folder, VS Code, terminal) stay out of the phone browser path
  - `Settings` adds a browser-local "Forget this device" action for clearing the saved mobile token
- Cloudtap/mobile integration:
  - `ToolCard` now exposes `Use on this phone` for the daemon tunnel on port `7878`
  - `Use on this phone` moves the current paired-device token from LAN origin storage into the Cloudflare tunnel origin via a one-click handoff URL
- Remote recovery:
  - `scripts/remote-recovery.ps1` starts or reuses the daemon, opens Cloudtap on port `7878`, waits for the WAN `/mobile` URL, and prints a fresh pairing code
  - packaged builds copy the helper to `resources/scripts/remote-recovery.ps1`
- Dev bootstrap + restart hardening:
  - `synapse.cmd` now delegates to `scripts/dev.ps1` so one wrapper owns the daemon, Vite, and Electron child lifetimes
  - the wrapper launches Vite through `node node_modules/vite/bin/vite.js` and Electron through `node node_modules/electron/cli.js`, which keeps restart ownership tied to the real long-lived processes
  - in-app restart now exits Electron with a dedicated wrapper restart code, letting the wrapper recycle the full stack instead of only relaunching Electron
- Packaging bootstrap:
  - `installer/build-daemon.ps1` now builds `installer/daemon-dist/synapse-daemon.exe`
  - Electron knows how to spawn the bundled daemon in packaged mode
  - the daemon now resolves bundled `tools/`, `templates/`, `docs/marketplace-sample.json`, `dist/`, and `mobile/` from packaged resources instead of assuming a source checkout
- Live E2E verified with Playwright at a 390x844 phone viewport:
  - paired on LAN at `http://192.168.1.143:7878/mobile`
  - opened Cloudtap for port `7878` from the phone `Tools` page
  - followed `Use on this phone` into `https://advisor-triumph-memorial-anti.trycloudflare.com/mobile`
  - launched a real PowerShell PTY session from the WAN phone `Sessions` page
  - cleared the token in-browser and paired directly on the Cloudflare URL with a fresh 6-digit code
- Live dev-wrapper restart verified on 2026-06-20:
  - launched `synapse.cmd` with renderer inspection enabled
  - verified the desktop renderer at `http://127.0.0.1:5173/` with Playwright
  - attached to the real Electron window via `scripts/inspect-electron.js`
  - triggered `window.synapse.restart()` from the live app
  - confirmed the wrapper stopped and restarted Vite + daemon, relaunched Electron, and came back on the real Synapse page instead of a dead renderer
- `npm run build` ✅
- `npm run typecheck` ✅
- `npm run build:daemon` ✅
- `pytest` -> **437 passed, 11 skipped**

### v0.1.36-dev — AI Factory + AI Operating System foundation
- Daemon:
  - new advanced AI case substrate with structured `intent`, `targets`,
    `directives`, and `policies`
  - mission profiles + expanded case modes
  - case graph fields (`parent_case_id`, `root_case_id`, comparison metadata)
  - case-owned jobs with transcript/finalization linkage
  - isolated worktree/branch manager for runnable cases
  - AI Factory catalog tables + starter seed data for components, recipes, and sources
  - AI Factory CRUD/promote routes plus expanded AI-case meta/graph/spawn/export routes
- Renderer:
  - new `AI Factory` nav page for browsing recipes/components/sources and launching cases
  - `Open in AI OS` action on project tiles
  - live AI-case refresh on `v1.ai_case.*` so the runs panel stays honest
  - explicit `Stop selected case` control in the AI Factory inspector
- AI OS app:
  - separate local app shell under `ai_os/`
  - richer board UI for mission profiles, recipe-aware case creation, graph summary, scorecards, and similarity panels
- Live verification:
  - isolated daemon on `7981` + Vite on `5174`
  - AI Factory page loaded cleanly in the browser
  - created a real case, launched it, confirmed isolated worktree allocation, then stopped it and verified the UI updated from daemon events without a manual refresh
- `npm run typecheck` ✅
- `pytest` -> **504 passed, 12 skipped**

### v0.1.36-dev — Fast Money launcher + proof app
- Daemon:
  - new built-in `FastMoneyTool` registered in `tools_registry.py`
  - launcher auto-installs the `fast-money` AI bundle on first use
  - launcher creates or reuses the target project, defaults to `data/projects/fast-money-client-ops`, writes `FAST_MONEY_BRIEF.md` + `PROMPT.md`, and returns `session_id` / `project_id` / `bundle_id` / chosen runtime in tool state
  - launcher scaffolds a runnable private/local-first client-ops SaaS starter with landing page, pricing page, auth shell, customer portal, operator console, optional catalog editor, billing/auth seams, README, architecture note, monetization note, and seed/demo data
- Bundles/catalogs:
  - bundled AI catalog now includes the `fast-money` pack (roles, personality, recipe, monetization/source note pack, quick action `fast-money-launch`)
  - bundled marketplace sample now includes the installable `fast-money` tool entry
- Renderer:
  - generic `ToolCard` now renders boolean manifest fields as real checkboxes so Fast Money's portal/console/catalog toggles work naturally in Tools
- Live verification:
  - launched Fast Money once into the real repo `data/` folder; the proof app is now registered as project `fast-money-client-ops`
  - confirmed `data/projects/fast-money-client-ops` exists with the scaffolded files
  - started the generated app locally and verified `/health`, `/`, `/portal`, and `/ops` all returned `200`
- `npm run typecheck` ✅
- `pytest` -> **528 passed, 12 skipped**

## What's next (immediate)

**AI Factory / AI OS depth.** The structured substrate is in, but the deeper
mode-specific behaviors still need follow-through:
- child-case bakeoffs for `benchmark`, `portfolio`, and alternate-path `challenge`
- scraper/browser evidence intake and promotion into the AI Factory catalog
- richer mode-specific AI OS panels (comparison boards, harvested-source promotion, benchmark score views)
- more deterministic case-native job execution beyond the current PTY-backed lead-worker path

**ADR-0003 closed.** ADR-0003 Phase G is OAuth (Sign in with Apple / Google), which has always lived in its own ADR-0004 -- deferred until the user gives the go (real OAuth client provisioning, redirect URIs, JWKS, device-migration plan).

**Milestone J — packaging.** Milestones A–I are done, and packaging remains the release gate after the current AI Factory / AI OS foundation hardens.
- PyInstaller bundled-daemon bootstrap is now wired (`installer/daemon-dist/synapse-daemon.exe`)
- electron-builder + an NSIS installer → one double-click install
- First-run wizard creates a desktop shortcut
- Then Milestone K — `v0.1.0` release (tag, GitHub release, screenshots)

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
python -m pytest -q    # should pass 528 tests, 12 skipped
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

_Last updated by the v0.1.36.11 benchmark reviewer pass (re-score pending / usage limit)._
