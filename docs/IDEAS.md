# Ideas — Synapse

A living punch list of tools, integrations, and features worth shipping
**eventually**. None are commitments; each entry includes the why, the
honest scope, and a rough effort tag. The user prioritises from here.

Effort tags: `S` < 2 h, `M` 2-6 h, `L` 6-16 h, `XL` an ADR + multi-day.

---

## Handler-tier tools (declarative — drop a manifest, ship)

These live under `tools/<id>/manifest.json` and use the existing
`url.open` / `process.spawn` / `pty.spawn` primitives. No daemon code.

- **`open-folder` (S)** — `process.spawn` of `explorer.exe` / `open` /
  `xdg-open` against the project path. Quick "show me this on disk".
- **`open-vscode-insiders` (S)** — companion to the existing
  `open-in-vscode`; spawn `code-insiders .`.
- **`open-cursor` (S)** — `cursor .` for Cursor users.
- **`open-zed` (S)** — `zed .` for Zed users.
- **`tail-logs` (S)** — `pty.spawn` of `powershell.exe Get-Content
  $log -Wait` (POSIX: `tail -f`). One-click live log tail.
- **`git-status` (S)** — `pty.spawn` of `git status --short` in the
  project cwd.
- **`docker-up` / `docker-down` (S)** — `process.spawn` of
  `docker compose up -d` / `down` in the project cwd. Detects
  `compose.yaml` / `docker-compose.yaml` via `condition` field.
- **`npm-install` (S)** — `pty.spawn` of `npm install` so the user
  can watch progress in xterm.
- **`pip-install-dev` (S)** — `pty.spawn` of `pip install -e ".[dev]"`.

## New primitives (need daemon code; mid-effort)

