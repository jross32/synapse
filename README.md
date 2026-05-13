# Synapse — by The WhatIf Company

A modular developer command center: one always-on hub for launching projects, managing tools, monitoring live processes, and remoting in from your phone.

> **Status:** `v0.1.0-alpha.1` — Milestone A (scaffolding). See [`PROGRESS.md`](./PROGRESS.md) for the live state of the build.

## What it is

Synapse is the **nucleus** of your dev environment. Instead of juggling terminals to start `wbscrper`, an Ollama chat server, a Cloudflare tunnel, and whatever else, you launch Synapse once at boot and everything is one click away — from your desktop or your phone on the same Wi-Fi.

- **Desktop app** (Electron + React + TypeScript) — primary workstation UI with a system tray icon.
- **Mobile Web UI** — responsive page served by the daemon over LAN; mirrors desktop state in real time.
- **Decoupled Execution Layer** — a Python (FastAPI) daemon owns every spawned process. Close the desktop window, lose your phone connection: everything keeps running.
- **Plugin layout** — new tools drop in as a folder + a `manifest.json`. No UI surgery required.

## Architecture (one paragraph)

The Python daemon (port `7878`) is the only stateful actor. It registers projects, spawns them as detached child processes, monitors them via `psutil`, and broadcasts heartbeat events over a WebSocket. The Electron desktop app and the mobile Web UI are dumb clients — they render whatever the daemon sends and POST commands back. Either client can die at any time without affecting running work.

## v0.1 features

- Project launcher (tiles for `wbscrper` and any future app)
- Live process monitor (PID, start time, uptime, kill button)
- Nucleus + Synapses UI (center workspace + peripheral tool cards)
- Featured slideshow on Home (Microsoft-Store-inspired)
- **Cloudtap** — first built-in tool: enter a port, get a Cloudflare tunnel URL
- Mobile Web UI accessible at `http://<pc-lan-ip>:7878/mobile`
- Auto-start on Windows login, hide-to-tray, right-click → Quit

## Tech stack

| Layer | Stack |
|---|---|
| Desktop UI | Electron 31 · Vite · React 18 · TypeScript · Tailwind CSS · shadcn/ui |
| Execution layer | Python 3.11+ · FastAPI · uvicorn · psutil · Pydantic |
| Storage | SQLite (stdlib) |
| Comms | WebSocket + REST on `localhost:7878` |
| Tunnels | `cloudflared` (shelled out) |
| Packaging | PyInstaller (daemon) · electron-builder (app) · NSIS (installer) |

## Getting started (dev)

```powershell
# One-time setup
npm install
pip install -e ./daemon

# Run dev mode (daemon + Electron together)
.\scripts\dev.ps1
```

See [`AGENTS.md`](./AGENTS.md) for repo conventions (commit rules, version bumps, AI-coding guardrails).

## Roadmap

| Milestone | Status |
|---|---|
| A — Repo scaffolding | 🟡 in progress |
| B — Daemon skeleton | ⚪ pending |
| C — Electron skeleton | ⚪ pending |
| D — Project registry + launcher | ⚪ pending |
| E — Live process monitor | ⚪ pending |
| F — Nucleus + Synapses UI | ⚪ pending |
| G — Cloudtap tool | ⚪ pending |
| H — Mobile Web UI | ⚪ pending |
| I — Auto-start + tray polish | ⚪ pending |
| J — Packaging | ⚪ pending |
| K — v0.1.0 release | ⚪ pending |

## License

MIT — see [`LICENSE`](./LICENSE).

---

**Synapse** is a product of **The WhatIf Company**.
