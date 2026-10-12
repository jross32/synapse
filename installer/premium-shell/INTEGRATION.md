# Synapse Premium Installer Shell — Integration Guide

## What this is

`installer/premium-shell/` is a **fully isolated** HTML/CSS/JS installer UI that implements the eight-screen Synapse setup wizard. It has zero dependencies on the main Electron/React build and does not modify any existing files.

The existing NSIS installer engine (via electron-builder) is **preserved untouched**. This shell provides the visual layer only.

---

## Directory layout

```
installer/premium-shell/
├── index.html          ← single-page installer app (all 8 screens)
├── installer.css       ← complete styling (~500 lines, no framework)
├── installer.js        ← screen logic, real system checks, progress sim
├── assets/
│   └── brain.svg       ← standalone SVG brain artwork
├── scripts/
│   └── capture-screenshots.js  ← Playwright screenshot script
├── screenshots/        ← output of capture-screenshots.js (gitignored)
├── serve.cjs           ← minimal local HTTP server (port 3457)
├── package.json        ← devDep: playwright (resolved from root node_modules)
└── INTEGRATION.md      ← this file
```

---

## Screens

| # | ID | Hash | Content |
|---|----|----|---------|
| 1 | welcome | `#screen-1` | Hero + feature chips + "Begin Setup" CTA |
| 2 | install-type | `#screen-2` | Standard / Custom cards + install path |
| 3 | system-check | `#screen-3` | 6 real browser-API checks with live status |
| 4 | install-progress | `#screen-4` | Animated progress bar + step log |
| 5 | account-signin | `#screen-5` | Email/password form + skip option |
| 6 | completion | `#screen-6` | Success animation + install summary |
| 7 | whats-new | `#screen-7` | Categorised changelog for v0.1.217 |
| 8 | launch | `#screen-8` | Launch button + startup checkbox + community links |

---

## Real system checks (Screen 3)

All checks use live browser APIs — **nothing is faked**:

| Check | API used |
|-------|----------|
| Operating System | `navigator.userAgent` |
| Available Memory | `navigator.deviceMemory` |
| Disk Space | `navigator.storage.estimate()` |
| Network | `navigator.onLine` + `navigator.connection` |
| Display Resolution | `window.screen.width/height` |
| Hardware Acceleration | `canvas.getContext('webgl2')` + `WEBGL_debug_renderer_info` |

---

## Running locally

```powershell
# From repo root:
cd installer/premium-shell

# Start the dev server (port 3457):
node serve.cjs

# Open in browser:
start http://localhost:3457
```

---

## Capturing screenshots (Playwright)

```powershell
# From installer/premium-shell/:
node scripts/capture-screenshots.js
```

Outputs `screenshots/screen-{1..8}-{name}.png` at 780×576 px.
Playwright is resolved from the **root** `node_modules/playwright` (already installed) — no extra install needed.

---

## Integration with electron-builder (safe path)

This shell is **additive** — it does not replace the existing NSIS engine or touch `package.json` `build` config.

### Option A: Electron window installer (recommended)

During the NSIS extraction phase, launch a separate Electron window loading `installer/premium-shell/index.html`. The JS uses `window.electronAPI` / IPC to drive actual install actions. Wire IPC calls to:

- Screen 2 → read/write install path via `dialog.showOpenDialog`
- Screen 3 → run real checks via `child_process` / `fs.statfs`
- Screen 4 → progress events from the NSIS/electron-builder extraction
- Screen 5 → call auth API

### Option B: NSIS page plugin (nsDialogs / nsNHTML)

Embed the HTML directly in NSIS via the `nshtml` plugin (or `nsDialogs` with an IE/WebView2 shell). Map NSIS variables (`$INSTDIR`, `$OUTDIR`) to the JS via `window.__nsParams`. This requires `nshtml.dll` and WebView2 runtime present.

### Option C: Standalone preview / marketing

Use the shell as-is for install flow mockups, screenshots, or documentation without touching the real installer. This is the current state.

---

## Current status

- [x] All 8 screens implemented and interactive
- [x] Real browser-API system checks
- [x] Animated progress bar with step log
- [x] Sign-in form with validation and skip
- [x] Hash-based routing for Playwright screenshot capture
- [x] Playwright screenshot script
- [x] Local dev server
- [ ] IPC bridge to Electron main process (needed for production wiring)
- [ ] Real disk space check from native `fs.statfs` (browser API is quota, not drive free space)
- [ ] NSIS nshtml plugin integration (requires Windows build environment evaluation)
- [ ] Signed commit + CHANGELOG entry (pending integration decision)

---

## Design tokens

```
Background:  #020509 / #050810 / #0d1229
Accent 1:    #22d3ee  (cyan)
Accent 2:    #8b5cf6  (purple)
Text:        #f1f5f9 / #94a3b8 / #475569
Success:     #10b981
Warning:     #f59e0b
Error:       #ef4444
Window:      780 × 576 px (36px chrome + 488px content + 52px footer)
Font:        Segoe UI / system-ui (no external fonts)
```
