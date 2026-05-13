# AGENTS.md — Synapse

Repo conventions for AI coding sessions (Claude, Copilot, Codex, etc.). Read [`PROGRESS.md`](./PROGRESS.md) first to know where the project is.

---

## Golden rule

**Never leave the repo broken.** If you can't finish a milestone in one session, finish a *commit* that compiles, typechecks, and passes tests. Then update `PROGRESS.md` to record what's left.

---

## Repo layout (high level)

```
electron/   Electron main + preload (TypeScript)
renderer/   React UI shown inside Electron
mobile/     Responsive Web UI served by the daemon to phones
daemon/     Python (FastAPI) execution layer — owns all state
tools/      Plugin manifests (drop in a folder, no code surgery needed)
installer/  PyInstaller + electron-builder + NSIS configs (Milestone J)
scripts/    PowerShell helpers (dev mode, version bump)
```

Decoupling rule: **the desktop UI and mobile UI are clients, not orchestrators.** The Python daemon is the only stateful actor.

---

## Code style

```js
const STYLE = {
  indentation:   'spaces',
  indentSize:    2,
  quotes:        'single',
  semicolons:    true,
  trailingComma: 'es5',
  maxLineLength: 120,
};
```

Match the surrounding file when editing existing code. These are defaults for new files.

Python: PEP 8, 4-space indent, double quotes for docstrings, single for strings. Type hints required on all public functions. Pydantic models for everything crossing the daemon ↔ client boundary.

---

## Commit rules (non-negotiable)

1. **Every commit bumps a version** via `scripts/version-bump.ps1` (updates `package.json`, `pyproject.toml`, and `daemon/synapse_daemon/__init__.py` together).
   - Docs-only commits use `-Kind design` (`X.Y.Z` → `X.Y.Z.5`).
   - Code commits use `-Kind patch | minor | major`.
2. **Every commit appends a `CHANGELOG.md` entry** under the in-progress version header. Group by Added / Changed / Fixed / Notes.
3. **Every commit updates `PROGRESS.md`** as the last edit before staging. State current version, current milestone, what's done, what's next, any broken state.
4. **Every commit syncs `README.md`** when any of these change:
   - Current version, milestone, or test count.
   - The roadmap status of any milestone.
   - Tech-stack table (deps added/removed/version-bumped).
   - Top-level features advertised in the feature list.
   - Getting-started commands.

   If unsure whether README needs an edit, open it and check — staleness is much worse than an unnecessary edit.
5. **Every commit syncs the affected docs in `docs/`**:
   - New REST endpoint or WS event → `docs/api-changes.md`.
   - Security-related change → `docs/security.md`.
   - New CLI command → README's CLI section + this file's CLI table.
   - Architectural decision that touches a contract → new `docs/adr/NNNN-*.md`.
6. **Commit author:** `jross32 <justinwross32@gmail.com>`. Don't change git config.
7. **Commit to the current branch.** Never switch branches without being asked.
8. **Commit message format:**
   ```
   vX.Y.Z[.5]: short subject

   Changed:
   - path/to/file: what changed
   - path/to/other: what changed

   Bugs fixed (if any):
   - ...

   Notes (if any):
   - ...
   ```
9. **Run `npm run typecheck && pytest` before committing.** CI will catch you if you skip.
10. **Never force-push.** Never `reset --hard`. Never bypass hooks (`--no-verify`).

### Docs-sync pre-flight (run mentally before every commit)

> Open `README.md` and `PROGRESS.md`. Does the **first 30 lines** of each still accurately describe the repo after my change? If no, edit them now.

If a commit ever ships with a stale README header, that's a regression — open a follow-up commit immediately.

---

## Design Contracts (load-bearing — applies to every milestone)

These 28 contracts are baked into the architecture from v0.1. **Every milestone must honour them.** If a feature can't satisfy a contract, write an ADR in `docs/adr/` before merging — never silently violate.

