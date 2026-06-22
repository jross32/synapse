# Found Bugs

Date: 2026-06-18

## Scope

This file started as a point-in-time audit of Synapse focused first on the reported launch freeze / blue-screen after enabling LAN access, then on adjacent startup, mobile-access, packaging, and tooling issues that can affect the same user journey.

It is now a **living shared bug ledger** for Synapse. When an AI coding session or a human finds a real bug, likely bug, regression, or follow-up verification result, update this file so the next session has the same context.

## Working Agreement

- Add newly discovered bugs here when they are real enough to matter, even if they are not fixed yet.
- If a bug is fixed, keep the original finding and add a dated follow-up section saying what changed and how it was verified.
- Prefer concrete evidence: file paths, logs, screenshots, runtime behavior, failing tests, or live repro steps.
- Keep high-signal bugs and regressions here. Do not turn this into a generic scratchpad or brainstorming file.

Confidence model used in this file:

- **Confirmed defect** means the issue is directly supported by the current source tree and/or current runtime artifacts in this workspace.
- **High-confidence probable bug** means the code path is strong enough to treat as a real issue, but I do not have the same level of direct runtime proof as the confirmed items.

This is **not** a mathematically complete list of every bug in the repo. It is an extensive audit of the highest-value defects and likely defects reachable from the current codebase and the reported failure.

## Executive Summary

The reported freeze after turning on LAN access is not explained by a single isolated mistake. It is a **bug cluster** centered on the fact that the in-app restart path does **not** restart the same system that the desktop shortcut starts in dev mode.

The most important findings are:

