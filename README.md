# Synapse — by The WhatIf Company

A modular developer command center: one always-on hub for launching projects, managing tools, monitoring live processes, and remoting in from your phone.

> **Status:** `v0.1.36-dev` — **ADR-0003 workbench expansion complete (Phases A–F) + mobile parity / WAN follow-up verified + first-party Profile hub landed.** Every project has a **Files** surface: drag-drop or pick, browser-side magic-byte inspection before upload, always-on AV via Windows Defender (POSIX: ClamAV) before the bytes land for real. Workbench PTY exits persist their scrollback as transcripts. **ChatGPT export.zip -> markdown**: drop the official OpenAI export into the Apps page header button; each conversation lands as a deterministic `.md` under the auto-created `imported-chatgpt` project, deduped by sha256. **AI Quick-actions** rail on Sessions: one click opens a Claude session in the `scratch` project with the templated prompt pre-loaded as `PROMPT.md` + `SYNAPSE_QUICK_ACTION_PROMPT`. Sessions now also includes a first-pass **Agent Squads** mode: durable planner / implementer / reviewer / researcher templates, explicit handoffs that append to `.synapse-ai-context.md`, and helper workers that stay real PTY sessions instead of hidden background jobs. `/mobile` now serves the full React shell (Home / Apps / Tools / Sessions / Processes / Settings), with paired-device auth, a touch-friendly two-row nav, a one-click LAN -> Cloudtap WAN handoff via **Use on this phone**, and `scripts/remote-recovery.ps1` as a Codex-friendly rescue path that starts/reuses the daemon, opens WAN, and prints the `/mobile` link plus pairing code. Tools → **Discover** now has a viewport-safe category rail with profile-backed favorites/history, and the shell now exposes an optional **Profile hub** for Synapse Accounts native sign-in, Google-ready linking/sign-in, connected-service readiness, host inventory, and synced catalog preferences. `synapse.cmd` now owns full dev restarts end to end, the desktop app self-heals local-token drift instead of sticking on 401s, the packaged daemon now builds into `installer/daemon-dist`, and the daemon resolves bundled tools/templates/mobile assets cleanly from packaged resources. Double-click `synapse.cmd` to launch. Agent Squads now has a guided **Team Builder wizard**, a `boss` / `supervisor` / `worker` role hierarchy with 11 seeded roles, and a **Stop all** kill switch; the Profile hub shows an honest "sync is optional" state when no accounts service is reachable. **437 tests pass + 11 skipped.** Next: email verification / password-reset flows on top of the new accounts service, then Milestone J packaging polish. See [`PROGRESS.md`](./PROGRESS.md) and [`CHANGELOG.md`](./CHANGELOG.md).

## What it is

Synapse is the **nucleus** of your dev environment. Instead of juggling terminals to start `wbscrper`, an Ollama chat server, a Cloudflare tunnel, and whatever else, you launch Synapse once at boot and everything is one click away — from your desktop or your phone on the same Wi-Fi.

- **Desktop app** (Electron + React + TypeScript) — primary workstation UI with a system tray icon.
- **Mobile Web UI** — full renderer-backed phone shell served by the daemon at `/mobile`; mirrors desktop pages in real time and works over LAN or a Cloudtap tunnel.
- **Optional Synapse account hub** — bottom-rail profile surface for first-party Synapse Accounts sign-in, connected-service readiness, host inventory, and synced favorites/history without making Synapse cloud-only.
- **Sessions-centric agent squads** — one visible lead plus helper PTY workers, explicit handoffs, shared project AI memory, and runtime preference routing across Claude / Codex / Copilot-style CLIs.
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
- Mobile Web UI accessible at `http://<pc-lan-ip>:7878/mobile` with direct pairing or LAN -> WAN handoff through Cloudtap
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
python -m pytest -q                  # 437 tests pass + 11 skipped

# Launch (no PowerShell) — double-click synapse.cmd in Explorer, or:
synapse.cmd

