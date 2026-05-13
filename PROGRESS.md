# Progress — Synapse

**Always read this file first** if you're an AI coding session resuming work. It's the single source of truth for "where are we right now."

---

## Current version

`0.1.0.5`

## Current milestone

**Pre-B contract pass** — locking design contracts before the daemon code begins.

| Version | Phase | Status |
|---|---|---|
| `0.1.0-alpha.1` | Milestone A — scaffolding | ✅ done |
| `0.1.0.5` | Design contracts round 1 (docs) | 🟡 in progress |
| `0.1.1` | Implement contract scaffolding | ⚪ next |
| `0.1.1.5` | Design contracts round 2 (docs) | ⚪ pending |
| `0.1.2` | Implement round 2 scaffolding | ⚪ pending |
| `0.1.3` | Milestone B — daemon skeleton | ⚪ pending |

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

## Design contracts (16 total — full spec in AGENTS.md)

Every milestone must honour all 16. Quick list:

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

---

_Last updated by Milestone A scaffolding._