1. **Confirmed:** the Settings restart path relaunches **Electron only**, while the desktop shortcut path in [synapse.cmd](synapse.cmd) is what actually starts the daemon and the Vite renderer in dev mode. Those are not equivalent launch paths.
2. **Confirmed:** the current Vite log already shows a **real 5173 port conflict** in [data/vite-runtime.log](data/vite-runtime.log#L2). That means there is also a clean-launch failure mode independent of the LAN toggle.
3. **Confirmed:** the wrapper teardown in [synapse.cmd](synapse.cmd#L102) and [synapse.cmd](synapse.cmd#L103) kills processes **by port ownership**, not by child PID ownership. That can interfere with restart and can also kill unrelated local processes.
4. **Confirmed:** the LAN setting itself is being saved correctly in [data/boot-config.json](data/boot-config.json), and the daemon boot path does honor that setting in [daemon/synapse_daemon/__main__.py](daemon/synapse_daemon/__main__.py#L167). The problem is not the toggle write. The problem is getting a clean post-toggle restart.
5. **Confirmed:** the repo has version drift across runtime, packaging, and docs: [package.json](package.json#L4) and [pyproject.toml](pyproject.toml#L7) still say `0.1.32`, while [daemon/synapse_daemon/__init__.py](daemon/synapse_daemon/__init__.py#L3), [README.md](README.md#L5), and [PROGRESS.md](PROGRESS.md#L7) are on `0.1.34`.

## 2026-06-19 Follow-Up

This file started as a read-only audit. The working tree has since moved on in a few important ways for the mobile/LAN/WAN path.

### Resolved in the current working tree

1. **Mobile shell parity**: `/mobile` no longer stops at a stripped-down projects list. It now serves the same React shell used by the desktop/web renderer, adapted for phone navigation:
   - Home
   - Apps
   - Tools
   - Sessions
   - Processes
   - Settings
2. **LAN -> WAN handoff**: the mobile Cloudtap card now exposes **Use on this phone**, which carries the paired-device token into the Cloudflare tunnel origin instead of losing auth at the origin boundary.
3. **Stale mobile token recovery**: if a phone/browser still has a revoked or expired token, the app now clears it and returns to the pair screen instead of rendering an empty/half-broken shell.
4. **Mobile/browser link honesty**: phone/browser project links no longer hardcode unusable `localhost` URLs on WAN. LAN links use the current host; tunnel-origin pages no longer pretend a non-tunnelled app port is reachable.

### Verified live on 2026-06-19

Using Playwright as a simulated phone client at `390x844`:

1. Paired successfully on LAN at `http://192.168.1.143:7878/mobile`.
2. Opened a real Cloudtap tunnel for daemon port `7878` from the phone Tools page.
3. Followed the **Use on this phone** link into `https://advisor-triumph-memorial-anti.trycloudflare.com/mobile` and stayed authenticated.
4. Launched a real PowerShell PTY session from the WAN Sessions page.
5. Cleared the browser-local token, then paired directly on the Cloudflare URL with a fresh 6-digit code and reached the full shell again.

### Important nuance

This follow-up **does not erase** the earlier restart/launcher findings in this file. Those findings remain useful for the desktop dev bootstrap path. This section only records that the phone-control path itself is now working in the current working tree and was validated over both LAN and Cloudtap WAN.

## 2026-06-20 Follow-Up

The working tree moved again after the 2026-06-19 mobile parity pass.

### Newly confirmed defects

1. **Confirmed:** Electron could still fail to launch in dev mode if `ELECTRON_RUN_AS_NODE=1` leaked in from the parent environment. In that case `npx electron .` behaved like plain Node and crashed before the app window opened with `TypeError: Cannot read properties of undefined (reading 'isPackaged')`.
2. **Confirmed:** on Windows / Python 3.12, the daemon could stay alive but silently stop accepting new LAN/WAN connections on `7878` after `asyncio` logged `WinError 64` (`The specified network name is no longer available`) from the Proactor accept loop. Existing sockets stayed alive, which made the failure look random from the phone side.

### Resolved in the current working tree

1. **Electron launch hardening:** [synapse.cmd](synapse.cmd) and [scripts/dev.ps1](scripts/dev.ps1) now clear `ELECTRON_RUN_AS_NODE` before starting Electron, and [electron/main.ts](electron/main.ts) now ignores broken stdout/stderr pipes instead of surfacing `EPIPE` as a fatal main-process popup.
2. **Windows accept-loop hardening:** the daemon installs a Windows-only accept-reset workaround at startup in [daemon/synapse_daemon/windows_asyncio.py](daemon/synapse_daemon/windows_asyncio.py), wired from [daemon/synapse_daemon/__main__.py](daemon/synapse_daemon/__main__.py). The goal is narrow: keep transient WinError 64 resets from closing the listener on `7878`.
3. **Mobile nav fit:** the phone shell nav no longer relies on horizontal scrolling for the six core tabs; [renderer/App.tsx](renderer/App.tsx) now renders a 2-row touch grid so Home / Apps / Tools / Sessions / Processes / Settings all stay visible on a narrow phone.

### Verified live on 2026-06-20

1. Restarted the full app through [synapse.cmd](synapse.cmd) with Electron inspection enabled.
2. Verified desktop Electron booted cleanly and reported no renderer console errors.
3. Verified LAN mobile shell on `http://192.168.1.143:7878/mobile` using Playwright at `390x844`, including the full navigation shell and a real PowerShell PTY launch from the Sessions page.
4. Verified the daemon still answered fresh `GET /api/v1/health` and `GET /api/v1/pty` requests after the mobile PTY launch, with `0.0.0.0:7878` still in `LISTEN`.
5. Opened a fresh Cloudtap tunnel for daemon port `7878` only, loaded `/mobile` through the resulting `*.trycloudflare.com` URL, and verified the full shell over WAN.
6. Verified `wss://.../api/v1/ws` over the Cloudflare URL with a paired-device token and received the replay buffer, including the WAN tunnel-open event and PTY session events.

## 2026-06-20 Desktop Tools Follow-Up

Another desktop auth issue showed up live after the WAN/mobile work:

1. **Confirmed:** the real Electron window could render `A valid X-Synapse-Token is required.` on the Tools page even though the daemon itself was healthy and `GET /api/v1/tools` succeeded with a fresh local token.
2. **Likely root cause:** the desktop app could hold onto a stale local token after daemon/token drift, and the Tools page did not clear an old auth error after a later successful refresh.

### Resolved in the current working tree

1. [renderer/lib/api-client.ts](renderer/lib/api-client.ts) now retries one time on desktop-side `401` by refreshing `/auth/local-token` directly, then replaying the original request.
2. [renderer/lib/ws-client.ts](renderer/lib/ws-client.ts) now treats WebSocket close code `1008` as an auth-recovery case: try refreshing the local token, then reconnect.
3. [renderer/pages/Tools.tsx](renderer/pages/Tools.tsx) now clears stale auth errors when a later refresh succeeds.
4. [electron/main.ts](electron/main.ts) no longer reads `data/auth-token` directly for tray/main-process daemon requests; it now asks the attached daemon for its trusted-local token and retries once on `401`.

### Verified live

Using the real Electron window via [scripts/inspect-electron.js](scripts/inspect-electron.js):

1. Reproduced the Tools-page banner in the desktop app: `A valid X-Synapse-Token is required.`
2. Applied the auth-recovery patch.
3. Relaunched Electron, reopened Tools, and confirmed the page rendered the Cloudtap card normally instead of the auth banner.

## 2026-06-20 WAN Reliability Follow-Up

The next live issue was narrower but important for real phone use over Cloudtap:

1. **Confirmed:** WAN reconnect links could appear to work at first, then fall back to `Reconnect this phone` about 10–15 seconds later.
2. **Confirmed root cause:** the paired-device token itself was valid and `/api/v1/projects` succeeded over the Cloudflare origin, but the WebSocket hub in [daemon/synapse_daemon/ws.py](daemon/synapse_daemon/ws.py) only gave the first authenticated `resume` frame **0.5 seconds** to arrive. Over the tunnel that was sometimes too short, so the daemon closed the socket with `1008`, the browser tried the desktop-only `/api/v1/auth/local-token` fallback, that failed with `403`, and the mobile shell cleared only the token while keeping the paired-device identity.

## 2026-06-21 Discover + Profile Follow-Up

### Resolved in the current working tree

1. **Confirmed / resolved:** the desktop Tools → Discover left rail could cut off the lower category entries (for example `Data`) on shorter viewports because the entire sticky rail was one unbounded stack. The rail is now split into a viewport-capped sticky shell with an internal scroll region for `Browse by category`, so every category remains reachable without losing the `Collections` and `Registry source` cards.
2. **Resolved UX gap:** Synapse did not yet have a personal account/profile surface for carrying favorites, recent tools/workflows, host inventory, or connected-service status between machines. The working tree now includes a daemon-owned Profile hub backed by `/api/v1/profile*`, plus UI entry points in the desktop rail and mobile header.

### Verified in the current working tree

1. `GET /api/v1/profile`, `GET /api/v1/profile/catalog-state`, `GET /api/v1/profile/service-connections`, and `GET /api/v1/profile/hosts` all round-trip in the automated daemon test suite.
2. `npm run typecheck`, `pytest`, and `npm run build` all pass after the Profile hub + Discover rail changes.

### Resolved in the current working tree

1. [daemon/synapse_daemon/ws.py](daemon/synapse_daemon/ws.py) now allows a realistic WAN/mobile delay before giving up on the first `resume` frame, preventing false `1008` auth closes on healthy paired-device sessions.
2. [renderer/lib/api-client.ts](renderer/lib/api-client.ts) now refuses to attempt the trusted-local `/auth/local-token` bootstrap from non-loopback origins, so paired mobile/WAN clients do not spam a guaranteed `403` during recovery paths.
3. [daemon/tests/test_app.py](daemon/tests/test_app.py) now covers a delayed WebSocket resume frame explicitly so this regression stays pinned.

### Verified live

Using Playwright plus a real Cloudtap tunnel:

1. Fully restarted Synapse, including daemon, Vite, Electron, and the app-owned `cloudflared` process for `localhost:7878`.
2. Verified LAN `/mobile` reopened directly into the full Home / Apps / Tools / Sessions / Processes / Settings shell with the stored paired-device identity after restart.
3. Reopened WAN through Cloudtap and confirmed [GET /api/v1/remote-access](daemon/synapse_daemon/routes_system.py) reported the tunnel on port `7878` with `verification.status = ready`, `health_ok = true`, and `mobile_ok = true`.
4. Used the desktop `Phone Access` hub's `Reconnect on WAN` action for the already paired `Playwright Phone`, opened the resulting `*.trycloudflare.com/mobile?...#synapseClaim=...` link, and confirmed the phone entered the full shell without another 6-digit code.
5. Waited 15 seconds on the Cloudflare-origin mobile shell; unlike the broken build, the session token remained present, the shell stayed authenticated, and no `/api/v1/auth/local-token` `403` appeared in the browser console.

## 2026-06-20 Launcher + Packaging Follow-Up

The older "restart/bootstrap cluster" findings in this file were re-checked and then fixed in the current working tree.

### Resolved in the current working tree

1. **Confirmed fixed:** the dev restart mismatch is resolved. [synapse.cmd](synapse.cmd) now delegates to [scripts/dev.ps1](scripts/dev.ps1), and [electron/main.ts](electron/main.ts) exits with a dedicated wrapper restart code in dev mode so the wrapper restarts the full daemon + Vite + Electron stack instead of only relaunching Electron.
2. **Confirmed fixed:** the broad port-kill teardown is gone. The old `netstat` + `taskkill` cleanup in [synapse.cmd](synapse.cmd) was replaced by PID-tree cleanup in [scripts/dev.ps1](scripts/dev.ps1), so the wrapper now stops only Synapse-owned children.
3. **Confirmed fixed:** the Vite bootstrap path is now owned and verified instead of relying on "something answered on 5173". The wrapper starts Vite from the repo-local binary, watches the actual process it launched, and waits for both HTTP readiness and Vite's own startup log before proceeding.
4. **Confirmed fixed:** the stale Electron preload version fallback is gone. [electron/preload.ts](electron/preload.ts) no longer falls back to a hardcoded `0.1.8`, and [renderer/lib/daemon-context.tsx](renderer/lib/daemon-context.tsx) now normalizes Python's PEP 440 `0.1.36.dev0` into the friendly `0.1.36-dev` UI label.
5. **Confirmed fixed:** the packaged-daemon bootstrap now exists end to end. [installer/build-daemon.ps1](installer/build-daemon.ps1) builds `installer/daemon-dist/synapse-daemon.exe`, [electron/main.ts](electron/main.ts) knows how to spawn that bundled daemon in packaged mode, and the daemon now resolves bundled tools/templates/docs/mobile assets through [daemon/synapse_daemon/runtime_paths.py](daemon/synapse_daemon/runtime_paths.py) instead of source-tree-only paths.
6. **Confirmed fixed:** the TypeScript config deprecation findings are resolved in the repo config. [tsconfig.json](tsconfig.json) no longer uses the deprecated top-level `baseUrl` pattern, and [electron/tsconfig.json](electron/tsconfig.json) now uses `Node16` module resolution.

### Verified live on 2026-06-20

1. Ran `npm run typecheck`, `pytest`, `npm run build`, and `npm run build:daemon`.
2. Verified the packaged daemon artifact directly with `installer/daemon-dist/synapse-daemon.exe --version`, which reported `synapse-daemon 0.1.36.dev0`.
3. Launched the full dev stack through [synapse.cmd](synapse.cmd) with renderer inspection enabled.
4. Verified the desktop renderer at `http://127.0.0.1:5173/` with Playwright and attached to the real Electron window with [scripts/inspect-electron.js](scripts/inspect-electron.js).
5. Triggered `window.synapse.restart()` inside the live Electron app and confirmed the wrapper:
   - logged `Electron requested a full Synapse restart`
   - stopped the owned Vite + daemon children
   - relaunched daemon, Vite, and Electron
   - came back on the real Synapse page instead of a dead renderer / `chrome-error://chromewebdata/` page

### Current status of the original top findings

The earlier confirmed defects in this file are still valuable as historical root-cause notes, but the current working tree no longer reproduces them in the tested dev path:

1. restart mismatch: fixed
2. false-ready / weak Vite bootstrap path: fixed
3. port-based teardown: fixed
4. LAN setting persisted but clean restart failed to return healthy: fixed in the tested wrapper restart path
5. version drift: fixed for active runtime/docs surfaces, with Python packaging intentionally using normalized `0.1.36.dev0`

## What Most Likely Happened On The User's Machine

This is the most likely sequence that matches both the code and the logs:

1. Synapse was originally started from the desktop shortcut that points to [synapse.cmd](synapse.cmd).
2. The LAN toggle in [renderer/components/NetworkPanel.tsx](renderer/components/NetworkPanel.tsx#L58) correctly persisted `bind_lan: true` through [daemon/synapse_daemon/routes_system.py](daemon/synapse_daemon/routes_system.py#L103) into [data/boot-config.json](data/boot-config.json).
3. The UI then offered an in-app restart via [renderer/components/NetworkPanel.tsx](renderer/components/NetworkPanel.tsx#L168) and [electron/preload.ts](electron/preload.ts#L15).
4. That restart path only relaunches Electron through [electron/main.ts](electron/main.ts#L306) and [electron/main.ts](electron/main.ts#L307). It does **not** rerun [synapse.cmd](synapse.cmd), which is the thing that originally launched the daemon and Vite.
5. The new Electron process still tries to load the dev renderer from [electron/main.ts](electron/main.ts#L234), but the workspace already has evidence that Synapse's Vite server failed to start because port 5173 was occupied in [data/vite-runtime.log](data/vite-runtime.log#L2).
6. When the original shortcut-driven process unwinds, [synapse.cmd](synapse.cmd#L102) and [synapse.cmd](synapse.cmd#L103) kill listeners on 7878 and 5173 by port. That is not coordinated with the relaunched Electron process.
7. The result is a window that can open without a healthy renderer or without a healthy daemon behind it, which matches the described “blue screen / freeze” symptom.

## Confirmed Defects

### 1. In-app restart is not a full Synapse dev restart

Severity: High

Affected paths:

- [renderer/components/NetworkPanel.tsx](renderer/components/NetworkPanel.tsx#L168)
- [electron/preload.ts](electron/preload.ts#L15)
- [electron/main.ts](electron/main.ts#L306)
- [electron/main.ts](electron/main.ts#L307)
- [synapse.cmd](synapse.cmd#L33)
- [synapse.cmd](synapse.cmd#L66)
- [electron/main.ts](electron/main.ts#L234)

Why this is confirmed:

- The LAN settings UI explicitly encourages an in-app restart in [renderer/components/NetworkPanel.tsx](renderer/components/NetworkPanel.tsx#L175).
- The preload bridge exposes that restart in [electron/preload.ts](electron/preload.ts#L15).
- The Electron restart implementation is only:
  - `app.relaunch()` in [electron/main.ts](electron/main.ts#L306)
  - `app.exit(0)` in [electron/main.ts](electron/main.ts#L307)
- The actual dev boot topology lives outside Electron in [synapse.cmd](synapse.cmd#L33) and [synapse.cmd](synapse.cmd#L66), where the daemon and Vite are launched.
- The dev Electron window still depends on `http://localhost:5173` via [electron/main.ts](electron/main.ts#L234).

Why this is a defect:

The app is offering “Restart now” from inside the UI, but in dev mode that action is **not equivalent** to rerunning the launch path that the desktop shortcut actually used. The restart mechanism and the original bootstrap mechanism are different systems.

User-facing impact:

- This directly explains why a LAN toggle can save correctly but still leave the app stuck or half-restarted.
- It blocks the follow-up goal of phone access because the daemon has to come back cleanly and remain reachable after the toggle.

Applies to:

- Dev restart path: Yes
- Clean first launch: Not by itself
- Phone access after LAN toggle: Yes

### 2. Vite can fail to start on 5173 while the launcher still proceeds

Severity: High

Affected paths:

- [data/vite-runtime.log](data/vite-runtime.log#L2)
- [synapse.cmd](synapse.cmd#L66)
- [electron/main.ts](electron/main.ts#L234)

Why this is confirmed:

- The current runtime artifact [data/vite-runtime.log](data/vite-runtime.log#L2) records `error when starting dev server:` and `Port 5173 is already in use`.
- The wrapper starts Vite in [synapse.cmd](synapse.cmd#L66).
- Electron still tries to load the renderer from [electron/main.ts](electron/main.ts#L234).

Why this is a defect:

There is a real, current clean-launch blocker on the renderer port. The failure exists independently of the LAN toggle.

Why this matters beyond the obvious port conflict:

- The wrapper waits for “something responding on 5173,” not “Synapse's Vite process successfully started.”
- If another local process owns 5173, the launcher can produce a false-positive “ready” state and then open Electron against the wrong thing or against an unusable renderer state.

User-facing impact:

- Fresh launch can fail even without touching LAN settings.
- The post-toggle restart path becomes even more fragile because it still depends on the same port.

Applies to:

- Dev restart path: Yes
- Clean first launch: Yes
- Phone access: Indirectly

### 3. The wrapper tears down listeners by port, not by process ownership

Severity: High

Affected paths:

- [synapse.cmd](synapse.cmd#L102)
- [synapse.cmd](synapse.cmd#L103)

Why this is confirmed:

- The wrapper uses `netstat` + `taskkill /F /PID` against **any** process listening on 7878 and 5173.

Why this is a defect:

This is not scoped to Synapse-owned children. It can kill unrelated local services, and it can also interfere with a newly relaunched Synapse instance if that instance has already rebound one of those ports.

User-facing impact:

- Exiting Synapse can unexpectedly kill non-Synapse software using those ports.
- Restart timing becomes unsafe because the old wrapper can kill ports out from under the relaunched instance.

Applies to:

- Dev restart path: Yes
- Clean first launch: No
- General local machine safety: Yes

### 4. The LAN setting persists correctly, but the last successful daemon session did not come back on LAN

Severity: Medium

Affected artifacts:

- [data/boot-config.json](data/boot-config.json)
- [daemon/synapse_daemon/routes_system.py](daemon/synapse_daemon/routes_system.py#L110)
- [daemon/synapse_daemon/__main__.py](daemon/synapse_daemon/__main__.py#L167)
- [daemon/synapse_daemon/__main__.py](daemon/synapse_daemon/__main__.py#L169)
- [data/daemon-runtime.log](data/daemon-runtime.log#L1)

Why this is confirmed:

- The persisted boot config currently says LAN binding is on in [data/boot-config.json](data/boot-config.json).
- The network route does save that setting via [daemon/synapse_daemon/routes_system.py](daemon/synapse_daemon/routes_system.py#L110).
- The daemon boot path does honor it in [daemon/synapse_daemon/__main__.py](daemon/synapse_daemon/__main__.py#L169).
- But the current daemon runtime log still shows a loopback-only boot in [data/daemon-runtime.log](data/daemon-runtime.log#L1).

Why this matters:

This does **not** mean the boot-config mechanism is broken. It means the restart sequence did not complete into a new healthy LAN-bound daemon instance after the setting was saved.

User-facing impact:

- Confirms that the failure is in restart/launch orchestration, not in the LAN toggle persistence itself.

Applies to:

- Dev restart path: Yes
- Clean first launch: Not enough evidence
- Phone access: Yes

### 5. Version declarations are currently inconsistent across runtime, packaging, and docs

Severity: Medium

Affected files:

- [package.json](package.json#L4)
- [pyproject.toml](pyproject.toml#L7)
- [daemon/synapse_daemon/__init__.py](daemon/synapse_daemon/__init__.py#L3)
- [README.md](README.md#L5)
- [PROGRESS.md](PROGRESS.md#L7)

Why this is confirmed:

- [package.json](package.json#L4) says `0.1.32`.
- [pyproject.toml](pyproject.toml#L7) says `0.1.32`.
- [daemon/synapse_daemon/__init__.py](daemon/synapse_daemon/__init__.py#L3) says `0.1.34`.
- [README.md](README.md#L5) and [PROGRESS.md](PROGRESS.md#L7) describe the repo as `0.1.34`.

Why this is a defect:

This repo has multiple authoritative version surfaces and they disagree right now. That creates misleading diagnostics, misleading UI labeling, and confusing packaging behavior.

User-facing impact:

- Version shown by the desktop UI and version reported by the daemon can diverge.
- Packaging and release metadata can ship stale version values.

Applies to:

- Dev: Yes
- Packaged builds: Yes
- Phone access: Indirectly

### 6. The packaged desktop build is not currently self-contained

Severity: Medium

Affected files:

- [package.json](package.json#L65)
- [package.json](package.json#L67)
- [installer](installer)
- [electron/main.ts](electron/main.ts#L94)

Why this is confirmed:

- The Electron build config expects extra resources from `installer/daemon-dist` in [package.json](package.json#L67).
- The [installer](installer) directory is currently empty.
- The desktop app still spawns the daemon with `python -m synapse_daemon` in [electron/main.ts](electron/main.ts#L94).

Why this is a defect:

The packaged app configuration implies a bundled daemon path that does not exist yet, while the runtime still assumes a Python environment and an installable `synapse_daemon` module.

User-facing impact:

- A packaged desktop build is not currently a clean end-user deliverable.
- Milestone-J style packaging is not actually wired end-to-end yet.

Applies to:

- Dev: No
- Packaged builds: Yes
- Phone access: Indirectly

### 7. The workspace currently has active TypeScript configuration diagnostics

Severity: Low

Affected files:

- [tsconfig.json](tsconfig.json#L22)
- [electron/tsconfig.json](electron/tsconfig.json#L6)

Why this is confirmed:

- The workspace diagnostics currently report:
  - deprecated `baseUrl` usage in [tsconfig.json](tsconfig.json#L22)
  - deprecated `moduleResolution: "Node"` usage in [electron/tsconfig.json](electron/tsconfig.json#L6)

Why this is a defect:

This is not the current freeze root cause, but the repo is not clean under current TypeScript deprecation diagnostics and will need migration before TypeScript 7.

User-facing impact:

- Tooling drift and future build break risk.

Applies to:

- Dev: Yes
- Packaged builds: Yes
- Phone access: No

## High-Confidence Probable Bugs

### 1. Electron-owned daemon restart can race port release on 7878

Severity: High

Relevant files:

- [electron/main.ts](electron/main.ts#L306)
- [electron/main.ts](electron/main.ts#L307)
- [electron/main.ts](electron/main.ts#L536)
- [electron/main.ts](electron/main.ts#L122)

Why this is likely:

- Restart is asynchronous: Electron relaunches immediately from [electron/main.ts](electron/main.ts#L306) and [electron/main.ts](electron/main.ts#L307).
- The old daemon child is only sent `kill()` in [electron/main.ts](electron/main.ts#L536).
- There is no wait for child exit and no explicit confirmation that 7878 has been released before the next health wait in [electron/main.ts](electron/main.ts#L122).

Why this probably matters:

If the active daemon was owned by Electron rather than by the wrapper, a restart can plausibly race the old daemon's socket release and create a startup timeout or bind conflict.

### 2. Daemon startup failures on 7878 are masked as a generic health timeout

Severity: High

Relevant files:

- [electron/main.ts](electron/main.ts#L122)
- [electron/main.ts](electron/main.ts#L498)
- [daemon/synapse_daemon/__main__.py](daemon/synapse_daemon/__main__.py#L202)

Why this is likely:

- Electron only waits for `/api/v1/health` and throws a generic timeout from [electron/main.ts](electron/main.ts#L122).
- The daemon boot path eventually calls `uvicorn.run()` in [daemon/synapse_daemon/__main__.py](daemon/synapse_daemon/__main__.py#L202), but there is no matching Electron-side discrimination between “daemon still booting,” “daemon crashed,” and “daemon could not bind.”

Why this probably matters:

Any issue before `health` becomes reachable can collapse into the same user-visible failure mode, which makes diagnosis much harder and allows one bug to mask another.

### 3. The Settings page can show a stale UI version if Electron does not populate `npm_package_version`

Severity: Medium

Relevant files:

- [electron/preload.ts](electron/preload.ts#L15)
- [renderer/lib/daemon-context.tsx](renderer/lib/daemon-context.tsx#L174)
- [renderer/pages/Settings.tsx](renderer/pages/Settings.tsx#L72)

Why this is likely:

- The preload bridge falls back to `'0.1.8'` in [electron/preload.ts](electron/preload.ts#L15).
- The renderer prefers `bridge.version()` in [renderer/lib/daemon-context.tsx](renderer/lib/daemon-context.tsx#L174).
- Settings renders that value directly in [renderer/pages/Settings.tsx](renderer/pages/Settings.tsx#L72).

Why this probably matters:

If the Electron environment does not provide `process.env.npm_package_version`, the UI can display a version older than both the live daemon and the repo docs.

### 4. Packaged resource path assumptions are still source-tree shaped

Severity: Medium

Relevant files:

- [daemon/synapse_daemon/app.py](daemon/synapse_daemon/app.py#L223)
- [daemon/synapse_daemon/__main__.py](daemon/synapse_daemon/__main__.py#L47)
- [daemon/synapse_daemon/__main__.py](daemon/synapse_daemon/__main__.py#L48)

Why this is likely:

- The mobile UI path is derived from the source tree in [daemon/synapse_daemon/app.py](daemon/synapse_daemon/app.py#L223).
- Default data and tools directories are relative source-style paths in [daemon/synapse_daemon/__main__.py](daemon/synapse_daemon/__main__.py#L47) and [daemon/synapse_daemon/__main__.py](daemon/synapse_daemon/__main__.py#L48).

Why this probably matters:

Even after the daemon is eventually bundled, packaged builds are likely to need additional path-hardening for `/mobile`, `data`, and `tools` resources.

## Findings Directly Related To Phone Access And Pairing

These are not separate bugs from the root cause. They explain why the user's phone workflow remains blocked after the freeze.

1. The LAN toggle route itself is working. The daemon will bind `0.0.0.0` on next clean boot through [daemon/synapse_daemon/__main__.py](daemon/synapse_daemon/__main__.py#L169).
2. The mobile UI is intentionally open and pair-first, which is covered by [daemon/tests/test_app.py](daemon/tests/test_app.py#L176).
3. The pairing REST flow exists and is tested at the daemon layer in [daemon/tests/test_auth.py](daemon/tests/test_auth.py#L136).
4. The missing piece is not pairing logic. The missing piece is that the app must finish a healthy post-toggle restart with the daemon actually reachable on LAN and `/mobile` actually served.
5. The QR path in [renderer/components/PairedDevicesPanel.tsx](renderer/components/PairedDevicesPanel.tsx#L177) depends on `mobile_urls` existing. Those URLs only appear after a successful LAN bind.

## Coverage Gaps That Explain Why This Escaped

These are not bugs by themselves, but they are the main reason the user-visible failure was able to land.

### 1. The current tests stop at persistence, not real restart

Relevant files:

- [daemon/tests/test_routes_system.py](daemon/tests/test_routes_system.py#L24)
- [daemon/tests/test_routes_system.py](daemon/tests/test_routes_system.py#L41)

What is covered:

- The daemon route correctly reports loopback by default.
- Toggling `bind_lan` persists to disk and returns `restart_required: true`.

What is not covered:

- No automated test proves that a real restart after toggle returns with the daemon actually rebound to `0.0.0.0`.
- No automated test covers the desktop shortcut wrapper and the in-app restart interaction.

### 2. There is daemon-level mobile coverage, but no desktop-to-phone end-to-end coverage

Relevant files:

- [daemon/tests/test_app.py](daemon/tests/test_app.py#L176)
- [daemon/tests/test_auth.py](daemon/tests/test_auth.py#L145)

What is covered:

- `/mobile` is served without a token.
- Pairing-code issuance and redemption exist at the daemon layer.

What is not covered:

- No automated path covers: desktop launch -> enable LAN -> restart -> phone opens `/mobile` -> pair device -> use mobile session.

### 3. No automated Electron or wrapper tests cover the failing path

Relevant files:

- [electron/main.ts](electron/main.ts)
- [synapse.cmd](synapse.cmd)

Why this matters:

- The actual user-facing bug lives at the boundary between the batch launcher, Electron lifecycle, daemon readiness, and the dev renderer.
- That boundary currently has no automated coverage.

## Bottom Line

The reported freeze is best explained by **multiple interacting defects**, not a single missing line:

1. The LAN toggle is persisting correctly.
2. The in-app restart path is not restarting the same dev system that the desktop shortcut started.
3. The renderer already has an independent 5173 startup failure in the current logs.
4. The wrapper teardown is broad enough to interfere with relaunch and to kill unrelated processes.
5. Phone pairing cannot become reliable until the app can complete a clean post-toggle restart and serve `/mobile` from a daemon that is truly bound to LAN.

## Suggested Repair Order

This section is intentionally about sequencing, not implementation details.

1. Fix the restart model mismatch between [synapse.cmd](synapse.cmd) and [electron/main.ts](electron/main.ts).
2. Fix the 5173 conflict handling and launcher readiness logic.
3. Fix wrapper teardown so it only stops Synapse-owned children.
4. Re-test the LAN toggle and phone pairing flow end to end.
5. After that, clean up the version drift and packaging-path issues.