# One-time: put a clickable shortcut on your Desktop
install-shortcut.cmd

# PowerShell dev variants are still available:
.\scripts\dev.ps1 -DaemonOnly        # just the daemon (foreground, see boot logs)
```

`synapse.cmd` boots the daemon + Vite + Electron, waits for health checks, and opens the Synapse window. Close the window — it hides to the tray. Right-click the tray icon → **Quit Synapse** to fully exit. Logs land in `data/daemon-runtime.log` and `data/vite-runtime.log`.

### Remote recovery from Codex

If the desktop UI is down but a Codex session still has access to this Windows machine, run the recovery helper. It starts or reuses the daemon, opens Cloudtap on port `7878`, waits for the WAN `/mobile` URL, and prints a fresh pairing code.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\remote-recovery.ps1

# First-use helper when cloudflared is missing:
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\remote-recovery.ps1 -InstallCloudflared
```

Packaged builds ship the same helper under `resources\scripts\remote-recovery.ps1` so a local automation session can recover WAN phone access without opening the desktop app first.

### Inspecting the live Electron app

`scripts/inspect-electron.js` attaches to a running Electron app over the Chrome DevTools Protocol — screenshot it, read its console, click elements. Launch with inspection enabled, then drive it:

```powershell
npx electron . --inspect-renderer          # or set SYNAPSE_INSPECT=1
node scripts/inspect-electron.js screenshot shot.png --full
node scripts/inspect-electron.js console error
node scripts/inspect-electron.js click "Launch"
```

It's app-agnostic — works against any Electron app started with a remote-debugging port.

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
scripts/       PowerShell helpers (dev mode, version bump, type gen, WAN recovery)
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
| D | Project registry + launcher (full CRUD UI) | ✅ done (`v0.1.5`) |
| ⌁ | Clickable launcher + Electron CDP inspector | ✅ done (`v0.1.6`) |
| E | Live process monitor (psutil heartbeat + crash detect + auto-restart) | ✅ done (`v0.1.7`) |
| F | Nucleus + Synapses UI (sidebar, shadcn, plugin system, slideshow) | ✅ done (`v0.1.8` shell · `v0.1.8.5` discovery · `v0.1.9` plugin system · `v0.1.10` slideshow · `v0.1.10.5` snapshot) |
| G | Cloudtap tool (port → tunnel URL) | ✅ done (`v0.1.9`) |
| H | Mobile Web UI (responsive, served by daemon on LAN) | ✅ done (`v0.1.11` device auth · `v0.1.12` mobile UI) |
| I | Auto-start + tray polish (login items, daemon attach-or-spawn, full tray menu) | ✅ done (`v0.1.13`) |
| ⌁ | Polish wave (`Ctrl+K` palette, Apps filter, Open-in-VS-Code / Terminal, audit log, theming, responsive sidebar) | ✅ done (`v0.1.14`–`v0.1.20`) |
| ⌁ | ADR-0001 tool marketplace (hot reload + primitives + Browse + install / uninstall) | ✅ done (`v0.1.21`–`v0.1.24`) |
| ⌁ | ADR-0002 AI workbench (PTY foundation, xterm.js, Claude/Codex bundles, install dialog, *Open in workbench*, `/ai/context`) | ✅ done (`v0.1.25`–`v0.1.29`) |
| ⌁ | ADR-0003 workbench expansion (project files, transcripts, inspection, AV scan, ChatGPT import, AI quick-actions) | ✅ done (`v0.1.30`–`v0.1.34`) |
| J | Packaging (PyInstaller + electron-builder + NSIS installer) | ⚪ pending |
| K | `v0.1.0` release (tag, GitHub release, README screenshots, desktop shortcut) | ⚪ pending |

## License

All rights reserved — see [`LICENSE`](./LICENSE).

---

**Synapse** is a product of **The WhatIf Company**.
