# Synapse — by The WhatIf Company

**Synapse is a command center for building apps with AI.** It runs on your computer, lets you put multiple AI coding assistants — like **Claude**, **Codex**, and **GitHub Copilot** — to work on your projects, and lets you watch and steer all of it, even from your phone.

Think of it as **mission control** for your projects and your AI helpers, all in one window.

> **Status:** early development (`v0.1.36-dev`). It already launches projects, runs AI coding sessions, and connects from your phone. We're actively building the unified "AI coding cockpit," a shared plan that every AI follows, and a one-click installer. **528 automated tests pass.**

---

## What can I do with it?

- **🚀 Launch & manage your projects** — one place to start, stop, and watch every app or tool you're working on. Close the window and everything keeps running.
- **🤖 Put AI to work** — run Claude, Codex, or Copilot on your code from inside Synapse. Give them a task; they build it. A shared **plan** keeps them all on the same page — one can even hand off to another.
- **👥 Build AI teams ("squads")** — assemble a team of AI workers, each with a **role** (designer, reviewer, tester…) and a **personality**, so they actually collaborate and debate instead of echoing each other.
- **🛒 A marketplace** — install tools, local AI models, MCP servers, workers, and ready‑made teams with one click.
- **📱 Control it from your phone** — pair your phone once, then drive everything remotely over Wi‑Fi (or securely over the internet). Check in or kick off work from anywhere.
- **🧠 A built‑in local AI** — an optional on‑device assistant (via Ollama) so you can work privately, and for free.

## How it works (the simple version)

Synapse has two parts that talk to each other:

1. **The engine** — a small, always‑on background program (a Python "daemon") that does the real work: it launches your apps, runs the AI sessions, and keeps everything alive on port `7878`.
2. **The windows** — the desktop app and the phone view are just *screens* into that engine. You can close them anytime and your work keeps running; open them back up and you're right where you left off.

That's why Synapse is dependable: the screens can come and go, but the engine never drops your work.

## Getting started

**Just want to use it?** Double‑click **`synapse.cmd`** — it starts everything and opens the window. Close the window and it tucks into your system tray; right‑click the tray icon → **Quit Synapse** to fully close. To put a shortcut on your desktop, run **`install-shortcut.cmd`** once.

**Connecting your phone:** in the app open **Settings → Phone Access**, then scan the QR code with your phone. That's it — you're connected.

---

## For developers

```powershell
# one-time setup
npm install
pip install -e ".[dev]"

# checks
npm run typecheck                 # TypeScript passes
(cd daemon && python -m pytest -q) # 528 tests pass + 12 skipped

# run the dev stack (daemon + Vite + Electron)
synapse.cmd
```

Before any AI coder (or you) starts a change, run `pwsh -NoProfile -File scripts/preflight.ps1` — it prints the next ADR/migration numbers to claim and flags if the uncommitted diff is getting too big to be one clean commit.

| Layer | Stack |
|---|---|
| Desktop UI | Electron 31 · Vite · React 18 · TypeScript · Tailwind · shadcn/ui |
| Engine | Python 3.11+ · FastAPI · uvicorn · psutil · Pydantic · SQLite (numbered migrations) |
| Comms | REST + WebSocket on `localhost:7878`, prefixed `/api/v1` |
| Tunnels | Cloudflare (`cloudflared`) for phone‑over‑internet |
| Packaging | PyInstaller (engine) · electron‑builder + NSIS (installer) |

- **Repo conventions, the 28 design contracts, and the cross‑AI workflow** → [`AGENTS.md`](./AGENTS.md)
- **Architecture decisions** → [`docs/adr/`](./docs/adr/) (latest: ADR‑0022, one Synapse + the coding cockpit + the usage‑aware auto‑router)
- **What shipped** → [`CHANGELOG.md`](./CHANGELOG.md) · **Where we are** → [`PROGRESS.md`](./PROGRESS.md) · **Where we're headed** → [`docs/roadmap.json`](./docs/roadmap.json) (also shown in‑app under **What's New**)

### Repo layout

```
electron/   Desktop app shell (Electron main + preload)
renderer/   The React UI (desktop + the phone view)
daemon/     The Python engine — owns all the real work + state
tools/      Drop-in plugins (a folder + a manifest.json, no UI surgery)
docs/       Architecture decisions (adr/), API notes, roadmap
scripts/    Dev, recovery, build, and preflight helpers
installer/  Packaging config
```

### Recovering phone access without the desktop app

If the desktop UI is down but you still have shell access to the machine:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\remote-recovery.ps1
# add -InstallCloudflared the first time if cloudflared isn't installed
```

It starts (or reuses) the engine, opens a Cloudflare tunnel on `7878`, and prints the phone URL + a fresh pairing code.

## License

All rights reserved — see [`LICENSE`](./LICENSE).

---

**Synapse** is a product of **The WhatIf Company** — building the tools that let anyone create software with AI.