Round 1 (#1–#16) locked in `v0.1.0.5`, scaffolded in `v0.1.1`.
Round 2 (#17–#28) locked in `v0.1.1.5`, scaffolded in `v0.1.2`.

### 1. Everything must be editable from the UI

Anything the user can configure must have an in-app editor. No "edit the JSON file by hand" UX.

- **Projects/apps:** edit name, icon, thumbnail, working directory, launch command, env vars, health-check URL, port, category — from a per-project Settings panel reachable from the tile's right-click / "⋯" menu.
- **Tools (Synapses):** every manifest field editable in the card's Expanded View. Reordering, hiding, and uninstalling are all UI actions.
- **System settings:** daemon port, auto-start toggle, LAN exposure, theme, update channel — all in a `Settings` page.
- **Adding new:** "+ Add" button in each section opens a form. Backed by daemon REST (POST/PATCH/DELETE).
- **Storage:** the daemon's SQLite DB is the source of truth. Tool manifests under `tools/<id>/manifest.json` are *defaults* on first run; the DB wins after that. "Reset to defaults" re-copies the manifest.
- **Validation:** every edit form validates inputs and shows inline errors. Pydantic models enforce the contract server-side.

### 2. Live status feedback on every action

The user must never wonder "did it work?" Every action displays a real-time state machine:

```
idle  →  launching  →  launched  →  stopped
              │
              └→  error: <reason>
```

- **State badges** on every tile/card: coloured pill + animated spinner during transitions.
- **Toast/inline messages** for one-shot actions ("Tunnel URL copied", "Project saved").
- **WebSocket-driven**: the daemon broadcasts state changes immediately; UI never polls.
- **Error display**: failures show the actual error inline on the tile (truncated with "details" expander). Full log via tile menu → "View logs".
- **History strip**: last 5 state transitions with timestamps, visible on hover or in Expanded View.
- **No optimistic UI** until daemon acks. "Launch" → "launching…" → "launched" only after daemon confirms PID assignment.

Every Pydantic model for a managed entity carries: `name`, `status`, `last_error`, `updated_at`, `last_transition_at`. Every mutating REST endpoint returns the new state object.

### 3. Log capture for every managed process

Daemon tees stdout + stderr of every spawned child to `data/logs/<entity-id>/<timestamp>.log` with rotation (10 MB × 5 files). Every tile has a "View logs" button: opens latest file + a live-tail mode streamed over WebSocket. **No process is launched without a log file behind it.**

### 4. Single error envelope

All REST 4xx/5xx responses and all WS error events use one Pydantic model:

```python
class ErrorEnvelope(BaseModel):
    code: str          # machine-readable, e.g. "project.not_found"
    message: str       # human-readable
    details: dict | None = None
    retryable: bool = False
```

UI has one `<ErrorBanner code={...}>` component handling every failure. No ad-hoc error shapes anywhere.

### 5. WebSocket reconnect protocol

Daemon assigns monotonically increasing IDs to every broadcast and keeps the last 1 000 events in a ring buffer. Client tracks `lastEventId`; on reconnect it sends `{"since": <id>}` and daemon replays missed events. Reconnect backoff: 1s, 2s, 4s, 8s, max 30s. UI shows a "reconnecting…" badge during gaps. **Never silently desync.**

### 6. Daemon orphan reconciliation

On daemon startup, before accepting any client connections, the daemon scans the DB's `managed_processes` table for non-terminal rows. For each, it calls `psutil.pid_exists` and `psutil.Process(pid).cmdline()`:

- Alive AND cmdline matches → re-attach (resume monitoring).
- Alive but cmdline differs → mark `stopped` with reason `pid-recycled`.
- Dead → mark `stopped` with reason `daemon-restart`.

This is what makes the "processes persist past UI death" promise actually survive a daemon restart.

### 7. Versioned API surface

REST is `/api/v1/...`; WS events are `v1.entity.event` from day 1. Breaking changes require a new version prefix + a documented migration in `docs/api-changes.md`. Old versions stay alive ≥ one minor release after deprecation.

### 8. Single schema source of truth

Daemon's Pydantic models are the canonical schema. `scripts/gen-types.ps1` exports them to `renderer/lib/generated-types.ts`. UI imports those types — never hand-maintains parallel ones. CI fails if `generated-types.ts` is stale.

### 9. DB migrations from day 1

Every schema change is a numbered migration file: `daemon/synapse_daemon/migrations/<NNN>_<slug>.sql`. Daemon runs unapplied migrations on startup against a `schema_migrations` table. **Never edit a shipped migration** — always add a new one.

### 10. Naming conventions

- **IDs:** kebab-case (`web-scraper`, `cloudtap`, `ollama-chat`)
- **Python:** PascalCase classes, snake_case fields, snake_case modules
- **TypeScript:** PascalCase types, camelCase fields, kebab-case files
- **WS events:** `noun.verb` (`project.launched`, `tool.errored`, `process.heartbeat`)
- **REST:** noun-plural + HTTP verb (`POST /api/v1/projects`, `GET /api/v1/projects/{id}/logs`)
- **DB tables:** snake_case plural (`managed_processes`, `audit_log`)

### 11. Audit log

Every state-changing action writes to `audit_log`: `id, timestamp_utc, entity_type, entity_id, action, source (desktop/mobile/tray/cli/auto), result, error_code, details`. UI surface: `Settings → Audit`. Never auto-delete rows; manual export + truncate only.

### 12. Confirm-before-destructive

Kill process, delete project, uninstall tool, reset config, "stop all" — every destructive action goes through a confirm dialog showing **exactly** what will happen, with a "Don't ask again for this action" checkbox stored per-user.

### 13. Empty states everywhere

Every list/table/grid renders something useful at zero items: one-line description + primary CTA + learn-more link. No blank pages. No spinner that never resolves. Every fetch has loading + error + empty + populated states.

### 14. Theming via CSS tokens

No hardcoded colour, spacing, or font values in components. Tokens live in `renderer/lib/theme-tokens.css` (e.g. `--synapse-bg-nucleus`, `--synapse-text-primary`). Dark is default (no class on root); light = `class="light"` on `<html>`. Future themes drop in without touching components.

### 15. No telemetry by default

The daemon makes zero outbound calls except when:

- A user-triggered action requires it (Cloudtap, a project running its own HTTP).
- The user has explicitly opted in to update checks (off by default).

No analytics, no error reporting service, no "phone home." If telemetry is ever added, it must be opt-in with full disclosure of what's sent.

### 16. Refuse Administrator

Daemon refuses to start as Administrator (Windows: elevated token) unless `--allow-admin` is passed. Documented in `docs/security.md`. Prevents an entire class of "managed process inherits elevation" bugs.

### 17. Health-check protocol per project

Every project manifest declares one health probe:

```python
class HealthProbe(BaseModel):
    kind: Literal["none", "http", "tcp", "command"]
    target: str | None = None       # URL, port, or shell command
    interval_seconds: int = 15
    timeout_seconds: int = 5
    expect_status: int | None = 200  # HTTP only
```

Daemon polls the probe on the declared interval and surfaces a **separate** `health` field alongside `status`. The state-machine is independent:

```
health:  unknown  →  healthy  →  degraded  →  unhealthy
```

UI shows a second pill on every tile. A process can be `status=launched` AND `health=unhealthy` (alive but hung) — Synapse must not lie that it's working.

### 18. Restart policy per project

Manifest field controls automatic recovery:

```python
class RestartPolicy(BaseModel):
    mode: Literal["never", "on-failure", "always"] = "never"
    max_retries: int = 3
    initial_backoff_seconds: int = 2
    max_backoff_seconds: int = 60
```

Daemon's process manager consults this on every child exit. Audit log records every restart attempt with attempt-number + delay. UI shows "restarting (attempt 2/3)" as a transitional status. Default `never` — autonomous restarts are opt-in.

### 19. Resource observability per process

`v1.process.heartbeat` events carry `cpu_percent` (0–100, system-normalised) and `rss_mb` per managed PID, broadcast on the daemon's heartbeat cadence. Tiles render mini-gauges. Manifests can declare soft caps:

```python
max_rss_mb: int | None
max_cpu_percent: int | None
```

Exceeding a cap raises an `over-budget` warning (not a stop) until the user decides.

### 20. Project dependencies

Manifest field `requires: [other-project-id]` declares hard prerequisites. Launching A:

1. Topologically resolves the dependency graph.
2. If any required project is `stopped`, daemon shows a confirm: "Launching A will also launch: B, C. Proceed?".
3. Spawns dependencies first, awaits each `health=healthy` (or `launched` if `health=none`), then spawns A.
4. Cycle detection: if a cycle is detected, launch is refused with `project.dependency_cycle`.

Stopping a project asks whether to also stop its now-orphaned dependencies.

### 21. Universal search / Ctrl+K command palette

A single keyboard-accessible palette indexes every project, tool, action, and setting:

- Keybind: `Ctrl+K` (Windows/Linux), `Cmd+K` (Mac). Reserved permanently.
- Daemon exposes `GET /api/v1/search?q=<query>` returning typed hits (`project | tool | action | setting`).
- Each entity must declare a `search_tokens` field on its model (auto-populated from `id`, `name`, `category`, `tags`) so the index never misses obvious matches.
- Mobile UI surfaces the same palette via a top-bar icon.

### 22. Native system notifications

Daemon emits a structured `v1.notification` event whenever:

- A managed process crashes or its `health` flips to `unhealthy`.
- A tunnel goes live or dies.
- A scheduled launch fires or fails.
- A user-flagged error occurs.

Electron renders these as Windows toast notifications. **Per-event opt-out** stored in the `notification_preferences` table — never globally muted by default. Mobile users opt in to Web Push separately (v0.2+).

### 23. Accessibility minimums

- **Contrast:** WCAG AA — already covered by `theme-tokens.css` ratios.
- **Focus:** every interactive element has a visible focus ring using `--synapse-accent`. No `outline: none` without a replacement.
- **ARIA:** every icon-only button has `aria-label`; every status badge has `aria-live="polite"`; every modal traps focus and restores on close.
- **Keyboard:** every action reachable via keyboard. Standard shortcuts: `Tab` (next), `Shift+Tab` (prev), `Enter` (activate), `Esc` (close), `Ctrl+K` (palette, #21).
- **Reduced motion:** already respected via `@media (prefers-reduced-motion: reduce)` in tokens.

Codified here so AI sessions can't silently regress. Add `eslint-plugin-jsx-a11y` in Milestone C.

### 24. Timestamps UTC in DB, local in UI

**Storage layer:** every timestamp column is timezone-aware UTC. Pydantic models use `datetime` with `tzinfo=timezone.utc`. SQLite stores ISO 8601 strings (`2026-05-13T14:22:05.123456+00:00`).

**Transport layer:** REST + WS always send UTC ISO 8601.

**Render layer:** UI is the only place that converts to the user's local timezone, via `Intl.DateTimeFormat`. Components must call a shared `formatLocal(ts, kind)` helper — never call `new Date(ts).toLocaleString()` directly. One rule, no exceptions.

### 25. Secrets management

Project manifests can declare env vars as secret:

```python
class EnvVar(BaseModel):
    key: str
    value: str | None = None      # plaintext OR "(set)" placeholder on read
    secret: bool = False
```

Storage rules:

- Secret values stored in `project_secrets` table, encrypted with Windows DPAPI scoped to the daemon's user account. Plaintext never written to disk in any other location (logs included).
- After the initial save, `GET /api/v1/projects/{id}` returns `value: "(set)"` for secrets — never plaintext.
- Audit log entries that record an env-var change record only `key` + `redacted_value: true`. The value never enters the audit log.
- Spawning a child injects the decrypted value into the child's environment only — never logged, never broadcast.

### 26. Hot manifest reload

A file watcher (Python `watchdog`) monitors `tools/` and every registered project's manifest path. On change:

1. Daemon reloads the manifest, validates against the Pydantic schema.
2. If valid: updates the DB record, emits `v1.manifest.reloaded` with the entity id.
3. If invalid: keeps the old version, emits `v1.manifest.error` with an `ErrorEnvelope`.

UI shows a small "manifests reloaded" banner with a "view changes" link. No daemon restart required to add/edit a tool.

### 27. CLI surface

The `synapse` command (installed alongside the daemon, same Python entry point) is a thin client over the daemon's REST API. Commands map 1-to-1 with endpoints:

| Command | Endpoint |
|---|---|
| `synapse list` | `GET /api/v1/projects` |
| `synapse status [id]` | `GET /api/v1/projects/{id}` or aggregate |
| `synapse start <id>` | `POST /api/v1/projects/{id}/launch` |
| `synapse stop <id>` | `POST /api/v1/projects/{id}/stop` |
| `synapse logs <id> [-f]` | `GET /api/v1/projects/{id}/logs` (stream if `-f`) |
| `synapse snapshot` | `POST /api/v1/snapshot` |
| `synapse restore <path>` | `POST /api/v1/restore` |
| `synapse doctor` | local diagnostics, no daemon needed |

The CLI never talks directly to the DB — always via the daemon, so single source of truth is preserved.

### 28. Snapshot / restore

`POST /api/v1/snapshot` returns a single JSON file containing:

```json
{
  "synapse_version": "0.1.0",
  "schema_version": 7,
  "exported_at": "2026-05-13T...",
  "projects": [...],
  "tools": [...],
  "settings": {...},
  "audit_log_tail": [...]
}
```

`POST /api/v1/restore` accepts the same shape and either creates fresh entities or merges by id (user chooses). **Secrets are NOT included** in snapshots — restoring on a new machine surfaces a list of secrets the user must re-enter.

Snapshots are the disaster-recovery story and the cross-machine portability story rolled into one. Stable schema today makes this trivial; sprawling schema later makes it weeks of work.

---

## Plugin contract — adding a new tool

A "Synapse" (tool card) is **one folder under `tools/`** with a `manifest.json` and a Python handler. Example:

```
tools/
└── my-new-tool/
    ├── manifest.json
    └── handler.py
```

The UI renders it automatically. **You do not edit `renderer/pages/Tools.tsx` to add a tool.** If you find yourself wanting to, the manifest schema needs extending instead.

Project (launchable app) manifests live in the daemon's SQLite DB and are seeded from `daemon/synapse_daemon/seed_projects.py`. wbscrper is the seed example.

---

## File sensitivity

| Path | Status | Why |
|---|---|---|
| `daemon/synapse_daemon/process_manager.py` | **Fragile** | Detached spawn + psutil tracking is subtle; breaking it kills the persistence guarantee |
| `electron/main.ts` | **Fragile** | Tray + window lifecycle + login items — easy to make the app un-quittable or invisible |
| `daemon/synapse_daemon/ws.py` | **Fragile** | WebSocket hub broadcasts to all clients; bugs here break real-time sync |
| `renderer/components/Nucleus.tsx` | Stable | Layout pivot; explain risk before restructuring |
| `tools/*/manifest.json` | Stable | Drop-in; safe to add new ones |
| `scripts/version-bump.ps1` | **Fragile** | Two version files must stay in lock-step |

"Fragile" = explain risk before touching, test after changes.

---

## Forbidden

- Don't add a second port (we use 7878 only — daemon allocates any others it needs).
- Don't make the desktop UI hold state the daemon doesn't know about.
- Don't introduce a third runtime (no Go, no Rust, no Bun) without an ADR in `docs/`.
- Don't add a tool by editing UI source — write a manifest.
- Don't change `commitAuthor` in git config.
- **Don't put non-ASCII characters in PowerShell `.ps1` files.** Windows PowerShell 5.1 reads `.ps1` files as Windows-1252 unless they start with a UTF-8 BOM, and several authoring tools used in this project do not emit a BOM. Multi-byte characters get split into garbled bytes that break the parser with errors like *"String is missing the terminator"* — exactly the failure mode that bit `v0.1.5`. Allowed substitutions:
  - `→` / `←` → `->` / `<-`
  - `—` (em-dash) → `--`
  - `•` (bullet) → `*` or `-`
  - `═` (box drawing) → `=`
  - `…` → `...`
  - `·` → `|` or `-`

  CI should `grep -P '[^\x00-\x7F]' scripts/*.ps1` and fail if any matches appear. Daemon Python files may use UTF-8 freely (Python 3 reads source as UTF-8 by default) **except** in strings that are written to stdout or to a console log — those should also stay ASCII, since Windows console encoding defaults to cp1252 and renders multi-byte UTF-8 as `�`.

---

## Security

- The daemon binds `0.0.0.0:7878` so the phone on LAN can reach it. **This means anyone on your network can hit it.** For v0.1 this is acceptable (home LAN). Mobile auth (PIN or device pairing) is on the v0.2 list.
- Never commit secrets. The daemon stores nothing sensitive by default.
- Cloudtap exposes a local port to the public internet via Cloudflare. **Warn the user** in the UI when they're about to tunnel a port that looks sensitive (e.g. anything running on `localhost` that isn't behind auth).

---

## When you're stuck

1. Read `PROGRESS.md`.
2. Read the relevant milestone's "Critical files" section in the plan at `C:\Users\justi\.claude\plans\how-is-it-that-staged-meteor.md`.
3. Run `npm run typecheck` and `pytest` to see what's actually broken.
4. If the work won't fit in your remaining tokens, commit what compiles and update `PROGRESS.md` with a clear "next session: do X" line.
