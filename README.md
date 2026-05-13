# Synapse — by The WhatIf Company

A modular developer command center: one always-on hub for launching projects, managing tools, monitoring live processes, and remoting in from your phone.

> **Status:** `v0.1.4` — **Milestone C complete: Synapse opens.** Electron app spawns the Python daemon as a child process, waits for `/api/v1/health`, opens a window with live conn-state badge + the `v1.daemon.started` event visible, and hides to a system tray on close. **117 tests passing.** Next: Milestone D (project launcher). Run `.\scripts\dev.ps1` to see it. See [`PROGRESS.md`](./PROGRESS.md) for the live build state.

## What it is

Synapse is the **nucleus** of your dev environment. Instead of juggling terminals to start `wbscrper`, an Ollama chat server, a Cloudflare tunnel, and whatever else, you launch Synapse once at boot and everything is one click away — from your desktop or your phone on the same Wi-Fi.

- **Desktop app** (Electron + React + TypeScript) — primary workstation UI with a system tray icon.
- **Mobile Web UI** — responsive page served by the daemon over LAN; mirrors desktop state in real time.
- **Decoupled Execution Layer** — a Python (FastAPI) daemon owns every spawned process. Close the desktop window, lose your phone connection: everything keeps running.
- **Plugin layout** — new tools drop in as a folder + a `manifest.json`. No UI surgery required.
- **Editable from the UI** — every project, tool, env var, icon, and setting has an in-app editor. No "edit the JSON file by hand" UX anywhere.
- **Live status feedback** — every action surfaces `idle → launching → launched → stopped → error` in real time over WebSocket. Never wonder "did it work?"

## Architecture (one paragraph)

The Python daemon (port `7878`) is the only stateful actor. It registers projects, spawns them as detached child processes, monitors them via `psutil`, enforces health-checks + restart policies, and broadcasts heartbeat events over a WebSocket with an event-id cursor and a 1 000-event replay ring buffer. The Electron desktop app and the mobile Web UI are dumb clients — they render whatever the daemon sends and POST commands back. Either client can die at any time without affecting running work.

## v0.1 features (planned, in roadmap order)

- Project launcher (tiles for `wbscrper` and any future app)
- Live process monitor (PID, start time, uptime, CPU%, RAM, kill button)
- Nucleus + Synapses UI (center workspace + peripheral tool cards)
- Featured slideshow on Home (Microsoft-Store-inspired)
- **Cloudtap** — first built-in tool: enter a port, get a Cloudflare tunnel URL
- Mobile Web UI accessible at `http://<pc-lan-ip>:7878/mobile`
- Universal `Ctrl+K` search palette
- Auto-start on Windows login, hide-to-tray, right-click → Quit
- `synapse` CLI for shell users (mirrors REST 1-to-1)
- Snapshot / restore (single JSON dump → fresh-install portability)

## Design contracts (28)

Every milestone honours all 28 contracts. Full spec lives in [`AGENTS.md`](./AGENTS.md); summary here:

**Round 1 — fundamentals (`v0.1.0.5` docs · `v0.1.1` code):**

1. Everything editable from the UI · 2. Live status feedback · 3. Log capture per managed process · 4. Single error envelope · 5. WebSocket reconnect + replay protocol · 6. Daemon orphan reconciliation · 7. Versioned API (`/api/v1`) · 8. Single schema source of truth (Pydantic → TS) · 9. DB migrations from day 1 · 10. Naming conventions · 11. Audit log · 12. Confirm-before-destructive · 13. Empty states everywhere · 14. Theming via CSS tokens · 15. No telemetry by default · 16. Refuse Administrator

**Round 2 — operational depth (`v0.1.1.5` docs · `v0.1.2` code):**

17. Health-check protocol per project · 18. Restart policy per project · 19. Resource observability (CPU + RAM per process) · 20. Project dependencies (topological launch) · 21. Universal search / `Ctrl+K` palette · 22. Native system notifications · 23. Accessibility minimums (WCAG AA + keyboard nav + ARIA) · 24. Timestamps UTC in DB, local in UI · 25. Secrets management (DPAPI on Windows, never logged) · 26. Hot manifest reload · 27. CLI surface · 28. Snapshot / restore

