# Progress — Synapse

**Always read this file first** if you're an AI coding session resuming work. It's the single source of truth for "where are we right now."

---

## Current version

`0.1.0-alpha.1`

## Current milestone

**A — Repo scaffolding** 🟡 in progress

## What's done

- [x] Folder structure created at `C:\Users\justi\synapse\`
- [x] Root config files written (`package.json`, `pyproject.toml`, `tsconfig.json`, `vite.config.ts`, `tailwind.config.ts`, `postcss.config.js`)
- [x] Docs written (`README.md`, `LICENSE`, `CHANGELOG.md`, `PROGRESS.md`, `AGENTS.md`)
- [x] `.gitignore` configured
- [x] GitHub Actions CI workflow (`.github/workflows/ci.yml`)
- [x] Dev + version-bump scripts under `scripts/`
- [x] Placeholder Electron main, renderer entry, daemon entry so toolchain runs green
- [x] First plugin manifest: `tools/cloudtap/manifest.json`

## What's next (immediate)

1. **Verify toolchain green:** `npm install`, `pip install -e ./daemon`, `npm run typecheck`, `pytest`. All four must succeed.
2. **Git init + first commit** as `jross32 <justinwross32@gmail.com>` on `main`.
3. **Create GitHub repo** `jross32/synapse` (public) and push.
4. **Move to Milestone B — Daemon skeleton.** Flesh out `daemon/synapse_daemon/app.py` with FastAPI, `/health`, `/ws` echo, SQLite init.

## Known issues / broken state

None right now — Milestone A is intentionally just configs + placeholders. Nothing is wired to run yet.

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

## Cross-cutting requirements (read every session — full spec in AGENTS.md)

1. **Everything is editable from the UI.** Projects, apps, tools, system settings — all reachable from a per-entity edit panel. No "edit the JSON file" UX. DB is the source of truth; manifests are first-run defaults.
2. **Live status feedback on every action.** State machine: `idle → launching → launched → stopped`, plus `error: <reason>`. WebSocket-driven, no polling. Spinners during transitions. Errors inline on the tile, not in modals. State history strip per entity.

Every Pydantic model for a managed entity carries: `name`, `status`, `last_error`, `updated_at`, `last_transition_at`. Every mutating REST endpoint returns the new state object.

---

_Last updated by Milestone A scaffolding._
