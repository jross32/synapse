# Changelog

All notable changes to Synapse will be documented in this file.
Format roughly follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
This project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Every commit must append an entry under the in-progress version header.

---

## [Unreleased]

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