## Tech stack

| Layer | Stack |
|---|---|
| Desktop UI | Electron 31 · Vite · React 18 · TypeScript · Tailwind CSS · shadcn/ui |
| Execution layer | Python 3.11+ · FastAPI · uvicorn · psutil · Pydantic · watchdog · cryptography |
| Storage | SQLite (stdlib) with numbered migrations |
| Comms | WebSocket + REST on `localhost:7878`, prefixed `/api/v1` |
| Tunnels | `cloudflared` (shelled out) |
| Packaging | PyInstaller (daemon) · electron-builder (app) · NSIS (installer) |

## Getting started (dev)

```powershell
# One-time setup
npm install
pip install -e ".[dev]"
python scripts/gen-icon.py          # generate tray + window icons (idempotent)

# Verify toolchain
npm run typecheck                    # TypeScript checks pass
python -m pytest -q                  # 117 tests pass (1 platform-conditional skip)

# Full dev mode — daemon + Vite + Electron window
.\scripts\dev.ps1

# Variations
.\scripts\dev.ps1 -DaemonOnly        # just the daemon (foreground, see boot logs)
.\scripts\dev.ps1 -AppOnly           # just Vite + Electron (assumes daemon is up)
.\scripts\dev.ps1 -BindLan           # daemon listens on 0.0.0.0 so phones can reach it
```

After running `.\scripts\dev.ps1` you should see: daemon log lines in the console, a Synapse window with the `v1.daemon.started` event visible, and a tray icon. Close the window — it hides to tray. Right-click the tray icon → **Quit Synapse** to actually exit.

After Milestone J ships, end users will install a single `.exe` instead of running scripts.

## Repo layout

```
electron/      Electron main + preload (TypeScript)
renderer/      React UI shown inside Electron
mobile/        Responsive Web UI served by the daemon to phones
daemon/        Python (FastAPI) execution layer — owns all state
tools/         Plugin manifests (drop in a folder, no UI surgery needed)
docs/          api-changes.md, security.md, adr/
installer/     PyInstaller + electron-builder + NSIS configs (Milestone J)
scripts/       PowerShell helpers (dev mode, version bump, type gen)
```

See [`AGENTS.md`](./AGENTS.md) for repo conventions (commit rules, version bumps, AI-coding guardrails, plugin layout, design contracts).

## Roadmap

| Milestone | Outcome | Status |
|---|---|---|
| A | Repo scaffolding | ✅ done (`v0.1.0-alpha.1`) |
| ⌁ | Round 1 design contracts (#1–#16) | ✅ done (`v0.1.0.5` docs · `v0.1.1` code) |
| ⌁ | Round 2 design contracts (#17–#28) | ✅ done (`v0.1.1.5` docs · `v0.1.2` code) |
| ⌁ | Commit-rule hardening + README sync | ✅ done (`v0.1.2.5`) |
| B | Daemon skeleton (FastAPI on `:7878`, `/health`, WS echo, SQLite + migration runner) | ✅ done (`v0.1.3`) |
| C | Electron skeleton (window, tray, daemon spawn, WS connect) | ✅ done (`v0.1.4`) |
| D | Project registry + launcher (full CRUD UI) | 🟡 next |
| E | Live process monitor (psutil heartbeat + state badges) | ⚪ pending |
| F | Nucleus + Synapses UI (sidebar, cards, slideshow, theming) | ⚪ pending |
| G | Cloudtap tool (port → tunnel URL) | ⚪ pending |
| H | Mobile Web UI (responsive, served by daemon on LAN) | ⚪ pending |
| I | Auto-start + tray polish (login items, detached daemon, full tray menu) | ⚪ pending |
| J | Packaging (PyInstaller + electron-builder + NSIS installer) | ⚪ pending |
| K | `v0.1.0` release (tag, GitHub release, README screenshots, desktop shortcut) | ⚪ pending |

## License

MIT — see [`LICENSE`](./LICENSE).

---

**Synapse** is a product of **The WhatIf Company**.
