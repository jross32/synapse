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

## Cross-cutting requirements (apply to every milestone)

These two design contracts apply to **every** feature, not just one milestone. If you add UI that violates either, fix it before committing.

### 1. Everything must be editable from the UI

Anything the user can configure must have an in-app editor. No "edit the JSON file by hand" UX.

- **Projects/apps:** edit name, icon, thumbnail, working directory, launch command, env vars, expected health-check URL, port, category — from a per-project Settings panel reachable from the tile's right-click / "⋯" menu.
- **Tools (Synapses):** every manifest field is editable in the card's Expanded View. Reordering, hiding, and uninstalling are all UI actions.
- **System settings:** daemon port, auto-start toggle, LAN exposure toggle, theme — all in a `Settings` page.
- **Adding new** projects/tools/scripts: a "+ Add" button in each section that opens a form. Backed by daemon REST endpoints (POST/PATCH/DELETE).
- **Storage:** the daemon's SQLite DB is the source of truth. Tool manifest files under `tools/<id>/manifest.json` are *defaults* on first run; once a tool is registered in the DB, the DB wins. Re-installing or "Reset to defaults" copies the manifest back over.
- **Validation:** every edit form validates inputs and shows inline errors (no silent failure). Pydantic models on the daemon side enforce the contract.

### 2. Live status feedback on every action

The user must never wonder "did it work?" Every action displays a real-time state machine:

```
idle  →  launching  →  launched  →  stopped
              │
              └→  error: <reason>
```

- **State badges** on every tile/card: coloured pill with the current state + a tiny animated spinner during transitions.
- **Toast/inline messages** for one-shot actions (e.g. "Tunnel URL copied", "Project saved").
- **WebSocket-driven**: the daemon broadcasts state changes immediately; the UI never polls.
- **Error display**: failures show the actual error message inline on the tile/card (truncated with "details" expander), not in a modal that requires dismissing. The full stack/log is available from the tile's menu → "View logs".
- **History strip** (per project/tool): last 5 state transitions with timestamps, visible on hover or in the Expanded View.
- **Optimistic UI is forbidden** until daemon acks the action. Clicking "Launch" shows "launching..." (not "launched") until the daemon confirms PID assignment.

These two requirements feed back into the schema: every Pydantic model for a managed entity has `name`, `status`, `last_error`, `updated_at`, `last_transition_at` fields. Every REST endpoint that mutates state returns the new state object so the UI can update without a refetch.

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
