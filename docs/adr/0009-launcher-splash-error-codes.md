# ADR-0009 — Launcher splash + error code catalogue

Date: 2026-06-20
Status: Proposed (gated on user "go" per phase)
Related: `plans/how-is-it-that-staged-meteor.md`, ADR-0008 (workspace layout)

## Context

Today launching Synapse runs a PowerShell script that prints
``Synapse — launching daemon + Vite + Electron`` followed by
``[1/4] Starting daemon …`` / ``[2/4] Compiling Electron main …`` /
``[3/4] Starting Vite dev server …`` / ``[4/4] Opening Synapse
window …`` in a terminal window. Functional but ugly. Users see the
raw CLI before the Electron window appears, and when one of the four
steps fails the message is a Python traceback with no actionable
guidance.

The user wishlist:

1. A **proper splash screen** with the Synapse logo, an animated
   typing-style phrase generator ("Starting up", "Hold your horses",
   "Making magic", etc.), a real-time progress bar, and a concrete
   sub-line ("Starting daemon", "Loading marketplace").
2. **Phrases time-keyed**: early ones are reassuring + literal, later
   ones are playful so a slow start doesn't feel broken.
3. **Failure codes** -- something like ``SYN-DAEMON-001`` with a
   one-line meaning the user can google or paste to support.

## Decision

Three-phase implementation. Each gated on user "go".

### L1 -- Electron splash window

When Electron boots:

1. Create a small (480x320) frameless `BrowserWindow` loading a
   bundled `splash.html` from `dist/electron/splash.html`.
2. Spawn the daemon + Vite *children* with a JSON-line protocol to
   stdout, e.g. ``{"step":"daemon","status":"starting","pct":12}``.
3. Forward those status lines to the splash window via IPC
   (`synapse:splash-update`).
4. When the renderer is ready (existing `ready-to-show` event on the
   main window), fade the splash out + reveal the main window.

This replaces the bare CLI flow for **Electron**. The `synapse.cmd`
PowerShell entry point stays for power users + CI.

### L2 -- Animated phrases + progress

Splash HTML ships **one** `index.html` with:

- **Logo** centred top (svg, animated draw on first paint).
- **Phrase row**: typewriter animation. Phrases scheduled by elapsed
  time -- 0-2 s "Starting up", 2-5 s "Booting the daemon", 5-10 s
  "Hold your horses", 10-20 s "Making magic", 20-40 s "Almost
  there", 40+ s "This is taking a while -- check the daemon log
  next". Each phrase types in ~80ms/char, holds 1.2 s, deletes
  fast (~25ms/char), then the next phrase appears.
- **Progress bar** beneath the phrase, fed by the main process's
  step counter (0% before daemon up, 33% after daemon ready, 66%
  after Vite ready, 100% just before reveal).
