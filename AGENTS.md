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

1. **Every commit bumps a version** via `scripts/version-bump.ps1` (updates `package.json` and `pyproject.toml` together). Even tiny commits — patch bump or alpha increment.
2. **Every commit appends a `CHANGELOG.md` entry** under the in-progress version header.
3. **Every commit updates `PROGRESS.md`** as the last edit before staging. State current milestone, what's done, what's next, any broken state.
4. **Commit author:** `jross32 <justinwross32@gmail.com>`. Don't change git config.
5. **Commit to the current branch.** Never switch branches without being asked.
6. **Commit message format:**
   ```
   vX.Y.Z[-alpha.N]: short subject

   Changed:
   - path/to/file: what changed
   - path/to/other: what changed

   Bugs fixed (if any):
   - ...

   Notes (if any):
   - ...
   ```
7. **Run `npm run typecheck && pytest` before committing.** CI will catch you if you skip.
8. **Never force-push.** Never `reset --hard`. Never bypass hooks (`--no-verify`).

---

## Design Contracts (load-bearing — applies to every milestone)

These 16 contracts are baked into the architecture from v0.1. **Every milestone must honour them.** If a feature can't satisfy a contract, write an ADR in `docs/adr/` before merging — never silently violate.

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
