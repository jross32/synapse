# Progress — Synapse

**Always read this file first** if you're an AI coding session resuming work. It's the single source of truth for "where are we right now."

---

## Current version

`0.1.4`

## Current milestone

**Milestone C — Electron skeleton — COMPLETE.** `.\scripts\dev.ps1` boots daemon → Vite → Electron window. Window shows live conn-state badge + the `v1.daemon.started` event. Closing the window hides to tray. 117 tests pass. Next: Milestone D wires real projects.

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
| `0.1.5+` | Milestone D — Project registry + launcher | ⚪ next |

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

## What's next (immediate)

**Milestone D — Project registry + launcher.** Wire the missing pieces:
- `daemon/synapse_daemon/projects.py` — Project Pydantic + CRUD against the `projects` table
- `daemon/synapse_daemon/process_manager.py` — detached child-process spawn that respects `restart_policy` (Contract #18), captures stdout/stderr to per-process log files (Contract #3), emits `v1.project.launched` / `v1.project.stopped` / `v1.project.errored` events
- `daemon/synapse_daemon/seed.py` — first-run insert of the wbscrper project so there's something to click
- `GET/POST/PATCH/DELETE /api/v1/projects` + `POST /api/v1/projects/{id}/launch` + `/stop` + `GET /logs`
- Renderer: `Apps.tsx` page with `ProjectTile` components, edit dialog (Contract #1), confirm-before-destructive (Contract #12), empty state (Contract #13), live state badge (Contract #2)
- End-to-end: click wbscrper tile → `npm start` runs in `C:\Users\justi\wbscrper` → tile turns green

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