- **Sub-line** beneath the bar: the literal current step
  ("Starting daemon", "Compiling Electron main", "Loading
  marketplace", "Opening Synapse window") -- helps the user see
  WHERE the slowness is.

All animations respect `prefers-reduced-motion` (constant phrase
shown, no typing) per existing v0.1.35 styles.css rule.

### L3 -- Error code catalogue

New file `docs/error-codes.md` enumerates every failure the launcher
can hit. Each row: code, short title, what triggered it, what the
user does next. The codes:

| Code | Title | Trigger |
|---|---|---|
| SYN-DAEMON-001 | Python missing | `python` not on PATH |
| SYN-DAEMON-002 | Module missing | `import synapse_daemon` fails |
| SYN-DAEMON-003 | Port in use | bind to 7878 fails |
| SYN-DAEMON-004 | Schema migration failed | Storage.migrate raised |
| SYN-DAEMON-005 | Tools dir missing | tools_dir resolves to nothing |
| SYN-DAEMON-006 | Token write failed | auth-token can't be persisted |
| SYN-DAEMON-007 | Health probe timeout | /health didn't return in 15s |
| SYN-VITE-001 | npm missing | `npm` not on PATH |
| SYN-VITE-002 | Vite already on 5173 | strictPort conflict |
| SYN-VITE-003 | Build failed | tsc/vite reported errors |
| SYN-ELECTRON-001 | Electron binary missing | `npx electron` resolution fails |
| SYN-ELECTRON-002 | Preload load failed | preload.js evaluation threw |
| SYN-ELECTRON-003 | Renderer load failed | Vite URL not reachable |
| SYN-IPC-001 | IPC channel timeout | child process didn't ack |
| SYN-CONFIG-001 | boot-config malformed | JSON parse failed |
| SYN-CONFIG-002 | Data dir unwritable | mkdir / write rejected |

The launcher emits the code + a one-line message to splash;
splash shows them in a small error panel with a "Copy details"
button and a link to `docs/error-codes.md#<code>` for context.

## Consequences

### Positive
- Replaces a third-party-looking terminal flow with a real
  application splash.
- Phrases give the user **something to read** during slow starts
  instead of a frozen CLI.
- Error codes make support tractable -- "what's SYN-DAEMON-003?"
  has a clear answer.
- L3's catalogue is useful even before L1+L2 ship; the launcher
  PowerShell script can adopt the codes immediately.

### Negative / honest trade-offs
- Three platforms (Windows / macOS / Linux) all have small
  rendering differences for frameless BrowserWindows. We'll need a
  brief platform-specific pass.
- The typing animation is delightful but **delays the reveal** by
  the cumulative phrase time. Phrases must keep up with actual
  progress, not be longer.
- The 480x320 splash is fine on a desktop but might be cramped on
  a 1024x768 laptop with HiDPI scaling. Need to verify.
- The error catalogue WILL grow. Build a mechanism (the markdown
  table) that's easy to amend rather than enums hardcoded in
  multiple places.

## Detailed design

### Process flow

```
electron/main.ts:
  app.whenReady
    -> create splash window (loadFile dist/splash.html)
    -> splash IPC handshake
    -> spawn daemon (JSON-line stdout)
    -> spawn vite (JSON-line stdout)
    -> wait until daemon ready + vite ready
    -> create main window
    -> wait for did-finish-load on main
    -> splash send "complete"
    -> splash fade out (150ms)
    -> show main
```

### IPC protocol

Main -> Splash:
- `synapse:splash-update` `{ step, status, pct, message? }`
- `synapse:splash-error` `{ code, title, detail, logTail }`
- `synapse:splash-complete`

Splash -> Main:
- `synapse:splash-ready` (handshake)
- `synapse:splash-copy-error` (copy details to clipboard)

### Phrase schedule (L2)

```js
const PHRASE_SCHEDULE = [
  { fromMs: 0, text: 'Starting up' },
  { fromMs: 2000, text: 'Booting the daemon' },
  { fromMs: 5000, text: 'Hold your horses' },
  { fromMs: 10000, text: 'Making magic' },
  { fromMs: 20000, text: 'Almost there' },
  { fromMs: 40000, text: 'This is taking a while...' },
];
```

A `setInterval` chooses the active phrase based on
`Date.now() - launchStart`. When the active phrase changes, the
typewriter animation starts on the new one.

### Reduced motion

When `window.matchMedia('(prefers-reduced-motion: reduce)').matches`,
skip the typing animation entirely -- show the active phrase as
static text. Progress bar still animates.

## Status

Proposed. Implementation does NOT start until the user gives the go.
L1 + L3 ship together (L1 needs the codes to display them);
L2 ships next.

## Verification plan

### L1 + L3
- Spawn Synapse via the launcher; splash window appears with the
  logo + progress bar + static phrase.
- Force-fail each error condition (kill daemon mid-start, remove
  Python from PATH, occupy 7878 with `nc -l`, etc.); verify the
  matching error code surfaces with the right title.
- Playwright snapshot of splash at 480x320 viewport on each
  platform.

### L2
- Visual: phrases type, hold, delete, next. No flicker.
- `prefers-reduced-motion`: static phrase only.
- Schedule respects elapsed time even when daemon starts quickly
  (phrase shouldn't be "Almost there" 800ms in).
