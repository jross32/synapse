# Changelog

All notable changes to Synapse will be documented in this file.
Format roughly follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
This project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Every commit must append an entry under the in-progress version header.

---

## [Unreleased]

## [0.1.4] — 2026-05-13

### Milestone C — Electron skeleton (Synapse opens)

`.\scripts\dev.ps1` now launches the full stack: daemon → Vite → Electron window, all wired together. Closing the window hides to a system tray; right-click → **Quit Synapse** is the only thing that actually exits.

#### Added
- `scripts/gen-icon.py` — pure-stdlib PNG generator (no Pillow dep) that draws the Synapse mark — nucleus dot + accent ring + six cyan sparks — at 32 × 32 (tray) and 256 × 256 (installer / About). Run once with `python scripts/gen-icon.py`; both PNGs are checked in so dev machines don't need to regenerate.
- `electron/icons/synapse.png` (936 B) and `electron/icons/synapse-256.png` (16 KB) — generated placeholder marks. Designer-drawn final lands in Milestone J without touching consumer code.

#### Changed — Electron main process
- `electron/main.ts` rewritten end-to-end (Contract #2 hide-to-tray, Contract #6 daemon child, Contract #16 admin refusal):
  · Single-instance lock — second launch focuses the existing window.
  · Spawns `python -m synapse_daemon --port 7878 --data-dir data` on `app.whenReady`, polls `/api/v1/health` for up to 15 s before opening the window so the renderer never sees a connect-failure flash.
  · Tray icon with **Show Synapse** / **Open daemon health page** / **Quit Synapse**. Single-click + double-click both show the window.
  · `mainWindow.on('close', ...)` prevents default and hides to tray unless `isQuitting` is set. Only the tray's Quit item flips that flag.
  · External links open in the user's browser via `shell.openExternal`, never inside an Electron BrowserWindow.
  · `app.on('will-quit')` kills the daemon child cleanly. Daemon stdout/stderr is prefixed with `[daemon]` in the Electron console.

#### Changed — preload bridge
- `electron/preload.ts` exposes a typed `window.synapse.*` surface: `version()`, `daemonBase()`, `daemonWsBase()`, `platform()`. Raw Node APIs stay off the renderer's window.

#### Changed — renderer
- `renderer/App.tsx` rewritten as the Milestone C proof of life:
  · Calls `setDaemonBase(window.synapse.daemonBase())` so `api-client.ts` aims at the right host even in packaged mode.
  · Fetches `GET /api/v1/health` and renders version / uptime / start time / contracts-honoured count.
  · Starts a `SynapseWsClient`, displays the colour-coded conn-state badge (idle / connecting / connected / reconnecting / closed) using `--synapse-status-*` tokens.
  · Renders the last 5 received WS events with id + name + local time (Contract #24 — `formatLocal` shared helper).
  · All colour, spacing, type, and radius values come from `theme-tokens.css` (Contract #14 — no hardcoded values).

#### Notes
- `npm run typecheck` ✅ · `npm run build:electron` produces `dist-electron/main.js` + `preload.js` cleanly.
- `pytest` 117 passing · 1 platform-conditional skip — daemon code untouched in this commit.
- Smoke-test path: run `.\scripts\dev.ps1` — you should see daemon boot logs, a Synapse window showing "connected" + the `v1.daemon.started` event, and a tray icon. Close the window → hides to tray. Right-click → Quit Synapse → both Electron and the daemon child exit cleanly.

#### Next
- Milestone D wires real projects (CRUD endpoints + Apps page with tiles + launch button). First tile = `wbscrper`.

## [0.1.3] — 2026-05-13

### Milestone B — Daemon skeleton (the daemon is alive)

`python -m synapse_daemon` now boots a FastAPI server on `localhost:7878`, applies all SQLite migrations, runs orphan reconciliation, and emits a `v1.daemon.started` event onto the WebSocket bus. `GET /api/v1/health` returns the contract shape; `WS /api/v1/ws` honours the full replay + ping protocol.

#### Added — daemon modules
- `synapse_daemon/storage.py` (Contracts #8, #9, #11): `Storage` class wrapping a single SQLite connection in autocommit mode with WAL + foreign keys + 5 s busy timeout; `migrate()`, `applied_migration_numbers()`, `schema_migration()`, `transaction()` ctx manager.
- `synapse_daemon/migrations/_runner.py` (Contract #9): atomic per-migration application — splits SQL on `;`, runs every statement plus the `schema_migrations` INSERT inside a single `BEGIN IMMEDIATE` / `COMMIT`. Idempotent on re-run.
- `synapse_daemon/ws.py` (Contract #5): `Event` model, `EventBus` (monotonic IDs, 1 000-event ring buffer, async-locked `publish`/`subscribe`, `replay_since`, `replay_window_exceeded`), `WsHub` (FastAPI WebSocket handler with `resume` + `ping` + `error` envelopes, per-connection `asyncio.Queue` fan-out, cancellation-safe cleanup).
- `synapse_daemon/orphan_reconciler.py` (Contract #6): `reconcile()` reads `managed_processes` where `stopped_at IS NULL`, classifies each row as `re-attached` / `pid-recycled` / `daemon-restart` via `psutil`, writes the non-re-attached rows to `stopped`; `summarise()` rolls outcomes up into a `ReconciliationReport`.
- `synapse_daemon/app.py` (Contracts #4, #5, #7, #15): `build_app(storage, bus)` factory mounts CORS for Vite + Electron `null` origin, registers `SynapseError` → `ErrorEnvelope` handler + fallback handler that hides internals, exposes `GET /api/v1/health` returning `HealthResponse`, mounts `WS /api/v1/ws` via `WsHub`. Helpers `boot_publish_daemon_started()` and `boot_publish_reconciliation()` for lifespan use.

#### Changed — daemon entry point
- `synapse_daemon/__main__.py` rewritten: argparse with `--host`, `--port`, `--bind-lan`, `--data-dir`, `--allow-admin`, `--log-level`. Calls `assert_not_admin()` (Contract #16) → opens storage → applies migrations → builds app → wires lifespan that runs `reconcile()` in a thread + publishes the boot events → hands off to uvicorn. Daemon prints "ready · schema=N · contracts 1-28 · port=P" on startup.
- `scripts/dev.ps1` now actually orchestrates: spawns daemon as a background job, polls `/api/v1/health` for up to 10 s before launching Vite + Electron, cleans up jobs on exit. Supports `-DaemonOnly`, `-AppOnly`, `-BindLan`.

#### Added — tests (32 new, 0 regressions)
- `daemon/tests/test_storage.py` (10): file creation, WAL + FK pragmas, migration application, idempotency on re-run, schema-migration reporter, transaction commit + rollback, pre-open guard, idempotent close.
- `daemon/tests/test_ws.py` (9): monotonic IDs, replay slicing, ring-buffer eviction, window-exceeded boundary, subscriber fan-out + unsubscribe, default buffer size, failing-subscriber isolation, concurrent publishers get unique IDs.
- `daemon/tests/test_orphan_reconciler.py` (5): empty table, dead PID → `daemon-restart`, alive matching cmdline → `re-attached` without touching row, alive different cmdline → `pid-recycled`, `summarise()` bucket totals.
- `daemon/tests/test_app.py` (8): `/health` shape, versioned-path enforcement (unversioned 404), `SynapseError` → 4xx envelope, fallback handler hides internals, CORS preflight, WS resume + replay, WS replay-window-exceeded boundary, ping/pong.

#### Smoke-tested end-to-end
- Launched `python -m synapse_daemon --port 7878 --data-dir data`.
- `curl http://localhost:7878/api/v1/health` returned `{ok:true, version:"0.1.3", contracts:[1..28], ...}`.
- `curl http://localhost:7878/health` returned 404 (Contract #7 enforcement).
- Connected Python `websockets` client: resume handshake delivered the `v1.daemon.started` event; ping → pong worked.
- Migrations 1 + 2 applied cleanly on a fresh DB; second boot was a no-op.

#### Docs
- `README.md`: version line → `v0.1.3`; status reflects "daemon is alive · 117 tests"; "Getting started" now shows real boot + curl commands; roadmap table updated with Milestone B done + Milestone C as next.
- `docs/api-changes.md`: `/api/v1/health`, `WS /api/v1/ws`, `v1.daemon.started`, `v1.process.reconciled`, `v1.daemon.reconciliation_complete` documented as shipped in 0.1.3; pending endpoints regrouped by milestone.

#### Notes
- 117 tests passing · 1 platform-conditional skip (Fernet fallback on Windows; DPAPI ran natively).
- The daemon now satisfies the "always-on backend" half of the architecture. Milestone C wires Electron to it.

## [0.1.2.5] — 2026-05-13

### Docs sync — README + commit rule hardening

#### Added
- `AGENTS.md` "Commit rules" section now requires:
  - **Rule #4** — every commit syncs `README.md` whenever version, milestone, test count, roadmap status, tech stack, advertised features, or getting-started commands change.
  - **Rule #5** — affected `docs/` files sync alongside the change that touched them (`api-changes.md` for new endpoints/events, `security.md` for security-relevant code, ADRs for contract-touching decisions).
  - New "Docs-sync pre-flight" mental check: re-read the first 30 lines of `README.md` and `PROGRESS.md` before every commit.

#### Changed
- `README.md` fully rewritten to reflect current state:
  - Version line now `v0.1.2.5` (was stale at `v0.1.0-alpha.1`).
  - Status reflects "pre-Milestone-B contract pass complete · 85 tests passing".
  - New "Design contracts (28)" section linking to AGENTS.md and listing both rounds inline.
  - "Live status feedback" and "Editable from the UI" added to features bullets.
  - Tech stack table updated (watchdog + cryptography deps added in v0.1.2 are now visible).
  - "Getting started" now mentions running typecheck + pytest as a sanity check.
  - Roadmap table inserts the two contract-pass rows (`v0.1.0.5/0.1.1` + `v0.1.1.5/0.1.2`) between Milestone A and Milestone B with done status.
- `PROGRESS.md`: current version → `0.1.2.5`, current milestone wording updated.
- All three version files: `0.1.2` → `0.1.2.5`.

#### Notes
- No code changes; toolchain green unchanged (typecheck ✅, pytest 85/1 ✅).
- Rule #4 (README sync) and Rule #5 (docs sync) are now load-bearing — any future commit that violates them is a regression.

## [0.1.2] — 2026-05-13

### Contract scaffolding — Round 2 (code)

Operationalises Round 2 contracts (#17–#28) locked in `v0.1.1.5`. Every Round 2 contract now has a real Pydantic/Python/TS shape; runtime wiring follows in Milestones B–E.

#### Added — daemon modules
- `synapse_daemon/time_utils.py` (#24): `utc_now`, `to_iso`, `from_iso` with Z-suffix tolerance.
- `synapse_daemon/health.py` (#17): `HealthProbe`, `HealthState` enum, `HealthSnapshot`, `is_terminal()`.
- `synapse_daemon/restart_policy.py` (#18): `RestartPolicy` + `should_restart()` + `next_backoff_seconds()` exponential backoff with cap.
- `synapse_daemon/resources.py` (#19): `ResourceSnapshot`, `ResourceCaps`, `over_budget()`.
- `synapse_daemon/dependencies.py` (#20): Kahn-based topological sort restricted to the reachable subgraph + cycle detection + `reverse_dependents()`.
- `synapse_daemon/search.py` (#21): `tokenise()`, `build_search_tokens()`, `Indexable` protocol — identical tokenisation rules client+server.
- `synapse_daemon/notifications.py` (#22): `Notification` model + `KNOWN_EVENT_KINDS` frozenset + `assert_known_event_kind()` guard.
- `synapse_daemon/secrets.py` (#25): `EnvVar`, `SecretStore` protocol, `encrypt`/`decrypt` (Windows DPAPI + Fernet fallback), `redact()`, `SECRET_PLACEHOLDER` ("(set)"), `generate_token()`.
- `synapse_daemon/manifest_watcher.py` (#26): `ManifestWatcher` class wrapping `watchdog` Observer — picks up `manifest.json` changes, ignores other files.
- `synapse_daemon/cli.py` (#27): `synapse list | status | start | stop | logs | snapshot | restore | doctor` argparse-based parser; doctor runs without daemon.
- `synapse_daemon/snapshot.py` (#28): `SnapshotPayload`, `RestoreReport`, `assert_compatible()` with format + schema version guards.

#### Added — daemon migrations
- `migrations/002_round2_schema.sql`: adds `health_probe_json` / `restart_policy_json` / `max_rss_mb` / `max_cpu_percent` / `current_health` / `last_health_at` columns to `projects`; new tables `project_dependencies`, `search_index`, `notification_preferences`, `project_secrets`.

#### Added — renderer
- `renderer/lib/format-time.ts` (#24): `formatLocal(ts, kind)` + `formatUptime()` — single conversion point UTC → local.
- `renderer/lib/search-client.ts` (#21): `search(query, limit)` wrapper + `tokenise()` matching the daemon.
- `renderer/lib/generated-types.ts`: extended with all Round 2 types (`HealthProbe`, `HealthSnapshot`, `HealthState`, `RestartPolicy`, `RestartMode`, `ResourceSnapshot`, `ResourceCaps`, `Notification`, `NotificationLevel`, `EnvVar`, `SnapshotPayload`, `RestoreReport`).

#### Added — tests (10 new files, all 85 passing)
- `test_time_utils.py`, `test_health.py`, `test_restart_policy.py`, `test_resources.py`, `test_dependencies.py`, `test_search.py`, `test_notifications.py`, `test_secrets.py`, `test_manifest_watcher.py`, `test_cli.py`, `test_snapshot.py`.
- Updated `test_migrations.py` to assert migration 002 + required tables.
- Updated `test_models.py` to assert `HealthResponse.contracts` covers 1–28 and `model_registry()` exports every new model.

#### Changed
- `daemon/synapse_daemon/models.py`: `HealthResponse.contracts` default bumped to `range(1, 29)`; `model_registry()` now includes 11 Round 2 models.
- `pyproject.toml`: added `watchdog>=4,<7` and `cryptography>=43,<46` deps; registered `synapse` console script alongside `synapsed`.
- All three version files: `0.1.1.5` → `0.1.2`.

#### Notes
- `npm run typecheck` ✅ · `pytest` 85 passed + 1 skipped (Fernet test on Windows; DPAPI test ran on Windows) ✅.
- All 28 contracts now have code shapes backing them. Milestone B can begin wiring them into a running daemon.

## [0.1.1.5] — 2026-05-13

### Design contracts — Round 2 (docs only)

Locked the following 12 contracts into `AGENTS.md`, taking the total to 28. Code scaffolding lands in `v0.1.2`.

#### Added — operational lifecycle
- **#17** Health-check protocol per project (`http | tcp | command | none` probe, separate `health` field alongside `status` so we don't lie when a process is hung).
- **#18** Restart policy per project (`never | on-failure | always`, max-retries, exponential backoff). Default `never`.
- **#19** Resource observability per process (CPU% + RSS MB on heartbeat, optional soft caps with warning).
- **#20** Project dependencies (`requires: [id]` in manifest, topological launch with confirm, cycle detection).

#### Added — UX primitives
- **#21** Universal search / `Ctrl+K` command palette. Reserves keybind + `GET /api/v1/search` + `search_tokens` model field.
- **#22** Native system notifications (Electron toast for crash/health-flip/tunnel-live/scheduled-launch, per-event opt-out table).
- **#23** Accessibility minimums (WCAG AA contrast, visible focus rings, ARIA labels on icon-only buttons, full keyboard nav, `prefers-reduced-motion` already done).
- **#24** Timestamps UTC in DB, local in UI (single shared `formatLocal()` helper; no ad-hoc `.toLocaleString()`).

#### Added — data + control
- **#25** Secrets management (`secret: true` env vars, DPAPI-encrypted at rest, never logged, never round-tripped in plaintext after save).
- **#26** Hot manifest reload (`watchdog` file watcher on `tools/` + project manifest paths; `v1.manifest.reloaded` / `v1.manifest.error` events).
- **#27** CLI surface (`synapse list | status | start | stop | logs | snapshot | restore | doctor` mapped 1-to-1 with REST).
- **#28** Snapshot / restore (single JSON dump containing projects + tools + settings + audit tail; secrets excluded, surfaced as re-enter list on restore).

#### Changed
- `AGENTS.md` header: 16 → 28 contracts, references Round 1 (`v0.1.0.5` → `v0.1.1`) and Round 2 (`v0.1.1.5` → `v0.1.2`) cycle.
- All three version files: `0.1.1` → `0.1.1.5`.

#### Notes
- `HealthResponse.contracts` model field still reports 1–16; bumps to 1–28 in `v0.1.2` when round-2 models exist.
- `npm run typecheck` ✅ · `pytest` 31/31 ✅ (no runtime changes).
- Round 2 implementation (v0.1.2) follows immediately.

## [0.1.1] — 2026-05-13

### Contract scaffolding — Round 1 (code)

Operationalises the 16 design contracts locked in `v0.1.0.5`. Every contract now has a real code shape backing it; runtime wiring follows in Milestone B onwards.

#### Added — daemon
- `daemon/synapse_daemon/api_versions.py` (Contract #7): `API_VERSION`, `API_PREFIX`, `WS_EVENT_PREFIX`, `event_name()` helper.
- `daemon/synapse_daemon/errors.py` (Contract #4): `ErrorEnvelope` Pydantic model + `SynapseError` exception + helper constructors (`not_found`, `conflict`, `invalid`).
- `daemon/synapse_daemon/models.py` (Contracts #2, #8): `BaseEntity` with the universal live-status fields, `EntityStatus`, `AuditSource`, `ErrorRef`, `StateTransition`, `HealthResponse`, plus `model_registry()` so `gen-types.ps1` knows what to export.
- `daemon/synapse_daemon/migrations/__init__.py` + `001_initial.sql` (Contracts #9, #11): schema_migrations, audit_log, projects, tools, managed_processes, confirm_preferences, settings tables.
- `daemon/synapse_daemon/audit.py` (Contract #11): `AuditRecord` Pydantic + `audit(db, record)` writer.
- `daemon/synapse_daemon/process_log.py` (Contract #3): rotation constants (10 MB × 5), per-entity log dir layout, `new_log_path`, `latest_log`, `list_logs`.
- `daemon/synapse_daemon/security.py` (Contract #16): `is_admin`, `assert_not_admin(allow_admin=False)`.

#### Added — renderer
- `renderer/lib/error-types.ts` (Contract #4): `ErrorEnvelope` TS interface + `isErrorEnvelope` guard + `formatError`.
- `renderer/lib/api-client.ts` (Contract #7): `apiFetch<T>()` wrapper that prepends `/api/v1`, throws `SynapseApiError` carrying an `ErrorEnvelope`.
- `renderer/lib/ws-client.ts` (Contract #5): `SynapseWsClient` class with backoff (1, 2, 4, 8, 16, 30 s cap), event-id cursor, `{type: "resume", since}` handshake, conn-state events.
- `renderer/lib/theme-tokens.css` (Contract #14): full CSS-variable palette + dark/light/prefers-reduced-motion.
- `renderer/lib/generated-types.ts` (Contract #8): hand-written TS mirroring the Pydantic models; CI will compare to generator output once active.
- `renderer/styles.css` now imports theme tokens; body uses `var(--synapse-bg-nucleus)` etc.

#### Added — scripts + docs
- `scripts/gen-types.ps1` (Contract #8): placeholder generator entry point; activates in Milestone B.
- `scripts/version-bump.ps1`: now supports `-Kind design` (appends `.5`) and updates `daemon/synapse_daemon/__init__.py` too.
- `docs/api-changes.md` (Contract #7): versioning rules + pending v1 endpoint table.
- `docs/security.md` (Contracts #15, #16): threat model, no-telemetry posture, LAN exposure caveats, secrets stance.
- `docs/adr/README.md`: ADR folder + template for any future contract amendments.

#### Added — tests
- `daemon/tests/test_errors.py` (Contract #4): envelope validation, helper constructors, status codes.
- `daemon/tests/test_models.py` (Contracts #2, #7, #10): status enum coverage, audit source values, kebab-case pattern, API version constants, registry completeness, validate-on-assignment.
- `daemon/tests/test_migrations.py` (Contract #9): file naming, monotonic ordering, required tables present.
- `daemon/tests/test_process_log.py` (Contract #3): rotation constants, log dir creation, timestamp format, list+latest ordering.
- `daemon/tests/test_audit.py` (Contract #11): inserts one row per record, serialises details as JSON.
- `daemon/tests/test_security.py` (Contract #16): refuses on elevation, allows with flag.

#### Changed
- All three version files: `0.1.0.5` → `0.1.1`.
- `daemon/synapse_daemon/__init__.py`: bumped `__version__` to `0.1.1`.

#### Notes
- `npm run typecheck` ✅ · `pytest` (full suite) ✅.
- Next step in the user's review cycle: pause to draft Round 2 design contracts.

## [0.1.0.5] — 2026-05-13

### Design contracts — Round 1 (docs only)

Locked the following 14 design contracts into `AGENTS.md` so they apply to every future milestone. No runtime changes; scaffolding implementation lands in `v0.1.1`.

#### Added
- `AGENTS.md`: renamed "Cross-cutting requirements" to "Design Contracts" and expanded from 2 items to 16. New entries:
  - **#3** Log capture for every managed process (rotating per-process log files + live tail).
  - **#4** Single error envelope (`{code, message, details?, retryable}`) across REST + WS.
  - **#5** WebSocket reconnect protocol with monotonic event IDs + ring buffer replay.
  - **#6** Daemon orphan reconciliation on startup (re-attach / mark-stopped based on `psutil`).
  - **#7** Versioned API surface (`/api/v1/...`, `v1.entity.event`).
  - **#8** Single schema source of truth (Pydantic → TS via `scripts/gen-types.ps1`).
  - **#9** DB migrations from day 1 (numbered SQL files, `schema_migrations` table).
  - **#10** Naming conventions (IDs kebab-case, Python snake_case, TS camelCase, events `noun.verb`).
  - **#11** Audit log table for every state-changing action.
  - **#12** Confirm-before-destructive (with "don't ask again" toggle).
  - **#13** Empty states on every list/grid.
  - **#14** Theming via CSS tokens (no hardcoded colours in components).
  - **#15** No telemetry by default.
  - **#16** Refuse Administrator unless `--allow-admin`.

#### Changed
- `package.json` version: `0.1.0-alpha.1` → `0.1.0.5` (4-component scheme honoured by both PEP 440 and npm-as-non-publisher).
- `pyproject.toml` version: `0.1.0a1` → `0.1.0.5`.
- `daemon/synapse_daemon/__init__.py` `__version__`: same bump.
- `daemon/tests/test_smoke.py`: regex relaxed to allow 4+ component versions.
- `PROGRESS.md`: now lists all 16 contracts as standing requirements.

#### Notes
- `npm run typecheck` ✅ · `pytest` ✅.
- `scripts/version-bump.ps1` only handles 3-component + alpha-tag bumps today; will be updated to support the `.5` design-bump pattern in `v0.1.1`.

## [0.1.0-alpha.1] — 2026-05-13

### Milestone A — Repo scaffolding

#### Added
- Initial folder structure for the three layers: `electron/`, `renderer/`, `daemon/`, `mobile/`, plus `tools/`, `installer/`, `scripts/`.
- Root config files: `package.json`, `pyproject.toml`, `tsconfig.json`, `vite.config.ts`, `tailwind.config.ts`, `postcss.config.js`.
- Docs: `README.md`, `LICENSE` (MIT), `CHANGELOG.md`, `PROGRESS.md`, `AGENTS.md`.
- `.gitignore` covering Node, Python, Electron build artefacts, and OS metadata.
- GitHub Actions CI workflow: lint + typecheck + pytest on every push.
- Dev orchestration script `scripts/dev.ps1` and version-bump helper `scripts/version-bump.ps1`.
- First plugin manifest: `tools/cloudtap/manifest.json` (handler ships in Milestone G).
- Placeholder Electron main, renderer entry, and daemon entry so `npm run typecheck` and `pytest` pass green.

#### Notes
- Repo pushed to GitHub at this commit.
- No runtime functionality yet — full daemon and UI come in Milestones B and C.