- **`browser.open` (M)** — open a URL inside an internal browser
  panel (Electron's BrowserView) rather than the user's default
  browser. Useful for quick previews without losing window focus.
- **`http.fetch` (M)** — declarative HTTP call with a templated body
  and a JSONPath-style result picker. Lets a manifest define "ping
  this API and report the JSON field". Removes the *"I had to write a
  Python tool just to GET something"* friction.
- **`sql.query` (L)** — declarative SQL against a registered
  connection. Tied to a per-project connection map; secrets handled
  by the existing DPAPI flow.
- **`file.watch` (L)** — register a `watchdog` observer and emit a
  daemon event when a path changes. Lets tools build on file activity
  without writing their own watcher.

## Integrations (each needs an ADR — `XL`)

- **Ollama** — same pattern as the wbscrper tab (ADR-0005). Detect a
  running ollama server, surface a dedicated tab with model list,
  chat, and pulled-model management. Pre-loads prompts for the
  workbench.
- **Cloudflare** — `cloudflared` tunnels already exist via Cloudtap;
  add Workers / Pages / DNS surfaces if the user starts using them.
- **Postgres / SQLite browser** — declarative `sql.query` primitive
  is the building block; the tab is the surface.
- **Stripe sandbox** — for app dev: list test customers, recent
  webhooks. Read-only.

## Quality-of-life improvements

- ~~Persist sidebar collapsed state~~ — **N/A.** The sidebar uses
  responsive CSS (56px under `sm`, 84px above) with no user toggle.
  No state to persist.
- ~~Cmd palette: project shortcuts~~ — **already shipped.** CommandPalette
  has `Launch <name>` / `Stop <name>` entries; Enter runs them directly.
- ~~Cloudtap one-click URL copy~~ — **already shipped.** ToolCard
  PublicUrl has a dedicated Copy button (1 click) alongside the
  open-in-browser link.
- **Apps page: bulk launch / stop** (M) — selection mode + a small
  toolbar that appears when 1+ tile is selected.
- **Processes page: filter by status chip** (S) — mirror the Apps
  page filter chips.
- ~~Sessions: terminal search overlay~~ — **shipped 2026-06-17.**
  `Ctrl/Cmd+F` while focus is in a Sessions terminal opens a search
  input with Prev/Next/Close buttons; Enter / Shift+Enter cycles
  matches; Esc dismisses. Built on `@xterm/addon-search`.
- ~~Sessions: "restart this session"~~ — **shipped 2026-06-16.** Each
  tab strip has a Restart button (rotate icon) next to the close X.
  Closes the existing PTY then spawns a new one with the same argv;
  the tab's position in the strip is preserved.
- ~~Audit log search~~ — **already shipped.** AuditLogPanel.tsx has
  multi-word filter on entity, action, source, error code.
- **Settings: LAN exposure toggle** (M) — flip the daemon's bind host
  between loopback and 0.0.0.0 from the UI rather than env vars.
- **Mobile: QR code pairing** (M) — render the 6-digit code as a QR
  next to it; phone scans, autofills.

## Accessibility / polish

- ~~Reduced-motion media query~~ — **shipped 2026-06-16.** styles.css
  wraps `.animate-synapse-pulse` / `.animate-spin` / `.animate-pulse`
  + a global animation+transition clamp under `prefers-reduced-motion`.
- ~~Focus trap on Modal~~ — **shipped 2026-06-16.** Modal now cycles
  Tab inside the panel (and Shift+Tab in reverse), restores focus to
  the previously-focused element on close. ConfirmDialog inherits via
  Modal.
- ~~Focus restore on StatusLegend popover~~ — **shipped 2026-06-17.**
  Focus jumps inside the dialog body on open, returns to the trigger
  on close. Only popover-style component that wasn't already inside
  Modal.
- ~~`aria-label` sweep~~ — **partial 2026-06-16.** `ProjectTile` pin
  button + `ToolCard` copy-URL button labelled. Remaining icon-only
  buttons to audit: `FilesPanel` rows, `DiscoveryDialog`,
  `MarketplaceBrowser`.
- ~~Keyboard shortcut help~~ — **shipped 2026-06-16.** `?` from
  anywhere outside an input opens the ShortcutsHelp modal. Grouped
  by scope (Global / Palette / Sessions). Single SHORTCUTS source
  of truth so listings can't drift.

## AI-session improvements

- **AI context: include open files** (S) — when the user has a
  `<FilesPanel>` open with selected files, expose the selection in
  `/ai/context` so a Claude session can `cat` what's on the user's
  screen.
- ~~AI quick-action: "explain this project"~~ — **shipped 2026-06-16**
  as `templates/quick-actions/explain-this-project.json`.
- ~~AI quick-action: "diagnose the failing test"~~ — **shipped
  2026-06-16** as `templates/quick-actions/diagnose-failing-test.json`.
- **Per-project "AI memory"** (M) — let a session write to a known
  scratch file (`$SYNAPSE_FILES/.ai-notes.md`) that future sessions
  read on prompt 1.

## Daemon / infra

- **Boot-time orphan reconciliation already exists** — make the
  resulting events show on the Home recent-activity feed.
- **Per-project log rotation** (M) — current logs grow without bound;
  rotate at 50 MB and keep 5 generations.
- **First-run wizard** (L) — a desktop shortcut, a tray check, a
  daemon health probe, and a "scan a folder" CTA. Currently launching
  Synapse for the first time drops you on an empty Apps page.
- **Snapshot diff** (L) — given two snapshots, show what changed
  (projects added / removed / launch_cmd edited). Existing
  `restore_snapshot` already validates the JSON; reuse the schema for
  the diff.

## Packaging (Milestone J)

- **PyInstaller bundle** for the daemon -> `synapsed.exe`.
- **electron-builder + NSIS** installer.
- **Code-signed binary** so SmartScreen stops nagging.
- **Auto-update** via electron-updater pointing at GitHub Releases.

## Things explicitly NOT on this list

- A generic "render any MCP server as a UI tab" framework. Each
  integration is its own ADR (per ADR-0005's tradeoff section).
- An embedded LLM. Synapse runs AI **CLIs** (Claude, Codex); it does
  not host model weights or hit OpenAI/Anthropic APIs directly. That
  separation is load-bearing for trust + size.
- A second port. Contract: 7878 only.
- A web "marketplace" outside the JSON registry. The marketplace is a
  static list of manifests; no server-side state.
