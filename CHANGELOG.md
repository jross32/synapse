# Changelog

All notable changes to Synapse will be documented in this file.
Format roughly follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
This project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Every commit must append an entry under the in-progress version header.

---

## [Unreleased]

## [0.1.201] - 2026-08-27

### Added
- **Durable improvement-proposal backlog** (`daemon/synapse_daemon/proposals.py`,
  `routes_review.py`, migration `035_proposal_lifecycle.sql`, and the Review UI) -- proposals now
  track two independent truths: human decision (`pending|accepted|declined`) and implementation
  lifecycle (`proposed|in_progress|done`). The API adds first-class `kind`, filtering/sorting, a
  discoverable `/review/proposals/schema`, manual lifecycle updates, and evidence-backed reconcile.
- **Implementation evidence instead of guesswork** -- reconciliation can mark work `in_progress`
  only when a live work item/session explicitly references the exact proposal id, and can mark it
  `done` only from a high-confidence completion claim in commit text. Every automatic transition
  records its source/evidence and auto-started work can return to `proposed` if the live signal
  disappears.
- **Improvement backlog UI** -- Review now exposes active/done/declined/all views with category,
  decision, lifecycle, latest evidence, Accept, Accept + backlog, Start, Done, Reopen, and Decline.

### Changed
- **Accepting an idea no longer pretends it was implemented.** The compatibility `/approve` and
  `/reject` URLs now update decision only; lifecycle remains independent. Existing legacy
  open/approved/rejected proposals migrate without inventing completion state.
- **AI working agreement and API docs** now teach exact-id lifecycle linking and the new schema so
  future workers can discover and drive the backlog without stale `status=open` instructions.

### Fixed
- **`scripts/version-bump.ps1` now updates Python versions on CRLF working trees** -- the old
  end-anchored regex silently missed `pyproject.toml` and `daemon/synapse_daemon/__init__.py` on
  Windows while still changing `package.json` and printing success. The matcher is now CRLF-safe
  and the script verifies all three version sources before reporting success. A regression test also
  proves Unicode survives the rewrite.

### Verification
- Focused proposal/review/version-helper suite: **34 passed**.
- Isolated real UI proof: desktop **1280x900** + mobile **390x844**, no overflow, zero console/page
  errors, expanded controls visible, and a real Start -> Accept flow persisted and refreshed.
- Renderer + Electron TypeScript gate: **PASS**.


## [0.1.200] - 2026-08-26

### Fixed
- **The staged multi-AI coordination gate authenticates itself again**
  (`scripts/coordination-preflight.ps1`) -- the documented `-Staged` invocation previously
  relied only on `-Token` / `SYNAPSE_LOCAL_TOKEN`; when neither was manually supplied it sent
  no `X-Synapse-Token`, received 401 from the live daemon, and silently degraded to the numbering
  check instead of checking file-lane overlap. It now resolves the same trusted-local
  `data/auth-token` used by Synapse when no explicit token is present, without printing the token.
  Added an end-to-end regression test with a temporary Git repo and authenticated fake overlap
  endpoint that proves the normal invocation sends the token, submits the staged paths, reaches
  the real overlap branch, and does not leak the credential.


## [0.1.199] - 2026-08-26

### Fixed
- **Home featured-app launch status reconciliation** (`renderer/pages/Home.tsx`) -- when a launch
  request fails, Home now immediately refetches that project's authoritative backend state and
  upserts it into the renderer's local project list. This fixes the real RackPilot case where port
  5089 was already served by a process started outside the daemon: the backend correctly marked the
  project `launched` before returning the conflict, but the card stayed `not running` because the
  catch path only rendered the error. The original launch error remains visible if the reconciliation
  read itself fails, so a secondary read cannot hide the primary failure. Renderer-only; no daemon
  restart is required.


## [0.1.198] - 2026-08-26

### Fixed
- **`scripts/dev.ps1`** -- `Start-DaemonWatchdog` and `Start-TunnelWatchdog` unconditionally
  spawned a new detached, hidden watchdog process on every restart, with no check for
  whether one from an earlier restart was still alive. Both watchdogs survive independently
  of the daemon/Electron process tree they were started alongside (that's the whole point --
  they need to outlive a wedged/killed daemon to be able to restart it), so they were never
  cleaned up by a normal restart either -- they just accumulated, one more pair every time.
  Confirmed live: after a night of restarts plus a real internet outage that repeatedly
  knocked the named tunnel down, **7 separate `tunnel-watchdog.ps1` processes and 7 separate
  `daemon-watchdog.ps1` processes** were all running simultaneously, independently racing
  each other to "fix" the same tunnel -- which is exactly what produced pairs of
  `relaunched cloudflared as PID X` / `... as PID Y` log lines landing in the same second:
  two (or more) watchdogs each saw the process missing and each relaunched it, leaving
  multiple redundant `cloudflared tunnel run synapse` processes live at once. Fixed by adding
  `Get-RunningWatchdogPid`, checked before either `Start-*Watchdog` function launches a new
  process; if a matching one is already alive, it logs that and returns instead of starting
  a duplicate. Live-verified: killed all 14 accumulated watchdog processes plus the duplicate
  cloudflared process, did a full clean restart, confirmed exactly one daemon-watchdog and
  one tunnel-watchdog process this time.

## [0.1.197] - 2026-08-26

### Added
- **`synapse_run_command_async` + `synapse_get_command_result`** (`daemon/synapse_daemon/mcp_connector.py`).
  `synapse_run_command` blocks the whole HTTP request for as long as the underlying shell
  command runs (up to its own timeout). Every hop between a remote caller (ChatGPT, claude.ai)
  and this daemon -- a Cloudflare Tunnel's own edge, in Justin's case -- has its own gateway
  timeout, commonly well under two minutes for a single proxied request. A command that runs
  past that gets its connection killed by the middle hop with a bare `502`, indistinguishable
  from the daemon itself being down, even though the daemon is fine and the command may finish
  successfully seconds later. Confirmed happening live: NabSignal's ChatGPT build thread hit a
  `502` finalizing a release (a combined CHANGELOG + compile/diff-hygiene command); Synapse's
  own daemon process never restarted and was fully healthy again within seconds -- a materially
  different signature from the actual wedge bugs fixed in v0.1.193/v0.1.194, which needed a real
  restart to recover. `synapse_run_command_async` starts the command on a background thread and
  returns a `job_id` immediately regardless of how long the command takes; `synapse_get_command_result`
  polls for the outcome (`running` with elapsed time, or `done` with the same `ok`/`exit_code`/
  `stdout`/`stderr` shape `synapse_run_command` already returns). No single HTTP request has to
  stay open for the command's actual duration anymore, so no proxy/tunnel timeout can kill it.

### Changed
- **`synapse_run_command`**'s own `timeout_seconds` is now hard-capped at 90s (previously 900s)
  regardless of what's requested. A command that would have run past the old cap now reliably
  hits this function's own existing graceful `TimeoutExpired` handling -- a clean, fast
  `{"ok": false, "timed_out": true, ...}` response -- well before any realistic proxy/tunnel
  timeout could kill the connection first. Its description now points to
  `synapse_run_command_async` for anything that might run long.

## [0.1.196] - 2026-08-26

### Fixed
- **`daemon/synapse_daemon/routes_system.py`** -- `_probe_remote_url()` (the health/mobile-
  shell verification behind both Cloudtap's WAN status and the new `public_hostname`
  feature from v0.1.195) sent no `User-Agent`, so Python's default `Python-urllib/x.y`
  went out on every request. Found live immediately after configuring `public_hostname`
  to a real, working, already-verified-by-curl named tunnel: Synapse reported
  `HTTP 403` from a health endpoint that `curl` reached fine seconds earlier. Isolated to
  the User-Agent specifically -- an otherwise-identical request differing only in UA went
  200 with curl's UA and 403 with Python's default. This is Cloudflare's own bot
  protection blocking a well-known non-browser UA string at the edge, not anything wrong
  with the tunnel or the daemon's reachability -- but it made the verification useless for
  any hostname sitting behind Cloudflare, which is the exact case this feature exists for.
  Fixed by sending a normal browser-shaped `User-Agent`.

## [0.1.195] - 2026-08-26

### Added
- **New setting: `public_hostname`** (`daemon/synapse_daemon/boot_config.py`, exposed via
  `PATCH /api/v1/system/network`, UI in `renderer/components/PhoneAccessPanel.tsx`). Lets
  an operator who already runs their own stable tunnel or reverse proxy to this daemon (a
  named cloudflared tunnel, for example) tell Synapse its hostname once. When set, it is
  used instead of Cloudtap's own auto-generated quick-tunnel for both the MCP connector URL
  (`GET /api/v1/mcp/connector`) and the remote-access WAN status/verification
  (`GET /api/v1/remote-access`) -- Cloudtap's tunnel gets a brand new random
  `*.trycloudflare.com` hostname on every daemon restart, which made the "Connect to
  Claude / ChatGPT" connector URL something you had to re-copy and re-paste into ChatGPT's
  connector settings after every restart. Synapse has no way to detect an externally-run
  named tunnel automatically (it isn't Cloudtap's own child process, so there was nothing
  to autodetect from) -- this makes it explicit instead. Settings UI gets a "Public
  hostname (optional)" field right in the MCP connector section, with Save/Clear and a
  status line showing which source (your hostname vs. Cloudtap vs. none) is currently
  active.

### Fixed
- **`renderer/lib/system-client.ts`** -- `patchMcpWrites()` (the "Full access" toggle for
  the MCP connector) passed an already-`JSON.stringify`'d body into `apiFetch`, which
  stringifies its `body` argument itself -- double-encoding it into a JSON string literal
  the server's `NetworkPatch` model can't parse as an object. Every click of that toggle
  in Settings failed against this call shape. Fixed by passing the plain object, matching
  every other `patch*` function in this file.
- **`daemon/synapse_daemon/routes_system.py`** -- `PATCH /system/network`'s response body
  had a duplicated `mcp_writes_enabled` key (harmless in Python -- the second silently won
  -- but a sign the block had been edited carelessly before); cleaned up while adding
  `public_hostname` to the same response.

## [0.1.194] - 2026-08-25

### Fixed
- **`daemon/synapse_daemon/mcp_connector.py`** -- the actual, confirmed root cause of the
  daemon "wedge" as hit through the MCP connector (claude.ai / ChatGPT): `POST /mcp/{token}`
  called the fully synchronous `_handle()` dispatch chain directly with no `await`, no
  `asyncio.to_thread`. `synapse_run_command` (the tool an AI coding agent actually uses to run
  shell commands) calls a plain blocking `subprocess.run(..., timeout=<up to 900s>)` inside
  that chain -- so any write/coding command froze the entire daemon event loop, including its
  own health endpoint, for however long the command took. Read-only tool calls were fast
  enough that this went unnoticed; anything that ran a real command (tests, git, builds -- the
  exact things a coding agent's connector is for) reliably froze the daemon and 502'd every
  other in-flight request. This is the v0.1.193 fix's actual missing piece: that release fixed
  a real but secondary bug in `ProcessManager.launch()` (Synapse's own "Launch project"
  button); this one fixes the tool a remote AI connector actually calls. Fixed by offloading
  the whole `_handle()` call to a worker thread via `asyncio.to_thread` in `mcp_post`, so a
  long-running command no longer blocks any other request.

## [0.1.193] - 2026-08-25

### Fixed
- **`daemon/synapse_daemon/process_manager.py`** -- `ProcessManager.launch()` called
  `self._spawn()` (a synchronous `subprocess.Popen(shell=True, ...)`) directly on the event
  loop thread instead of offloading it like `stop()` already does for `_terminate_tree`. On
  Windows, `shell=True` spawns `cmd.exe` via `CreateProcess`, which real-time antivirus
  scanning can stall for several seconds under load -- long enough to freeze every other
  request the daemon was serving (health checks, MCP tool calls, the ChatGPT connector) for
  the duration. This is the confirmed root cause of the recurring "daemon wedge": launching
  any managed project reproducibly froze the daemon, which then 502'd on every call routed
  through the tunnel (ChatGPT could still see read-only state that had already returned, but
  any request that needed a fresh round trip -- including its own next coding action --
  hung until the freeze cleared or the daemon was killed and restarted). Fixed by wrapping
  the spawn in `asyncio.to_thread`, matching `stop()`'s existing pattern.
- **`electron/main.ts`** -- `waitForDaemon()`'s default timeout was 15000ms, matching the
  daemon's own typical cold-start time (`Listening` to `Application startup complete`) with
  essentially no margin. Under any real machine load the tray's "Restart" health-check
  window could expire before the daemon actually became healthy, surfacing `SYN-BOOT-102`
  ("did not become healthy in time") even though the daemon went on to start successfully a
  few seconds later. Raised the default to 30000ms for real margin.

## [0.1.192] - 2026-08-25

### Changed
- **`renderer/components/DiscoveryDialog.tsx`** -- "Scan for projects" always started with a blank
  root folder, so nothing on disk was found until the user remembered to type a path in by hand.
  The root now defaults to whichever directory the MOST already-registered projects have in common
  (in practice, a dev-projects home like `C:\Users\justi`), computed from what Synapse already
  knows rather than needing a new IPC call to the OS. Real symptom this closes: RackPilot, sitting
  right under that same home directory, was never found by a scan because the root field gave no
  hint that a scan there would ever find anything.
  Two real bugs found and fixed on the way to landing this cleanly:
  1. The first implementation used a strict "every project must share this exact prefix with the
     first one" comparison -- a single registered project with a relative path
     (`data\projects\scratch`) zeroed the whole computation out to empty, even though 29 of the
     other 30 projects agreed perfectly. Replaced with a majority vote over each project's first
     three path segments, so one outlier can no longer blank out an otherwise-obvious answer.
  2. The first wiring used a `useEffect` that recomputed the default only when its dependencies
     changed; both of its runs happened to land before the daemon's initial project list had
     finished loading (which always starts empty while that request is in flight), and it never
     got a further chance to recompute correctly. Replaced with a plain render-time `useMemo`,
     which has no such race since it recalculates from whatever `projects` the current render
     already has.
  `tsc --noEmit` clean; live-verified against the real running dev server + daemon (30+ real
  registered projects) before and after each fix to confirm exactly what each one changed.

## [0.1.191] - 2026-08-25

### Fixed
- **`daemon/synapse_daemon/routes_projects.py`, `daemon/synapse_daemon/app.py`** -- a project
  registered, edited, or deleted through any means other than the currently-open Apps page's own
  form (a direct API call, a future discovery-scan/import path) never appeared in an already-open
  window until its next manual reload. Root cause: `POST/PATCH/DELETE /projects` never published a
  `v1.project.*` WebSocket event, and the renderer's `DaemonProvider` only refreshes its project
  list in response to one. Real symptom hit live: RackPilot was registered via a direct
  `POST /api/v1/projects` call and did not appear in an already-open Synapse window. Now
  `create_one`/`patch_one`/`delete_one` publish `v1.project.created` / `.updated` / `.deleted`
  after each mutation, via the same `EventBus` + `event_name()` pattern already used by process
  launch/stop events elsewhere. 16/16 route tests pass, including 3 new ones proving each event is
  actually published (not just that the underlying CRUD still works).

## [0.1.190] - 2026-08-25

### Changed
- **`renderer/pages/Apps.tsx`** -- the project list defaulted to alphabetical (pinned first, then
  by name), which meant an app used constantly all day could sit below one touched once months ago
  just because of its name. Now sorts by whichever is more recent of `last_transition_at` (a launch
  or stop) and `updated_at` (an Edit-dialog save, a pin toggle, etc.) -- pinned projects still float
  to the top, then most-recent-activity-first.

### Fixed
- **`renderer/components/ui/modal.tsx`** -- clicking outside a modal (the project detail view, the
  project form, confirm dialogs, etc.) did not close it, even though the component's own backdrop-
  click handler looked correct on read. Root-caused live: a genuine native `click` event fires and
  bubbles correctly on the backdrop element (confirmed with a plain `addEventListener` directly on
  the node), but React's own synthetic `onClick` on that same element was never invoked for the
  identical click (confirmed by reading the handler straight off the DOM node's current React props
  and wrapping it -- the wrapper was never called). Rather than chase React's internal delegation
  further, backdrop-click-to-close now uses a native `addEventListener`, the same proven-reliable
  pattern this component already used for its Escape-key handling. Live-verified via real (CDP-
  driven, not JS-dispatched) clicks: closes on a genuine outside click, stays open on a click inside
  the panel -- both confirmed before and after the fix to isolate the regression precisely.

## [0.1.189] - 2026-08-25

### Added
- **`daemon/synapse_daemon/chatgpt_browser_runtime.py`** -- a conversation can hit ChatGPT's own
  hard length ceiling ("You've reached the maximum length for this conversation, but you can keep
  talking by starting a new chat.") -- a PERMANENT condition, not a stall or a slow reply, confirmed
  happening for real the same night as v0.1.187's fix, on the same sibling project's build thread
  (RackPilot), after 30+ turns and hundreds of tool calls. Left undetected, `run_prompt()` would
  wait out the full `DEFAULT_TIMEOUT_SECONDS` (20 minutes) for a reply a maxed-out conversation can
  never send, reporting only a generic "no reply" timeout that gives no hint of the real cause.
  Added `conversation_length_limit_reached()`, checked both before a send is attempted (in
  `_send_and_confirm_started()`, so a dead conversation is never typed into) and during the reply
  wait (in `_wait_for_reply()`, so the wait ends immediately instead of running out the clock) --
  the resulting `RuntimeResult.error` now names the real problem and the fix ("branch to a new
  conversation... before continuing") instead of a misleading "stalled" message.
  Deliberately does NOT automate the actual branch -- that's a human/Claude-driven browser action
  ("Branch in new chat": hover a message -> More actions -> Branch in new chat) attempted by hand
  the same night with an interactive browser tool and found unreliable enough on a heavily-loaded
  tab (silent no-ops) that it isn't shipped here without being provable live first. 16/16 targeted
  tests pass (3 new), full daemon suite 1129/1130 (the one failure is `test_skill_catalog_...` --
  pre-existing/unrelated, caused by an untracked "stock-hunter" skill pack from a different
  in-flight thread, confirmed dirty before this change touched anything).

## [0.1.188] - 2026-08-25

### Changed
- **`renderer/components/ProjectTile.tsx`, `renderer/components/ProjectDetailModal.tsx`** -- the
  Apps page's project tiles were reported as "very long" (each showing kind/group/tags, description,
  a cmd/port/disk/cpu-ram metadata table, an error box, and two full rows of action buttons inline),
  forcing endless scrolling to see more than a couple of apps at once. Tiles are now short --
  name, path, status, pin, and the two actions people reach for constantly (Launch/Stop, Open in
  browser) -- with everything else (Edit/Logs/Delete, Open folder/VS Code/Terminal/AI OS/Workbench/
  Files, kind/group/tags, description, disk size, cpu/ram) moved into `ProjectDetailModal`, which
  already opened on a tile click; the modal gained a new action bar to hold what moved there.
  Measured live: tiles dropped from ~250-350px+ to ~120-133px tall.

### Fixed
- **Same files** -- "Open in browser" was reported missing on some registered apps with no
  indication why. Root cause: the button was wrapped in `project.expected_port !== null &&`, so a
  project added without an expected port (the field is optional in "Add Project") silently never
  got the button at all, with nothing telling the user that port was the reason. The button is now
  always rendered and only *disabled*, with a tooltip naming the exact fix ("No expected port set
  for this project -- open its details and Edit to set one, then this button will work.") -- and
  correctly enabled with the right localhost URL once a port is set and the app is running (live-
  verified against two real registered apps, one with a port and one deliberately without).
  Separately, a real app (RackPilot, a sibling project) was found completely absent from the
  registry -- registered directly via `POST /api/v1/projects` (id `rackpilot`, port 5089) rather
  than through the UI, confirming both the registration path and the new tile/button behavior work
  end to end for a genuinely new project, not just the 32 already in the registry.
  Typecheck clean (`tsc --noEmit`); no dedicated renderer test suite exists yet to extend, so
  verified live against the running dev server + daemon instead (Vite HMR on `:5173`, daemon on
  `:7878`, 32 real registered projects).

## [0.1.187] - 2026-08-25

### Fixed
- **`daemon/synapse_daemon/chatgpt_browser_runtime.py`** -- sending a prompt through this rung
  trusted a `type()`/`page.keyboard.press("Enter")` call succeeding as proof the message actually
  reached ChatGPT. A stale or unfocused composer (e.g. right after a navigation) can silently accept
  neither the typed text nor the Enter press while both calls still report success with no error --
  confirmed happening for real driving this exact chatgpt.com UI in a sibling project's build loop
  (a different toolset, same underlying page): a "continue" nudge appeared to work, but the composer
  never actually received the text, leaving both sides idle with no visible failure until noticed by
  hand. Left unverified, `run_prompt()` would then wait up to the full `DEFAULT_TIMEOUT_SECONDS`
  (20 minutes) for a reply that was never going to arrive, because nothing was ever sent. Fixed with
  `_send_and_confirm_started()`: every send is now verified twice -- before, by reading the
  composer's actual content back and comparing it against what was typed (`_typed_text_landed()`,
  tolerant of contenteditable whitespace/line-break normalization but not of the composer coming
  back empty or drastically truncated), and shortly after, by polling (bounded to
  `SEND_VERIFY_TIMEOUT_SECONDS`, 12s) for the stop button to appear or the composer to clear. A
  failed send retries once from a cleared composer (`MAX_SEND_ATTEMPTS`) before `run_prompt()` gives
  up with a clear diagnostic -- surfacing a real failure in seconds instead of silently waiting the
  full reply timeout. 13/13 tests pass, including two new fake-page-driven regression tests proving
  a send is never trusted on an empty/stale composer and Enter is never pressed on unverified content.

## [0.1.186] - 2026-08-25

### Fixed
- **`electron/main.ts`** -- dev-mode's window creation raced Vite's own startup and had zero retry
  on the initial load. `dev.ps1`'s `Wait-HttpReady` check confirms Vite is reachable before
  launching Electron, but that check and `mainWindow.loadURL('http://localhost:5173')` are two
  separate HTTP requests moments apart -- a dev server can still refuse a connection in that gap.
  A single failed `loadURL` used to be permanent: `did-fail-load` set `SYN-BOOT-201` immediately,
  the window (created with `show: false`) never showed or reached `ready-to-show`/`did-finish-load`,
  and the *separate* 45s interface-readiness timer then also fired `SYN-BOOT-202` -- two diagnostics
  for what was really just Vite not being reachable yet, with the console showing nothing past
  "-> Launching Electron" the whole time. Reproduced live: running `node node_modules/electron/cli.js .`
  in isolation while Vite wasn't up yet produced the exact `ERR_CONNECTION_REFUSED` failure with no
  retry. Fixed with `loadDevServerWithRetry()` -- up to 5 attempts, 750ms apart, retrying only on
  `ERR_CONNECTION_REFUSED`/`ERR_EMPTY_RESPONSE`; a real non-transient failure (Vite never starts,
  wrong port) still exhausts the retries and reports `SYN-BOOT-201` normally. Verified live via a
  fresh `dev.ps1 -AppOnly` run: the Electron window loaded and showed the full Home dashboard on the
  first attempt with the fix in place.

## [0.1.185] - 2026-08-25

### Fixed
- **`daemon/synapse_daemon/tools/cloudtap.py`** -- the URL regex Cloudtap uses to parse the public
  tunnel hostname out of `cloudflared`'s output (`_URL_RE`) could match `api.trycloudflare.com`,
  Cloudflare's own fixed control-plane hostname, instead of the real assigned tunnel hostname.
  `cloudflared` prints that URL in its own output when a quick-tunnel request to Cloudflare's API
  fails (most commonly during a network outage) -- the old regex, being unanchored, grabbed the
  *first* `https://*.trycloudflare.com` match in the stream, which could be that error line rather
  than the real boxed-banner URL. The tunnel was then reported "live" pointing at Cloudflare's real
  API, which returns HTTP 405 on every request -- found live via WAN auto-start's
  `/api/v1/remote-access` verification reporting `"failure_code":"http_status","failure_message":
  "HTTP 405 from https://api.trycloudflare.com/api/v1/health"` after a real internet outage.
  Fixed by excluding the exact `api.trycloudflare.com` hostname from the regex via a negative
  lookahead -- real tunnel hostnames are always random multi-word subdomains and will never
  literally be `api`. Added a regression test
  (`test_api_trycloudflare_error_line_is_not_mistaken_for_the_tunnel_url`) that reproduces the
  exact failure sequence (an error line mentioning the API URL, followed by the real banner) and
  asserts the real hostname is still correctly picked up.

## [0.1.184] - 2026-08-24

### Fixed
- **`scripts/daemon-watchdog.ps1`** -- the sibling of the v0.1.183 tunnel-watchdog fix, found live
  the same day on the daemon-watchdog itself: `$GraceSeconds` (25) was actually *less* than
  `$IntervalSeconds` (30), so the post-restart grace window structurally covered zero check
  cycles -- by the time the first check after a restart ran, grace had already expired, and a
  single "nothing listening yet" observation (the relaunched daemon just hadn't finished binding
  the port) immediately read as an intentional stop and the watchdog exited for good, leaving the
  daemon completely unprotected. Confirmed happening for real under today's memory pressure (see
  the same day's daemon-wedging/memory-pressure investigation). Fixed with the same pattern as
  tunnel-watchdog.ps1: `$GraceSeconds` raised to 60 (safely above `$IntervalSeconds`), and the
  non-grace "nothing listening" branch now requires `$FailureThreshold` consecutive absent checks
  before concluding an intentional stop, instead of exiting on the very first one.

## [0.1.183] - 2026-08-24

### Fixed
- **`scripts/tunnel-watchdog.ps1`** -- closed a real false-positive self-termination bug found
  live: the watchdog treated a single "nothing listening on port 7878" observation as proof
  Synapse was intentionally stopped and exited permanently, orphaning the tunnel with nothing
  watching it afterward. In practice the daemon-watchdog's own restart cycle (killing a wedged
  daemon process and relaunching it) creates a brief 1-2s gap where the port isn't listening --
  a gap the tunnel-watchdog's 45s-interval check can land inside purely by coincidence. Confirmed
  happening for real 2026-08-24 (`02:14:46 ... tunnel watchdog exiting`), leaving the persistent
  tunnel unwatched for over 40 minutes until caught and manually relaunched. Fix: the "daemon
  absent" check now requires the same `FailureThreshold` consecutive-check discipline already
  used for the reachability check (default 3 checks, ~135s) before concluding an intentional
  shutdown, instead of exiting on the very first miss.

## [0.1.182] - 2026-08-22

### Added
- **`scripts/tunnel-watchdog.ps1`** -- companion to the daemon watchdog, closing the other real
  gap for leaving Synapse running unattended for multiple days: nothing previously restarted
  the persistent Cloudflare Tunnel (`cloudflared tunnel run synapse`) if it crashed. The daemon
  could stay perfectly healthy locally while every MCP connector went completely dark, with no
  automatic recovery and no signal other than a person noticing. Checks two distinct failure
  modes every 45s: the `cloudflared` process itself missing (restarts immediately, no threshold
  -- an absent process is unambiguous), and the process alive but the public URL not actually
  answering for 3 consecutive checks (a stale/stuck tunnel, mirroring how the daemon's own
  wedge was invisible to a plain process-liveness check). Self-terminates if the daemon itself
  isn't running at all, matching `daemon-watchdog.ps1`'s existing convention -- assumes an
  intentional stop rather than fighting it. Wired into `scripts/dev.ps1` via a new
  `Start-TunnelWatchdog` helper, called alongside `Start-PersistentTunnel` in both
  `-DaemonOnly` and the full-stack launch path.
  Verified against a real kill, not just a syntax check: force-killed the live `cloudflared`
  process, confirmed the watchdog detected it missing on its very next check and relaunched it
  automatically, confirmed `synapse.whatapc.com` was answering correctly again within seconds
  -- zero manual intervention.

## [0.1.181] - 2026-08-21

### Fixed
- **`scripts/daemon-watchdog.ps1`'s v0.1.180 fix was itself incomplete -- found by continuing to
  watch the same live incident rather than declaring victory after the first repair.** The
  defense-in-depth try/catch added in v0.1.180 correctly kept the watchdog process alive, but
  it revealed a second bug hiding behind the first: `Restart-WedgedDaemon` wrote its
  `=== WATCHDOG RESTART ===` marker into `data/daemon-runtime.log` *before* calling `taskkill`,
  and that `Add-Content` call was throwing (`The process cannot access the file ... because it
  is being used by another process` -- the still-alive wedged daemon holds its own open write
  handle on that same log via its `>>` redirect). Because that write had no try/catch of its
  own, the exception aborted `Restart-WedgedDaemon` immediately -- meaning `taskkill` and the
  relaunch never ran at all, every single restart attempt, even though the outer catch made it
  *look* like the watchdog was working (it kept logging "restarting" every cycle). The daemon
  stayed down for several minutes across repeated failed cycles as a result -- a real, current
  outage caught and fixed live, not a hypothetical.
  Fixed by reordering (log the marker *after* `taskkill`, once the old process's handle is
  actually released) and wrapping that write in its own try/catch too, matching every other
  step in this function -- a logging failure must never be able to skip the actual recovery
  action that follows it. Verified against the real, still-active incident: killed both the
  stuck watchdog and the wedged daemon manually, relaunched clean via `scripts/dev.ps1
  -DaemonOnly` (which starts the newly-fixed watchdog automatically), confirmed the fresh
  daemon healthy both locally and through the persistent tunnel with zero manual tunnel/connector
  changes needed.
  Also confirmed during this same incident, for the record: two delegated ChatGPT sessions
  running `npm test` as daemon-managed child processes drove the underlying CPU contention that
  triggered all of this (82% system load) -- filed as a separate, lower-priority proposal (not
  a bug in this fix) rather than addressed here.

## [0.1.180] - 2026-08-21

### Fixed
- **`scripts/daemon-watchdog.ps1` could silently die instead of restarting a wedged daemon --
  found live, the same day it shipped, by a real production trigger.** Two delegated ChatGPT
  sessions running heavy `npm test` suites as managed child processes drove real CPU
  contention (82% load observed), which intermittently starved the daemon's event loop long
  enough to fail 3 consecutive health checks. The watchdog correctly detected this and logged
  "restarting" -- then the whole watchdog process vanished with no further log line, no
  relaunch, and the old (still-unresponsive) daemon process left completely unprotected. Root
  cause: `$ErrorActionPreference = 'Stop'` is script-wide, but the restart path
  (`taskkill` / `Start-Process`) and the main loop itself had no try/catch anywhere -- a single
  exception (this machine promotes native-command non-zero exit codes to terminating errors)
  propagated all the way out and killed the script. Fixed with try/catch around each risky step
  in `Restart-WedgedDaemon` (a failure there now logs and keeps trying rather than propagating)
  plus a defense-in-depth try/catch around the entire main loop body, so no unexpected error
  anywhere can silently take the watchdog down again. Re-verified against a second real trigger
  minutes later: full cycle completed correctly (3/3 failures -> killed the old PID -> relaunched
  -> confirmed healthy), unlike the first attempt.
  Separately confirmed as a genuine non-bug during the same investigation: the underlying
  CPU-contention-driven flapping itself is not a Synapse defect -- it is expected behavior when
  a managed test suite (reattached by `process_manager` on every daemon start) competes for CPU
  with the daemon's own event loop on this one machine. Worth a future look (a more generous
  health-check timeout, or de-prioritizing managed test-runner children) but out of scope for
  this fix, which is specifically about the watchdog's own reliability.
  The persistent Cloudflare Tunnel from v0.1.179 needed zero manual intervention through two
  real restarts during this incident -- confirming its whole purpose held up under a genuine,
  unplanned trigger, not just the planned verification.

## [0.1.179] - 2026-08-21

### Added
- **Persistent Cloudflare Tunnel (`synapse.whatapc.com`), replacing the per-restart random
  quick-tunnel hostname.** Justin's explicit ask: stop having to recreate the ChatGPT/claude.ai
  connector every time the daemon restarts. Root cause: `cloudflared tunnel --url` ("quick
  tunnel", what Cloudtap's WAN auto-start already used) issues a brand-new random
  `*.trycloudflare.com` hostname on every run -- any live connector pointed at the old one
  breaks and has to be manually recreated, and a freshly created hostname can also take a
  while to become reachable from an external consumer's own network path even after
  recreating it (observed live this session: confirmed externally reachable via a fetch from
  a different network origin, while a ChatGPT session still got `mcp_network_error` for a few
  minutes -- consistent with propagation lag on a brand-new hostname, not a real outage).
  A named tunnel has a hostname that never changes across restarts, which removes both costs
  at once.
  Justin connected his own `whatapc.com` domain (registered at GoDaddy, previously used for a
  Shopify store + Microsoft 365 email, not currently in active use for the store) to a new
  Cloudflare account, keeping the email-related DNS records (`MX`, `autodiscover`, `msoid`,
  `lyncdiscover`, SIP `SRV`, SPF/domain-verification `TXT`) exactly as scanned/imported --
  none were touched or need to be, and this was confirmed by direct DNS lookup after the
  nameserver cutover (`MX` still resolves to `whatapc-com.mail.protection.outlook.com`). DNSSEC
  was off, so no propagation conflict there either. A zone-file backup was downloaded before
  the nameserver change as a precaution.
  `cloudflared tunnel login` / `tunnel create synapse` / `tunnel route dns synapse
  synapse.whatapc.com` set up the tunnel and DNS route; `C:\Users\justi\.cloudflared\config.yml`
  routes `synapse.whatapc.com` to `http://localhost:7878`. Verified end to end before treating
  it as done: both `tools/list` and `tools/call` succeed through the new hostname (confirmed
  locally and from a separate external network origin), and the ChatGPT connector itself
  successfully fetched live tool schemas through it.
  `scripts/dev.ps1` now has a `Start-PersistentTunnel` helper (idempotent -- detects an
  already-running `cloudflared tunnel run synapse` process rather than starting a duplicate)
  called alongside `Start-DaemonWatchdog` in both `-DaemonOnly` and the full-stack launch path,
  so the same tunnel comes up automatically on every future restart rather than requiring a
  manual step. `wan_auto_start` was turned off via `PATCH /api/v1/system/network` now that this
  replaces Cloudtap's quick-tunnel for that role, so the daemon no longer opens a redundant
  second tunnel on boot.
  A new ChatGPT connector ("Synapse") was created pointed at the stable URL and given full
  ("Allow all actions") permissions, replacing the disposable "Synapse Live N" series from
  earlier in the session -- this one should not need to be recreated again.

Changed:
- `scripts/dev.ps1`: new `Start-PersistentTunnel` helper, called from both `Start-DaemonOnly`
  and the full-stack launch loop.

## [0.1.178] - 2026-08-21

### Added
- **Daemon watchdog (`scripts/daemon-watchdog.ps1`).** Found live this session: the daemon
  wedged (event loop stopped serving requests) while staying alive at the OS level -- process
  running, port still LISTENING -- for 25+ minutes before anyone noticed, silently blocking
  every MCP connector call the whole time. `Get-Process` and `netstat` both say "fine" in that
  state; only a real HTTP round-trip against `/api/v1/health` reveals it. Filed and immediately
  fixed as review proposal `d8e50063a990` rather than left for later, per standing instruction
  that a significant reliability gap found in passing gets fixed on the spot, not just filed.
  The watchdog polls `/api/v1/health` every 30s (configurable) and force-restarts the daemon
  after 3 consecutive failures, identifying the daemon process by which PID owns the port
  (same pattern `dev.ps1`'s `Clear-StalePort` already uses) rather than trusting a PID it
  remembered, so it works correctly even across a restart it did not itself trigger.
  Self-terminating by design: if nothing is listening on the port at all, it assumes the
  daemon was stopped on purpose (Ctrl+C, taskkill, script exit) and exits quietly rather than
  fighting an intentional shutdown -- nothing has to remember to stop it.
  `scripts/dev.ps1` now spawns it automatically alongside the daemon in both `-DaemonOnly` and
  the full-stack launch path.
  Verified against a *real* reproduction, not just a syntax check: a disposable Python process
  that binds the port and never responds (faithfully reproducing the actual incident's
  connect-timeout symptom) on a scratch port, confirming detect -> kill -> relaunch ->
  healthy-again actually works end to end, and that a clean stop still self-terminates the
  watchdog. That test caught a real bug before it shipped -- the first version restarted the
  wedged process correctly, then saw no listener on its very next poll (the fresh daemon was
  still mid-boot, hadn't bound the port yet) and immediately self-terminated, leaving the
  just-recovered daemon completely unprotected. Fixed with a grace window after a
  watchdog-triggered restart that checks the relaunched process's liveness by PID rather than
  by port state, since the port genuinely is not bound yet during that window.
  Known, honest tradeoff: restarting the daemon opens a new Cloudtap WAN tunnel with a new
  random hostname (existing, unrelated daemon behavior) -- any live MCP connector pointed at
  the old tunnel needs to be recreated after a watchdog-triggered restart. A wedged daemon is
  already fully unreachable to that connector either way; recovering automatically, even at
  that cost, beats staying wedged indefinitely.

Changed:
- `scripts/daemon-watchdog.ps1`: new module.
- `scripts/dev.ps1`: new `Start-DaemonWatchdog` helper, called from both `Start-DaemonOnly` and
  the full-stack launch loop right after the daemon becomes ready.

## [0.1.177] - 2026-08-21

### Added
- **`synapse_watch_repo` MCP tool + `POST /api/v1/watch/repo`.** A bounded server-side
  long-poll (default 60s, max 120s) that waits for a git repo's `git status --porcelain` to
  change, then returns what changed -- built directly from a real need this session: an AI
  waiting on delegated work (another AI session through a connector, a background build)
  shouldn't have to burn a full context-gathering turn every time it checks in. One call held
  open costs far less than repeated full checks, and only produces something worth acting on
  when a real change actually happened.
  New module `repo_watch.py` ships both an async version (`wait_for_repo_change`, used by the
  REST route) and a blocking one (`wait_for_repo_change_sync`, used by the MCP tool --
  `mcp_connector._call_tool` is not async, matching the existing convention that tools like
  `synapse_run_command` already block their calling thread for the call's duration).
  Known, honest gap: only git-tracked paths are supported -- a non-git directory returns an
  error rather than silently timing out forever. A generic mtime-walk fallback for non-git
  paths is real future work, not built here because nothing this session needed to watch was
  outside a git repo.

Changed:
- `daemon/synapse_daemon/repo_watch.py`: new module.
- `daemon/synapse_daemon/routes_watch.py`: new REST route.
- `daemon/synapse_daemon/app.py`: mounts the new router.
- `daemon/synapse_daemon/mcp_connector.py`: new `synapse_watch_repo` schema, annotation, handler.
- `daemon/tests/test_repo_watch.py`, `test_routes_watch.py`: new, cover the async/sync module
  functions directly and the REST route.
- `daemon/tests/test_mcp_connector.py`, `test_mcp_tool_annotations.py`: MCP-layer coverage for
  the new tool.
- `package.json`, `pyproject.toml`, `daemon/synapse_daemon/__init__.py`: 0.1.176 -> 0.1.177.

## [0.1.176] - 2026-08-21

### Fixed
- **Home page's "Needs attention" panel showed a raw `Failed to fetch` with no way to recover
  without a full page reload.** `refreshInsights` (renderer/pages/Home.tsx) already caught
  fetch failures via `Promise.allSettled` and set a local error string, but the error surfaced
  the raw `Error.message` (literally "Failed to fetch" for a network failure) and had no retry
  action -- unlike the sibling `projectsError` block in the same file, which already had a
  proper "Couldn't load your projects" card with a Retry button. Gave the insights error the
  same treatment: friendlier fixed messages instead of the raw browser error text, and a Retry
  button that re-runs the fetch. `refreshInsights` moved out of the effect it lived in so the
  button can call it directly (a plain function is fine here -- the setters it calls are
  React's stable setState identities, so a call landing after unmount is a harmless no-op, same
  risk profile the file already accepts elsewhere).
  Verified: `tsc --noEmit` clean, live render confirmed no console errors and the happy path
  unchanged. Did not specifically trigger the error state live (would need simulating a real
  fetch failure) -- noting that honestly rather than claiming full UI verification.

Changed:
- `renderer/pages/Home.tsx`: `refreshInsights` lifted out of its `useEffect`, friendlier error
  messages, new `retryInsights` handler, Retry button next to the insights error.
- `package.json`, `pyproject.toml`, `daemon/synapse_daemon/__init__.py`: 0.1.175 -> 0.1.176.

## [0.1.175] - 2026-08-20

### Added
- **`token-lean-delegation` playbook** -- documents the pattern this session started using to
  keep the orchestrating AI's own token spend low: scope a unit precisely, delegate the actual
  implementation to a cheaper path (local Ollama via `coder_runtimes`/`synapse_delegate_module`,
  or ChatGPT UI via the Synapse connector), then review like a code reviewer instead of writing
  every diff itself. Captures the real gotchas discovered the hard way setting this up live: the
  Cloudflare quick-tunnel URL rotates on every daemon restart and there is no way to edit an
  existing ChatGPT connector's server URL in place (only rename/disconnect/delete) -- so a
  reconnect after a restart means creating a fresh connector, always against
  `GET /api/v1/remote-access`'s current `wan.public_url`, never a URL seen in an earlier log
  line or turn (using a stale one produces a 424 that looks identical to the unrelated,
  already-documented transient 424 in `chatgpt-autonomous-app-build`). Also documents two
  browser-automation pitfalls hit live this session: typing a long URL via synthesized
  keystrokes can silently drop its last character (use a direct form-value/JS set and verify
  length instead), and a "new chat" composer can carry stale draft text across navigation that
  silently prepends to the next thing typed into it (verify it's empty first).

Changed:
- `daemon/synapse_daemon/playbooks.py`: new `ensure_bootstrap_token_lean_delegation_playbook`
  + `TOKEN_LEAN_DELEGATION_PLAYBOOK_ID`.
- `daemon/synapse_daemon/app.py`: seeds the new playbook alongside the existing three at startup.
- `daemon/tests/test_playbooks.py`: two new tests -- real steps seeded, reseed preserves a
  reported status.
- `package.json`, `pyproject.toml`, `daemon/synapse_daemon/__init__.py`: 0.1.174 -> 0.1.175.

## [0.1.174] - 2026-08-20

### Added
- **`default_execution_mode` on agent role templates** -- closes ADR-0025's own named
  "load-bearing gap": PTY-spawned squad workers reported zero tokens, because nothing
  actually launched them in `automatic` (headless, prompt-driven) mode by default, only
  `interactive` (an idle TUI a human drives by hand, which never prints a usage line for
  anything to parse). Scoping this before touching code found the fix was NOT "build a
  usage parser" -- `runtime_usage.py`'s parsers and `ai_executions.finalize_pty_execution`
  already read usage from automatic-mode PTY output correctly, proven end to end by an
  existing test (`test_agent_squads.py`'s automatic-launch coverage). The actual gap was
  one layer up: every launch path (quick-actions, `/delegate`) falls through to the
  `interactive` default because nothing opts a role in.
  A role can now set `default_execution_mode: "automatic"`; a launch request's own
  `execution_mode` still wins when given explicitly, so nothing about today's behavior
  changes for any existing role -- this is pure opt-in infrastructure. New migration
  `034_role_default_execution_mode.sql` (nullable column, `NULL` = today's behavior
  exactly). No default role was switched over in this change -- deliberately: flipping a
  role's default execution behavior is a real UX change (a worker a human expected to be
  able to watch/drive interactively would instead run headless), so that's left for
  whoever actually wires it into the qa-bug-hunt-squad roles or another automatic-shaped
  workflow to decide explicitly, not something to default silently.
  Separately found and NOT fixed here (flagged to the review inbox instead): the
  `templates/quick-actions/bug-hunt-squad.json` prompt references
  `POST /ai-bundles/install/qa-bug-hunt-squad` and role ids like `edge-case-hunter`/
  `user-simulator` that do not exist anywhere in `ai_bundles.py` or `agent_squads.py` --
  that quick-action would 404 if actually run today. A real, separate bug from the
  token-accounting gap.

Changed:
- `daemon/synapse_daemon/migrations/034_role_default_execution_mode.sql`: new, additive.
- `daemon/synapse_daemon/agent_squads.py`: `default_execution_mode` field on
  `AgentRoleTemplate`/`Create`/`Update`, row mapper, and the create/update SQL.
- `daemon/synapse_daemon/routes_agent_squads.py`: `AgentWorkItemLaunchRequest.execution_mode`
  is now `AgentExecutionMode | None` (None = no explicit request, distinct from an explicit
  "interactive"); the launch handler resolves request -> role default -> interactive once,
  right after the role is fetched, and every downstream use reads that resolved value.
- `daemon/tests/test_agent_squads.py`: two new tests -- a role default reaching a real
  launch (argv included) when the request specifies nothing, and an explicit request
  overriding the role default.
- `package.json`, `pyproject.toml`, `daemon/synapse_daemon/__init__.py`: 0.1.173 -> 0.1.174.

## [0.1.173] - 2026-08-20

### Added
- **`synapse_quality_summary` MCP tool.** Closes the fourth and final subsystem the 0.1.168
  playbook note listed as having no MCP tool at all (after search in 0.1.170 and AI-memory
  read-back in 0.1.172). Wraps the existing zero-argument `quality_os.quality_summary(conn)`
  -- already used internally by `routes_ai.py`'s `/ai/context` digest -- and returns open
  gate counts, which are blocking, the most recently failing UI contracts, and the latest
  browser-proof evidence. Placed in the always-available (ungated) tool set alongside
  `synapse_list_sessions`/`synapse_recent_activity`, since UI-quality state carries no more
  sensitivity than the activity feed. Test seeds a real failing contract run through the
  REST API first, so the assertion is against actual gate data, not an empty shape.

  The MCP-server marketplace remains the one subsystem still without a tool, on purpose --
  its gap is the mutating half (install/start/stop other MCP servers), which needs an
  explicit decision about how much autonomous control to hand a remote AI before any code
  gets written, not a quiet wrapper.

Changed:
- `daemon/synapse_daemon/mcp_connector.py`: new `synapse_quality_summary` schema,
  annotation entry, and handler; imports `quality_os`.
- `daemon/tests/test_mcp_tool_annotations.py`: added to `EXPECTED_READ_ONLY`.
- `daemon/tests/test_mcp_connector.py`: new test seeding a real failing UI-contract run via
  REST, then asserting the MCP tool's summary reflects it.
- `package.json`, `pyproject.toml`, `daemon/synapse_daemon/__init__.py`: 0.1.172 -> 0.1.173.

## [0.1.172] - 2026-08-20

### Added
- **`synapse_get_project_ai_context` MCP tool.** `synapse_capture_note` has written to a
  project's shared AI memory (`.synapse-ai-context.md`) since it shipped, but nothing could
  read it back over MCP -- a write with no matching read, named explicitly as a gap in the
  same 0.1.168 playbook note that named the now-closed `search` gap ("a dedicated read-back
  tool for project AI-memory (.synapse-ai-context.md is write-only via capture_note
  today)"). The new tool wraps the existing `ai_context_memory.ai_context_path`/
  `ai_context_metadata` helpers directly (no REST route needed, same shape as
  `synapse_web_search` wrapping `local_agent.web_search`) and returns path/exists/size/
  last_modified plus the capped file content. Annotated `readOnlyHint: true`, ungated (like
  `synapse_get_project_records`, not behind the full-access URL) -- reading a project's own
  notes is no more sensitive than reading its ADRs/backlog, which are already unrestricted.
  A missing file (a project nobody has captured a note to yet) returns `exists: false`
  rather than an error; an unknown project id still 404s as a tool error.
  Of the four subsystems the 0.1.168 note listed as having no MCP tool, this closes the
  third (after `search` in 0.1.170). Quality OS (`quality_summary()`, already a
  zero-argument existing function) is next in line. The MCP-server marketplace's gap is the
  mutating half (install/start/stop other MCP servers) and needs an explicit decision about
  how much autonomous control to hand a remote AI before any code gets written -- it stays
  open on purpose.

Changed:
- `daemon/synapse_daemon/mcp_connector.py`: new `synapse_get_project_ai_context` schema,
  annotation entry, and handler.
- `daemon/tests/test_mcp_tool_annotations.py`: added to `EXPECTED_READ_ONLY`.
- `daemon/tests/test_mcp_connector.py`: three new tests -- file exists, file missing (not an
  error), and unknown project (is an error).
- `package.json`, `pyproject.toml`, `daemon/synapse_daemon/__init__.py`: 0.1.171 -> 0.1.172.

## [0.1.171] - 2026-08-20

### Added
- **A wall-clock deadline on scaffold piece retries (Phase B of the coder-runtime-ladder
  plan).** `build_blueprint`'s retry loop was already bounded by `max_attempts` (a count);
  it had no way to say "keep retrying until 6am" for an overnight batch, which the plan
  called for and the codebase didn't have. Added `deadline_seconds: float | None = None` --
  checked once per loop iteration against the elapsed time since the piece's own attempts
  began, and structured so it can only ever refuse to *start* a retry, never cancel one
  already running, and never skip the first attempt regardless of the deadline's value.
  Wired through `BuildRequest.deadline_seconds` in the `/blueprints/{id}/build` REST
  endpoint alongside the existing `max_attempts`, so it's reachable from the actual build
  API, not just from a Python caller of `build_blueprint` directly.
  Audited while resolving Phase B/C/D status against the plan doc at
  `.claude/plans/improve-it-so-we-expressive-bee.md`: Phases A, C, and D turned out to
  already be fully shipped (v0.1.144-v0.1.148), leaving this deadline as the one genuine
  gap worth filling now. (The plan's other Phase B ask -- queuing a build through "the
  existing scheduler" -- doesn't correspond to anything in this codebase; no
  scheduler/cron/queue module exists here, so that's a real feature to design, not a
  missed wiring.)

Changed:
- `daemon/synapse_daemon/scaffold/runner.py`: new `deadline_seconds` param on
  `build_blueprint`; retry-loop guard; a note recorded on early stop.
- `daemon/synapse_daemon/routes_blueprints.py`: `BuildRequest.deadline_seconds`, passed
  through to `build_blueprint`.
- `daemon/tests/test_scaffold_scenarios.py`: new test asserting a 0-second deadline still
  runs the first attempt but refuses a retry.
- `package.json`, `pyproject.toml`, `daemon/synapse_daemon/__init__.py`: 0.1.170 -> 0.1.171.

## [0.1.170] - 2026-08-20

### Added
- **`synapse_web_search` MCP tool.** The only way to reach the public internet through the
  connector before this was `synapse_http`, which is deliberately restricted to
  localhost/private addresses (it exists to reach the web scraper on :12345 and Synapse's own
  API, not the open web). That left search as a named, known gap in the MCP surface (called
  out explicitly in the 0.1.168 changelog note about the ChatGPT-web coder runtime playbook:
  "a list of subsystems that exist but have no MCP tool yet (search, Quality OS, ...)"). The
  new tool reuses `local_agent.web_search` (already shipped, unused by any MCP tool until now)
  -- DuckDuckGo's HTML endpoint, no API key needed -- and returns numbered title+URL results.
  Annotated `readOnlyHint: true, openWorldHint: true`: the first tool in this file to carry
  both, since it genuinely cannot change state anywhere but does reach the public internet
  (`synapse_http`'s `openWorldHint: false` reflects the opposite tradeoff -- it can write, but
  only locally). Gated behind the full-access URL (`_require_writes()`), same as
  `synapse_read_file` -- both are part of the "full access" surface by classification, not
  because either mutates anything.

Changed:
- `daemon/synapse_daemon/mcp_connector.py`: new `synapse_web_search` tool -- schema, annotation
  entry, and handler delegating to `local_agent.web_search`; imports `local_agent`.
- `daemon/tests/test_mcp_tool_annotations.py`: added to `EXPECTED_READ_ONLY`.
- `daemon/tests/test_mcp_connector.py`: two new tests -- a successful search (mocked) and a
  search failure surfacing as `isError: true` rather than a transport error.
- `package.json`, `pyproject.toml`, `daemon/synapse_daemon/__init__.py`: 0.1.169 -> 0.1.170.

## [0.1.169] - 2026-08-20

### Fixed
- **`synapse_runtime_status` reported a runtime as usable right after a daemon restart even
  when it was actually quota-exhausted.** `coder_runtimes.preflight()`'s cooldown tracking is
  in-memory by design and deliberately forgets exhaustion on every restart (the squad/blueprint
  dispatcher this serves treats one wasted call as cheap). That's the wrong default for this
  MCP tool: a caller right after a restart saw `usable_now: true` for a runtime the durable,
  evidence-backed `ai_runtime_capacity` ledger still remembered as `quota_exhausted` from a
  real provider error minutes earlier. Found live: a ChatGPT session called
  `synapse_runtime_status` through the connector and got the stale, optimistic answer while
  `/api/v1/ai/runtimes` showed the real exhausted state side by side. The MCP tool's handler
  now merges the durable capacity ledger in and overrides `usable_now` (with an explanatory
  note) whenever it disagrees with the fresher-but-less-informed in-memory cooldown.

Changed:
- `daemon/synapse_daemon/mcp_connector.py`: `synapse_runtime_status` handler merges
  `ai_executions.list_capacity()` into `coder_runtimes.preflight()`'s results.
- `daemon/tests/test_mcp_full_access_end_to_end.py`: new regression test seeding a durable
  quota-exhausted row and asserting the merged tool output reflects it.
- `package.json`, `pyproject.toml`, `daemon/synapse_daemon/__init__.py`: 0.1.168 -> 0.1.169.

## [0.1.168] - 2026-08-19

### Added
- **A real, autonomous ChatGPT-web coder runtime.** `chatgpt_browser_runtime.py` drives a
  live, already-signed-in `chatgpt.com` tab via Playwright the same way a human does: types
  a prompt (using Shift+Enter for line breaks -- a bare newline sends the message prematurely
  on the real UI, proven directly this session), waits for the send/stop button to flip back
  to "send" (with a separate stall timeout for the known "frozen tab" failure mode, not just
  an overall timeout), and reads the reply back. Registered as `CoderRuntime.CHATGPT_WEB` in
  `coder_runtimes.py`, mirroring the same `RuntimeResult` contract every other rung uses.
  Deliberately left out of `DEFAULT_LADDER` for now: it needs a one-time human login into its
  Playwright profile before it can run unattended, and it hasn't been exercised live yet --
  not an account-risk hedge, ordinary "don't ship untested code to the default path"
  discipline. Runs fully autonomously once that one-time login exists.
- **Third AI-facing playbook: `chatgpt-workflow-design-notes`.** An append-only living log
  (distinct from the other two operating-procedure playbooks) for ideas, gaps, and decisions
  about evolving the ChatGPT<->Synapse workflow itself, seeded with today's findings: the MCP
  connector is genuinely full-access with zero per-client filtering, a list of subsystems that
  exist but have no MCP tool yet (search, Quality OS, the MCP-server marketplace, project
  AI-memory read-back), confirmation that multiple simultaneous ChatGPT conversations already
  work today against the same connector with no code changes, and the ChatGPT-web-runtime
  decision above.
- **`chatgpt-autonomous-app-build` playbook amended** with an early step distinguishing the
  separate local-Ollama scaffold/blueprint system from ChatGPT building something itself via
  `synapse_write_file` (a real point of confusion this session), and noting that ChatGPT's own
  native web browsing is available alongside Synapse's web-scraper MCP tool.

## [0.1.167] - 2026-08-19

### Added
- **Second AI-facing playbook: `chatgpt-autonomous-app-build`.** Captures the brief structure,
  verification discipline, and check-in pacing that got ChatGPT to build a complete,
  independently-verified app (FlipLedger, a clothes-resale tracker) end to end through the
  connector with zero delegation to another coding runtime -- real scraped pricing data, a
  real self-caught bug fix via Reflex, real passing tests, real git history. Encodes the two
  load-bearing moves: naming the forbidden delegation tools outright in the brief, and never
  trusting a "done" summary without independently re-checking it (re-run the tests yourself,
  read the actual files, `git log` yourself). Also records two known, non-fixable gotchas so
  nobody re-diagnoses them from scratch: the ChatGPT tab can freeze mid-long-generation
  (recover via a fresh tab to the same chat URL) and new-connector creation can 424 transiently
  on OpenAI's own endpoint even when the MCP server is completely healthy.

## [0.1.166] - 2026-08-19

### Fixed
- **The Electron startup-recovery window could get permanently stuck** after an interrupted
  restart, even once the daemon and interface underneath were fully healthy. Root cause:
  `loadRestartMarker()` falls back to a synthetic SYN-BOOT-301 progress object (its `desktop`
  stage permanently marked `error`) when the saved `data/restart-progress.json` marker is
  missing, malformed, or more than ten minutes old. The recovery path cleared the stale
  marker *file* correctly, but kept layering subsequent stage updates onto that same
  in-memory object -- and `finishRestartWindow()` only auto-closes once every stage reads
  `success`, which a permanently-errored stage can never do. `electron/main.ts` now starts a
  fresh `startup`-kind progress object after handling an invalid marker, the same shape as an
  ordinary cold boot, so the window can reach all-success and close itself normally.
- Reproduced live: triggering `POST /system/restart` against a bare (non-Electron-supervised)
  daemon process left exactly this kind of orphaned marker; the next Electron launch showed
  the stuck "Synapse needs attention" / SYN-BOOT-301 window indefinitely. Confirmed fixed
  after the patch: clean relaunch, no leftover `restart-progress.json`, Electron/Vite/daemon
  processes all healthy.

## [0.1.165] - 2026-08-19

### Added
- **AI-facing playbooks** (`daemon/synapse_daemon/playbooks.py`, migration `033_playbooks.sql`):
  step-by-step procedures for driving something outside this codebase (the first one:
  how to actually get ChatGPT to call the Synapse MCP connector's tools from its own Chat
  tab, learned by hand this session). Steps are semantic, never pixel coordinates. Each
  playbook carries a `healthy` / `needs_attention` / `broken` status any executing AI can
  read (`synapse_list_playbooks`, `synapse_get_playbook`) or update
  (`synapse_report_playbook_status`) - so a UI change on the far end shows up as
  "needs_attention" for the next AI instead of a silent, repeated failure. Re-seeding the
  built-in playbook on every daemon startup refreshes its content but never resets a status
  an AI already reported.
- Reflex now reports a genuine `connected` status (same badge/styling as Web Scraper)
  instead of a static "launched by your AI when needed". Its stdio launch now includes
  `--http`, which opens a small side-channel health server (JSON status only, never the
  MCP protocol itself - the actual control plane stays per-session stdio, unchanged) that
  `McpServerManager.status()` now genuinely reachability-checks for Reflex specifically.
  `mcp-server.js`'s health server also gained an `EADDRINUSE` handler so multiple
  concurrent Reflex sessions attempting the same health port no longer crash - the first
  one binds it, the rest skip gracefully.

### Fixed (verified this session)
- ChatGPT genuinely calling Synapse MCP tools from a normal Chat-tab session (not the
  separate "Work" surface) was unverified until now. Live-tested through the actual
  connector: `synapse_write_file` wrote a real Python file to disk (content verified
  byte-for-byte independently), and `synapse_call_mcp_tool` reached the `reflex` server
  live - listing all 103 tools, reading real-time desktop state (`get_active_window`), and
  creating a real directory on disk (`create_directory`, independently verified). Root
  cause of the earlier confusion: attaching a connector via a chat's "..." menu doesn't
  reliably make the model call it - only a plugin's dedicated "View plugin detail" page's
  "Try in chat" button does, and that button defaults into ChatGPT's separate "Work"
  surface (its own, often-exhausted usage limit) rather than the normal Chat tab.

## [0.1.164] - 2026-08-18

### Fixed
- **Every MCP tool was unannotated, so ChatGPT treated all of them as write actions
  needing confirmation - including the ones that only read.** Per OpenAI's own docs, a tool
  with no `annotations.readOnlyHint` is a pessimistic default: treated as a write action.
  None of the 24 tools carried one. Every tool now declares `readOnlyHint`, and the
  genuinely dangerous ones (`synapse_run_command`, `synapse_http`, `synapse_call_mcp_tool`)
  are marked `destructiveHint: true` rather than softened to slip past a client's safety
  layer - a client asking for confirmation before those run is correct, not a bug.
  `test_mcp_tool_annotations.py` checks each classification against what the handler
  actually does, not just that a value is present.

- **`_writes_allowed()` hardcoded `repo_root() / "data"` instead of the daemon's actual
  configured data directory.** Silently wrong for any daemon started with a non-default
  `--data-dir`, and caught by a new test that set `mcp_writes_enabled=False` in an isolated
  scratch data dir and watched a write tool succeed anyway - it was reading the real repo's
  config instead. `_writes_allowed(data_dir)` now requires the caller to say which
  directory, with no silent fallback to get wrong again; both routers thread
  `storage.data_dir` through explicitly. A dead, never-actually-called duplicate of
  `_require_writes` (shadowed by a local one with the same name) is removed.

### Changed
- **One connector URL instead of two.** The same link now switches between read-only and
  full access as the toggle in Settings is flipped, rather than being two separate links to
  remember. `?mode=read` still exists for handing someone a link that stays read-only
  regardless of the toggle - documented as one line, not a second card.

## [0.1.163] - 2026-08-18

### Fixed
- **The real cause of the home-page error, this time.** 0.1.162 fixed one nested-transaction
  call site; a second, unrelated one (`ensure_current_host`) kept crashing `GET /profile`
  with the same `sqlite3.OperationalError: cannot start a transaction within a transaction`.
  It was not nesting - it was a genuine **concurrency** bug, self-inflicted in 0.1.161: the
  new health-probe heartbeat held a transaction open across a network `await` (up to
  `timeout_seconds`, every 2s heartbeat tick), on the single connection the whole daemon
  shares. Any request that opened its own transaction while that await was in flight
  collided with it.

  Fixed at both ends:
  - `_probe_health` no longer holds a transaction across the network probe - the read needs
    none, the probe runs with nothing held, and the write opens a transaction only once the
    slow part is done.
  - `Storage.transaction()` now serializes callers with a `threading.Lock`, so this class of
    bug can't be reintroduced by a future call site making the same mistake. The shared
    connection was already documented as multi-thread-accessible; nothing had ever made it
    safe.

  Verified against the live daemon under real load, not just unit tests: 798 concurrent
  `GET /profile` requests over 30 seconds (~15 heartbeat ticks) - 0 failures. Before the fix
  this failed intermittently within seconds.

## [0.1.162] - 2026-08-18

### Changed
- **MCP write access is a toggle in Settings, not an environment variable, and defaults ON.**
  An env var is the wrong shape for a user setting: it has to be present in whichever shell
  launched the app, so it silently reverted whenever Synapse was started a different way -
  which is exactly what happened repeatedly today. It is now persisted in `boot-config.json`
  and switched beside the connector URLs it governs.

  `SYNAPSE_MCP_ALLOW_WRITES` still wins when explicitly set to `1`/`0`, so a locked-down
  deployment can force either state, but it is no longer how a person turns this on.

  The safety property that replaces "off by default" is the read-only URL: `?mode=read`
  stays read-only however the machine is configured, so there is always a link you can hand
  out. The tests were repointed at that rather than deleted.

### Fixed
- **The error on the home page.** `GET /profile` returned 500 because `_set_sync_status`
  opened a transaction inside one that was already open - and it is called from the *failure*
  path of `_refresh_from_remote`. So any ordinary sync failure (offline, remote down) was
  replaced by `sqlite3.OperationalError: cannot start a transaction within a transaction`,
  and the real reason was never recorded. Recording a failure can no longer raise one.

## [0.1.161] - 2026-08-18

### Fixed
- **Every MCP server is now reachable and shows its tools.** Measured after the fixes:
  reflex 103, web-scraper 93, github 26, playwright 24, memory 9 - **255 tools**, where
  before only reflex answered.

  - `npx`-launched servers (playwright, memory, github) failed with `[WinError 2]` because
    `npx` is a `.cmd` shim on Windows and CreateProcess will not find it from a bare name.
    Now resolved through `resolve_command`, which already knew how to look beyond PATH.
  - The web scraper returned `400` on every call: streamable-HTTP MCP hands out an
    `Mcp-Session-Id` on `initialize` and rejects everything after it unless the id comes
    back. Its 93 tools were unreachable for want of one header.

- **A project running outside this daemon session is recognised again.** The health probe
  only looked at processes this daemon spawned, so an app started before a restart was never
  probed - the web scraper sat at `status: stopped` while serving happily. The probe now
  covers every project that declares one, and a healthy probe corrects a stale status.

- `GET /mcp-servers/{id}/tools` opened a transaction inside an existing one
  (`cannot start a transaction within a transaction`). It is a read; it uses the shared
  connection.

### Added
- **A page for every installed MCP server.** Reflex was listed in the sidebar and rendered
  a blank pane, which is why it felt missing. It now shows its live tool list, filterable,
  with the connection state taken from the server answering `tools/list` rather than from a
  flag written down once.

## [0.1.160] - 2026-08-18

### Added
- **Two connector URLs instead of one.** Read-only vs writes was a server-wide env var, so
  there was no link you could safely hand out while your own could still drive the machine.
  `?mode=read` now pins a URL to the read-only surface regardless of the server setting:
  **10 tools on the read-only link, 24 on the full one**, and the read-only link refuses a
  write with an explanation rather than a stack trace. Both are shown in Settings with what
  each can do.

- **All 103 Reflex tools reachable from a remote chat**, via a generic stdio MCP proxy
  (`synapse_list_mcp_tools` / `synapse_call_mcp_tool`) rather than a Reflex special case -
  so Playwright, GitHub and anything else registered comes along for free. Verified end to
  end: `get_system_info` returned this machine's real CPU and username through the tunnel.

### Fixed
- **Relaunching a project that was already running reported "failed".** `self._live` only
  knows children this daemon spawned, so anything started before a daemon restart was
  invisible: pressing Launch spawned a second copy, which died on the bound port. A healthy
  app looked broken, and the button that appeared to fix it was the thing breaking it.

  The contradiction was visible in the API the whole time - status `stopped` alongside
  health `healthy`. Launch now checks the expected port first, marks the project running,
  and says so instead of spawning a doomed duplicate.

## [0.1.159] - 2026-08-18

### Added
- **A remote MCP client can now dispatch real work, not just read.** The connector advertised
  10 read-only tools, so a chat connected over MCP could look at projects and do nothing with
  them. It now advertises 22, gated behind `SYNAPSE_MCP_ALLOW_WRITES` and the auth token:

  | Tool | What it unlocks |
  |---|---|
  | `synapse_runtime_status` | which rungs are usable and what each has spent today |
  | `synapse_delegate_module` | have codex/gemini/claude WRITE a module here and return it |
  | `synapse_run_command` | shell: create folders anywhere, git, npm, tests, launches |
  | `synapse_read_file` / `synapse_write_file` | file IO anywhere on the machine |
  | `synapse_http` | reach the web scraper's full REST API on :12345, and Synapse's own |
  | `synapse_list_blueprints` / `synapse_launch_work_item` | build recipes, start squad workers |

  Verified by driving the MCP endpoint exactly as a remote chat would: Gemini wrote a working
  `slugify.py` in 84.7 s (`'Hello, World!' -> 'hello-world'`), a new project folder was
  created outside the repo with a file in it that runs, and the web scraper answered on
  :12345.

  `SYNAPSE_MCP_ALLOW_WRITES=1` moved above the daemon launch in `scripts/dev.ps1` - it was
  set 13 lines *after* the `-DaemonOnly` branch already started the process, so it had never
  taken effect on that path.

  `synapse_http` is restricted to localhost and private ranges: it runs inside the operator's
  network, and an arbitrary outbound URL would make it an open proxy behind their firewall.
  Public fetching goes through the web scraper, which is reachable through it.

## [0.1.158] - 2026-08-18

### Fixed
- **Claude calls recorded $0.00 spend, always.** Claude only reports usage under
  `--output-format json` and the argv never asked for it, so the one rung metered in real
  money contributed nothing to the ledger. A spend tracker that always reads zero is worse
  than none, because it looks like it is working. Safe to add: `write_module` reads the
  module back off disk, so stdout only ever carries telemetry.

### Measured
- **Delegating to a cheaper Claude.** Same piece, same scenario deciding the verdict:
  haiku/low verified in 30 s for **$0.043**; sonnet/low verified in 20 s for $0.087. Haiku
  costs half for the same result; sonnet is faster.

  The larger saving is structural: a delegate's tokens never enter the orchestrator's
  context window. Context is paid for again on every later turn, while a delegate starts
  cold, does one job, and its transcript is discarded.

  And a second or third pass is not needed - the acceptance scenario already decides
  pass/fail objectively, so a reviewer can only add cost and opinions. Five delegated
  modules have now passed their tests first time with no review pass.

  Written up in `DELEGATION.md`.

## [0.1.157] - 2026-08-18

### Fixed
- **Health probes never ran.** `HealthProbe` has been in the project model since the
  beginning and `projects.set_health` was written to record the outcome, but nothing ever
  called either - `set_health` had exactly one caller in the whole repo and it was a test.
  Every project sat at `current_health: "unknown"` with `last_health_at: null` forever, so
  no health target could work however correct it was. The heartbeat now probes every live
  project.

- **`wbscrper` was polled at `/api/status`, which that server has never served.** The app
  came up fine and the probe 404'd, so it looked broken while working perfectly. Added a real
  `GET /api/health` to the scraper (version, uptime, pid - no DB, no browser, so it cannot
  fail for a reason unrelated to the process being alive) and repointed the probe.

### Added
- `HealthState.MISCONFIGURED`, distinct from `UNHEALTHY`. A 4xx other than 408/429 means the
  server *answered* - the process is alive and the URL is wrong. Those need opposite fixes
  and were indistinguishable, which is why this went unnoticed. Verified against the live
  scraper: `/api/status` reports misconfigured with "the app is up but that endpoint does not
  exist", `/api/health` reports healthy.

  Probing runs off the existing heartbeat rather than its own timer, logs only on transition
  so a bad probe cannot spam every 15 s, and cannot kill the loop.

## [0.1.156] -- 2026-08-17

### Added
- **Canonical Agent Squad execution and accounting foundation (ADR-0036).** Every squad
  launch now reserves a durable execution before PTY startup, returns its `execution_id`,
  and finalizes process/work outcomes and provenance-tagged usage exactly once. SQLite
  persists provider capacity across daemon restarts; unknown measurements remain null.
- `GET /api/v1/ai/runtimes`, `GET /api/v1/ai/executions/{id}`, and local-operator-only
  capacity/recheck actions expose typed, AI-discoverable readiness, usage, evidence,
  user attestation, and reset acknowledgement contracts without requiring a paid canary.

### Fixed
- Agent Squad PTY output now feeds the same token values used by work-item/squad rollups
  and budget gates. Copilot monthly exhaustion becomes durable and subsequent automatic
  selection skips it; Codex ANSI-wrapped usage footers parse correctly.
- Execution rows exist before an instant-exiting PTY can finalize, relaunches create
  separate attempts, failed spawns retain receipts while leaving work retryable, and
  timeouts remain sticky after late process events.
- Project-scoped workers can read only their assigned project's execution list and their
  own execution detail. Direct REST session documentation now includes the required bound
  session key and labels current root-token WAN/MCP writes as legacy high-risk access.

## [0.1.155] - 2026-08-15

### Added
- **Drafted blueprints arrive with scenario skeletons that fail until filled in.** Writing
  scenarios was the remaining bottleneck after `from-build`. The judgement cannot be
  automated - a scenario says what a *caller* needs - but the typing can be.

  The safety property is the design: every stub is
  `assert False, "TODO: state what a caller needs from read_rows(). It returned %r..."`, so
  an unfinished scenario **fails**. A stub that passed while asserting nothing would be a
  false pass wearing a TODO. It also prints what the function really returned, so whoever
  fills it in is looking at output rather than guessing.

  Placeholder arguments are typed by name - `user_id` and anything ending in `_id` get `0`,
  the rest get `""` - because a string in an id position fails for the wrong reason and
  sends whoever reads it after the wrong bug.

  Stronger than 0.1.154's empty `tests`, which would have let a draft run and report nothing
  wrong; the test asserting `tests == ""` now asserts the stronger property instead.

  Delegated to codex:low (162 s, 7/7 first time) - fourth clean delegation in a row.

## [0.1.154] - 2026-08-15

### Added
- **POST /blueprints/from-build** - draft a blueprint from an app that already works.
  Authoring one by hand was the expensive part of the system and the only thing standing
  between "delegate this shape" and "delegate anything". The file layout is the piece list
  and each module's public signatures are its contract, so most of it is mechanical.

  Proven against a real build: distilling phase-d-cli recovers exactly the piece set of the
  hand-written cli-csv-report blueprint - reader, summary, cli - with cli's dependencies
  read off its imports and 
eport.py identified as the entrypoint.

  It deliberately does **not** invent scenarios. A scenario says what a *caller* needs, which
  is not recoverable from code that happens to work; inferring one from the implementation
  would assert whatever the code already does. Every piece returns 	ests="" and the
  blueprint is marked draft.

  The file-scanning half was delegated to codex:low per DELEGATION.md (105 s, 6/6 tests
  first time); the Blueprint/Piece wiring stayed hand-written because it needs the
  surrounding types.

### Fixed
- Two wiring bugs found by running the distiller on a real build rather than trusting it:
  scaffold_partials.py is copied into every workspace by the scaffold, so it looked like
  app code; and entrypoint detection was backwards - keying on "imports the most modules"
  picked cli.py, which 
eport.py imports. The entrypoint is the module **nothing**
  imports.

## [0.1.153] - 2026-08-15

### Added
- **DELEGATION.md** - which runtime, at what effort, for what work. Measured, dated and
  re-runnable, and surfaced through /ai/context so the next AI finds it without being told.
- enchmarks/delegation/bench.py - builds a real blueprint piece per (runtime, effort) and
  lets that piece's own contract and acceptance scenario decide whether it worked.

### Changed
- **Codex default effort: medium -> low, on measurement.** Eight builds across three real
  pieces at three effort levels **all verified with zero repairs**. Effort bought nothing in
  quality and cost real time: high averaged 136 s against low's 86 s. Token counts did not
  order by effort at all - low was cheapest on one piece and dearest on another, so
  run-to-run variance is larger than the effect.

  This reverses the medium default shipped in 0.1.151, which was reasoning rather than
  measurement.

  The result that settles it: storage - nine coupled functions, the piece the local tier
  failed 0/4 in every configuration across 441 minutes - was verified by **codex:low in 89
  seconds, first try**. Low suffices because a blueprint piece arrives with a contract and a
  scenario, so the model fills in a known shape rather than deciding what the shape is.

- write_module and uild_blueprint take per-runtime profiles; usage is recorded per
  piece, so a routing decision and a budget read from the same measurement.

## [0.1.152] - 2026-08-15

### Added
- **A spend ledger and a preflight**, so a long build is planned against what is left rather
  than started hopefully. RuntimeResult.usage is captured on every call - success or
  failure, because a failed call still spends - appended to an append-only JSONL by
  
ecord_call, and rolled up per rung by preflight.

  The reactive half only fires *after* a call fails, and the rungs that fail first are the
  ones that would have been driving the build.

  
untime_ledger.py was delegated to Gemini, like the usage parser: 96 seconds, stdlib
  only, 7/7 tests first time - including that a half-written last line costs one entry
  rather than the whole history.

### Fixed
- **Gemini reports exhaustion on stdout, inside its JSON**, not on stderr:
  "You have exhausted your daily quota on this model". looks_exhausted read only stderr,
  so an empty tier looked like an ordinary failure. Both streams are read now.

  Third vendor, third wording: copilot says "exceeded your monthly quota", gemini says
  "exhausted your daily quota", and the original patterns wanted "quota exceeded" in that
  order and matched neither.

- The squad test still asserted codex's old argv containing --ignore-user-config. That
  flag was removed in 0.1.149 because it silently disabled the sandbox - meaning every squad
  worker on codex had been unable to write a file. The expectation now asserts what
  WORKSPACE authority means there: --sandbox workspace-write.

## [0.1.151] - 2026-08-15

### Added
- **Per-rung model and effort control.** RuntimeProfile (model, effort, max_budget_usd,
  max_credits) rendered into each vendor's own flag vocabulary:

  | rung | model | effort | ceiling |
  |---|---|---|---|
  | claude | --model | --effort {low..max} | --max-budget-usd |
  | codex | -m | -c model_reasoning_effort= (max/xhigh collapse to high) | - |
  | copilot | --model | none - not faked | --max-ai-credits |
  | gemini | -m | none | - |

  Two defaults were quietly costing us. **Codex runs at 
easoning effort: low** unless
  told otherwise - its own header prints it - so the default profile asks for medium.
  **Gemini free allowance is per-model**: Flash ~1,500 requests/day against Pro's 25-50, so
  the default profile names a Flash model rather than letting a rung burn the tier by
  accident.

- **
untime_usage.parse_usage**, reporting what one run consumed per rung. Gemini -o json
  is now always on, since it is the only way to get that rung's token counts back.

  Written by **Gemini** rather than by hand: free tier, idle, and exactly the shape Phase C
  showed works - small, contract-shaped, checkable against samples that already existed.
  105 seconds, stdlib only, and it passed all 8 tests first time, including the two cases
  most likely to be wrong: gemini prints warning lines before its JSON, and 1,200.50 must
  parse as 1200.50 rather than 1.

## [0.1.150] - 2026-08-15

### Added
- **Gemini joins the default ladder**, between the paid trio and the local models:
  claude -> codex -> copilot -> gemini -> local.

  Almost nothing had to be built - it was already installed, already in the CoderRuntime
  enum, and already had a headless_argv branch mapping our authority levels onto its
  --approval-mode (plan / auto_edit / yolo). It was simply never in the rotation.

  Exercised before being trusted, because the two rungs before it had never been run and
  both turned out to be broken: gemini built the 
eader piece 1/1, verified, 0 repairs,
  188 s.

  Placement is deliberate - a **last paid resort**, not a preference. Weaker than Claude or
  Codex here, but a far better landing than the local tier, because it answers in minutes
  rather than overnight and its free allowance is generous where Copilot's is not.

  Recorded in the module docstring because it will otherwise bite: Google's free allowance
  is per-model and lopsided. Flash and Flash-Lite get ~1,500 requests/day; Pro is 25-50/day
  and, since May 2026, largely behind billing. A gemini rung should ask for a Flash model
  unless told otherwise.

## [0.1.149] - 2026-08-14

### Fixed
- **Codex could never write a file.** --ignore-user-config silently overrides
  --sandbox workspace-write back to read-only - whatever the flag order, and even against
  an explicit -c sandbox_mode="workspace-write". Codex reported sandbox: read-only in its
  own header, refused every patch with "writing is blocked by read-only sandbox", **and
  exited 0**, so the build recorded a success over an empty workspace. The flag is gone.

  Measured, same directory and prompt: with it, no file; without it, file written. This also
  affected every Codex squad worker, which has been running read-only since the argv was
  first written.

- **A real quota message did not read as exhaustion.** Copilot says
  "You have exceeded your monthly quota (Request ID: ...)" and exits 1. The patterns expected
  "quota exceeded" in that order and matched nothing, so an exhausted tier looked like a hard
  failure - the one distinction the ladder exists to make.

### Verified for the first time
The middle rungs of the ladder had never produced a piece: claude had built all 3, local
had been measured for 441 minutes, and codex and copilot had built nothing ever. They are
exactly the rungs that engage when Claude credits run out.

- codex now builds the 
eader piece: 1/1, verified, 0 repairs, 113 s.
- **Fallback proven against a genuinely exhausted tier.** Copilot on this machine really has
  exceeded its monthly quota, so the ladder was tested against the real condition rather than
  a mock: it detected the exhaustion at 27 s, dropped a rung, and codex finished the piece
  verified at 142 s, with a 3485 s cooldown recorded against copilot.

## [0.1.148] - 2026-08-14

### Phase C measured

Four proposed reliability changes, gated on four runs each. The result is a **conjunction**,
not a winner:

| Arm | Piece size | Targeted repair | Model's test | All pieces pass | Median run |
|---|---|---|---|---|---|
| baseline | 9 functions | off | is the gate | 0/4 | 2310 s |
| both | 9 functions | on | advisory | 0/4 | 594 s |
| deepseek | 9 functions | on | advisory | 0/4 | 732 s |
| split-plain | 3 x 3 | off | is the gate | 0/4 | 3132 s |
| **split** | **3 x 3** | **on** | **advisory** | **4/4** | **244 s** |

Splitting alone does not work and the switches alone do not work. Only small pieces *and* an
advisory self-test together turned a task the tier could never finish into one it finished
four times out of four - 9.5x faster than the baseline into the bargain.

split-plain exists because "splitting works" would otherwise have been a claim about three
changes at once, and it would have been the wrong claim. Its pieces failed on the model's own
test - TypeError: tuple indices must be integers - not on the blueprint's.

All five arms complete: four runs each, 441 minutes of local inference. `split-plain` was
published as 0/2 while its last two runs were still going, rather than rounded to the 0/4 it
was plainly heading for. It did land on 0/4, but it was measured before it was written -
which is the only order that means anything in a benchmark this one keeps catching itself
out on.

deepseek-coder:6.7b is slower and no more reliable. Selectable, not promoted.

Written up in enchmarks/app-build/PHASE_C_RESULTS.md.

## [0.1.147] - 2026-08-14

### Fixed
- **The contract checker could not see a re-export**, so it rejected every facade.
  `public_interface` read `def` statements off the AST, and a facade exposes its interface
  through `from store_users import create_user` instead. The split-storage build was
  reported as *"storage.py does not define `create_user(email, password_hash)`. It defines:
  ['init_db']"* while being entirely correct.

  This was the only thing standing in front of the best result of the Phase C sweep.
  Re-exported names now count as exposed, and their argument comparison is skipped rather
  than failed - the signature lives in the other file, and the generated contract test
  already checks it at runtime via `inspect.signature`, which resolves through the
  re-export. A name that is neither defined nor imported is still caught, and a wrong
  signature on a real `def` is still caught.

- `test_every_guarantee_names_a_check_that_really_exists` did not know about
  `acceptance`, which 0.1.146 introduced. A guarantee mapped to it must now have an
  acceptance script to be mapped to.

- The Phase C batch reported a run as failed when only its *storage* pieces were built -
  the assembled-app check cannot pass on a deliberate subset, since `app.py` imports an
  `api` that was never generated. It now judges the pieces it built and records the
  whole-app verdict separately, rather than quietly using whichever number was convenient.

## [0.1.147] - 2026-08-14

### Fixed
- **The contract checker could not see a re-export**, so it rejected every facade.
  `public_interface` read `def` statements off the AST, and a facade exposes its interface
  through `from store_users import create_user` instead. The split-storage build was
  reported as *"storage.py does not define `create_user(email, password_hash)`. It defines:
  ['init_db']"* while being entirely correct.

  This was the only thing standing in front of the best result of the Phase C sweep.
  Re-exported names now count as exposed, and their argument comparison is skipped rather
  than failed - the signature lives in the other file, and the generated contract test
  already checks it at runtime via `inspect.signature`, which resolves through the
  re-export. A name that is neither defined nor imported is still caught, and a wrong
  signature on a real `def` is still caught.

- `test_every_guarantee_names_a_check_that_really_exists` did not know about
  `acceptance`, which 0.1.146 introduced. A guarantee mapped to it must now have an
  acceptance script to be mapped to.

- The Phase C batch reported a run as failed when only its *storage* pieces were built -
  the assembled-app check cannot pass on a deliberate subset, since `app.py` imports an
  `api` that was never generated. It now judges the pieces it built and records the
  whole-app verdict separately, rather than quietly using whichever number was convenient.

## [0.1.146] - 2026-08-14

Phase D: a second blueprint, of a shape sharing nothing with the first. It found three real
holes, which is what a second example is for.

### The result

`cli-csv-report` built through the ladder: **3/3 pieces, all independently verified, 204
seconds, 1 repair.** Every piece written by `claude`. The equivalent local-tier piece takes
~1800 seconds and passes about one run in five.

The tool works: `1,200.50` and `$99.50` total to `1300.00`, `(25)` reads as `-25.00`, bad
rows are reported with their line numbers while the run continues, and exit codes are 0 / 1
/ 2 as specified.

### Fixed — three holes a second blueprint exposed

- **Multi-line prompts were being truncated at the first line.** `claude` resolves to
  `claude.CMD`, and cmd.exe ends an argument at a newline. Proven directly: a `.cmd` echoing
  its first argument printed `GOT:[LINE-ONE]` and dropped the rest. Every spec reached the
  model as its opening sentence, so modules came back built from the *filename* alone -
  asked for a CSV summariser in `summary.py`, Claude returned a file containing
  `# summary.py`. The requirement now goes in a brief file and the argument stays one line,
  which is what `routes_agent_squads` has always done.

  This also retires an earlier claim: the "successful" slugify verification was Claude
  inferring the function from the filename, not following the spec. It was luck wearing the
  costume of a passing test.

- **The entrypoint was only written as a side effect of the web checks.** A blueprint with
  no web surface was never assembled, so the CLI build reported "3/3 pieces built, 3
  independently verified" with no runnable program in the workspace. Verified pieces are not
  a delivered app.

- **Nothing checked the seams between pieces.** Every piece passed its own scenario while
  the assembled tool exited 1 on its own example: `cli` called `parse_amount` for validation,
  discarded the parsed value, and handed the raw string to a `summary` module doing its own
  `float()`. This is the `distance` / `distance_km` failure in new clothes - contracts catch
  signature drift, nothing caught data-shape drift across a seam.

### Added
- **`Blueprint.acceptance`** — a script run against the assembled app once every piece is
  built. Web blueprints got this from `webcheck`; everything else had nothing.
- **`_smoke_entrypoint`** — does the assembled program start at all. Fails on a traceback
  and deliberately *not* on a non-zero exit, because argparse raises `SystemExit` for
  `--help` and failing that would be the check inventing a requirement the blueprint never
  stated. A false failure costs exactly as much trust as a false pass.
- The `cli` piece's own scenario now uses formatted amounts, so the seam bug is caught
  *inside* the repair loop where it is fixed for free, rather than only reported afterwards.

## [0.1.145] - 2026-08-14

Phase C of the scaffold plan: the four changes aimed at the local tier's reliability, each
built as a **switch** rather than a rewrite, so one code version produces every arm of the
measurement. Editing source between arms is how a comparison quietly stops being one.

### Added
- **Targeted repair.** When a failure names a function, the model is asked to rewrite *only*
  that function and the result is spliced into the existing file by line range. The measured
  failure mode is regression, not incapacity: building `storage`, the scenario positions ran
  `[18, 21, 18]` - `create_user` fixed, next assertion reached, `create_user` broken again -
  because a repair prompt asks for the whole module back. Splicing makes that structurally
  impossible. Falls back to a whole-file repair when the function cannot be pinned down
  unambiguously, because repairing the wrong function is worse than repairing the file: it
  looks targeted.
- **`Piece.source`** — fixed source, written verbatim instead of generated, for the parts of
  a build with one correct answer and no judgement in them. Still checked exactly like any
  other piece; "we wrote it" has never been a reason to trust code here.
- **`blueprints/webapp-auth-crud-split/`** — the same app with `storage` split into three
  modules of three functions behind a fixed facade, so `api.py` is unchanged. The original
  plan's thesis was "shrink what they get to invent"; this applies it one level deeper.
  Each new piece carries its own scenario, verified in both directions, with the negative
  cases checked to fail *for the right assertion* - two of them initially did not.
- **`benchmarks/app-build/phase_c_batch.py`** — the gate. Six named variants, reporting
  attempts-to-first-success rather than a per-attempt pass rate.

### Changed
- The model's own generated test is **advisory** when the blueprint supplies a scenario. It
  asserted `user_id == 1` (true only of a fresh database), and its message-less assertions
  collided into a single fingerprint that stopped a progressing loop eight repairs early.
  Skipping it also saves a whole generation per piece.

Whether any of this actually helps is a measurement, not a claim, and it is running.

## [0.1.144] - 2026-08-13

### Added — the runtime ladder

A build now uses the best coding runtime available and falls to the free one only when
forced:

```
claude  ->  codex  ->  copilot  ->  local
```

This inverts the previous design, which was local-first and escalated upward to save tokens.
Two days of measurement showed local models cost more than they save when used as the
default; they belong at the bottom of the ladder, for overnight work nobody is waiting on.

- `daemon/synapse_daemon/coder_runtimes.py` (new): one place that knows how to invoke each
  CLI headlessly, and whether it can be used right now. The per-CLI flags are **lifted from
  `routes_agent_squads`, not rewritten** - each was learned from a real failure (a worker
  that sat forever on an interactive prompt, one that refused to file its findings), and
  that module now calls this one. 118 lines of duplicated flag logic removed.
- `PieceOutcome.runtime` and `.ladder_note` record which tier wrote each piece and what was
  skipped to get there. Per piece, not per build: a build routinely spans tiers when a paid
  runtime runs out of room halfway through, and a build-level label would attribute the
  whole app to whoever started it.
- `run_pipeline` takes an injectable `generate`. Contract assertions, the blueprint
  scenario, the repair loop and the honesty about what was verified are worth exactly as
  much when Claude wrote the piece as when a 7B did, so they are shared rather than
  reimplemented per runtime. This is what makes the ladder cheap.

### Added — overnight mode

- `build_blueprint(max_attempts=N)` retries a failing piece from a clean slate and reports
  `attempts_to_first_success`. The free tier passes roughly one run in five, which is a poor
  interactive tool and a perfectly good batch one - but only if the cost is reported as
  attempts rather than as a pass rate.
- Each retry clears `__pycache__`, every `*.db`, and the previous module. All three have
  already caused a failure that belonged to the harness rather than to the model.

### Changed
- `POST /blueprints/{id}/build` takes `runtimes` (the ladder, best first) and
  `max_attempts` (overnight retries, capped at 20 so a typo cannot spend a whole night).
- That endpoint no longer refuses to start unless Ollama is installed and running. That was
  right when every build was local; a build routed to Claude has no use for Ollama, and
  gating it that way made a paid runtime depend on the free one being present. Ollama is
  now checked only when the build could actually reach the local tier.
- `BuildResult.summary()` names the tiers that wrote the app ("via 1x claude, 2x local")
  instead of claiming everything was "built locally", and reports attempts-to-first-success
  for any piece that needed more than one.
- The `/ai/context` playbook told every connecting AI to grind locally and escalate upward.
  It now states the ladder and why it was inverted.
- `max_repairs` is capped at 3 on paid tiers (`PAID_REPAIR_BUDGET`) and left generous on
  local. The budget of 10 was sized for free inference; on a paid tier each repair is a
  fresh billed session.

### Documented
- `docs/adr/0035-coding-runtime-ladder.md` — the decision, the measurements behind it, and
  the fact that it reverses the previous one.

### Exhaustion detection, deliberately reluctant

`looks_exhausted` only inspects stderr of a **failed** invocation, and skips traceback
lines. A build prompt can legitimately ask a model to *write* rate-limiting code, and a
crash inside a function called `rate_limit` would otherwise demote a paid runtime to the
free tier for an hour with nothing announcing it. The patterns match English phrasing
("rate limit") and not identifiers ("rate_limit"); `429` is ignored after "line " and before
"tests passed". Nine cases pin the false-positive direction, which is the expensive one.

## [0.1.143] - 2026-08-12

### Corrected
- **The storage pass is 1 in 5, not 1 in 1.** Four repeat runs of the identical
  configuration all failed. The previous entry's result stands as an existence proof - a 7B
  *can* produce a correct nine-function stateful module - but any claim of reliability built
  on the single pass was overstated, and had already been made.

### Fixed
- **A bare `AssertionError` fingerprinted as every other bare `AssertionError`.** All four
  failing runs stopped on the repeated-error guard after 5-8 of 10 allowed repairs, each
  having reached a *different* assertion. `error_fingerprint` returned only the exception
  type, so unrelated failures compared equal and the loop concluded the model was circling.

  This was a regression introduced by 0.1.141. Making generated tests actually execute meant
  the model's own message-less `assert x == 1` lines started running - and colliding. The
  fix that removed a false pass created a false stop.

  Fingerprints now fall back to the statement that raised when the exception carries no
  detail of its own, while still ignoring line numbers so the same assertion at a shifted
  line is still the same failure.

- The probe reported those runs as "PROGRESSING - ran out of budget" when the guard had cut
  them off well short of it. It now distinguishes the two, because they call for opposite
  responses.

## [0.1.142] - 2026-08-12

### The storage piece passed

`qwen2.5-coder:7b` wrote a complete, correct nine-function stateful storage module locally,
for free, in 31 minutes - every signature right and, for the first time, every return shape
right:

```
passed=True  attempts=6  1843s
stop_reason: tests passed
```

Verified independently of the build: the acceptance scenario re-run against the produced
module three times from a cleared bytecode cache, three passes.

**The model did not change.** Same 7B, same 6 GB card, same repair budget. What changed was
the harness around it: the contract stated up front (0.1.131), bytecode staleness fixed
(0.1.131), scenarios that actually execute (0.1.134), a scenario that survives being re-run
(0.1.137), and failures that name what came back and what a caller needs (0.1.138).

Before those, `storage` escalated on every attempt, and the reasonable reading was that a 7B
cannot write a nine-function stateful module. That reading was wrong. The harness was
measuring itself.

`benchmarks/app-build/CONTRACT_AB.md` carries the full trail, including what these numbers
are *not*: the pass followed five changes at once, so it is evidence the stack works rather
than a measurement of any one part, and one pass on one piece is a proof of possibility, not
a rate.

### Fixed
- The probe's verdict line never consulted `result.passed`, so it reported a successful
  build as "PROGRESSING - ran out of budget". The same class of mistake as everything else
  it found: a summary that ignores the field which settles the question.

## [0.1.141] - 2026-08-12

### Fixed
- **Generated tests that define a test function and never call it.** Small models routinely
  emit `def test_storage(): ... assert ...` and stop, with even the closing `print('OK')`
  indented inside. Nothing at module level executes, so the file exits 0 having asserted
  nothing, and the piece is recorded as passing.

  This is the mechanism behind the worst false pass this project has produced. `passwords`
  was graded a clean pass in 117 seconds with zero repairs while `verify_password` raised
  `NameError: name 'hmac' is not defined` on **every** call. Its generated test did call
  `verify_password` - inside a function nobody ran. The evidence was unrecoverable at the
  time because each piece overwrote the previous piece's test file (fixed in 0.1.130); the
  mechanism was only identified when an identical test turned up in a later build and could
  be read directly.

  `_ensure_the_test_runs` now appends calls to zero-argument functions the model defined and
  left uncalled, and emits a `test_never_ran` event rather than repairing it silently. Tests
  that already call themselves, module-level tests, and helpers that take arguments are left
  alone - appending a second call would run every assertion twice and can corrupt state.

  Appending is preferred to rejecting: the assertions the model wrote are usually
  reasonable, they were simply never reached.

## [0.1.140] - 2026-08-12

### Added
- `local-app-scaffold` is registered as an installable AI bundle, so the scaffold appears in
  the marketplace where a human looking for "build me an app" would actually look, rather
  than only over HTTP and in `/ai/context`.

  Installed through the real API rather than declared done: `POST
  /api/v1/ai-bundles/install/local-app-scaffold` returns 200, the bundle joins
  `installed_ids`, and `build-from-blueprint.json` lands in the installed quick-actions
  directory. The catalog is re-read live - no restart.

  Its `caveats` say the things a marketplace description usually will not: a 7B on a 6 GB
  card will not finish a large stateful module unaided, and `passed` means the model agrees
  with itself - read `verified`.

This completes Phase 9's registration: bundle, quick action, and the `/ai/context` entry
that already carried `for_building_a_whole_app`.

## [0.1.139] - 2026-08-12

### Added
- `Blueprint.guarantee_checks`: which check enforces each guarantee, as data. The model's
  docstring already claimed each guarantee mapped to a real check, and `/ai/context`
  repeats that claim to every AI that connects. It was prose, and for a stretch it was
  false - the `api` piece had no acceptance scenario at all, and the stored-XSS probe had
  never been fired at a vulnerable page.

  `test_every_guarantee_names_a_check_that_really_exists` now resolves each mapping:
  `scenario:<piece>` must name a piece that exists *and* carries a scenario, and
  `webcheck:<name>` must match a name `webcheck.py` actually emits. Verified to fail on a
  missing mapping and on a check name that does not exist, and to pass when restored - a
  test that cannot fail proves nothing.

- `templates/quick-actions/build-from-blueprint.json`, matching the existing quick-action
  shape. Picked up live by the daemon's tools watcher; 17 actions now.

  Its instructions tell the operating AI to read `passed` **and** `verified` rather than
  `passed` alone, to never describe a `not_run` check as a pass, and - given how this week
  went - to suspect the scenario before concluding the model is incapable.

## [0.1.138] - 2026-08-12

### Added
- `benchmarks/app-build/CONTRACT_AB.md`: the measured result of stating a piece's contract
  before it writes anything, rather than enforcing it afterwards.

  | | Contract withheld | Contract stated |
  |---|---|---|
  | Repair attempts | 10 (budget exhausted) | 3 |
  | Distinct failures | 9 | 2 |
  | Wall clock | 3269 s | 1974 s |

  Reproduced across two independent runs with the same ratios. The withheld arm spent its
  first six repairs discovering its own interface one function at a time - `init_db`
  missing, `create_user` args, `get_user_by_email` missing, `create_session` args,
  `user_id_for_token` missing, `delete_session` missing - at roughly 200 seconds each.

  It did not make the piece pass. It converted wasted repairs into useful ones: the budget
  is now spent on behaviour instead of signatures.

### Changed
- The storage scenario's `get_user_by_email` guard excluded tuples and then indexed what it
  got, so a bare int walked past it and surfaced as
  `TypeError: 'int' object is not subscriptable` - the shape of the failure, never the shape
  that was wanted. It now asks for the field and, on any failure, names what came back and
  what a caller needs. Checked against all four wrong shapes seen in real builds.

## [0.1.137] - 2026-08-12

### Fixed
- **A scenario was failing every repair attempt after the first, for free.** The storage
  scenario cleared three guessed database filenames. The model called its database
  `storage.db`, so nothing was deleted, rows survived between attempts, and
  `create_user("scenario@test.io", ...)` raised `ValueError: Email already exists` from
  attempt two onward. The build reported the model as "circling a problem it cannot
  diagnose" - accurately, since the problem was in the scenario. Both scenarios now clear
  whatever database the module actually created.

  This is the second time in two versions that a build blamed the model for a defect in the
  harness, and both were found by reading a failing run rather than by a test. So:
  `test_a_scenario_gives_the_same_verdict_when_run_again` runs the storage scenario three
  times against a committed known-good module named the way the model named it. A scenario
  that passes once and fails twice is not a check, it is a fuse.

### Added
- `daemon/tests/fixtures/control_storage.py`: a correct storage module kept as the positive
  control, so "the scenario rejected a correct module" and "the scenario leaks state" are
  distinguishable failures rather than one confusing one.

## [0.1.136] - 2026-08-12

### Added
- Every accessibility and layout check is now proven against the defect it exists to catch,
  not just the XSS probe. One fixture carries them all - inputs with no `<label for>` and no
  `aria-label`, 20px-tall controls, a literal `undefined km`, and a 2000px element at a
  390px viewport - and each check must fail its own defect while passing the well-built
  fixture in the same suite.

  Every one of those defects passed Arm B of the build-off. That is how a page with no
  labels, no focus ring, no tap-target rule and a visible `undefined km` scored full marks
  on the frontend. The checks were written afterwards; this is the part that shows they
  bite.

## [0.1.135] - 2026-08-12

### Added
- `daemon/tests/test_webcheck_end_to_end.py`: the stored-XSS probe is now proven against a
  real vulnerable app. Two FastAPI fixtures are served on real ports and driven by a real
  browser, identical except for one word - whether user text reaches the DOM through
  `innerHTML` or `textContent`. The probe must fail the first and pass the second.

  This was the plan's first verification gate and it had never been run. The existing
  `test_webcheck.py` covers the helpers - token-key detection, verdict arithmetic, email
  uniqueness - none of which is evidence that the probe fires. That distinction has now cost
  this project three separate bugs: a render check that graded the wrong page, acceptance
  scenarios that sat in the test file and never executed, and an XSS probe that reported a
  pass on a vulnerable app. **Testing that a check is wired is not testing that it works.**

- A registered `slow` marker for tests that serve an app and drive a browser. They run by
  default; the marker exists so they can be deselected deliberately rather than forgotten.

## [0.1.134] - 2026-08-12

### Fixed
- **Acceptance scenarios were never executing.** Scenarios call the module's functions by
  bare name, the way a caller does. The only `from <module> import *` in the composed test
  file was the one inside the *model's* generated test, which is appended after the
  scenario - so every scenario died with `NameError: name 'init_db' is not defined` on its
  first line, in every build since they were introduced in 0.1.130. Not one scenario
  assertion had ever run.

  The failure was convincing, which is why it survived three versions: it arrived as a real
  Python error attached to a real repair attempt, and the loop reported the model as
  "circling a problem it cannot diagnose". The model was diagnosing a problem in the test
  harness.

  `test_the_scenario_actually_executes_rather_than_merely_being_present` now asserts a
  scenario assertion is reached, rather than asserting - as the previous test did - that the
  scenario reached the file. It did reach the file. That was never the question.

## [0.1.133] - 2026-08-12

### Changed
- `run_pipeline` takes a `requirement` separate from `spec`. The codegen spec accretes
  implementation aids - the declared contract, every dependency's public interface, and an
  entire worked exemplar page - and all of it was being handed to the test-writing prompt
  too. None of it describes what the module must *do*, and a test prompt carrying a whole
  exemplar HTML page invites the model to write about the exemplar. Callers that do not
  separate the two are unaffected.

### Fixed
- `benchmarks/app-build/probe_storage_repairs.py` never called `.instantiate()`, so it fed
  the model a spec still containing five literal `{{title_field}}`-style placeholders. Both
  arms were equally affected, so the comparison was internally consistent, but it measured
  the probe rather than the pipeline. Both arms are being re-run.

### Added
- `benchmarks/app-build/run_contract_ab.ps1`, which runs the two arms sequentially - two
  7B generations at once on a 6 GB card would measure contention rather than prompts.

## [0.1.132] - 2026-08-12

### Changed
- A repair that cannot escape itself is now asked to **start over from the requirement**,
  with the failure quoted but the current code withheld, as the last thing tried before
  escalating.

  This follows directly from a measurement that contradicted the previous version's
  assumption. Raising temperature was supposed to unstick a repeating repair; it did not.
  `qwen2.5-coder:7b` demonstrably varies its output at 0.8 and 1.5 on open prompts, yet the
  `storage` repair returned byte-identical ~3.8 KB at 0, 0.4 and 0.8. The reason is the
  prompt shape: a repair hands the model the entire current file and asks for a corrected
  copy, so most of the output is copying and the distribution stays peaked however hot the
  sampler runs. Temperature cannot fix a prompt problem. Removing the thing being copied
  can.

  `RepairAttempt` records `started_over`, so how often this fires is measurable rather than
  assumed - which matters, because a rewrite discards whatever the current attempt already
  had right, and that trade needs watching.

## [0.1.131] - 2026-08-12

Three of these are measurement bugs rather than feature work. Each one made a local model
look less capable than it is, so every escalation count taken through this pipeline was a
lower bound rather than a measurement.

### Fixed
- **Repairs were graded against stale bytecode.** Python treats a cached `.pyc` as current
  when the source's mtime (whole seconds) and size both match, and a repair routinely
  rewrites a module to the same byte length within the same second - so the test subprocess
  imported the *previous* attempt's code and blamed the fix just written. Reproduced in
  isolation before fixing. `__pycache__` is now cleared and `-B` /
  `PYTHONDONTWRITEBYTECODE=1` set at all three launch sites: the repair loop, the web checks
  that serve the assembled app, and the benchmark scorer.
- **"The model stopped changing the code" was measuring the sampler.** `generate_code`
  hardcoded `temperature: 0`, so a near-identical repair prompt returned near-identical code
  by construction. Measured: `storage` gave up after 2 of 10 allowed repairs having never
  reached its acceptance scenario. Identical repairs are now resampled at 0.4 then 0.8, and
  the stop reason states how many samples were drawn.

  Measured afterwards, and worth recording because it did not go the way the fix assumed:
  resampling did **not** rescue that run. Sampling is demonstrably live (the same model at
  1.5 returns different text on repeated calls), yet the storage repair returned identical
  ~3.8 KB output at 0, 0.4 and 0.8. A repair prompt that carries the whole current file and
  asks for a corrected copy is dominated by copying, so its distribution stays peaked no
  matter the temperature. The value delivered here is an honest stop reason - "identical
  across 3 samples" is a claim that has been tested, where "the model stopped changing the
  code" was an artifact. Getting a stuck repair unstuck needs a different *prompt*, not a
  different temperature.
- **Pieces were held to a contract they were never shown.** The storage spec described its
  tables and rules in prose and never listed the nine signatures a contract test asserted
  exactly, so every build opened by discovering the contract through failure - on two
  consecutive runs, repair 1 was "init_db is missing" and repair 2 was "create_user takes
  ['email', 'password'] but the contract requires ['email', 'password_hash']". The declared
  contract is now part of the generation prompt.
- A declared `web` check reported "the build runner does not execute web checks yet" when
  the build does run them, once, against the assembled app. It now says where it runs.
- `_run`'s timeout message hardcoded "45s" regardless of the timeout actually applied.

### Added
- An acceptance scenario for the `api` piece - the only piece that escalated on both builds
  and the only one that never carried one. Verified in both directions: it rejects the api
  module the local model produced and accepts the escalated one.
- `test_every_builtin_piece_declares_a_scenario`, so a new blueprint cannot reintroduce a
  piece that passes a build with no check the model did not write itself.
- `benchmarks/app-build/probe_storage_repairs.py`, which records what each repair attempt
  changed and runs the contract-in-prompt A/B. It is the tool that found two of the bugs
  above.

## [0.1.130] - 2026-08-12

### Fixed
- Blueprint pieces declared a `tests` scenario that the build runner never read, so the
  only behavioural check on a generated module was the test the model wrote about its own
  code. Scenarios now run inside the repair loop, where a failure is fixed locally and free.
- `check_contract` compares names and argument lists without calling anything, so a
  `storage` module passed with every signature correct while `create_user` returned `None`
  and `get_user_by_email` returned a bare row tuple without the password hash. Its caller
  could neither open a session nor verify a password.
- `passwords` was graded a clean pass with zero repairs while `verify_password` raised
  `NameError: name 'hmac' is not defined` on every call.
- ~~`pages` never routed through `scaffold_partials.page()`, so the UI kit was silently
  unused by the build it exists to style.~~ **Retracted in 0.1.131** — this was wrong.
  The check behind it asserted the literal string `"kit.css"` appeared in the rendered
  HTML, but `page()` *inlines* the stylesheet rather than linking it, so a correctly built
  page failed. `pages` had been using `scaffold_partials` all along. Two of the three
  passing pieces were unusable, not three.
- Each piece wrote its test to a shared `_pipeline_test.py`, erasing the evidence for the
  piece before it; tests are now per-module and the deciding test is recorded on the
  outcome.

### Added
- `daemon/tests/test_scaffold_scenarios.py`, pinning each defect verbatim.
- `benchmarks/app-build/arm-c-run1-signatures-only/`: the build that reported 3/4 pieces
  passing, kept with a write-up of why none of the three worked.

## [0.1.129] -- 2026-08-12

### Fixed -- the rubric can now see the bugs it used to miss
The frontend section awarded a perfect 15/15 to a build carrying a stored XSS hole and a
dashboard that rendered nothing, because it only checked that pages were *served*. Serving a
page proves the HTTP layer works and says nothing about what a person would see.

`shared/render_checks.py` now drives a real browser: it stores a hostile payload through the
API, reloads, and asks whether script executed; scans rendered text for values that leaked
through a template; checks every input has a label; and checks tap targets and 390px fit.
Being served is worth 4 of the 15 now, not all of it.

**Both earlier arms have been re-scored and the numbers restated**, rather than quietly
superseded:

| | old rubric | strengthened rubric |
|---|---|---|
| Arm A (Claude only) | 100% | **100%** -- and its XSS check is a real pass: the payload rendered inertly |
| Arm B (local models) | 100% | **94.3%** -- frontend 9/15 |

Arm B loses those points for unlabelled inputs, and for an XSS check that could not be
verified *because the dashboard never renders a record at all* -- which is the more serious
of the two faults.

When Playwright is unavailable every render check returns `skip`, never `pass`.

## [0.1.128] -- 2026-08-12

### Added -- build modes
- `preferences.build_mode` with three settings, validated so an unknown value is refused:
  **`assist`** (a frontier model writes the code, local models do bulk work), **`review`**
  (the default -- local models write, machine checks run, then a frontier model reviews before
  it reaches the user), and **`auto`** (local models write, machine checks alone gate it).
- `review` is the default because it is the only mode that would have caught the two defects
  the build-off actually shipped -- a stored XSS hole and a dashboard rendering "undefined" --
  both of which passed every automated check.
- The modes are published in `PLAYBOOK`, so a connecting AI reads the user's setting and obeys
  it rather than deciding for itself how much to trust local output.

### Fixed
- The two "stuck" conditions were being reported as one. When a model repeats itself the error
  necessarily repeats too, so the recurring-error guard was firing first and reporting the
  symptom instead of the cause. They are now distinct: **"the model stopped changing the
  code"** when the output is identical, and **"a different fix produced the same error"** when
  it is circling a problem it cannot diagnose. The two suggest different remedies, so
  collapsing them lost information.

## [0.1.127] -- 2026-08-12

### Added
- **Blueprints gallery** (AI Coding -> Blueprints). Follows the one-window rule: the page
  itself never scrolls, only the list and the detail panel scroll internally, and long lists
  page with "show more" rather than growing without end.
- **Blueprints are discoverable by any AI.** The catalog is injected into `/ai/context`, and
  `PLAYBOOK` gained `for_building_a_whole_app` and `for_measuring_and_improving`, so an AI told
  "build me an app" or "use the local models" finds the route in one read instead of
  rediscovering it by experiment -- which would spend exactly the tokens this exists to save.
- The detail panel shows **enforced guarantees** rather than a description, and says plainly
  that each maps to a check which runs during the build.

### Fixed
- Registering the blueprints router passed it as a second *positional* argument to
  `include_router`, which crashed the daemon at startup. Caught because the API was checked
  rather than assumed to work after the edit.
- The blueprint card overflowed its grid track: a `<button>` does not shrink to its container
  the way a `div` does, so the title's intrinsic width set the card's `scrollWidth`. Verified
  fixed in the running app at 1280px and 390px -- zero overflowing elements, and the page
  scrolls in neither direction.

## [0.1.126] -- 2026-08-12

### Added -- the improver: bounded search that earns its autonomy
- **`local_improve.py`** searches the *harness*, never the model and never the source. It may
  only choose among pre-registered options (which model holds a seat, context size, repair
  budget, exemplar/contract injection, temperature) -- a test asserts every search value is
  plain data, because anything executable would make this an agent rewriting the system
  rather than a bounded search.
- **Four gates before any promotion**: the gain must clear a measured noise floor (found by
  repeating the *same* config, since a lucky run and a real improvement look identical without
  it); no other skill may regress beyond a small epsilon; the win must hold on a slice of
  checks it was never tuned against; and `active_config` is versioned so `rollback()` is one
  call.
- **Autonomy is earned.** It ships in shadow mode -- runs everything, changes nothing, records
  what it *would* have promoted. Auto-promotion unlocks only after three consecutive
  predictions hold up on held-out checks. If they never do, that is the finding and it stays a
  proposal engine.
- **Bench + improver REST**: `/local-ai/bench`, `/bench/history`, `/bench/skills`,
  `/bench/run`, `/improve`, `/improve/run`, `/improve/rollback`.

### Fixed
- **`generate_code` ran at `num_ctx: 4096`**, but that window covers the prompt *and* the
  generation. A piece receiving an exemplar plus its dependencies' interfaces had no room left
  to emit a full module, which surfaced as a 300s timeout rather than an obvious
  context-exhausted error -- the `pages` piece failed exactly this way, having produced
  nothing. Now 8192, with a 900s ceiling.

## [0.1.125] -- 2026-08-12

### Added
- **`local_bench.py`** -- the scorecard as a module the app can run, not a script to remember.
  Skill packs are **JSON**, so measuring a new capability is a file rather than a code change,
  and every run is kept so `trend()` can show a regression instead of implying one.
- **Contract assertions now run inside the repair loop.** Previously the contract was checked
  after the pipeline finished, so the model never saw the one problem it could most easily
  fix. Measured on the first blueprint build: the storage piece went from **3 of 9 correct
  signatures to 6**, repairing `create_session(email->user_id)`,
  `create_user(password->password_hash)` and adding two functions it had omitted.
- Repair budget raised to 10. Local attempts are free, the contract assertions converge, and
  the recurring-error guard stops a genuinely stuck loop long before the ceiling.

### Fixed
- **The first JSON conversion silently dropped 27% of the benchmark.** 16 of 60 checks could
  not be expressed declaratively and were left out, which would have made the bench quietly
  measure less than it claimed. The expectation vocabulary was extended instead
  (`expect_tool_args`, `expect_only_known_tools`, `expect_max_chars`, `expect_line_count`,
  `expect_starts_with`, `expect_absent_chars`, `expect_absent_regex`) and all 60 restored.
- Generated contract tests nested quotes inside quotes and produced a file that would not
  parse, failing the piece for a reason unrelated to the model's work.

## [0.1.124] -- 2026-08-12

### Added -- blueprints as a Synapse primitive
- **`blueprints.py`** -- a blueprint is a verified recipe: pieces, contracts, checks, assets,
  and the score it actually achieved last time it ran. `kind` is open from the start
  (`web-app`, `backend`, `data`, `animation`, `library`, `integration`, `infra`, `agent`) and
  what differs between kinds is only which *checks* apply -- and checks are data, so a new kind
  needs no new code.
- **Composition, not memory.** Each blueprint declares what it `provides` and `requires`, so
  "which of these fit together" is a query rather than something a human recalls.
  `compatible_with` answers it in both directions; `resolve_stack` assembles a set and reports
  unmet requirements instead of silently dropping them.
- **`scaffold/runner.py`** -- executes a blueprint piece by piece in dependency order, giving
  each piece its contract, the *real* interfaces of the modules it imports (read off the files
  that exist, not assumed), the UI kit, and a worked exemplar. Contract checks run even when
  the unit test passed, because a module can satisfy its own test and still expose the wrong
  signature to callers.
- **`routes_blueprints.py`** -- list, filter, inspect, check compatibility, resolve a stack,
  register a new one, and build. Blueprints are data, so growing the library needs no code.
- **First blueprint: `webapp-auth-crud`**, authored as data with six enforced guarantees.

## [0.1.123] -- 2026-08-12

### Added -- the generation scaffold (phases 1-4)
- **`scaffold/ui_kit/kit.css` + `scaffold/partials.py`** -- a house style the models may use
  but not invent. `field()` takes the label as a *required argument*, so there is no call that
  produces an unlabelled input; every page ships `escapeHtml` so client-side rendering has a
  safe default available. The build-off's pages had 0 labels, 0 focus styles, 0 tap-target
  rules and 0 media queries -- not from incapacity, but because the model was asked to design.
- **`scaffold/webcheck.py`** -- renders the app and attacks it. Delegates broken links and
  security-header grading to the web-scraper already running on :12345 rather than
  reimplementing them, and adds what it cannot do: a stored-XSS probe, a scan for `undefined`
  reaching the screen, tap-target and focus checks. Missing dependencies report `not_run`,
  never `pass`.
- **`scaffold/contracts.py`** -- reads real signatures off generated files and fails a module
  whose interface drifts, inside the loop. This is the `distance` vs `distance_km` failure.
- **`scaffold/assertions.py`** -- assertions that render got-vs-expected plus a likely cause.
  Measured worth: a bare `AssertionError` cost four wasted repairs; the explanatory version
  fixed the same bug in one.
- **Early escalation** in `local_pipeline` -- `error_fingerprint` normalises line numbers and
  paths, so a *recurring* error stops the loop. Arm B spent ~20 minutes emitting four
  identical `user_exists` errors; two is enough to know.

### Fixed -- a false green in my own security check
The XSS probe initially **passed** against an app that is genuinely vulnerable. Two causes:
it assumed a localStorage key name (the app used a different one, so the page bounced to
/login and never rendered), and it treated "payload did not fire" as proof of escaping. It now
detects the key from the page's own JavaScript, and reports `not_run` when the record never
rendered -- because a payload that was never given the chance to run proves nothing. A
security check that can produce a false pass is worse than no check.

## [0.1.124] -- 2026-08-11

### Fixed -- driving a runtime from a phone
- **The runtime picker reported "Not detected" for Claude, Codex and Copilot while it was
  still checking.** Detection shells out to probe each CLI binary, so there is a real window
  where the answer is unknown -- and the UI rendered "absent" for it. On a phone, where that
  window is longest, it looks exactly like the runtimes are missing. Connections are now
  tri-state (`null` = unknown) and the picker says "Checking..." until the probe returns.
  Verified at 375px: all three now read "(Ready)".
- **The Send button was 32px tall**, under the 44px minimum this project sets for tap targets,
  and it is the one control that has to be hittable first time when dispatching a run from a
  phone. Now 44px below `sm`, unchanged on desktop.

## [0.1.123] -- 2026-08-10

### Changed -- a headline finding corrected by better measurement
The full 13-model sweep disproved this project's own claim that "the scaffolding is the
bottleneck, not the model". Re-running the agent topologies with `qwen2.5:7b` in the seat:

| Approach | Pass | Time/task |
|---|---:|---:|
| solo agent, qwen2.5:1.5b | 33% | 22s |
| coder+reviewer, 1.5b | 67% | 103s |
| pipeline, no agent | 100% | 45s |
| **solo agent, qwen2.5:7b** | **100%** | 87s |
| coder+reviewer, 7b | 100% | 171s |

Capability, not scaffolding, was the binding constraint. The original conclusion generalised
from one 1.5B model to all local models without ever putting a larger one in the same seat.
The pipeline is still the right default -- 100% in half the time, because it never pays for
tool-calling round trips -- but for the right reason now.

The finding that *survived* is stronger for having been retested at both capability levels:
**extra seats buy nothing.** A planner seat scored identically and cost ~18s; a reviewer
behind a capable agent took 100% to 100% and added 84s.

`PLAYBOOK` now carries the correction explicitly, and the UI panel renders it, because an AI
reading a confident but wrong rule is worse off than one reading nothing.

## [0.1.122] -- 2026-08-10

### Fixed -- mobile overflow, found by measuring every page at 375px
- **Apps: one project tile blew out the whole grid** -- 556px of content in a 237px box while
  every other tile fitted. A `1fr` track cannot shrink below its min-content width, and a
  launch command like `C:\Users\...\python.exe` has no break opportunities, so the entire
  path became the track's minimum. Fixed with `minmax(0,1fr)` plus `break-all`;
  `break-words` cannot help, because it only breaks between words and a path has none.
- **AI Factory: metric cards overflowed their own cells.** `tracking-[0.22em]` on uppercase
  text makes even "Components" 106px wide against an 89px cell once cards sit two-up.
- **AI Factory: a two-column select row** left ~120px per control at 375px, truncating the
  option labels the control exists to show. Single column below `sm`.
- **Home: the longest shortcut button** pushed 228px into a 189px column, because the Button
  base sets `whitespace-nowrap`. It now wraps, keeping the label rather than trading it for
  an ellipsis.

Apps, AI Coding, Tools and Live measure clean at 375px; Home and AI Factory are down from
three offenders to two and one. Verified in the running app.

## [0.1.121] -- 2026-08-10

### Fixed (found by auditing the running app, not by reading code)
- **A second event-loop blocker.** `POST /review/proposals/reconcile` ran `git log -n 300`
  inline in an async route with a 15s timeout, stalling every other request behind it -- the
  daemon appears hung rather than slow. Found by an AST sweep for blocking calls inside
  `async def`, which is now the check to re-run after touching any route.
- **A wall of 404s in the live UI.** The coder workspace fetched terminal scrollback for
  historical runs and reported "Could not read session output" for each. PTY buffers live in
  the daemon's memory, so after any restart every past run legitimately has none -- normal
  behaviour was being presented as failure, and real errors were buried among dozens of
  identical red messages. Now says so plainly.
- **The new "How to use local AI" panel overflowed at 375px** (`scrollWidth` 497 against a
  237px track). Grid and flex children default to `min-width: auto`, so the long monospace
  endpoint strings set the track's minimum and `truncate` never got the chance to act.
  Verified fixed in the running app: zero overflowing elements, no horizontal page scroll.

### Added
- **`local_router.py` + `POST /local-ai/do`** -- one call that works out *how* to do a task
  locally and then does it. Callers no longer need to know that code belongs in the pipeline,
  that file work needs an agent, or which of thirteen installed models is strongest at each:
  the strategy is chosen in code and the model is chosen from the testbench scorecard.
- **`local_models.skill_scores()` / `best_model_for()`** -- routing now reads the measured
  per-skill results, so the coder seat gets whichever model actually scored highest at coding
  on this machine, and the file-handling seat deliberately avoids the coding leader, since
  coder-tuned models cannot call tools at all.
- Judgement work (`should we`, `trade-off`, `security review`, `best approach`) is **never
  attempted locally**. Code can be proved wrong by running it; an architectural opinion
  cannot, so a confident wrong answer would cost the caller more than an honest handoff.

### Added
- **`benchmarks/local-models/testbench.py`** -- a per-skill scorecard for every installed
  model: six skills x ten checks, all machine-verified (code executed, JSON parsed, tool
  calls inspected). No model grades another, so nothing can be talked into a pass. Results
  append to `history/` so the effect of a change is visible as a delta rather than a vibe.
  Skills mirror how models are actually evaluated in public work: execution-checked coding,
  repair-from-error, verifiable instruction constraints, function calling, structured
  extraction, and short-chain reasoning. Reported per skill and only then blended, because
  the best coder here is not the best instruction-follower and a squad wants the right
  specialist per seat.

### Fixed
- **The bench was mis-scoring reasoning by 20 points.** Numeric answers were graded with a
  substring check over the first 20 characters, so "The next number is 32." -- entirely
  correct -- was marked wrong, while "32" would also have matched inside "1032". Now graded
  on the final number in the reply, the convention GSM8K-style scoring uses, because a model
  that reasons aloud puts its conclusion last. Caught by spot-checking raw model output
  instead of trusting the harness.

### Added
- **A measured playbook for local models, served to humans and AIs from one constant.**
  `local_models.PLAYBOOK` is injected into `/ai/context` and returned by
  `GET /local-ai/models`, and the new "How to use local AI" panel on the Local AI page
  renders that same object. An AI told "use the local models" now learns the right approach
  in one read instead of rediscovering it by experiment -- which would spend exactly the
  tokens the local models exist to save. It states the decision rule, the endpoint for each
  kind of work, and the four approaches that were tried and measurably made things worse.

## [0.1.119] -- 2026-08-08

### Added
- **`local_pipeline.py` + `POST /local-ai/pipeline`** -- the shape the benchmark selected:
  generate, write a test from the same brief, run it, repair from the real traceback, repeat.
  Python does the orchestrating and the model only writes code, which measured 100% against
  33% for an agent-driven loop. Local inference is free, so repairs are cheap; a frontier
  model is only invited in when the loop is genuinely stuck, and then it receives a compact
  `escalation_packet` (requirement, current code, real error) instead of a transcript.
- Three hermetic pipeline tests -- repair-from-error, escalation-packet completeness, and
  early stop when the model stops changing its answer.

### Fixed
- **The pipeline blocked the event loop.** `subprocess.run` was awaited inline inside an async
  handler, so a single pipeline call would freeze every other request the daemon was serving
  for up to 45 seconds, and on Windows deadlocked the Proactor loop outright. Found because
  the test suite hung only when a prior test had already created a loop; each test passed
  alone. Now dispatched through `asyncio.to_thread`.

## [0.1.120] -- 2026-08-08

### Added
- **`estimate_vram_fit()`** -- answers "will this model actually run well here" *before* a
  multi-gigabyte download, and how much context it can hold. Spilling even slightly into
  system RAM is the largest performance cliff on a small card (~6 tok/s versus ~25 measured),
  and the KV cache is the part people forget: it grows linearly with context and is ~1 GB at
  4k on a 7B, which is exactly the difference between fitting and not on 6 GB.
  It independently reproduces what the benchmark measured -- a 7B does not fit on this card
  at 4k, but does at 1.5k.

### Fixed
- **The pipeline's generated tests could prove nothing.** Left to itself the coding model
  pasted a *copy* of the implementation into the test file and asserted against that, so the
  test passed while never importing the module being shipped. A test that doesn't import what
  it claims to test is worse than no test, because it manufactures confidence. The generator
  now demands an import and the pipeline verifies one is present, repairing the test if not.

### Dogfooding note
This release was written the way the benchmark says local models should be used: the local
pipeline produced the first draft of the estimator for free, its own test loop caught that it
was wrong, it exhausted its repair attempts, and escalated a compact packet. Reviewing that
packet took a fraction of the tokens writing it from scratch would have -- and the review
caught two real bugs (`max_context` dividing gigabytes by 512 instead of solving for tokens,
and reporting 0 context whenever `fits` was false) plus the self-test flaw above.

## [0.1.119] -- 2026-08-08

### Added
- **`local_pipeline` + `POST /api/v1/local-ai/pipeline`** -- the cheapest way to get correct
  code out of this machine, and the shape the benchmark selected: generate, write a test from
  the same requirement, run it, repair from the real error, repeat. Measured at 100% versus
  33% for an agent-driven loop.
- **Escalation instead of silent failure.** When the local loop is genuinely stuck the result
  carries an `escalation_packet` -- requirement, current code, the test, the real error, and
  why it stopped -- sized for a frontier model to finish in one shot. Local attempts are free
  and can run all night; a frontier model's budget is not, so it is invited in only when the
  free effort is exhausted, and then handed a briefing rather than a transcript.
- Gives up early when the model returns identical code twice, because a model that has stopped
  changing its answer is not one attempt away from success.

### Fixed
- **`run_pipeline` blocked the event loop.** It ran the generated code with a synchronous
  `subprocess.run` inside an async function, which would freeze every other request the daemon
  was serving for up to 45 seconds, and deadlocks outright on Windows' Proactor loop. Now runs
  off-thread. Found because the test suite hung, not by reading the code.

## [0.1.118] -- 2026-08-08

### Added
- **`write_code` tool.** Local models split cleanly into two useless halves: the coder-tuned
  models write correct code but *cannot call tools at all*, and the small general models call
  tools flawlessly but produce stubs like `# Your code here`. `write_code` joins them -- the
  agent keeps the hands, a coding model writes the source, and the coding model never touches
  the filesystem. The original task is prepended to the spec **in code**, because a 1.5B agent
  paraphrases the requirement when relaying it and the coder cannot see the conversation.
- **`benchmarks/local-models/squad_bench.py`** -- measures whether more agents actually help,
  scored by executing the produced file against assertions the agents never see.

### Measured: how to get real quality out of local models
| Topology | Pass | Time/task |
|---|---:|---:|
| **pipeline_repair** (no agent; Python orchestrates) | **100%** | 45s |
| coder_reviewer | 67% | 103s |
| planner_coder_reviewer | 67% | 121s |
| solo agent | 33% | 22s |
| self_verify (agent runs its own code) | 33% | 19s |

- **Removing the agent tripled correctness.** Called directly, `qwen2.5-coder:3b` solves every
  task; wrapped in a 1.5B-driven agent loop the same coder drops to a third. The scaffolding is
  the bottleneck, not the model.
- **A reviewer seat doubles a weak agent (33% -> 67%) at 5x the wall-clock.** A planner seat
  bought nothing at all -- same 67%, ~18s slower. More seats is not more quality.
- **Letting a small model verify its own work made it worse.** It can see the failure and
  cannot act on it; feedback only helps a model strong enough to use it.
- `wordcount`, the only task needing punctuation handling, failed in *every* topology except
  the pipeline, which fixed it from the real traceback.

### Fixed
- `run_agent` never told the model its workspace root, so agents invented absolute paths, were
  refused, and then explained the refusal instead of retrying -- reading as "task failed" when
  it had never been attempted. The chat path had this fix; the agent path did not.
- Lengthening the system prompt to demand verbatim specs made results *worse* (33% -> 0%): a
  small model's context is crowded out by instructions. Reverted, and solved structurally.

## [0.1.117] -- 2026-08-08

### Added
- **Local model runs appear in Live View.** A local model driving this machine is an AI at
  work like any other, so each conversation registers a coordination session (`runtime_id:
  ollama`) and heartbeats its current step as it reads and writes files. One session per
  conversation via `resume_key`, not one per message. Registration failure never breaks a
  chat -- visibility is a nicety, the conversation is the point.
- **All twelve installed models benchmarked, including vision.**

### Measured -- the numbers that change what you should run
| Role | Winner | Score | Speed |
|---|---|---|---|
| Agent / tools | `qwen2.5:1.5b` | 100% | 24.8 tok/s |
| Coding | `qwen2.5:1.5b` | 100% | 24.8 tok/s |
| Review | `llama3.2:3b` | 100% | 14.7 tok/s |
| Structured output | `qwen2.5:1.5b` | 100% | 24.8 tok/s |
| Vision | `qwen2.5vl:3b` | 100% | 14.2 tok/s |

- **`qwen2.5vl:3b` matches `llava:7b` on vision (both 100%) at nearly 3x the speed**, because
  the 7B spills out of 6 GB of VRAM and the 3B does not.
- **`moondream` fails both vision tasks outright** despite being the fastest model measured at
  54.7 tok/s. Speed is worthless when the answer is wrong, which is exactly why the
  recommendation ranks on capability first and throughput second.
- **`qwen2.5-coder:1.5b` scores 42.9%** -- the weakest model tested -- while plain
  `qwen2.5:1.5b` of the same size scores 85.7%. The coder-tuned variants cannot call tools at
  all, and that costs them more than their coding advantage returns.

## [0.1.116] -- 2026-08-08

### Added
- **A place to actually code with your local model.** New *Local AI* section under AI Coding:
  conversation sidebar, streamed replies, collapsible tool rows showing exactly which files
  were read or written, a model picker that displays each model's **measured** throughput,
  and a permission-mode picker with a plain-language description of what each mode allows.
  The machine's GPU and VRAM are shown so the constraint is visible rather than mysterious.
- `renderer/lib/local-ai-client.ts` -- typed client plus an SSE reader built on `fetch`
  rather than `EventSource`, because `EventSource` cannot send the `X-Synapse-Token` header
  the daemon requires. It returns an abort handle so Stop genuinely stops: a local model on a
  laptop can take a while, and being unable to cancel is worse than being slow.

### Fixed
- **The streamed reply never appeared in the thread.** Sending from a brand-new chat set
  `activeId`, which fired the load-transcript effect, which replaced the in-flight bubbles
  with the database's view (just the user message). The stream then patched a bubble that no
  longer existed, so every token was silently discarded while the file was really being
  written on disk. Guarded with a ref, and the transcript is re-read from the server once the
  turn completes so it reflects what was actually stored.
- The workspace path is now stored absolute, so the path the model is told matches the one
  the containment check enforces.

### Verified end to end, in the real UI
Typed a prompt as a user, watched the model write `tip.py` with a working `calculate_tip`
function, read it back, and explain it -- then asked it to list the workspace, where it
answered "three files: greet.py, hello.py, tip.py", which is exactly correct. It also tried
an absolute path once, received the corrected error message, and fixed its own call.

## [0.1.115] -- 2026-08-08

### Added
- **Persistent conversations with local models** (migration 031). Chats are stored as a row
  per message rather than a JSON blob per chat, so appending is cheap, an interrupted stream
  can be repaired in place, and tool calls stay attached to the message that made them.
  Chats are auto-titled from their opening prompt, listed most-recent-first, renameable,
  archivable and deletable. `project_id` is nullable on purpose -- a local chat is usually a
  scratch conversation, and forcing a project would push people into inventing throwaway ones.
- **Streamed replies over SSE** (`POST /local-ai/chats/{id}/send`). The stream reports real
  phases -- `engine_starting`, `model_loading`, `ready` -- then tokens, then tool activity,
  then a final `done` with token count and duration.
- **The engine starts only when it is wanted.** Ollama is not launched, and no model is
  loaded, merely because Synapse is open: a resident 5 GB model on a 16 GB laptop costs the
  user everything else they are doing. The first prompt brings it up, and failures name the
  phase that failed with a concrete remedy rather than hanging on a spinner.
- Chat CRUD: `GET/POST /local-ai/chats`, `GET/PATCH/DELETE /local-ai/chats/{id}`,
  `GET /local-ai/chats/{id}/messages`.
- `daemon/tests/test_local_ai.py` -- 20 hermetic tests covering permission gating, workspace
  containment, tool-argument validation, hardware profiling and chat storage. Nothing in the
  suite needs a GPU or a 5 GB download, because a test that does is a test nobody runs.

### Fixed
- Local models invented absolute paths like `/home/user/workspace/x.py`, were refused by the
  containment check, and then looped inventing different absolute paths. The system prompt now
  states the workspace root and that paths must be relative to it, and the refusal message
  says what to do instead. Verified: the model now writes and reads a file successfully.
- "Connected" was only emitted on the first text token, so a turn that opened with a tool call
  looked stalled. It now fires on the first sign of life.
- A tool called with missing arguments produced a raw `TypeError`. Missing arguments are now
  named, so the model can correct the call instead of repeating it.

## [0.1.114] -- 2026-08-08

### Added
- **Permission modes for local agents**, enforced at the tool layer rather than by asking the
  model to behave -- a small model will ignore "do not write files" the moment it decides a
  file needs writing. Unavailable tools are simply never offered, and mutating calls are
  refused even if the model invents them: `plan` (read-only), `manual` (every mutation needs
  approval, and fails closed when no approver is supplied), `accept_edits` (files yes, shell
  no), `auto` (free inside the workspace), `bypass` (no gates, including the
  destructive-command guard).
- **Measured benchmark results for every installed model** (`benchmarks/local-models/REPORT.md`),
  generated by `report.py` with real numbers: an efficiency ranking (pass rate x tokens/sec),
  accuracy by category, resource cost, and per-task detail.

### Measured on a GTX 1660 Ti Max-Q (6 GB), and worth knowing
- **Every 7B model spills to CPU on this card** -- only 4.19 GB of ~5.12 GB stays resident --
  which drops throughput to ~6 tok/s versus ~25 tok/s for a model that fits. A 7B costs 4x the
  time for no accuracy gain here.
- **`qwen2.5:1.5b` is the efficiency winner**: 85.7% overall at 24.8 tok/s, fully GPU-resident.
- **The `qwen2.5-coder` models cannot call tools at all** -- Ollama returns HTTP 400 because
  they ship without a tools template. They are capable coders but unusable as agents, which is
  exactly the kind of thing that is invisible until measured.

## [0.1.113] -- 2026-08-08

### Added
- **Local models can now do real work, and every AI can find them.** Synapse gained a local-AI
  layer so jobs that don't need a frontier model cost no API tokens at all.
  - `daemon/synapse_daemon/local_models.py` profiles the machine honestly and turns measured
    benchmark results into per-role recommendations. VRAM comes from `nvidia-smi` rather than
    `Win32_VideoController.AdapterRAM`, which is a 32-bit field that silently caps at 4 GB --
    a 6 GB card reports as 4 GB, and every recommendation built on that number is wrong.
  - `daemon/synapse_daemon/local_agent.py` is a real agent loop: prompt -> tool calls ->
    execute -> feed results back -> repeat. Local models had no CLI and therefore could not be
    squad workers; this supplies the missing execution path. Tools are filesystem (confined to
    a workspace root), opt-in shell, and **web search + fetch, which gives local models
    internet access**. Tool output is truncated hard and repeated calls are detected, because
    a 7B at 4k context silently drops its system prompt when the transcript overflows and
    small models loop.
  - `GET /api/v1/local-ai/hardware`, `GET /api/v1/local-ai/models`, and
    `POST /api/v1/local-ai/agent/run`.
  - `GET /api/v1/ai/context` gained a `local_ai` block listing installed models, what each is
    measured to be good at, and how to call them -- so any connecting AI can offload work
    instead of burning tokens on it.
- **A benchmark that measures rather than guesses** (`benchmarks/local-models/`). Seven tasks
  across tool-calling, structured output, code generation, code repair, instruction adherence
  and diff reasoning, plus two vision tasks. Generated code is executed against real
  assertions and tool calls are shape-validated, so no model grades itself. Test images are
  produced by a hand-written PNG encoder rather than a Pillow dependency, so the suite runs on
  any user's machine. Results are written after every task, so a long run survives an
  interrupt.

### Fixed
- Web search returned zero results because DuckDuckGo serves a stripped, result-less page to
  anything that doesn't look like a browser. Corrected the User-Agent and made the result
  parser independent of HTML attribute order.

## [0.1.112] -- 2026-08-04

### Added
- **Any AI that connects can now discover Synapse's equipment.** `GET /api/v1/ai/context` gained an
  `mcp_servers` block listing every enabled MCP server with its transport and description, plus a
  `how_to_use` note. Previously the endpoint returned no MCP information at all, so an external AI had
  no way to learn that Reflex (real mouse/keyboard/screen control), Playwright, or the web scraper were
  installed -- it had to be told by the operator. Synapse-launched workers got these injected via
  `--mcp-config`; every other AI was flying blind.
- The `ai_activity.hint` now tells a connecting AI to **register with a `project_id`** (registering
  without one grades the connection yellow, `degraded.no_project`, and costs project memory, the files
  surface, and per-project scoping) and to **resume with `resume_key`** rather than registering again,
  which is what was filling the operator's Live tab with a fresh row on every reconnect.

### Fixed
- **Gemini workers could not actually launch.** Gemini had been added to `runtime_resolution` and to
  every role template's `preferred_runtimes`, and offered in the squad UI -- but `_automatic_worker_argv`
  still rejected it with "supported only for Claude, Codex, and GitHub Copilot", so choosing Gemini
  hard-failed the launch. Added the missing branch, mapping authority onto Gemini's enforced
  `--approval-mode`: OBSERVE -> `plan` (read-only), WORKSPACE -> `auto_edit`, FULL -> `yolo`, plus
  `--prompt` for headless execution so a spawned worker cannot sit waiting for a human.

### Notes
- Gemini's `--approval-mode` is an enforced CLI mode, so its OBSERVE level is a genuine read-only
  boundary (like Codex's `--sandbox read-only`) rather than the policy-only boundary Claude's OBSERVE
  provides. Flags were verified against `gemini --help` on this machine, not assumed.
- Registered the `synportal` project so patient-portal work connects green instead of degraded.
- Verified live against the running daemon: `/ai/context` returns the `mcp_servers` block naming
  github / memory / playwright / reflex / web-scraper, and the hint mentions both `project_id` and
  `resume_key`. Sweep: agent_squads + routes_ai + mcp_servers + coordination = 99 passed / 4 skipped;
  renderer typecheck clean.

## [0.1.111] -- 2026-08-03

### Added
- Integrated Gemini as a first-class AI provider runtime, supporting both backend squad workers and frontend runtime selection.

### Changed
- daemon/synapse_daemon/runtime_resolution.py: Added detection for `gemini` binary.
- daemon/synapse_daemon/agent_squads.py: Added `gemini` to all role template preferred runtimes.
- renderer/components/AgentSquadsView.tsx: Updated UI runtime override placeholder to include `gemini`.

## [0.1.110] -- 2026-08-03


## [0.1.109] -- 2026-08-02

### Changed
- **One session per AI, with its workers nested inside it (PLAN 7 Phase 1).** The Live rail had become
  unreadable: measured at **84 sessions, 72 of them top-level**, for a handful of real tasks. Two causes,
  both fixed. *A returning AI could not re-attach* -- `SESSION_STALE_SECONDS` marks a session `gone`
  between wakes and registration always took `MAX(seq)+1`, so one autonomous agent minted a new number
  every wake (#079-#083 were all the same Claude); `AgentSessionRegister` now takes a `resume_key` that
  revives and re-adopts the existing session, and the response reports `resumed: true`. *Every squad
  worker was a top-level row* -- workers now register with `parent_session_id`, take **no** `seq`, and
  `GET /activity/sessions` returns roots only, each carrying `children[]` + `child_count`.
- A nested worker no longer raises its own "connected" notification.

### Fixed
- **`scripts/version-bump.ps1` was silently destroying the files it edits.** Windows PowerShell 5.1's
  `Get-Content` decodes a BOM-less file as Windows-1252, so every non-ASCII character was read as
  mojibake and rewritten as UTF-8. Because each bump rewrites whole files, the corruption compounded at
  roughly **2.2x per release**: CHANGELOG.md went 220 KB (0.1.95) -> 3.9 MB (0.1.104) -> 90 MB (0.1.108)
  -> **201 MB**, at which point GitHub rejected the push for exceeding its 100 MB file limit. package.json
  (1.65 MB), pyproject.toml (550 KB) and `__init__.py` (548 KB) were corrupted the same way. All reads now
  go through an explicit-UTF-8 `Read-Utf8` helper, and the four files were restored from the last clean
  commit. Verified by re-running the bump under PowerShell 5.1: sizes stay normal and mojibake is zero.
- `SYNAPSE_LEAD_SESSION_ID` now carries the parent **coordination session** id; it previously carried a
  PTY session id -- a different namespace -- which is why nothing consumed it.

### Notes
- Migration `030_session_hierarchy.sql` adds `parent_session_id` + `resume_key`, makes `seq` optional, and
  backfills existing workers' parents from `activity_journal`. Resume-key uniqueness is scoped to *live*
  sessions by a partial index. Resume deliberately does **not** require `ended_at IS NULL` -- the case it
  exists for is the agent that went stale and came back.
- Verified through the real routes on a migrated database (`TestClient`): reconnecting returns the same id
  and does not grow the rail; a nested worker is absent from the top level, present in its parent's
  `children[]`, and raises no notification. `test_coordination` 35 passed; dependent sweep 108 passed /
  4 skipped. Not verified against the running daemon -- Codex is live in session #063.

### Recovered release history (0.1.96 - 0.1.108)

The detailed entries for these releases were lost to the encoding bug above and are reproduced here from
their commit messages, which are intact in git. Full detail: `git show <version tag or commit>`.

- **0.1.96** -- restore keyboard focus after closing any modal + unbreak the docs-sync gate
- **0.1.96.5** -- delete the orphaned NetworkPanel component (dead code that misleads AI sessions)
- **0.1.97** -- repair the multi-AI lane-conflict gate (it crashed, then it silently passed)
- **0.1.98** -- a blank project_id can no longer make the lane check silently match nothing
- **0.1.99** -- make the lane gate usable (-SessionId) and actually discoverable
- **0.1.100** -- an idle terminal no longer silently swallows its last character
- **0.1.101** -- a failing sub-frame no longer reports the whole restart as failed
- **0.1.102** -- sweep public tunnels that outlived the daemon that opened them
- **0.1.103** -- let read-only reviewers file the review they just wrote
- **0.1.104** -- a wedged daemon can no longer leave panels spinning forever
- **0.1.105** -- `synapse doctor` can see a stuck port
- **0.1.106** -- `synapse doctor` stops printing part of the auth token
- **0.1.107** -- an offline accounts service no longer looks like a broken Synapse
- **0.1.108** -- the review inbox stops reporting skipped ideas as done

## [0.1.95] -- 2026-08-01

### Changed
- Squad launch reservation is serialized at the daemon boundary while the shared SQLite transaction is
  released before awaited PTY startup, preserving per-squad capacity checks without blocking heartbeats,
  audit writes, or simultaneous launch requests.

### Fixed
- Parallel Claude, Codex, and Copilot launch requests no longer collide with `cannot start a transaction
  within a transaction`; each request receives its own clean launch result instead of an internal 500.
- Failed PTY startup now closes the pre-registered worker presence, records an audited error, publishes the
  session end, and leaves the work item safely queued for retry.
- A Codex CLI account usage limit is classified as an actionable, secret-safe blocker that points to Codex
  Settings → Usage and makes clear that other signed-in runtimes may continue.

### Notes
- Focused squad-launch coverage proves the transaction is released across the awaited spawn, concurrent
  requests are serialized without 500s, failed startup releases presence, and usage-limit text is sanitized.
- Release verification: renderer + Electron typecheck, **787 passed / 14 skipped**, a supervised full-app
  restart to v0.1.95, and a real simultaneous Claude/Codex/Copilot acceptance launch in which all three
  requests returned HTTP 200, reached running, and stopped without a nested-transaction error or stale worker.
- The Synapse-hosted post-work reviewer found no critical correctness issue and verified the transaction
  split, finalizer ordering, cleanup, ErrorEnvelope behavior, and tests. It identified serialized cold-start
  throughput as an important follow-up (`a4bdab9cd169`); observe-mode Claude handoff reliability is tracked
  separately as `410a4a2b4a01` after bounded reviewers exposed the limitation without editing files.


## [0.1.94] -- 2026-08-01

### Added
- **Trustworthy automatic runtime delegation (ADR-0034).** Work-item launch now supports explicit
  interactive or automatic execution, named observe/workspace/full authority, and a 30-second to
  24-hour timeout while preserving interactive mode as the safe compatible default.
- Runtime-native automatic commands for Claude, Codex, and GitHub Copilot deliver the daemon-authored
  role prompt immediately, keep role-scoped MCP injection per worker, and require an explicit handoff.
- Workers receive protected daemon-owned API/auth/project identity in their process environment so a
  sandboxed worker can report its handoff without reading the token file; caller env cannot override it.
- Squad workers receive their exact runtime and PTY session identity, can repair an early/incomplete
  registration through an audited endpoint, and can list sibling work without downloading role metadata.
- Automatic workers are pre-registered and receive a short-lived session/work-item/authority-bound API
  credential whose hash is stored, instead of inheriting the desktop's trusted-local root token.
- Deep Live View now pairs its compact current focus with the latest structured **Why this step** summary.
- Live sessions now have a collapsed editable **Goals** inspector with `[completed/total]` progress; the
  same milestones are AI-discoverable and writable through the daemon API.

### Changed
- Claude workspace automation uses its policy-aware non-interactive `auto` permission mode; Codex keeps
  project rules in workspace mode and receives `--ignore-rules` only with explicit full authority.
- Squad Stop All blocks live work before closing PTYs, returns the paused squad state, and automatic workers
  are stopped with an audited blocker when their task timeout expires.
- Automatic deadline tasks are owned and cancelled on finalization, stop, or daemon shutdown. A handoff
  preserves its work status but cannot bypass the deadline of a still-running PTY.
- Synapse now owns a 30-second coordination heartbeat for each automatic worker while its PTY is alive;
  long MCP/browser calls no longer make a healthy worker look gone or revoke its scoped credential mid-task.
- AI Council quick-action guidance now describes the real interactive/automatic launch contract instead of
  claiming Windows squad launches are unavailable.
- New AI connections select themselves in Live immediately. Authenticated Synapse actions reactivate their
  declaring session after an app restart, and squad worker/reviewer receipts roll up to the parent session.
- Live keeps the active root operator selected when child workers connect; degraded connection history is
  informational and no longer masquerades as a blocked work result.
- On initial load, Live prefers a project-bound root operator over legacy unbound worker sessions, preventing
  an old reviewer from replacing the current parent after restart.
- Live's session listing now performs the coordination stale sweep, so an exited legacy worker becomes
  `gone` instead of remaining misleadingly `active · stale` forever.
- New external AI registrations return a one-time session key for bound Live attribution; observe/workspace
  worker credentials enforce self-report/cross-session/global-lifecycle boundaries at the API guard.

### Fixed
- A clean worker process exit without an explicit handoff no longer becomes false completion; it remains a
  transcript-backed handoff requiring inspection, while nonzero exits become blocked.
- Known Claude OAuth expiry is reported as an actionable sign-in blocker without copying raw terminal output;
  operator-authored journal and worker handoff text strip terminal control characters before persistence.
- Automatic role-prompt, AI-context, and generated MCP configuration paths are absolute across all runtimes.
- Stop/timeout now wins the PTY-finalization race, so a killed worker cannot reappear as successfully completed.
- Unknown PTY exit state is blocked rather than treated like exit zero, and overlong Live View intent updates
  are rejected cleanly instead of failing a heartbeat transaction.
- Development restarts no longer leave the main window hidden until `SYN-BOOT-202`: a successful document
  load is an idempotent readiness fallback, the cold-development readiness window allows Vite to warm without
  flashing a false error, and the all-green progress window returns focus to Synapse.
- Restart errors are terminal for one operation, so a delayed health/readiness callback cannot erase a shown
  diagnostic or repaint a failed restart as all-green.
- PTY capture now redacts recognized credential environment values before WebSocket output, scrollback, or
  transcript persistence, including secrets split across read chunks or truncated by process exit.
- PTY EOF/shutdown finalization is single-flight and drains queued output before exit/finalized receipts, so
  duplicate callbacks cannot duplicate lifecycle events or deliver the last redaction marker too late. An
  EOF-first blocked reap now rechecks operator shutdown before choosing its fallback exit code.
- Live announces appended activity to assistive technology, includes squad-worker plans in “Why this step,”
  labels the goals list, and lets Escape cancel an inline goal rename.
- Live goal create and update calls now pass structured bodies to the shared API client instead of
  double-encoding JSON, so the visually complete Goals inspector also saves successfully end to end.
- The global Capture button now moves clear of desktop Live inspectors and drops behind mobile overlays,
  preventing it from intercepting Goals/Squads/Preview controls near the lower-right corner.
- Automatic worker presence no longer depends on the child CLI interrupting its own work to heartbeat;
  stop, finalization, timeout, and daemon shutdown cancel the owned presence loop with the PTY.

### Notes
- Release verification: renderer + Electron typecheck, **783 passed / 14 skipped**, a three-runtime automatic
  launch + isolated Reflex + handoff acceptance run, and a Synapse-hosted post-work council whose final Codex
  re-review returned **RELEASE UNBLOCKED** after protected caller/MCP environment and timeout-task fixes.
- Live View passed real 1280x800 + 375x812 browser click-through with no body or horizontal overflow. The only
  pytest warnings are the two previously documented Windows closed-pipe cleanup warnings.
- A real pre-fix restart reproduced `SYN-BOOT-202`; the same API restart after the fix completed all five
  audited stages green. A second post-fix restart loaded the daemon-owned worker heartbeat and again completed
  all five stages green; a live Copilot PTY advanced its presence timestamp on Synapse's 30-second cadence.


## [0.1.93] -- 2026-08-01

### Added
- **Deep AI operator journal (ADR-0033).** `POST /api/v1/activity/sessions/{id}/events` now persists
  deliberate plans, reasoning summaries, decisions, searches, actions, evidence, blockers, squad activity,
  MCP/tool receipts, and results with real identity links, state, authority, and UTC timestamps.
- Live View defaults to **Deep View**, with a calmer persisted Summary View toggle, current-focus banner,
  clean Synapse/MCP/tool visuals, click-for-detail receipts, token evidence, and status explanation dialogs.
- Collapsible same-page squad drill-down: click a real squad for its worker topology, then a worker for role,
  personality, runtime, status duration, task, PTY/live session, MCP scope, and token profile.
- Authenticated AI calls carrying `X-Synapse-Session` create safe automatic Synapse method/result receipts;
  request/response bodies, auth headers, credentials, and secret values are never copied.

### Changed
- Enabled stdio MCP servers are now labeled **Auto-attached · starts per AI**. Worker launch events carry the
  exact role-scoped MCP ids and emit `v1.agent_mcp.attached`; Reflex remains an isolated per-worker process.
- The session rail shows five recent sessions by default, with explicit history expansion. Empty squad/tool
  inspectors take no space and squad detail opens only when a real squad exists.
- Generated worker prompts and `/ai/context` now teach every runtime to update `last_intent`, report detailed
  operator summaries, add the session receipt header, and keep secrets/private hidden reasoning out of the feed.

### Fixed
- Live View now correlates notifications, PTY output, squad events, and MCP receipts to the selected session
  or its real project squads instead of accepting unrelated global WebSocket events.
- Heartbeats and session release refresh Live View immediately, carry complete session state, and persist focus
  or release receipts; yellow connection health and blocked work status are now clearly separated and explained.
- The advertised universal-search endpoint is now actually mounted and returns live MCP-server results; the real
  `reflex` dogfood query exposed and then verified this previously hidden 404.
- Live View now owns a true fixed-height route shell at 375/1024/1280/2560, with styled inner scrolling and no
  page-level or horizontal overflow; narrow receipts stack their metadata above a full-width card.

### Notes
- Release verification: renderer + Electron typecheck, **750 passed / 14 skipped**, real Deep/Summary and
  squad → worker Playwright click-through, and containment proof at 375/1024/1280/2560. The refreshed
  1280×800 + 375×812 gallery captures have zero console errors or page/horizontal overflow.
- Dogfood proof used real Synapse session #025, a five-worker linked squad, Reflex v2.6.0 observation plus
  named takeover/pause/resume/release, a scored `mcp:reflex` search result, and a real all-green whole-app
  restart. WS replay retained `v1.daemon.started` as event 1 for v0.1.93.


## [0.1.92] -- 2026-07-31

### Added
- **Portable, immutable AI skill packs (ADR-0032).** AI Bundles can now install versioned instruction/resource
  packages that any Synapse-connected AI can discover through REST or the local MCP connector without
  disabling GitHub, Playwright, Web Scraper, Warden, or any other direct tool.
- **Super Internet Digger v2 + Skill Lab.** The first bundled skill adds permission-aware source planning,
  provenance ranking, safe acquisition gates, a single-pass polyglot project inspector, four specialist
  roles, two quick actions, and a reusable baseline-vs-Synapse benchmark contract.
- New AI-discoverable skill endpoints: `GET /api/v1/ai-bundles/skills`, `GET
  /api/v1/ai-bundles/skills/{skill_id}`, and `GET
  /api/v1/ai-bundles/skills/{skill_id}/resources/{resource_path}`; matching MCP tools list and read packs.
- A reusable `templates/skills/benchmark-template.json` and a real 15-repeat Windows benchmark under
  `benchmarks/super-internet-digger/`, including raw timing, quality, safety, and claim-gate evidence.

### Changed
- The AI Bundle Marketplace now counts and displays portable skill packs, and generated worker context tells
  AIs how to discover/read them while preserving normal direct-tool routing.
- Super Internet Digger v2 measured **5.08x faster** warm inspection and **10.82x** warm quality-adjusted
  throughput on the scoped 5,001-file offline fixture. Cold CLI startup measured 1.45x; the full web/model
  workflow remains explicitly unproven at 4x rather than being marketed as a blanket win.

### Fixed
- Skill installation rejects symlinks, generated bytecode, path traversal, mutated same-version packages, and
  read-time hash drift; copied package bytes are verified before activation and uninstall preserves benchmark
  history.
- AI Bundle cards wrap narrow filter/header content correctly at 375 px, eliminating the mobile horizontal
  scrollbar found during live browser verification.

### Notes
- Release verification: renderer + Electron typecheck, **744 passed / 14 skipped**, skill-package validation,
  live daemon `v0.1.92` health, and browser proof at 1280x900 + 375x812 with no console errors or page-level
  horizontal overflow.


## [0.1.91] -- 2026-07-31

### Added
- **Observable startup and whole-app restart (ADR-0031).** Every desktop start now opens a focused progress
  window. Tray, Settings, and AI/API restarts share one cross-process lifecycle: request accepted, previous
  services stopped, desktop relaunched, daemon health passed, and interface visible. Checks turn green only
  after the corresponding fact is measured.
- New AI-discoverable restart control plane: `GET/POST /api/v1/system/restart`, `GET
  /api/v1/system/restart/errors`, `POST /api/v1/system/restart/{operation_id}/stage`, plus
  `v1.system.restart_requested` and `v1.system.restart_progress` events. Requests and stages are audited.
- Stable, plain-language restart diagnostics: `SYN-RST-001/101/201` and `SYN-BOOT-101/102/201/202/301`.
  Failures stay visible and offer **Copy diagnostics** instead of disappearing into a console log.
- **First-party Reflex bootstrap (ADR-0030).** Production startup discovers a valid local Reflex checkout and
  reconciles an enabled stdio MCP entry automatically.

### Changed
- **Managed MCP injection is runtime-neutral for every built-in worker.** Claude receives additive
  `--mcp-config`, Codex receives one-launch `mcp_servers.*` overrides, and GitHub Copilot CLI receives
  `--additional-mcp-config`. The same role binding semantics apply to all three.
- Codex/Copilot MCP credentials remain in the worker environment: Codex arguments contain only variable names,
  and Copilot's generated JSON contains only `${NAME}` references. Conflicting values fail before launch.
- Reflex is `autorun=false` with no shared health port. Each AI host starts its own stdio child on demand, so
  simultaneous workers do not share control leases, pause/emergency state, or a stale fixed-port process.

### Fixed
- Tray restart can no longer race an already-requested API restart into a second untracked operation.
- Abandoned restart operations now age out with diagnostic `SYN-BOOT-301` instead of remaining ambiguously
  active, and a failed local handoff cannot poison the next normal startup with a stale marker.
- The native progress page now emits valid inline JavaScript, keeps the all-green result readable for 3.2
  seconds, and explicitly unlocks/closes its protected window so a successful boot cannot leave an orphaned
  splash behind.
- Reflex reconciliation removes only obsolete shared-port variables while preserving other user-configured
  per-worker settings.

### Verified
- Full regression coverage is green at **734 passed, 14 skipped**; renderer + Electron TypeScript and the
  version/CHANGELOG/README synchronization gate pass.
- A real Windows tray restart upgraded the running app from `0.1.89` to `0.1.91`; a follow-up instrumented
  restart recorded all five stages as successful, returned daemon health `ok`, and left exactly one Synapse
  window. The final native checklist is captured in `docs/screenshots/restart-progress-desktop.png`.


## [0.1.90] -- 2026-07-31

### Added
- **Warden is now an optional, one-click MCP marketplace download (ADR-0029).** Synapse downloads Chris
  Asmussen's MIT-licensed Warden `0.2.1` from immutable commit
  `29cb1355c33f19e8c9c6c6d48ba3136234eeaf2c`, installs it in a Synapse-owned isolated environment,
  verifies Git HEAD + package version + import + CLI before activation, and retains verified releases for
  rollback. The marketplace card shows the active verified version and local/HTTP coverage, with Sync,
  Update (when a newer pin ships), and Restore controls.
- New AI-discoverable Warden lifecycle endpoints: `GET /api/v1/mcp-servers/warden/status` and `POST`
  `/sync`, `/update`, `/rollback`, with audit entries and `v1.mcp_server.updated` broadcasts.

### Changed
- **Warden is additive, never exclusive.** Every enabled MCP remains directly available to Claude/Codex;
  Warden is simply another enabled MCP the AI may choose. Synapse automatically mirrors enabled stdio
  servers into Warden (excluding Warden itself), while HTTP MCPs such as Web Scraper stay direct-only.
- Warden's Synapse-managed registry never receives copied credentials. Secrets remain in Synapse's
  redacted MCP store and are injected into Warden's process environment; a downstream server with a
  conflicting environment-variable value is skipped from Warden but remains directly available.

### Verified
- Full regression coverage: **730 passed, 14 skipped**; focused Warden + MCP marketplace coverage is
  **28 passed**; renderer TypeScript, production build, Python lint, and compile checks are green. A real
  Windows smoke install cloned the exact pinned commit, built the isolated environment, imported Warden
  `0.2.1`, and ran its CLI verification successfully. Live browser proof installed Memory beside Warden,
  verified Warden's Ready state and HTTP-direct count, found zero console errors, and passed 1280 px +
  375 px horizontal-overflow checks.


## [0.1.89] -- 2026-07-31

### Changed
- **AI Activity (ADR-0028) marked complete — docs finalized.** ADR-0028 status is now
  "accepted — Phases 0–6 shipped (v0.1.78–v0.1.88)" with the full shipping table; the
  `ai-activity-live-view` and `one-window-ui-standard` roadmap items are **shipped**; `PROGRESS.md` records
  the whole wave; and the README leads with what the feature actually gives you — see the moment an AI
  connects (graded green/yellow/red with an explained code), a session number per run, a notification
  center with token usage + jump-to links, and a **Live** tab to watch it work with a preview of the app
  it's building. Feature summary: 7 versions (`0.1.82`–`0.1.88`), 2 migrations, 3 new daemon modules
  (`connection_codes`, `activity`, `routes_activity`), 5 new renderer modules, 2 read-only MCP tools, and
  ~25 new tests — every phase verified live against the running stack, not just typechecked.

## [0.1.88] -- 2026-07-31

### Added
- **AI Activity is now AI-facing too — the feature is complete (ADR-0028, PLAN 5 Phase 6).** An AI driving
  Synapse can see the same picture the operator sees:
  - `GET /api/v1/ai/context` carries a new **`ai_activity`** block: the connected sessions (each with its
    `#NNN` number, runtime/label/task, status, and green/yellow/red grade + code) and the last 10
    notifications, plus a hint on how to register and read the feed.
  - `GET /api/v1/coordination/snapshot` already returns full `AgentSession` objects, so every session there
    now carries `seq` + `connection_level` + `connection_code` (from Phase 1).
  - Two **read-only MCP tools** (always available, no writes flag): **`synapse_list_sessions`** (numbered
    sessions with runtime/status/grade) and **`synapse_recent_activity`** (the recent feed) — so an MCP
    client over the WAN tunnel can see who's connected and what just happened.
  - `docs/DRIVE-SYNAPSE-FROM-AI.md` gained a **"Your session"** section: the grade table (register with a
    `project_id` to come up green), what the operator sees, and how to read sessions/activity via REST + MCP.
  - ADR-0028 records the full Phase 0–6 shipping table, including the CSP finding from Phase 5.

## [0.1.87] -- 2026-07-30

### Added
- **Live app preview — watch the app an AI is building, inside Live View (ADR-0028, PLAN 5 Phase 5).**
  A **Preview** toggle appears on a session whose project is actually running; it opens a pane beside the
  timeline that **iframes the live project URL** (`http://localhost:{expected_port}`). Because Synapse
  launches real dev servers, this is the *real* app — full framework, real backend/data, and it updates as
  the AI edits — which beats a sandboxed artifact snapshot (the approach researched for ADR-0028). The pane
  has **device widths** (mobile 375 / tablet 768 / desktop), **Reload**, **Logs** (reuses `LogViewer`), and
  **Open in browser**, and closes away entirely — one-window, not a new page.
- Shared `InlineBold` helper so the Live View timeline renders activity bodies as cleanly as the
  Notification Center (no raw `**` markers); the Notification Center now imports it instead of its local copy.

### Fixed
- **The preview was blocked by the app's Content-Security-Policy** (`default-src 'self'` with no
  `frame-src`, so Chrome refused to frame the project — the iframe existed but rendered nothing). Added a
  **loopback-scoped** `frame-src 'self' http://localhost:* http://127.0.0.1:*` — Synapse-launched projects
  only, never arbitrary origins. Caught by live verification, not by types.

### Verified (live, against the running stack)
Launched a real project (`fast-money-client-ops`, port 8740 → HTTP 200), registered a session bound to it —
it graded **green (`ok`)**, confirming the whole grading path — then in the browser: the **Preview** button
appeared *only* for that project-bound running session, opening it rendered the live app in the iframe
(517×887, `src=http://localhost:8740`) with all 7 controls, **0 console errors** after the CSP fix, and the
page still does not scroll (3 `.scrollbar-thin` panes). `tsc` 0 errors.

## [0.1.86] -- 2026-07-30

### Added
- **The Live View tab — watch your AIs work in real time (ADR-0028, PLAN 5 Phase 4).** A new top-level
  **Live** hub in the sidebar (AI section). Left rail: every AI session ever registered, newest number
  first — `#011 · Claude · active · just now`, with a connection dot (green/yellow/red via the semantic
  `status-*` tokens) that pulses while the session is live, plus its status/stale flag and task. Main pane:
  the selected session's story — its persisted milestones from the activity feed, then **live events
  appended as they happen** (`v1.activity.notification`, work-item/agent-run events, and the AI's own
  `pty.session_output` terminal lines rendered mono, buffer capped at 300), with a header strip showing the
  connection code, recorded **token total**, and a pulsing **live** indicator. Real loading / empty / error
  states throughout (Contract #13), and the timeline auto-follows new entries.
- **This is the reference implementation of the one-window standard** (AGENTS.md "Frontend UI standard"):
  a fixed-height shell where the session rail and the timeline are *independent* `min-h-0 overflow-y-auto`
  panes with `.scrollbar-thin` — **the page body never scrolls**. New surfaces should copy this page's shape.
- New nav plumbing: `'live'` added to `CorePageId` / `NavigationIntent` / `SidebarLayout`, a `Radio`-icon
  entry in `CORE_NAV_ITEMS`, and `'live'` added to the AI-section defaults — `completeOrder()` appends any
  default missing from a **saved** layout, so the new hub shows up for existing installs without a migration.

### Verified (live, against the running stack)
Clicked **Live** → the rail listed all 10 existing sessions; registering a new AI session by `curl` made
**#011 appear at the top of the rail instantly** ("just now") and stream into the timeline with the live
indicator — **no reload**. Page body does not scroll at **1536px** or **375px** (0px overflow at mobile
width), 2 `.scrollbar-thin` panes present, `tsc` 0 errors, 0 console errors after a full reload.

## [0.1.85] -- 2026-07-30

### Added
- **The Notification Center — see when an AI connects and what it does (ADR-0028, PLAN 5 Phase 3).** A
  persistent **bell** with an unread badge, reachable on every screen (desktop + mobile, mounted globally
  beside the Capture FAB). Opening it shows the AI-activity feed: a coloured status dot per level
  (green/yellow/red via the app's semantic `status-*` tokens — no raw palette), the title, relative time,
  a per-row **✕ to dismiss** (marks read), and **Mark all read**. Clicking a row opens a detail view with
  the full body, the **session number**, a **token-usage** breakdown (in/out/total + per-role) when the
  daemon recorded one, and the notification's **jump-to links** rendered as buttons that route through the
  app's existing `navigate()` flow (via the `synapse:navigate` event) — so "Session #7 filed an idea" can
  take you straight to the Review inbox. New `renderer/lib/activity-client.ts`, `renderer/lib/use-activity.ts`
  (live via the `v1.activity.notification` event, with optimistic read-marking), and
  `renderer/components/NotificationCenter.tsx`.
- **`.scrollbar-thin` utility (one-window standard).** The first piece of the ADR-0028 UI standard lands in
  `renderer/styles.css`: theme-driven thin scrollbars (WebKit + Firefox) for the *inner* scroll panes every
  new surface is built from. The Notification Center is built to that standard — a fixed-height panel whose
  list/detail pane scrolls while the page itself never does.

### Verified (live, against the running stack)
Registering an AI session by `curl` made the bell badge appear **live over the WebSocket with no reload**
("AI activity — 1 unread"); the row read "Session #009 — claude connected · just now" with the yellow
`bg-status-launching` dot; the detail view showed the connection code (`degraded.no_project`), the task, and
the session number, and auto-marked it read (badge cleared). Page body does not scroll (vertical or
horizontal). `tsc` 0 errors; 0 console errors after reload.

## [0.1.84] -- 2026-07-29

### Added
- **Persisted AI-activity notifications (ADR-0028, PLAN 5 Phase 2).** The daemon now keeps a truthful
  feed of the milestones an AI hits while driving Synapse. New migration `028_activity_notifications` +
  `activity.py`: an **event→notification projector** subscribed to the daemon's own bus at startup maps
  `session_registered` (title "Session #007 — Claude connected", level/code from the graded connection),
  `agent_squad.created` (quotes the squad's real goal), `agent_work_item.created/handoff` (role, handoff
  summary, squad token rollup via the token ledger), `review.proposal_filed` (reads the proposal's real
  title — "Idea filed to inbox: …"), `project.launched/errored` (errored = red), and `tool.primitive_ran`
  into rows with jump-to `links` in renderer NavigationIntent shape. A projector failure never breaks the
  bus; each new row is also announced as `v1.activity.notification` so the bell badge can update live.
  New `routes_activity.py`: `GET /api/v1/activity/notifications?unread=&limit=` (+`unread_count`),
  `POST .../{id}/read`, `POST .../read-all`, `GET /activity/sessions` (full #-numbered history, newest
  first — via new `coordination.list_all_sessions`), `GET /activity/sessions/{id}` (session + its
  project's squads/work-items + real token rollups + its notifications). 8 tests incl. a live
  end-to-end: registering a coordination session produces the "Session #001 … connected" notification
  through the real bus→projector→feed chain. Next: the Notification Center UI (bell + list + detail).

## [0.1.83] -- 2026-07-29

### Added
- **Session numbers + graded connections for AI sessions (ADR-0028, PLAN 5 Phase 1 step 2).** When an AI
  registers a coordination session, it now gets:
  - a monotonic operator-facing **session number** (`seq` — #001, #002, …; migration `027_session_connection`
    backfills existing sessions by registration order and adds a unique index), and
  - a stored **connection grade** (`connection_level` green/yellow/red + `connection_code`), computed at
    register time via `connection_codes.classify()` — `has_project` from the payload, `mcp_all_connected`
    probed best-effort by the route from the live MCP manager (STDIO servers count available; HTTP must be
    CONNECTED; any probe failure or a bare test app defaults to available so registration is never wrongly
    degraded, guarded by a 3s timeout).
  The register route's audit row and the **`v1.coordination.session_registered` event are enriched** with
  `seq`, `runtime_id`, `agent_label`, `task`, `connection_level`, `connection_code` — this is the "an AI
  connected" signal the notification projector + Live View key off. 5 new tests (`test_coordination`).

## [0.1.82] -- 2026-07-29

### Added
- **Connection status codes for AI sessions (ADR-0028, PLAN 5 Phase 1, step 1).** New
  `daemon/synapse_daemon/connection_codes.py`: a pure catalog + `classify()` that grades an AI's
  connection as **green** (`ok` — full control), **yellow** (`degraded.mcp_unavailable` /
  `degraded.no_project` — connected but a capability is offline), or **red** (`failed.internal`), each
  with a stable machine code + a plain-language explanation + a remedy so degraded/failed connections are
  self-diagnosing. This is the foundation the notification center renders and that sessions/`ai/context`
  will report. 6 tests (`test_connection_codes`). Next: the session sequence number (#001…) + emitting
  `v1.agent_session.connected` on register.

## [0.1.81] -- 2026-07-29

### Added
- **Docs-sync gate + the plan, in-repo (ADR-0028).** Three owner directives, made durable:
  - **Docs-sync is enforced.** `scripts/docs_sync_check.py` fails a commit if the three version files
    disagree, if `CHANGELOG.md` lacks a `## [<version>]` entry, or if `README.md` doesn't name the current
    version. Mirrored as `test_version_consistency` pytest tests so CI enforces it on every push, and added
    to the `AGENTS.md` pre-commit ritual. (It immediately caught that v0.1.80 left the README at 0.1.79.)
  - **The plan lives in the repo.** ADR-0028 + `docs/roadmap.json` entries capture the AI Activity feature
    (connection status, session #s, notification center, Live View) so any AI — Claude, **Codex**, Copilot —
    codes to the same plan, not one AI's private notes. `AGENTS.md` now points every AI at the in-repo plan.
  - **One-window UI standard.** A binding frontend convention in `AGENTS.md`: new surfaces are a fixed-height
    shell whose *inner* panels scroll (never the page), with styled professional scrollbars; Apps + AI Coding
    refactor to it, and the upcoming Live View pilots it.
- Verified: `docs_sync_check.py` passes at 0.1.81; the new tests pass; README/PROGRESS/roadmap synced.

## [0.1.80] -- 2026-07-29

### Fixed
- **`profile._state_row()` could raise `UNIQUE constraint failed: profile_state.id`.** The singleton
  `profile_state` row (id=1) was created with a check-then-`INSERT`: a concurrent caller — or a stale read
  snapshot that missed the existing row — would try to insert id=1 a second time and crash the profile read
  (seen in the daemon log). Changed to `INSERT OR IGNORE` so the duplicate creation is a no-op; the row
  exists either way. Added `test_state_row_creation_is_race_safe`. (Diagnosed while restoring a wedged daemon
  that left the desktop stuck on "loading" — the restart itself was clean; this removes the latent state bug.)

## [0.1.79] -- 2026-07-29

### Fixed
- **Desktop startup no longer blocks the whole shell on trusted-local auth bootstrap.** In the
  renderer's `DaemonProvider`, `/health` still starts immediately, but the desktop shell no longer
  waits for `/api/v1/auth/local-token` before it kicks off `/projects`, `/profile`, and the main
  WebSocket. Local-token bootstrap is now an opportunistic background warm-up instead of a hard
  startup gate, which lets the existing REST `401 -> tryRefreshLocalToken()` retry path and the WS
  `1008 -> tryRefreshLocalToken()` recovery path do their jobs without leaving Home/Apps stuck on
  global loading states when the trusted-local token call is slow. A successful background bootstrap
  now also triggers one clean second-pass refresh for projects/profile, and Home shows a real retryable
  project-load error instead of a false "no projects yet" empty state if that first protected load fails.

### Notes
- Verification: `npm run typecheck`; fresh `synapse.cmd` relaunch under Electron renderer inspection
  reached a live Home shell immediately, then settled the slower operator cards normally; click-through
  proof reached the Apps page on the same relaunch; full daemon suite `689 passed, 14 skipped, 2 warnings`
  in `598.33s`.


## [0.1.78] -- 2026-07-29

### Added
- **WAN auto-start toggle in Settings (finishes ADR-0026; PLAN 5 Phase 0).** The `wan_auto_start`
  preference (default on, since v0.1.71) now has a UI: an "Auto-connect on startup" switch in the
  Settings → Phone Access → **WAN via Cloudtap** section (`PhoneAccessPanel`), wired to
  `PATCH /api/v1/system/network {wan_auto_start}` with a note that it takes effect on the next daemon
  start. `RemoteAccessNetwork` (the `/remote-access` aggregate the panel reads) now carries
  `wan_auto_start`; added `patchNetworkWanAutoStart` to the system client. (The orphaned `NetworkPanel`
  component is not mounted — the live network UI is `PhoneAccessPanel`.) Verified: tsc 0 errors; the
  toggle renders in the running app; `test_remote_access_network_carries_wan_auto_start` + the existing
  `/system/network` wan tests pass. The live toggle reflects its true state once the daemon reloads the
  updated model (next launch) — not force-restarted here to avoid disrupting an active AI session.

## [0.1.77] -- 2026-07-29

### Fixed
- **Local browser auth bootstrap no longer bursts into temporary `401`s on first load.** On
  non-mobile trusted-local browser routes such as `http://127.0.0.1:5173`, Synapse now prefers the
  daemon's trusted-local token (`/api/v1/auth/local-token`) before reusing a remembered paired-device
  token from `/mobile`. That keeps stale remembered mobile tokens from briefly failing protected
  routes such as `/projects`, `/profile`, `/review/inbox`, `/ai/health-report`, and
  `/installed-pages` before the shell recovers. Explicit handoff tokens and `/mobile` paired-device
  flows still keep their intended precedence.
- **Top-level repo status headers are back in sync with the actual shipped version.** `README.md`
  and `PROGRESS.md` now reflect the real `0.1.74`–`0.1.77` state instead of stopping at `0.1.73`.

### Notes
- Verification: `npm run typecheck`; live Playwright reloads against `http://127.0.0.1:5173`
  finished with `0 errors` (only the existing early WebSocket-close warning) and the Home shell
  loaded normally; full daemon suite `688 passed, 14 skipped, 2 warnings` in `529.90s`.


## [0.1.76] -- 2026-07-29

### Added
- **GitHub repo-health templates + policy files (repo audit).** CI (`ci.yml` — typecheck + pytest on
  push/PR) and `LICENSE` were already present; added the high-impact missing pieces: a **PR template**
  (`.github/PULL_REQUEST_TEMPLATE.md`) that enforces the repo's own version/CHANGELOG/tests/docs-sync +
  coordination discipline, a **bug-report issue template** (`.github/ISSUE_TEMPLATE/bug_report.md`), a
  **`SECURITY.md`** documenting the token / WAN (Cloudtap) / MCP trust model + secret handling + private
  reporting (ties to ADR-0026/0027), and an **`.editorconfig`** matching the documented style (2-space JS/TS,
  4-space Python, 120 cols, CRLF for `.ps1`/`.cmd`). Left for the owner to decide (not added): CODE_OF_CONDUCT,
  CONTRIBUTING (AGENTS.md already covers norms), automated GitHub Releases, branch protection, status badges.

## [0.1.75] -- 2026-07-29

### Added
- **Drive-capable MCP connector (ADR-0027, increment 3).** The `/mcp/<token>` connector (ADR-0012) was
  read-only; it now offers **drive tools** for MCP-native clients (e.g. the claude.ai web connector over the
  auto-on WAN tunnel), gated behind `SYNAPSE_MCP_ALLOW_WRITES=1` (default **off**):
  - `synapse_create_squad` — create an Agent Squad on a project.
  - `synapse_add_work_item` — assign a work item (role + title) to a squad.
  - `synapse_capture_note` — append a note to a project's AI memory or backlog.
  These are in-process (storage-only) writes; **launching** a worker stays on the REST path
  (`POST /agent-work-items/{id}/launch`, reachable over the same tunnel), which is the riskier capability. The
  `initialize` instructions now announce drive-mode when writes are on. Note: the WAN tunnel already exposes the
  *whole* token-guarded REST API, so any HTTP-capable AI (another Claude Code) has full remote drive over the
  tunnel URL today — the MCP tools are specifically for MCP-protocol clients. Docs: `DRIVE-SYNAPSE-FROM-AI.md`
  §8 rewritten (two remote paths) + ADR-0027 consequences. Tests: 4 new (`test_mcp_connector`) — drive tools
  hidden/uncallable when off; create-squad→add-work-item + capture succeed when on; unknown project is a tool
  error. 17 connector tests pass.

## [0.1.74] -- 2026-07-29

### Added
- **`docs/DRIVE-SYNAPSE-FROM-AI.md` — a task-oriented guide for driving Synapse from another AI (ADR-0027).**
  The second increment of the AI-drivable effort: connect + auth (`X-Synapse-Token` from `data/auth-token`,
  localhost or the WAN URL), orient (`/ai/context`, `/openapi.json`, `/coordination/snapshot`), then real
  `curl` flows for the core capabilities — drive an AI squad (create → add work-item → launch → monitor →
  handoff/delegate → kill switch), run a workflow (quick-action), harvest the web (web-scraper MCP), register
  + evaluate an app (projects / Quality OS / benchmarks / review inbox), capture notes, and drive remotely via
  the `/mcp/<token>` connector over the auto-on WAN tunnel — plus a security note (the token is the trust
  boundary). Endpoints verified against `routes_*.py`; exact bodies deferred to the live `/api/v1/openapi.json`
  so the guide can't drift from the code. Linked from `AGENTS.md` + `README.md`.

## [0.1.73] -- 2026-07-29

### Added
- **Home now surfaces the first operator-grade attention + trust snapshot.** The Home page gained a
  new **Needs attention** card (review inbox items, AI-filed proposals, blocking quality gates, quick
  jump into Review/Coder Workspace) plus a **Trust signals** card (last recorded test run, latest
  browser proof, latest successful review pass, daemon version/uptime). This is the first concrete
  product slice of the broader "AI operator experience" gap list.
- **Synapse's own plan now tracks the AI-operator follow-up work explicitly.** The `synapse-self`
  backlog records the five next operator improvements: attention hub, trust signals, runtime-launch
  trust, automatic session hygiene, and faster AI context recovery. The public roadmap gained matching
  items under a new **AI operator experience** phase.

### Changed
- **`GET /api/v1/ai/health-report` is now useful for lightweight trust surfaces, not just self-test
  loops.** It now includes `review.latest_successful_pass` alongside the existing compact quality/test
  summary, so a Home-level operator card can answer "what was last actually reviewed?" without pulling
  the full `ai/context` digest.
- **The Home trust snapshot tolerates older daemon payloads during a rolling update.** Nested trust
  fields are read defensively, so the renderer can fall back gracefully if it is talking to a daemon
  that has not yet picked up the new `review.latest_successful_pass` shape.

### Notes
- Verification: `npm run typecheck`, `npm run build:renderer`, targeted `python -m pytest
  daemon/tests/test_routes_ai.py -q`, and full daemon suite `684 passed, 14 skipped` in 503.51s.
- Playwright reached the live dev shell at `http://127.0.0.1:5173`, but a local-token bootstrap/auth
  issue returned repeated `401` responses on protected routes, so no trustworthy signed-in browser proof
  was claimed for this slice.


## [0.1.72] -- 2026-07-29

### Added
- **API discovery is ON — an AI can now enumerate Synapse's full endpoint surface (ADR-0027).** The
  daemon's `openapi_url` / `docs_url` / `redoc_url` were disabled; they're now served at
  `/api/v1/openapi.json`, `/api/v1/docs` (Swagger UI), and `/api/v1/redoc`. This is the first increment
  of making Synapse fully drivable from another AI chat (a same-machine Claude Code over `localhost:7878`,
  or a remote AI over the auto-on WAN tunnel). The schema is the API **contract** only — every data read
  / action still requires the `X-Synapse-Token`, so exposing the shape carries no data/action risk. Next
  increments (ADR-0027): a `docs/DRIVE-SYNAPSE-FROM-AI.md` driver guide and a drive-capable extension of
  the `/mcp/<token>` connector. New test: `test_openapi_discovery_is_enabled` (schema lists 100+ paths incl.
  `/api/v1/agent-squads`; Swagger UI serves).

## [0.1.71] -- 2026-07-29

### Added
- **WAN auto-start (ADR-0026) — the Cloudtap tunnel now opens on daemon boot by default.** Previously
  reaching Synapse from off-LAN meant clicking "Expose to WAN via Cloudtap" every launch. Now a persisted
  `wan_auto_start` boot setting (default **on**) drives a startup hook (`_autostart_wan_tunnel`) that opens
  the tunnel on the bound port automatically. It mirrors `_autostart_mcp_servers`: best-effort (a tunnel
  failure never aborts startup), idempotent (won't stack tunnels if one is already open for the port),
  graceful when Cloudtap isn't installed, and gated by a new `allow_wan_autostart` flag (default off; only
  the real daemon sets it) so TestClient app-builds never spawn a real `cloudflared`. `GET/PATCH
  /api/v1/system/network` now carry `wan_auto_start` (both patch knobs optional; each change audited under
  `network.<knob>.set`) so the Settings toggle + the API can flip it. This makes the ADR-0012 `/mcp/<token>`
  connector reachable remotely out of the box. Verified live: on daemon restart the tunnel auto-opened at a
  public `*.trycloudflare.com` URL and reached `ready` in ~5s with no manual action. The Settings +
  onboarding toggle ships next. New tests: `test_boot_config` (wan_auto_start default/roundtrip/type-guard)
  + `test_routes_system` (patch persists/audits/GET reflects, single-knob + both-knobs).

## [0.1.70] -- 2026-07-17

### Fixed
- **Coder Workspace top-level error banner was not announced to screen readers (UI/UX audit, Contract
  #23, a11y).** The error `Card` was set dynamically but lacked `role='alert'`/aria-live, so assistive
  tech never announced a workspace error — inconsistent with `Review.tsx` and `AgentSquadsView.tsx`,
  which both mark their error displays as alerts. Added `role='alert'` to the card. Playwright-verified
  against the running renderer: with the thread-list fetch forced to fail, the error card renders as
  the page's single `role='alert'` carrying the error text. tsc 0 errors.

## [0.1.69] -- 2026-07-17

### Fixed
- **Coder Workspace thread rail showed a false "No threads yet" during the initial load (UI/UX audit,
  Contract #13).** `threadsByProject` starts `{}` and `refreshThreads` only batch-populates it after all
  per-project `listProjectCoderThreads` calls resolve, so on first mount every project rendered the
  empty copy "No threads yet. Start one from this project." while the fetch was still in flight —
  loading indistinguishable from genuinely empty. Added a `threadsLoaded` flag (false until the first
  `refreshThreads` settles, set in a `finally` so it flips even on error) threaded into
  `ProjectThreadRail`; each project now shows a "Loading threads…" spinner while unloaded and the empty
  copy only after the fetch completes. Playwright-verified against the running renderer (with the
  coder-threads fetch delayed): during load the rail shows "Loading threads…" with a per-project spinner
  and no "No threads yet"; after load it resolves to the thread list or the genuine empty state. tsc 0
  errors.

## [0.1.68] -- 2026-07-17

### Fixed
- **Four bare `<select>` controls in the Agent Squads view had no accessible name (UI/UX audit,
  Contract #23, a11y).** The new-squad project + lead-role selects, the new-work-item role select, and
  the delegate-role select were unwrapped and unlabeled, so screen readers announced them as unnamed
  combo boxes (unlike the handoff-section selects, which are label-wrapped). Added a descriptive
  `aria-label` to each: "Project for new squad", "Lead role for new squad", "Assigned role for new work
  item", "Assigned role for delegated work item". Playwright-verified against the running renderer: all
  7 visible selects on the Squads view now have an accessible name (0 unnamed). tsc 0 errors.

## [0.1.67] -- 2026-07-17

### Fixed
- **Two icon-only buttons in the Coder Workspace thread rail had no accessible name (UI/UX audit,
  Contract #23, a11y).** The per-project "new thread" button (MessageSquarePlus) and the per-thread
  delete button (Trash2) rendered an icon with no text, `aria-label`, or `title`, so screen readers
  announced each as an unlabeled "button". Added descriptive `aria-label` + `title` to both:
  `New thread in {project.name}` and `Delete thread {thread.title}`. Playwright-verified against the
  running renderer: of 34 visible icon-only buttons, 0 are now unlabeled; the new-thread buttons read
  e.g. "New thread in AI Operating System" and delete buttons read e.g. "Delete thread run the app".
  tsc 0 errors.

## [0.1.66] -- 2026-07-17

### Fixed
- **Review inbox showed a contradictory error + "All caught up" at once on a failed load (UI/UX audit,
  Contract #13).** When `getReviewInbox()` failed, `error` was set but `inbox` stayed null, so `isEmpty`
  was true and the page rendered BOTH the red error line and the "All caught up" empty card — telling
  the user everything is fine and something failed simultaneously, with no way to recover. Added a
  dedicated first-load error branch (`error && !inbox`) with a `role='alert'` card and a **Retry**
  button (re-runs `refresh()`), placed before the empty branch so a failed load never renders "All
  caught up". The small top-of-page error line is now gated to `error && inbox` (a stale-refresh
  failure that still has data to show). Playwright-verified against the running renderer: happy path
  unchanged (list renders); on a simulated `/review/inbox` failure the error card + message + Retry
  render, "All caught up" is absent, and exactly one `role='alert'` exists (was two); clicking Retry
  after recovery restores the list. tsc 0 errors.

## [0.1.65] -- 2026-07-17

### Changed
- **Normalized two arbitrary `grid-template-columns` Tailwind classes from commas to underscores**
  (`AgentSquadsView.tsx` squad cockpit `xl:grid-cols-[320px_minmax(0,1fr)_360px]`,
  `MarketplaceBrowser.tsx` `lg:grid-cols-[240px_minmax(0,1fr)]`). Underscore is Tailwind's documented
  separator for spaces in arbitrary values, and every other grid in the repo already uses it. **No
  visual change**: a UI audit flagged the comma form as producing an invalid declaration that collapses
  the grid to a single column, but Playwright inspection of the generated CSS showed this Tailwind
  version normalizes the top-level commas to spaces, so both forms compiled to the same valid multi-track
  grid. The change removes reliance on that undocumented comma-normalization (which could break under a
  different Tailwind version or a non-JIT production build) and restores repo consistency. Verified: tsc
  0 errors; generated CSS for both classes is `grid-template-columns: 320px minmax(0,1fr) 360px` /
  `240px minmax(0,1fr)`.

## [0.1.64] -- 2026-07-17

### Fixed
- **Apps page header actions overflowed the viewport on mobile (UI/UX audit, important).** The
  header action cluster (Import ChatGPT export + help, Scan for projects, Add Project ~500px+) was a
  non-wrapping `flex gap-2` row, so at 375px the buttons ran past the ~343px content width and got
  clipped. Added `flex-wrap justify-end` so the actions stack onto additional rows (right-aligned) on
  narrow widths. Playwright-verified: at 375px the 3 actions wrap to 3 rows with the cluster right edge
  at 342px (within the 375px viewport) and zero horizontal page overflow; at 1280px they stay on a
  single row, unchanged.

## [0.1.63] -- 2026-07-17

### Fixed
- **A contract PASS could silently clobber a human-waived quality gate (`quality_os.run_contract`).**
  When a caller ran a UI contract with `verdict=pass` and an explicit `gate_id` pointing at a gate a
  human had already **waived** (accepted the known issue), the PASS branch called `resolve_gate`
  unconditionally -- flipping the gate to `status=passed` while `waiver_state` stayed `waived`, an
  inconsistent state that erased the human decision. The PASS branch now resolves a gate only when it
  is still `OPEN` (the auto-discovery path already filtered to OPEN; this protects the explicit-`gate_id`
  path and also makes a redundant PASS on an already-resolved gate idempotent). Added
  `test_pass_does_not_clobber_a_waived_gate` (8 quality_os tests pass).

## [0.1.62] -- 2026-07-16

### Fixed
- **Benchmark efficiency-frontier (`benchmarks._mark_efficiency_frontier`) inverted Pareto domination
  for zero-valued metrics.** The domination check used `x or math.inf` / `x or -math.inf` fallbacks,
  which treat a legitimate `0` as falsy ("missing"). A zero-token candidate -- the *most* token-efficient
  -- got `0 or math.inf` = `inf` (the worst), so the best candidate was wrongly marked dominated and
  kicked off the efficiency frontier. The fallbacks were also dead code: `comparable` already guarantees
  all three metrics are non-`None`. Now the check compares the real values directly. Added
  `test_efficiency_frontier_zero_tokens_is_most_efficient_not_least` (proves the fix) +
  `test_efficiency_frontier_basic_pareto_still_holds` (non-zero sanity). Full benchmarks + bug-hunt
  suites green (21 tests).

## [0.1.61] -- 2026-07-16

### Fixed
- **Bug-hunt scoring (`benchmarks.score_bug_hunt`) under-counted true positives.** A finding whose
  text names two distinct bugs was greedily attributed to the *first* one in answer-key order and, if
  that bug was already claimed by an earlier finding, dropped as a `duplicate` -- even when it was a
  valid, unique match for a different, still-open bug. That deflated `true_positives` and the headline
  `bugs_per_1k_tokens` the topology benchmark (Plan 3 Phase 2) ranks on. Now the scorer collects every
  matching bug and credits the first *unclaimed* one, only counting a duplicate when every matched bug
  is already claimed. Behaviour is unchanged when a finding's first match is unclaimed (all prior tests
  still pass). Added `test_finding_naming_two_bugs_credits_the_still_open_one` +
  `test_true_duplicate_still_counts_when_no_other_bug_matches` (18 bug-hunt tests pass).

## [0.1.60] -- 2026-07-10

### Notes
- **Bug-hunt: the multi-AI coordination substrate (ADR-0024) is clean + well-covered.** Reviewed
  `coordination.py` (session presence + staleness, the stale sweep, advisory file-lane overlap
  detection, repo-vs-project scope isolation, git-collision detection) -- no bugs found; the logic is
  sound and well-defended. Added the one missing regression test,
  `test_heartbeat_reactivates_a_gone_session`: a bare heartbeat resurrects a gone/swept session and
  clears `ended_at`, while an explicit status on the heartbeat is honored. Coordination suite: 18 passed.

## [0.1.59] -- 2026-07-10

### Fixed
- **Status chips + badges follow the theme instead of fixed off-brand colors (UI/UX audit fix #6 --
  completes the 8-fix audit).** Review, Tools, and ToolCard used raw Tailwind palette tints
  (`bg-emerald-500/15`, `bg-amber-500/15`, `text-sky-300`, `border-yellow-400/40`, ...) that don't adapt
  to the light/hacker/surfer themes and drop contrast in light mode. Swapped them for the semantic
  status tokens the rest of the app already uses: `bg-status-launched/15 text-status-launched` for
  success/ready, `bg-status-launching/15 text-status-launching` for warning/blocked, and `primary` for
  idea highlights. Verified live with Playwright: the tokens resolve to real per-theme colors with
  correct opacity (e.g. `status-launched` -> `rgba(26,230,100,.15)`), 0 console errors. Renderer-only.

## [0.1.58] -- 2026-07-10

### Fixed
- **Section tabs are keyboard-navigable (UI/UX audit fix #8 -- a11y).** The `role="tablist"` rows had a
  roving tabindex but no arrow-key handler, so keyboard/screen-reader users couldn't move between tabs
  the way a tab strip should behave. A shared `handleTablistKeydown` helper (`renderer/lib/tablist.ts`)
  now handles Arrow Left/Right (wrapping) + Home/End on the tablist container, moving focus and
  activating the tab -- wired into all four tab rows across AI Coding, My Tools, and Apps. Renderer-only,
  tsc-clean.

## [0.1.57] -- 2026-07-10

### Fixed
- **Home no longer flashes "Welcome to Synapse" (as if you have no projects) during load (completes
  UI/UX audit fix #2).** The home banner chose between the featured-projects slideshow and a "Welcome"
  card purely on whether any projects had loaded yet, so during the initial fetch it showed the new-user
  welcome even when projects exist. It now shows a "Loading your projects..." card until `projectsLoaded`
  settles, then the slideshow (or the welcome only when genuinely empty). `renderer/pages/Home.tsx`,
  renderer-only, tsc-clean.

## [0.1.56] -- 2026-07-10

### Fixed
- **Apps no longer flashes "No projects yet" during load or on a daemon error (UI/UX audit fix #2 --
  states, Contract #13).** `daemon-context` now exposes `projectsLoaded` + `projectsError`; the Apps page
  shows a "Loading your projects..." card while the first fetch is in flight, an error card (role=alert)
  with a Retry button if it fails, and the "No projects yet" empty state only once loading has settled
  with zero projects. Verified live with Playwright: Apps shows the loading card, then the real project
  tiles, never a false empty state, 0 console errors. (Home's welcome card gets the same treatment in a
  follow-up.) Renderer-only.

## [0.1.55] -- 2026-07-10

### Changed
- **Consistent name for the coder surface (UI/UX audit fix #4 -- consistency).** The main AI-Coding
  section tab was labeled "Workspace" while the command palette calls the same destination "Coder
  Workspace" -- one place, two names. The tab (and the hub's help text) now say **"Coder Workspace"**,
  matching the palette, so the same destination reads the same everywhere. `renderer/pages/AiCoding.tsx`,
  renderer-only, tsc-clean.

### Notes
- Verified the web-scraper MCP is healthy (v2.5.9, 93 tools, REST server 200, Playwright + browser
  automation on) and Playwright MCP works -- both usable for verification/analysis.

## [0.1.54] -- 2026-07-10

### Fixed
- **Home carousel now respects reduced motion + keyboard focus (UI/UX audit fix #7 -- a11y).** The
  featured-projects banner auto-advanced every 6.5s regardless of the user's `prefers-reduced-motion`
  setting and only paused on hover. It now skips the auto-advance timer entirely when reduced motion is
  requested, and pauses while any child control has keyboard focus (onFocus/onBlur), mirroring the hover
  pause. `renderer/components/FeaturedSlideshow.tsx`, renderer-only, tsc-clean.

## [0.1.53] -- 2026-07-10

### Fixed
- **Section tab rows no longer overflow the page on mobile (UI/UX audit fix #5 -- responsive).** The AI
  Coding (5 tabs), My Tools (4 tabs), and Apps section tablists used `inline-flex w-fit` with no wrap, so
  at 375px they forced the whole page to scroll sideways and pushed the rightmost tabs (Review, ChatGPT)
  off-screen. They now use `flex flex-wrap` so tabs reflow onto multiple rows within the viewport.
  Verified live with Playwright at 375px: no horizontal page overflow (scrollWidth == clientWidth == 375)
  and the tablist stays within the viewport. Renderer-only.

## [0.1.52] -- 2026-07-10

### Added
- **The nav now shows a live "needs review" count badge (UI/UX audit fix #1 -- findability).** The Review
  inbox was invisible in the nav, so AI-handed-back work and filed ideas piled up unseen. A new shared
  `useReviewCount` hook fetches the inbox count and refreshes on the `v1.review.*` / `v1.agent_work_item*`
  events the daemon already broadcasts; the AI Coding sidebar item renders a numeric badge (with an
  aria-label) whenever items need review. Verified live with Playwright: the badge shows "5 items need
  review", app connected, 0 console errors. Renderer-only. From the parallel UI/UX audit (53 findings).

## [0.1.51] -- 2026-07-09

### Changed
- **Flagged ideas now show "possibly addressed" in the Review inbox (completes the v0.1.50 reconcile
  loop).** When `POST /review/proposals/reconcile` flags an open idea whose fix already landed in a
  commit, the inbox renders a small amber *"possibly addressed"* badge on the card and a *"Possibly
  already done — a recent commit references this idea"* note in the detail popup, so you can confirm and
  Approve to clear it. Renderer-only; verified via `tsc`.

## [0.1.50] -- 2026-07-09

### Added
- **Stale-idea reconciliation for the inbox.** `POST /api/v1/review/proposals/reconcile` scans recent
  commit messages and, for any **open** idea whose id is referenced in a commit, **flags** it as
  *possibly addressed* (`metadata.addressed_by` = the matching commit) — it never auto-resolves, so a
  richer idea is never silently removed; the human confirms and closes it. Fixes the case Justin raised:
  a bug fixed in passing that leaves its idea stale in the inbox. Core matcher + flagger are pure/
  isolated and unit-tested (`test_proposals_reconcile.py`); advertised to in-app AIs via
  `GET /api/v1/ai/context`.

## [0.1.49] -- 2026-07-09

### Added
- **Version-drift guard test.** `daemon/tests/test_version_consistency.py` fails if `package.json`,
  `pyproject.toml`, and `synapse_daemon.__version__` don't all match — the drift that bit 0.1.40 (a
  missed pyproject bump) can no longer land silently. Resolves inbox idea 11ac413441c8.

## [0.1.48] -- 2026-07-09

### Fixed
- **Corrected the stale `routes_coordination.py` module docstring** that claimed the coordination router
  was "mounted as a follow-up once the concurrent wave is committed" — it has been mounted in `app.py`
  for a while and the `/api/v1/coordination/*` endpoints are live. Resolves the inbox idea filed this
  session; demonstrates the v0.1.47 "close what you address" lifecycle (resolve-on-commit).

## [0.1.47] -- 2026-07-09

### Changed
- **Proposal-lifecycle rules baked into the AI Working Agreement (fixes stale ideas + adds
  plain-language impact).** When filing an improvement idea, every AI now must: (1) include a
  plain-language `metadata.impact` line (the inbox renders it as *"What this means for you"*); (2)
  **dedup-check** `GET /review/proposals?status=open` before filing so it doesn't duplicate an existing
  idea; and (3) **close what it addresses** — if its work resolves an existing open idea, resolve it
  (`POST /review/proposals/{id}/approve`, or reject if obsolete) with a note and reference the idea's id
  in the commit, so a bug fixed in passing no longer leaves a stale idea sitting in the inbox. The
  richer parts of an idea are never edited away for a partial fix — the rest is left for manual review.
  Applied to `AGENTS.md` and the prompt injected into every squad worker (`AI_WORKING_AGREEMENT_PROMPT`).

## [0.1.46] -- 2026-07-09

### Changed
- **The Review inbox's AI-filed ideas are now organized + clickable.** Improvement proposals are
  grouped under friendly categories (Bugs, Design & UX, Performance, Reliability, Docs, …) so a growing
  inbox stays tidy, and each idea is now a compact clickable row that opens a **detail popup** with a
  plain-language *"What this means for you"* summary (from a proposal's optional `metadata.impact`), the
  full why-and-how reasoning, effort, who filed it, and Approve / Reject / Promote actions. Builds on
  the v0.1.45 fix that first surfaced proposals in the UI. Renderer-only; verified via `tsc` + a live
  Vite HMR update into the running app.

## [0.1.45] -- 2026-07-09

### Fixed
- **AI-filed improvement ideas now actually show in the Review inbox.** The daemon's
  `GET /api/v1/review/inbox` has always returned AI-filed proposals in its `proposals` field (ADR-0025),
  but the renderer (`Review.tsx`) only rendered work-item handoff `items` and drove its "All caught up"
  empty-state off `count` (handoffs only) — so a filed idea was invisible in the UI. `Review.tsx` now
  renders a **"Improvement ideas from your AI workforce"** section with each proposal's rationale,
  source, effort, and **Approve / Reject / Promote** (approve + add to backlog) actions; the empty-state
  now accounts for proposals; and the live-refresh subscription also fires on `v1.review.proposal_filed`
  so a newly filed idea appears without a manual refresh. `review-client.ts` gains the `Proposal` type,
  the `proposals` field on `ReviewInbox`, and `approveProposal` / `rejectProposal` / `promoteProposal`.

## [0.1.44] -- 2026-07-09

### Fixed
- **`/profile/service-connections` is no longer ~1.5s on every poll.** Local CLI/service detection
  shells out (`where claude`, `where codex`, `gh auth status`, …) for four providers on every call.
  Those results are now cached per provider+host for 45s (`_LOCAL_DETECT_CACHE_TTL_SECONDS`); an
  explicit connect/verify (`use_cache=False`) still bypasses the cache for a fresh probe, so a
  just-installed CLI is picked up immediately. Implements the inbox proposal *"Cache local-CLI detection
  in the Profile service-connections endpoint"* filed this session. Regression test:
  `test_local_cli_detection_is_cached`.

## [0.1.43] -- 2026-07-09

### Added
- **AI Working Agreement — the cross-AI coordination + idea-filing habits are now baked in so every AI
  actually uses them, not just this session.** The coordination substrate (ADR-0024) and the
  improvement-proposals inbox (ADR-0025) already existed and were advertised via `GET /api/v1/ai/context`,
  but nothing told AIs to *use* them, so no sessions registered and the inbox stayed empty. Now:
  - `AGENTS.md` gains a canonical **"AI Working Agreement — every AI, every session"** section: at the
    start of any Synapse work (even from a terminal outside Synapse), every AI (Claude, Codex, Copilot,
    local, …) should (1) **check in** via `GET /api/v1/coordination/snapshot` + register a session +
    claim a file lane so agents don't collide, and (2) **file improvement ideas** it notices to the
    review inbox (`POST /api/v1/review/proposals`) instead of dropping them or rabbit-holing.
  - New thin entry files **`CLAUDE.md`** and **`.github/copilot-instructions.md`** point tool-specific
    AIs at that agreement (Synapse previously had neither), and `docs/MULTI-AI-WORKFLOW.md` links to it.
  - The same two habits are injected into **every squad/workbench worker's prompt**
    (`ai_context_memory.write_role_prompt`, new `AI_WORKING_AGREEMENT_PROMPT`) using the `$SYNAPSE_API`
    / `$SYNAPSE_TOKEN` / `$SYNAPSE_PROJECT_ID` env vars each worker already gets.
  - Six real improvement ideas discovered while fixing the 0.1.40–0.1.42 bugs were filed to the inbox
    (scoped `synapse-self`) to seed it. Regression test:
    `test_prompt_includes_working_agreement`.

## [0.1.42] -- 2026-07-09

### Fixed
- **`GET /profile` is now fast when the accounts server is offline (completes the 0.1.41 freeze fix).**
  `summary()` also probes the accounts server for available auth providers (`_available_auth_providers`
  -> `public_config`), and that probe deliberately did not cache *failures*, so every poll paid the full
  ~2s connect timeout even after the 0.1.41 breaker silenced the token refresh. That probe now honors the
  same circuit breaker: after one failure it serves the last-known providers for the cooldown window (an
  explicit, non-best-effort refresh still re-probes immediately, so a just-started accounts server is
  picked up). Measured: `/profile` drops from ~2s/call to ~7ms after the first call while offline.
  Regression test: `test_circuit_breaker_also_covers_public_config_probe`.

## [0.1.41] -- 2026-07-09

### Fixed
- **The app no longer freezes with every panel stuck on "Loading..." (async event-loop starvation).**
  When signed into a Synapse account whose remote accounts server (`127.0.0.1:8788`) is down or
  unreachable, every `GET /profile` and `GET /profile/service-connections` poll called that server with
  a **synchronous `urllib` request on the asyncio event loop** (`profile._refresh_from_remote` ->
  `SynapseAccountsClient._request`), blocking the loop for up to the 12s request timeout. That starved
  the daemon so it could not serve **any** request — health, projects, web-scraper, everything — which
  the renderer showed as an endless "Loading..." on every tab (confirmed via a py-spy dump of the hung
  daemon). Two-part fix: (1) a **circuit breaker** in `_refresh_from_remote` / `_sync_to_remote` — after
  one remote failure the daemon serves local state for a 60s cooldown instead of re-hitting a known-down
  server on every read; (2) the two hot GET profile routes now run the (possibly blocking) manager call
  via `asyncio.to_thread`, so a slow/down accounts server — or slow local-CLI detection — can never
  freeze the event loop. Synapse stays local-first and fully usable with the accounts server offline.
  Regression test: `test_remote_circuit_breaker_stops_hammering_a_down_accounts_server`.

## [0.1.40] -- 2026-07-08

### Fixed
- **`synapse.cmd` reliably launches even after a crashed or force-quit run (fixes "it crashes when
  starting / it said stopping a daemon").** A previous run that was force-quit or crashed leaves its
  Vite (5173) and/or daemon (7878) child orphaned and still squatting on the port. On the next launch
  Vite then fails with `Port 5173 is already in use` and exits; `scripts/dev.ps1`'s `finally` block
  stops the daemon and reports a non-zero exit — surfacing as "-> Stopping daemon" and looking like a
  crash even though the daemon started perfectly. `dev.ps1` now runs a best-effort pre-flight
  `Clear-StalePort` before starting the daemon and Vite, evicting a stale process **only** when its
  command line is clearly Synapse-owned (`synapse_daemon` / `vite`) — an unrelated process on the same
  port is left alone and warned about. This is the orchestrator-level twin of the daemon's own 7878
  self-eviction.
- **Stale-daemon eviction can never abort daemon startup.** `_evict_stale_daemon_on_port` is now fully
  guarded at the call site and around process termination, so any unexpected error while stopping a
  stale daemon is logged and the daemon proceeds to bind anyway.

## [0.1.39] -- 2026-07-08

### Fixed
- **Daemon reliably claims port 7878 on startup (fixes "the app is stuck loading everything" + dead
  WAN).** `python -m synapse_daemon` now evicts a *stale* Synapse daemon still listening on the bind
  port before starting uvicorn — a daemon that outlived its app (a crash, an orphaned tunnel, or a
  previous run that was never reaped) previously caused `WinError 10048`, a silent daemon exit, and a
  wedged desktop app / dead Cloudtap WAN. Only a process whose command line is a synapse daemon is
  evicted; anything else on the port is left alone. (Root cause of the stuck-app report.)
- **The web-scraper boot autorun can never abort daemon startup.** `reconcile_web_scraper_project`
  and the auto-launch step run inside the fatal `on_startup` handler, so they're now fully wrapped —
  a web-scraper hiccup degrades gracefully (logged) instead of taking the whole daemon down.

### Changed
- **First-party Web Scraper boot wiring is now real in the production daemon, not just the test harness.**
  The `python -m synapse_daemon` lifespan now runs the app's startup/shutdown hooks, so the
  first-party `web-scraper` MCP bootstrap + autorun path actually executes on a real Synapse boot.
- **Web Scraper first-party defaults now model the real split surfaces explicitly.**
  Synapse now keeps the MCP endpoint on `http://127.0.0.1:12000/mcp`, the companion UI/API app on
  `http://127.0.0.1:12345`, and the installed-page overview prefers `SCRAPER_URL` when present.

### Fixed
- **Fresh installs no longer half-wire the Web Scraper companion app.**
  If Synapse bootstraps the official checkout, the seeded `wbscrper` project now rehomes from stale
  placeholder paths to the actual active checkout before launch, so the first-party app and MCP stay
  aligned.
- **Known first-party Web Scraper configs are repaired on boot.**
  Existing `web-scraper` / `wbscrper` MCP rows are rehomed to the first-party HTTP launch config,
  corrected to the real MCP/UI port split, and re-enabled for autorun.
- **Desktop restart feedback is more honest and safer.**
  The Electron bridge no longer reports restart success before the restart path clears its first
  failure points, and a failed relaunch now recovers the window instead of hard-exiting the app.


### Added
- **Bug-hunt scoring: per-category breakdown.** `score_bug_hunt` / `POST /benchmarks/score-bug-hunt`
  (and the standalone `grade.py`) now return `by_category` (`{category: {found, total}}`) so a
  topology run shows *where* it's weak — e.g. finds all functional bugs but misses accessibility.
- **Squad capacity check.** `GET /agent-squads/{id}/capacity` reports headroom against the launch
  gates — `running`/`max_concurrent`, `tokens_spent`/`token_budget`, and a `can_launch` boolean — so
  an AI or the UI can check whether there's room before delegating another worker (0 = unlimited).
- **Promote a proposal to a backlog item.** `POST /review/proposals/{id}/promote` approves a
  project-scoped improvement proposal and turns it into an actionable item in that project's backlog
  — closing the "agents brainstorm → you approve → it becomes real work" loop. (Synapse-wide
  proposals with no project return 400.)
- **Project-free "New chat" (Plan 2 Phase A, migration `026`).** Coder threads can now live in a
  "General" scope with no project: `POST /coder-threads/general` creates one and
  `GET /coder-threads/general` lists them. `coder_threads.project_id` is now nullable
  (`ON DELETE SET NULL`), so deleting a project orphans its threads into General instead of cascading
  them away. Dispatching a General thread (and launching its review passes) now spawns the PTY in a
  dedicated `data/general-workspace` dir with no project, and its context read is null-safe. (The
  renderer "New chat" entry is the remaining follow-up.)
- **Migration runner: FK-safe table rebuilds.** A migration can opt into a `runner:foreign_keys=off`
  marker so a SQLite "12-step" table rebuild (DROP + RENAME to change a column constraint) runs with
  foreign keys disabled — otherwise dropping a parent table silently cascade-deletes its children.
  The runner toggles the pragma around the transaction and runs `foreign_key_check` before
  committing. This is what lets migration 026 run without destroying coder message/run history.
- **Delegated children can auto-launch (Plan 3 Phase 3).** `POST /agent-work-items/{id}/delegate`
  accepts `auto_launch: true` — the child launches immediately, bounded by the squad's concurrency
  cap + token budget; if a gate trips it's left QUEUED (with a `queued_reason`) instead of erroring
  the delegation. Closes the delegate dead-end where a supervisor could create a child it couldn't
  start. (The launch route body was refactored into a shared `_do_launch` helper — no behavior change
  to `POST /agent-work-items/{id}/launch`.)
- **Bug-hunt fixture discovery.** `GET /benchmarks/bug-hunt-fixtures` lists the shipped fixtures
  (`name` / `fixture` / `total_bugs`) so an AI can discover the valid `fixture` names before scoring.
- **`score-bug-hunt` accepts a fixture name.** `POST /benchmarks/score-bug-hunt` now takes an
  optional `fixture` (e.g. `"bug-hunt-fixture"`) instead of a pasted `answer_key` — the daemon loads
  the shipped `benchmarks/<fixture>/answer-key.json` (path-validated single segment; 404 if a build
  doesn't ship it, so callers fall back to inline `answer_key`). Much less for a squad synthesist to
  send when scoring itself against the standard fixture.

## [0.1.38] — 2026-07-07

### Added
- **ChatGPT Companion, rebuilt (AI Coding).** `ChatgptCompanion.tsx` is now a full companion
  workspace: project-file context (list / upload / download), a desktop live bridge that captures
  the visible ChatGPT reply, prompt/revise/save controls, and a reusable `ChatWorkspaceTemplate`
  shell. (Copilot.)
- **UX / onboarding polish pass.** New `HelpIcon` + `Tooltip` primitives thread "?" help tooltips
  and friendlier human-readable labels through AI Factory, Agent Squads, and AI Coding; `PageHeader`
  gained an optional `helpText`. (Copilot.)
- **AI Coding "Squads" tab + Apps "Memory" section.** AI Coding surfaces Agent Squads inline
  (`SessionsPage` in `squads` mode); the Apps hub gains a project-memory section. (Copilot.)
- **Bug-hunt scoring wired into the benchmark engine (Plan 3 Phase 2).** `benchmarks.score_bug_hunt()`
  — an in-daemon twin of the fixture grader — plus `POST /benchmarks/score-bug-hunt` (stateless: a
  squad synthesist posts findings + tokens + the answer key, gets `bugs_per_1k_tokens` /
  `false_positive_rate` / `recall` back). `BenchmarkScore` gains `bugs_found_true_positive`,
  `false_positive_rate`, `bugs_per_1k_tokens`. Added to `endpoints_for_ai` + `api-finds.md`.
- **Bug-hunt benchmark fixture (Plan 3 Phase 2).** `benchmarks/bug-hunt-fixture/` — a deliberately-
  buggy static site (`app/`) with 12 categorized bugs (functional, state, ui, perf, a11y, edge-case,
  security), a machine-checkable `answer-key.json`, and a zero-dep `grade.py` that scores a run's
  findings into `true_positives` / `false_positive_rate` / `bugs_per_1k_tokens`. This is the fixed
  fixture the topology benchmark (solo-baseline vs flat vs supervisor-tree) scores against to prove
  the "more bugs per 1k tokens with Synapse" claim honestly.
- **Proposals API completed.** `GET /review/proposals` (optional `?status=open|approved|rejected`)
  + `GET /review/proposals/{id}` — so a brainstormer can skip already-rejected ideas and the UI
  can show the full proposal history.
- **`brainstorm-improvements` quick-action.** Launch it at a project (or Synapse itself); an AI
  surveys the app + backlog + inbox and files ranked improvement ideas as proposals in your review
  inbox (propose-only, no changes) — completing the "agents brainstorm, you approve" loop.
- **Improvement proposals inbox (Plan 3 Phase 3f, migration `025`).** An AI (or a squad
  brainstormer) can `POST /review/proposals` to file an improvement idea — for an app or for
  Synapse itself — into the human review inbox instead of acting on it unilaterally.
  `GET /review/inbox` now surfaces open proposals alongside work-item handoffs; approve/reject
  via `/review/proposals/{id}/approve|reject`. The safe "agents brainstorm, you approve" path.
- **Frictionless token reporting on handoff (ADR-0025).** `POST /agent-work-items/{id}/handoff`
  now accepts optional `input_tokens` / `output_tokens` / `total_tokens` and records them to the
  token ledger — so a worker reports usage as part of the handoff it already does, instead of a
  separate call it forgets (`api-finds.md` GAP-05).
- **AI-first API discoverability.** `GET /api/v1/ai/context` → `endpoints_for_ai` now
  advertises the full AI menu: multi-AI coordination, per-worker token accounting,
  squad kill-switch/cap/budget, delegate, review verdicts, capture, the human review
  inbox, files/transcripts, quick-actions, personalities, MCP/models/assistant, search,
  and a pointer to `docs/api-finds.md`. Committed **`docs/api-finds.md`** (Copilot's
  complete AI-capability audit: every endpoint, WS event, env var, memory file + a
  gaps analysis + a session-start protocol).

### Changed
- **"Fast Money" tool → "Listing Multiplier".** The built-in launcher pivots from a generic
  client-ops SaaS starter to a listing-operations SaaS (`Listing Multiplier`): renamed constants,
  brief/config filenames (`APP_BRIEF.md` / `app.config.json`), spawn env vars (`SYNAPSE_STARTER_*`),
  and all scaffold + seed content (listings / drafts / publications / metrics). The internal bundle
  id `fast-money` is preserved for contract stability; marketplace/bundle/manifest labels updated. (Copilot.)
- **Finishing pass on the wave (Claude):** fixed the `HelpIcon` click-hijack (it now
  `stopPropagation()`s so a "?" inside a `<label>` no longer redirects focus to the field), and
  removed dead code the wave left behind (unused `EmptyState` component + unused `Tooltip` imports
  in `StatusBadge` / `SquadWizard`).
- **AGENTS.md Golden rule: "Build for the AI, not just the human."** Every new capability
  must ship a daemon REST endpoint, be advertised in `endpoints_for_ai`, and be documented
  in `docs/api-finds.md` — a feature an AI can't discover + drive via the API is not shippable.
  Mirrored in `docs/MULTI-AI-WORKFLOW.md`.

## [0.1.37] -- 2026-07-06

### Added
- **Experimental ChatGPT Companion inside AI Coding.** Added a new
  `ChatGPT` sub-tab with browser-managed sign-in guidance, an embedded
  desktop bridge, visible project/chat context capture, draft/revise
  controls, and save-back of exchanges or live workspace snapshots into
  normal project files.
- **First-party Web Scraper MCP bootstrap/install path.** The MCP
  catalog now ships a native `web-scraper` entry, marketplace install can
  clone the official GitHub repo into Synapse data, install its
  dependencies, register the HTTP MCP server, and mark it `enabled` +
  `autorun`.

### Changed
- **Synapse startup now repairs and auto-starts the canonical Web Scraper
  MCP entry** when it finds a trusted local checkout, so the owner's local
  tool comes up with Synapse without manual reconfiguration.
- **Release docs and screenshot gallery were refreshed** for the ChatGPT
  companion and the first-party Web Scraper install/autorun flow.

### Fixed
- **The WebSocket replay test no longer assumes startup event ids begin at
  `1`.** It now asserts against the seeded event ids directly, so new MCP
  startup broadcasts do not break the suite.
- **MCP server tests now cover the first-party Web Scraper HTTP shape and
  bootstrap path,** including catalog presence, install-time autorun, and
  canonical launch args.


## [0.1.36.21] -- 2026-07-06

### Added
- **Squad token budget (Plan 3 Phase 3, migration `024`).** A squad can set `token_budget`
  (0 = none); the work-item launch path refuses to start a new worker (409 "token budget
  exhausted") once the squad's recorded token spend reaches the budget, reusing the per-worker
  token roll-up (`sum_squad_tokens`). Pairs with the concurrency cap (023) to bound autonomous spend.

## [0.1.36.20] -- 2026-07-06

### Added
- **Squad concurrency cap (Plan 3 Phase 3, migration `023`).** A squad can set `max_concurrent`
  (0 = no cap, the default). The work-item launch path refuses to start a new worker (409
  "concurrency cap reached") once that many are already running, so an autonomous boss can't
  thrash a small machine. Relaunching an already-running item is exempt.

## [0.1.36.19] -- 2026-07-06

### Added
- **Per-work-item token accounting (Plan 3 Phase 2, migration `022`).** A squad worker can now
  report its own token usage (`POST /agent-work-items/{id}/tokens`) and Synapse rolls it up per
  squad grouped by role (`GET /agent-squads/{id}/token-usage`), reusing the benchmark engine's
  provenance/source vocabulary (`reported` / `runtime_self_report`). This is the load-bearing
  enabler for honestly proving "fewer tokens than a non-Synapse agent" -- PTY squad workers
  reported zero tokens before. New `token_ledger` module + `routes_token_ledger`.

## [0.1.36.18] -- 2026-07-06

### Added
- **Quality OS evidence honesty: `artifact_present` flag.** When a hunter records
  "browser-proof" evidence with an absolute screenshot path, the daemon now checks and
  records whether that file actually exists (`metadata.artifact_present`), so consumers
  (the UI, the benchmark) can trust the proof instead of accepting a dangling path.

## [0.1.36.17] -- 2026-07-06

### Fixed
- **Quality OS: repeated contract failures no longer churn duplicate gates.** `run_contract`
  used to resolve the open gate to FAILED and create a fresh one on every failing verdict, so
  several bug-hunters (or personas) hitting the same broken surface spawned N gates for one bug.
  Now an already-open blocking gate for a (contract, subject) keeps accumulating evidence and
  stays open until a PASS resolves it -- one bug, one gate. Regression test added.

## [0.1.36.16] -- 2026-07-06

### Added
- **Launchable `bug-hunt-squad` quick-action + ADR-0025 (Plan 3 Phase 1 complete for the MVP).**
  Point it at a running app URL: it assembles the QA & Bug-Hunt Squad, claims a coordination
  lane per surface (ADR-0024) so hunters don't overlap, launches browser hunters that drive the
  app via the Playwright MCP as distinct personas/viewports, and records findings as Quality OS
  evidence + auto-opened blocking gates. Modeled on `autonomous-boss` (a launchable prompt, not a
  daemon engine). ADR-0025 documents the feature + an honest maturity boundary: the per-worker
  token accounting, the topology benchmark, auto-spawn + budgets, and the live browser E2E are the
  next phases.

## [0.1.36.15] -- 2026-07-05

### Added
- **QA & Bug-Hunt Squad bundle (Plan 3 Phase 1).** An installable AI bundle shipping a
  token-efficient bug-finding team: **9 roles** — browser-driving `user-simulator`,
  `edge-case-hunter`, `state-corruptor`, `ux-critic`, `a11y-auditor` + coordination
  `qa-lead` / `triage-steward` / `bug-report-synthesist` / `token-steward` — and **12
  user personas** (impatient, mobile-thumb, rage-clicker, form-abuser, screen-reader-mimic,
  first-timer, power-user, …). Browser roles carry only the Playwright MCP; coordination
  roles carry none (dogfooding the v0.1.36.14 role->MCP binding). Findings are meant to land
  as Quality OS evidence + gates. Ships a `qa-bug-hunt-kickoff` quick-action.

## [0.1.36.14] -- 2026-07-05

### Added
- **Per-role MCP binding (Plan 3 Phase 1, migration `021`).** A squad role can now
  scope which MCP servers its workers receive via `agent_role_templates.mcp_server_ids`:
  `null` -> all enabled (backward-compatible), `[]` -> none (token-lean roles),
  `[ids]` -> only those (e.g. a browser-testing role gets just Playwright). The
  `--mcp-config` written at launch is keyed per role so different roles don't clobber.

### Fixed
- **Every Claude squad worker no longer receives every enabled MCP server** — that
  was a token cost + attack surface. Non-browser roles can run with no servers at all
  (and skip the `--mcp-config` flag entirely); browser roles get only what they need.

## [0.1.36.13] -- 2026-07-05

### Added
- **Synapse can now turn itself into a first-class improvement workspace.**
  Added a bundled `synapse-self` project seed, an `improve-synapse` quick-action
  that launches as a real coder thread, a guarded `GET /api/v1/ai/health-report`
  diagnostic surface, and the first safe `SYNAPSE_DEV_ENABLED=1` developer-loop
  endpoints: `POST /api/v1/synapse-dev/test/full` and
  `POST /api/v1/synapse-dev/test/file`.
- **Web Scraper graduated from a simple proxy page into a design-harvest
  workspace.** The dedicated page now captures authorized references, tracks
  provenance/adaptation mode, compares reference -> generated -> adopted output,
  and saves generated artifacts back into normal project files through new
  curated harvest routes under `/api/v1/installed-pages/web-scraper/*`.
- **Token-efficient review tooling landed in the coder workspace.** Added
  `ux`, `qa`, `token-efficiency`, and `judge` review presets, a new
  `quality-loop-v1` benchmark spec, and a bundled `Synapse UX Lab` AI bundle for
  self-improvement + harvest-driven review loops.
- **Quality OS foundation (migration `019_quality_os.sql`).** A durable UI surface
  map, UI contracts, blocking/waivable quality gates, and browser-proof evidence
  records (plus `verdict_json` on work items + review passes) so multiple AI
  runtimes share the same quality/evidence contracts (`quality_os.py`,
  `routes_quality_os.py`).
- **Native multi-AI coordination (ADR-0024, migration `020_coordination.sql`).**
  A daemon-owned presence registry (`agent_sessions`) + advisory file-lane claims
  (`file_lanes`) with automatic overlap detection, a git-working-tree collision
  detector, and disk-truth migration/ADR numbering — served at
  `/api/v1/coordination/*`, with an enforceable pre-commit gate
  (`scripts/coordination-preflight.ps1`). Turns the manual "read the markdown,
  notice the overlap, hold" dance between concurrent AI coders into an API call
  plus a commit check. Cockpit panel + shared Plan to follow.

## [0.1.36.12] -- 2026-07-04

### Added
- **Benchmark re-score: the reviewer pass wins every category.** Re-scored the
  two dimensions the original single-pass with-Synapse build lost, head-to-head
  vs the baseline (same judge scored both apps, live-tested in a browser):
  **backend-correctness 100 vs 88** (was 78) and **adversarial bug-hunt 98 vs 70**
  (was 42) — both flipped to wins. Combined with the four dimensions Synapse
  already won, the reviewed app now leads **all six** (avg 86.0 vs 64.8) at
  build+review tokens still under the 51,314-token baseline.
  `benchmarks/makeup-business-demo/results/quality/reviewed-rescore.md`, with the
  summary + README benchmark section updated to show the reviewer-pass result
  (the single-pass table is kept for transparency).

## [0.1.36.11] -- 2026-07-04

### Added
- **Benchmark reviewer pass** (`benchmarks/makeup-business-demo/apps/with-synapse-reviewed/`):
  a minimal review-and-fix pass on the with-Synapse Glow Studio app that
  corrects the two documented bugs which lost the original benchmark's
  backend-correctness + bug-hunt dimensions — (1) contact form falsely
  reporting success on empty submits (removed `novalidate`, added a
  `checkValidity()` guard + form reset), (2) mobile nav overlapping/blocking the
  hamburger at ≤768px (added `visibility:hidden` + `pointer-events:none` to the
  closed state). **Both fixes empirically verified in a real browser** (Playwright
  @375px): closed nav no longer intercepts the hamburger, and an empty submit no
  longer shows the false success. See `raw-logs/with-synapse-reviewed-run.md`.

### Notes
- The full 6-dimension re-score (to show the reviewed app leads all 6 at total
  tokens under the 51k baseline) is **pending — the reviewer sub-agent hit the
  account usage limit (resets 2pm ET)**. Committed complete per commit-before-limit;
  re-score resumes after reset.

## [0.1.36.10] -- 2026-07-04

### Fixed
- **Windows squad-launch bug: multi-arg `.cmd`/`.bat` runtimes now forward their
  arguments (`daemon/synapse_daemon/pty_sessions.py`).** A PTY spawn like
  `claude.CMD --mcp-config <path>` dropped its args under winpty (cmd.exe
  reported the 2nd token as "not recognized"), so **every squad-launched
  `claude` worker silently failed whenever an MCP server was enabled** — the
  process exited but the work item stayed "running." Fix: generalize the proven
  Copilot PowerShell-`&` wrapper (`_spawn_argv_for_runtime` via a new
  `_powershell_wrap` helper) to `.cmd`/`.bat` shims with arguments, so the shim
  forwards args via `%*`. Only `spawn_argv` is wrapped — the UI/transcript still
  show the real `claude.CMD` argv. Scoped to the broken multi-arg case
  (single-arg `.cmd` stays on its proven raw-winpty path, locked by a test); if
  `powershell.exe` is missing it now **fails loudly** instead of silently
  hanging. `cmd.exe /c` and backend-level fixes were rejected (quoting-safety /
  layering).

### Notes
- Reviewed pre-work by a 4-member AI council (Architect / Skeptic / Tester /
  Security). The Skeptic (REVISE) caught that the wrapper was only proven for
  space-free args — so the fix is now proven with a **hostile-path integration
  test** (a real `.cmd` echoing `%*` with a `--mcp-config` path containing a
  space and parens, `a b (x86)`) plus a **live repro**: `claude.CMD --version`
  now prints `2.1.185 (Claude Code)` where it previously errored. 6 new tests.
- Versioning: this session is solo (no concurrent agent), so per the
  `docs/MULTI-AI-WORKFLOW.md` version policy the multi-agent `-dev` collision
  risk doesn't apply; kept a clean monotonic `0.1.36.N` sequence.

## [0.1.36.9] -- 2026-07-04

### Added
- **AI Council Review — first-class workflow + discipline (ADR-0023).** A primary
  AI no longer works alone: a **pre-work council** critiques its plan and a
  **post-work council** hunts bugs/gaps before it claims done, with an **adaptive
  2–10 reviewer** panel (by task size), prioritized critical/important/optional
  findings, and synthesis (not blind-follow). Shipped as:
  - `templates/quick-actions/ai-council-review.json` — a launchable quick-action
    (Plan → Council → Build → Council → Verify). Runs reviewers as prompt passes
    by default; **does not spawn reviewer squad-workers on Windows** until the
    Phase 2 multi-arg `.CMD` squad-launch bug is fixed.
  - `docs/adr/0023-ai-council-review.md` (accepted) + index entry.
  - a canonical-pattern section in `docs/MULTI-AI-WORKFLOW.md` and a pointer rule
    in `AGENTS.md` (Golden rule).
  - a `docs/roadmap.json` item (status `in_progress`).
- Honest scope: v1 is a launchable prompt + discipline, **not** a daemon council
  engine (deferred; see ADR-0023 follow-ups). Dogfood proof: real councils this
  session caught a decision-audit recall gap (~66% miss) and a commit about to
  violate the version-bump rule.

## [0.1.36.8] -- 2026-07-04

### Added
- **`docs/screenshots/` — a real UI screenshot gallery** (Home desktop + mobile,
  the AI Coding cockpit), captured from the running renderer via Playwright, with
  a README that evolves as the UI does. Linked from the top of `README.md`.
- **`AGENTS.md` docs-sync rule:** a change that alters a user-visible surface must
  refresh the affected `docs/screenshots/` image(s) in the same commit.

### Notes
- **Live E2E state verified (2026-07-04):** launched against the running stack
  (daemon `:7878` + Vite `:5173`); Home + AI Coding render with 0 console errors
  (only a benign token-less-browser WS warning). **Finding:** the AI Coding
  cockpit works but is **project-scoped only** — no project-free "New chat"
  (you must pick a registered project before starting a thread). This confirms
  the flagged cockpit gap (project-free New chat) and feeds that upcoming work.

## [0.1.36.7] -- 2026-07-04

### Added
- **`AGENTS.md` — commit-before-limit rule** (Golden rule): when usage/tokens run
  low for *any* AI coder, the last action must be to bring the current unit to a
  working state and commit + push it (still running the standard fast
  version-bump + one-line CHANGELOG/PROGRESS ceremony) — never leave the app
  half-done because credits ran out.
- **`AGENTS.md` — commit rule #11:** commit AND push after every logical change,
  green-then-push (typecheck + pytest, plus E2E per Rule #6 for code bumps),
  don't batch unrelated changes; push-vs-concurrency defers to
  `docs/MULTI-AI-WORKFLOW.md`.

### Changed
- `.gitignore`: ignore `daemon/auth-token` (a per-launch runtime token file that
  was noise in every `git status`).

### Notes
- Also recorded (in `PROGRESS.md`, prior commit) a 2026-07-04 **decision-coverage
  audit** confirming the origin build session left no decisions uncaptured in the
  durable docs. That audit note was committed without a version bump, which is
  out of step with commit-rule #1; this `0.1.36.7` bump restores the
  version/CHANGELOG lock-step going forward.

## [0.1.36.6] -- 2026-07-03

### Added
- **`README.md`**: expanded the "Build AI teams" bullet with a concrete worked
  example (same `reviewer` role run twice with different personalities --
  Skeptic vs. Pragmatist -- to show deliberate disagreement in action), and
  added a new **autonomous "AI boss"** bullet (ADR-0013) explaining how it
  writes durable ADRs and `.synapse-ai-context.md` updates as it works, so the
  *next* run starts smarter -- Synapse improving its own working knowledge,
  not just shipping one app.

## [0.1.36.5] -- 2026-07-03

### Added
- **`README.md` rewritten, extensively.** Now leads with "built for AI, not
  just for a human" framing (`GET /api/v1/ai/context`, versioned REST/WS as
  the primary interface), a non-technical explainer aimed at a
  non-developer reader, a drift/memory comparison table, a "build a
  business with Synapse" section (Fast Money, e-commerce/resale use
  cases), an extensive Web Scraper MCP usage section with concrete tool
  examples grouped by use case, a "how any AI can connect to Synapse"
  section (simple + developer terms), and a real benchmark section.
- **`benchmarks/makeup-business-demo/`** -- a real, reproducible benchmark:
  the same small business site spec ("Glow Studio") built once through a
  real Synapse project + Claude Code session, once by a single memory-less
  AI session with no Synapse involvement. Nested folders: `apps/` (both
  full source trees), `results/tokens/`, `results/quality/` (one file per
  scored dimension -- UI/UX, visual design, code quality, backend
  correctness, usability/accessibility, adversarial bug hunt -- plus a
  `summary.md`), `screenshots/` (desktop + mobile, both apps), and
  `raw-logs/` (chronological real timestamps for both runs). See
  `benchmarks/makeup-business-demo/methodology.md`.
- **`AGENTS.md`**: added a `benchmarks/` doc-sync trigger to the commit
  rules, and an explicit note that the doc-sync obligation applies to
  every AI coder touching this repo, not only Claude.
- **Fast Money launcher + AI bundle.** Synapse now ships a built-in
  `fast-money` tool, a bundled Marketplace entry, and a paired AI bundle
  that installs client-ops revenue roles, an operator-style personality, a
  client-ops recipe, monetization/source notes, and the `fast-money-launch`
  quick action. Launching the tool creates or reuses the target project
  (default `data/projects/fast-money-client-ops`), writes
  `FAST_MONEY_BRIEF.md` + `PROMPT.md`, scaffolds a runnable private/local-first
  client-ops SaaS proof app (landing page, pricing page, auth shell, customer
  portal, operator console, optional catalog editor, billing/auth seams,
  README, architecture note, monetization note, seed/demo data), and opens a
  PTY session in that project using runtime precedence `codex -> claude ->
  copilot`.
- **AI personalities — a worker = role + personality (ADR-0018 MW3).** New
  `personalities` table (migration 015) + CRUD + REST at `/personalities`, with
  five seeded built-ins (Pragmatist, Perfectionist, Skeptic, Visionary,
  Mediator). A roster work-item can carry a `personality_id`; the synthesized
  worker prompt now layers a `## Personality` section after the role guidance, so
  two same-role workers differ in voice and can collaborate/debate. Built-ins are
  editable but protected from deletion. The Marketplace **Workers** section shows
  the personality + role galleries (create/remove custom personalities), and the
  **squad builder** now picks a personality per role — add the same role twice
  with different personalities and the AIs collaborate/debate.
- **AI Factory + AI Operating System foundation (ADR-0020).** Synapse now ships
  a native **AI Factory** page plus a separate **AI Operating System** app shell.
  Daemon-side this adds structured AI cases (`intent`, `targets`, `directives`,
  `policies`), mission profiles, richer case modes (`research`, `generate`,
  `hybrid`, `audit`, `repair`, `migrate`, `replicate`, `benchmark`, `harvest`,
  `portfolio`, `challenge`), case lineage/graph fields, case-owned job rows, new
  export kinds, AI Factory catalog tables/endpoints, and an isolated worktree
  launch path for case-owned workers. Renderer-side this adds the `AI Factory`
  nav page, catalog browsing, case creation/run controls, and project-tile
  `Open in AI OS` launchers. Packaging now bundles the `ai_os/` app resources.
- **AI Bundles + installer bootstrap (ADR-0021).** Marketplace now exposes an
  **AI Bundles** pillar for AI-first packs of roles, personalities, quick
  actions, recipes, and sources. The daemon now ships bundle install tracking
  (`ai_bundle_installs`, `ai_bundle_assets`, migration 017), `GET /api/v1/ai-bundles`
  plus install/uninstall routes, bundle-aware profile catalog state, and
  bundle-owned quick-action loading. The Windows installer now accepts optional
  bundle choices up front and writes a bootstrap selection file that Electron
  consumes on first launch.
- **First mode-specialization pass for the advanced case engine.** Running
  `benchmark`, `portfolio`, `challenge`, `harvest`, `repair`, `migrate`, and
  `audit` cases now seeds mode-specific artifacts instead of falling back to the
  same generic loop: benchmark candidates spawn child generate cases, portfolio
  sweeps spawn ordered repo slices, challenge runs force a minority-path child
  case, harvest runs promote reference URLs into reusable sources, and the
  squad builder now resolves bundle-installed roles/personalities when present.

### Fixed
- **CLI doctor now degrades cleanly on raw socket timeouts.** A half-open or
  slow responder on `127.0.0.1:7878` no longer crashes `synapse doctor` with a
  bare `TimeoutError`; the CLI now reports the same friendly "could not reach
  daemon" failure shape it already used for normal connection errors.
- **Consistent Synapse icon everywhere.** The window/taskbar + tray now use the
  crisp multi-resolution `synapse.ico` (was a 936-byte low-res PNG), and the
  in-app brand mark (sidebar), boot splash, and `icon.svg` favicon were realigned
  to the same disc-with-ring-and-nodes design as the app/taskbar icon (they had
  drifted to an unrelated hub-glyph and an "S"). `electron/icons/` is now bundled
  as an extra resource so the packaged window/tray icon resolves too. The sidebar
  + mobile-topbar marks now sit on a subtle elevated badge (rim + shadow) so the
  dark disc stands out on the dark rail instead of blending in.
- **AI Factory case state no longer goes stale after external case updates.**
  The page now listens to `v1.ai_case.*` events, refreshes its run list when the
  daemon changes a case, and exposes an explicit `Stop selected case` control so
  run/stop state stays honest without a manual reload.

### Changed
- **Generic tool cards now render boolean fields as real toggles.** Manifest
  booleans no longer fall back to plain text inputs, which keeps bundled tools
  like Fast Money honest in the Tools page.
- **Bundled AI bundle prompts are tighter and less repetitive.** The fallback
  Marketplace bundle catalog (`docs/ai-bundles-sample.json`) was
  pressure-tested against live AI-case installs and then trimmed so the
  role/personality guidance no longer repeats labels the worker prompt already
  provides. Quick-action prompts were also shortened to keep the quality bar
  intact while cutting low-signal prompt overhead for research, generation,
  rescue, and harvest/bakeoff runs.

### Notes
- **Real bug found while dogfooding Agent Squads on Windows**: any PTY spawn
  with a multi-element `argv` for a `.CMD`-shimmed runtime (e.g.
  `claude.CMD --mcp-config <path>`) fails silently -- the child never
  receives its arguments and `cmd.exe` reports the second argv element as
  "not recognized." Practical impact: on a machine with any MCP server
  enabled, every squad-launched `claude` work item currently fails this way
  (`routes_agent_squads.py`, `launch_work_item` always appends
  `--mcp-config` in that case). Root cause not yet fixed -- see
  `benchmarks/makeup-business-demo/methodology.md` for the full repro and
  the filed follow-up task. The benchmark itself worked around it via the
  single-arg workbench launcher.

## [0.1.36-dev] -- 2026-06-22

Profile completion + Agent Squads usability/power + daemon resilience
(authored by Claude on top of the Codex wave). Gates green: renderer +
electron tsc clean, 420 daemon tests pass / 11 skipped. Daemon changes
re-verified live against an isolated daemon.

### Added
- **Autonomous AI boss (ADR-0013)**: a launchable `autonomous-boss` quick-action.
  Give it a goal and the AI boss drives Synapse's own REST API to orient
  (`/ai/context`), pick or **create** a project, post a visible plan as a squad
  (lead=`boss`), staff + launch the workers it chooses across the
  boss/supervisor/worker hierarchy, **leverage existing tools/quick-actions**
  (installing from the marketplace rather than reinventing), and **record +
  learn** via project ADRs / backlog / `.synapse-ai-context.md`. Full autonomy,
  human-initiated, bounded by the squad **kill switch** (ADR-0010). No new
  daemon subsystem -- composes ADR-0010/0011/0012 primitives.
- **claude.ai connector / MCP server (ADR-0012)**: Synapse now answers MCP over
  a hand-rolled, stateless Streamable-HTTP endpoint at `/mcp/{token}` so it can
  be added to claude.ai (or Claude Desktop) as a *custom connector*. Read-only
  by default (tools: `synapse_get_context`, `synapse_list_projects`,
  `synapse_get_project_records`, `synapse_list_tools`,
  `synapse_list_quick_actions`, `synapse_list_agent_squads`); the path `{token}`
  must equal the daemon's local token (the secret in the URL). Expose it by
  opening Cloudtap on 7878 and pasting `https://<tunnel>/mcp/<token>`. Writes
  (e.g. `synapse_add_project_idea`) are gated behind `SYNAPSE_MCP_ALLOW_WRITES=1`.
  No new dependency; `daemon/synapse_daemon/mcp_connector.py` + 11 tests.
- **Remote WAN recovery helper**: `scripts/remote-recovery.ps1` starts or
  reuses the daemon, optionally installs `cloudflared` through winget, opens
  Cloudtap on port `7878`, waits for the WAN `/mobile` URL, and prints a fresh
  pairing code for Codex/local automation rescue sessions. Packaged builds now
  include it under `resources/scripts/remote-recovery.ps1`.
- **Per-project decision records (ADR-0011)**: every managed project now
  carries its own **ADRs**, **backlog**, and **version history**. ADRs have a
  quick-idea -> promote-to-numbered lifecycle (a one-field "Idea" capture, then
  "Promote" assigns the next per-project ADR number). Daemon: migration
  `012_project_records.sql`, `project_records.py` (models + CRUD),
  `routes_project_records.py` (REST CRUD + `/promote` + a `/records` bundle),
  10 tests. UI: a tabbed Decisions/Backlog/History section in
  `ProjectDetailModal.tsx` (`ProjectRecordsSection.tsx` +
  `project-records-client.ts`). AI-callable -- the endpoints are listed in
  `GET /api/v1/ai/context` so a worker can capture an idea or record a
  decision as it works. Verified live (add idea -> promote -> ADR-001).
- **Team Builder wizard** (`renderer/components/SquadWizard.tsx`): a guided
  goal -> preset team -> roster -> review flow. "Build a team" is the primary
  CTA on Agent Squads; the raw create forms moved behind an Advanced
  disclosure so the page no longer overwhelms first-time users.
- **Role hierarchy + roster**: `role_tier` (`boss` / `supervisor` / `worker`)
  via migration `011_squad_hierarchy.sql`; seeded roles expanded 4 -> 11
  (boss, planner, supervisor, implementer, reviewer, researcher, tester,
  designer, docs-writer, devops, security).
- **Squad kill switch**: `POST /api/v1/agent-squads/{id}/stop` closes a
  squad's live PTY sessions and finalizes its work items; "Stop all" button in
  the cockpit. Substrate for the future autonomous boss.
- **Profile reachability**: `ProfileSummary.account_backend_reachable`. The
  Profile hub now shows an honest "sync is optional / not configured" panel
  when no Synapse Accounts service is reachable, instead of sign-in forms that
  always error. Local-first Profile features are unaffected.

### Fixed
- Daemon no longer crashes when a work item launches with a missing/invalid
  working directory -- the cwd is validated before the native PTY backend
  (winpty/ConPTY) is invoked, so a bad cwd returns a clean 422 and the daemon
  stays up.
- "Stop all" reliably finalizes work items (they were left `running` because
  finalization depended on async event delivery).
- Agent Squads overview uses `Promise.allSettled` so one failing fetch no
  longer zeroes the whole HUD (the misleading 0 projects / 0 roles / 0 squads).
- `test_pick_runtime` is machine-independent (mocks `resolve_command`, not
  `shutil.which`, which broke on machines with the Codex VS Code extension).
- **White dropdown in dark mode**: native `<select>` popups rendered with the
  OS light theme because body-level `color-scheme: dark` did not reach
  Electron's OS-painted `<option>` popups. `renderer/styles.css` now sets
  `color-scheme` directly on `select` / `input` / `textarea` (light theme
  overrides), fixing every dropdown app-wide.

### Changed
- **Agent Squads is no longer overwhelming.** The cockpit (8 cards / 4 forms)
  is gated on a selected squad -- the empty state is just the hero +
  "Build a team" + squad picker. Delegate/Handoff forms appear only after a
  work item is selected; the "New work item" form is collapsed behind an
  "Add work item" disclosure; the three status buttons became one "Set status"
  control; the Direct/Squads mode toggle is a larger, labeled tablist; and the
  Direct-mode roadmap card is gated behind Help. Verified over a Cloudtap WAN
  tunnel (phone pairing, not LAN).

## [0.1.36-dev] -- 2026-06-20..21

Phone-parity + multi-AI workflow wave (authored primarily by the Codex
AI coder, verified + committed by Claude). All gates green: renderer +
electron tsc clean, 406 daemon tests pass.

### Remote access + phone parity
- `GET /api/v1/remote-access` aggregate: computer name, network bind,
  pairing code, paired devices, and live Cloudtap WAN verification
  (health + mobile probes; failure codes `cloudtap.wrong_port` /
  `.no_public_url` / `.unavailable`).
- `/mobile` now serves the full React shell with paired-device
  in-browser auth, stale-token recovery, and a 2-row touch nav grid
  for 390px phones. Same session carries LAN -> Cloudtap WAN via
  durable paired-device identity + short-lived handoff claims
  (migration `007_pairing_claims.sql`).
- Settings `Phone Access` hub merges LAN, pairing, reconnect, WAN
  verification, and diagnostics.
- WS hub resume-timeout widened to stop false `1008` closes over
  Cloudflare; desktop auth self-heals (REST retries after refreshing
  `/auth/local-token`; WS retries after a 1008 close).
- Windows-only asyncio accept-reset workaround for transient WinError
  64 socket drops on port 7878.

### Agent Squads (Sessions)
- Durable role templates (planner / implementer / reviewer /
  researcher), squad + work-item tables (migration
  `008_agent_squads.sql`), handoff capture appended to
  `.synapse-ai-context.md`, PTY launches tagged with
  `SYNAPSE_SQUAD_ID` / `SYNAPSE_WORK_ITEM_ID` / `SYNAPSE_ROLE_PROMPT_FILE`,
  three-pane Sessions cockpit.

### Profile hub
- `/api/v1/profile*` + migration `009_profile_state.sql`: local-first
  profile, optional Supabase sign-in (email/password, Google, GitHub),
  connected-service readiness, synced catalog favorites/history/host
  inventory, viewport-safe Discover category rail.

### Packaging bootstrap
- `installer/build-daemon.ps1` -> `synapse-daemon.exe`; Electron spawns
  the bundled daemon; daemon resolves bundled tools/templates/docs/
  mobile from packaged resources (`runtime_paths.py`).

### Tooling / infra
- `tools_dir` now resolves to the repo's bundled `tools/` when launched
  from any cwd (fixes "Cloudtap isn't loaded" when Electron spawns the
  daemon from `electron/`). Applied in both `__main__.py` and
  `build_app()`.
- ADR-0009 drafted: professional launcher splash + error-code catalogue.

## [0.1.36-dev] -- 2026-06-18..19

A two-day UX wave responding to a long generative user wishlist.
Phase A polish ships in this release; Phases B / C / D each get
their own ADR + gate.

### Phase A — UX polish (no ADR)

- **A1**: Sessions AI Quick-actions rail becomes a collapsible
  disclosure. Chevron rotates; click anywhere on the header toggles;
  starts collapsed by default; state in localStorage
  (`synapse.sessions.qa-collapsed`).
- **A2**: GitHub Copilot CLI joins Claude + Codex as a quick-launch.
  Install recipe + marketplace entry (declarative tier, pty.spawn).
  Bundled marketplace: 10 -> 11.
- **A3**: `idle` and `stopped` collapse to "not running" in UI labels +
  the Home HUD. Contract #2's six-status enum is unchanged on the
  daemon side; audit log still records both.
- **A4**: Settings clarifies that port 7878 is the only port users
  need; 5173 is the Vite dev server, only present during
  `npm run dev`. Renamed "Base URL" -> "Daemon URL".
- **A5**: Apps tiles show a "size on disk" badge driven by the new
  `GET /api/v1/projects/{id}/disk-usage` route (60s cache). Walk
  caps at 100k files. Apps subtitle clarifies projects vs Tools.
- **A6**: Editable sidebar -- drag-to-reorder + per-item hide/show.
  Home + Settings are locked. Layout persists in
  `localStorage('synapse.sidebar.layout')`. New gear icon at the
  bottom opens the customize modal.
- **A7**: Phase B preview Card on Sessions signals project
  objectives + cross-AI continuity (ADR-0006 forthcoming).

### UX wishlist follow-ups

- **Dark native dropdowns**: `body { color-scheme: dark }` makes
  Windows + macOS render `<option>` panels, scrollbars, and date
  pickers in the dark variant.
- **Project + Tool detail modals**: clicking anywhere on a project
  tile opens a `ProjectDetailModal` (3-col meta grid, AI-lens
  callout, raw JSON disclosure). Click the info icon on a tool tile
  to open `ToolDetailModal` (per-action primitive hints).
- **WAN exposure via Cloudtap**: new "Expose to WAN via Cloudtap"
  button on the Network panel. Active/Inactive status badge; copy
  / refresh / close buttons on the live tunnel. Security note about
  the device token still gating access.
- **Color themes**: `theme-hacker` (near-black + neon green) and
  `theme-surfer` (deep navy + bright sky blue) join Dark / Light /
  System. ThemePanel becomes a 2-column swatch grid driven by
  `THEME_OPTIONS`.
- **PairedDevices**: "Allow LAN access" copy is now a real button
  that scrolls + flashes the Network panel toggle so users can find
  it.
- **Phone parity + WAN handoff**: `/mobile` now serves the full React
  shell instead of the old standalone page when `dist/` is present.
  Paired-device auth works inside the browser, stale mobile tokens
  bounce back to the pair screen, `ToolCard` exposes **Use on this
  phone** for the daemon tunnel on port `7878`, and the phone shell
  now exposes Home / Apps / Tools / Sessions / Processes / Settings
  with dedicated mobile chrome. Verified on both LAN and
  `*.trycloudflare.com` with a real PTY launch from the WAN Sessions
  page.
- **Phone dock + launcher hardening**: the mobile bottom nav is now a
  2-row touch grid so all six core tabs stay visible on narrow
  screens, `synapse.cmd` / `scripts/dev.ps1` clear
  `ELECTRON_RUN_AS_NODE` before `npx electron .`, and Electron's
  daemon-log forwarding now ignores broken stdout/stderr pipes instead
  of throwing `EPIPE` in the main process.
- **Windows LAN/WAN stability**: the daemon installs a Windows-only
  asyncio Proactor accept-reset workaround so transient WinError 64
  socket drops no longer kill fresh accepts on port `7878`. Verified
  live by re-opening LAN and Cloudtap WAN sessions after mobile PTY
  traffic and by connecting directly to `wss://.../api/v1/ws` with a
  paired-device token.
- **Desktop auth recovery**: if the desktop app's local daemon token
  drifts after a restart / attach, renderer REST calls now retry once
  after refreshing `/auth/local-token`, the desktop WS client retries
  after a `1008` auth close, the Tools page clears stale 401 banners
  on a later success, and Electron main-process daemon requests
  bootstrap the token from the attached daemon instead of reading
  `data/auth-token` directly.
- **Dev restart ownership fixed**: `synapse.cmd` now delegates to
  `scripts/dev.ps1`, the wrapper owns only Synapse's own daemon/Vite/
  Electron children, and in-app restart exits Electron with a dedicated
  wrapper restart code so the full stack gets recycled instead of only
  relaunching Electron.
- **Wrapper child-process hardening**: the wrapper now launches Vite
  through `node node_modules/vite/bin/vite.js` and Electron through
  `node node_modules/electron/cli.js`, which keeps process ownership
  tied to the real long-lived children instead of short-lived launch
  stubs.
- **Packaged daemon bootstrap**: `installer/build-daemon.ps1` now
  produces `installer/daemon-dist/synapse-daemon.exe`; Electron knows
  how to spawn that bundled daemon in packaged mode; and the daemon now
  resolves bundled tools, templates, docs, and mobile assets from
  packaged resources instead of source-tree-only paths.
- **Version-surface cleanup**: `package.json` now reports `0.1.36-dev`,
  Python packaging uses `0.1.36.dev0`, and the renderer normalizes the
  PEP 440 daemon version back to the friendly `-dev` label in the UI
  instead of falling back to a stale hardcoded `0.1.8`.
- **TypeScript config cleanup**: removed the deprecated top-level
  `baseUrl` usage from `tsconfig.json` and moved Electron to
  `moduleResolution: "Node16"` / `module: "Node16"`.

### Marketplace

15 bundled tools (was 11). Added: open-vscode-insiders, open-cursor,
open-zed, pip-install-dev. `must_include` set in
`test_routes_marketplace.py` updated.

### Tray + IPC (carried from v0.1.35)

- New tray entries: "Restart Synapse" and "Exit Synapse".
  `synapse:restart` + `synapse:exit` IPC channels.
- Settings → Network → "Restart now" button when running in
  Electron (feature-detected via the preload bridge).

### Daemon

- `GET /api/v1/projects/{id}/disk-usage` (A5).
- Status enum unchanged; UI merge only.

### ADRs drafted (implementation gated on user "go")

- **ADR-0006** -- Project objectives table (migration 007) +
  per-project `.synapse-ai-context.md` NOTES file for cross-AI
  continuity + Saved tasks rail on Sessions. Four sub-phases.
- **ADR-0007** -- AI-improves-Synapse REST endpoints (`/api/v1/
  synapse-dev/test/full`, `/commit`, `/pr`) + `/api/v1/ai/health-
  report`. Token-guarded + env-gated + audited.
- **ADR-0008** -- Tools marketplace reorg (categories +
  filters) + Quick-actions catalogue under Tools + sidebar item
  promotion (`promoted` array in workspace layout).

### Tests

- 376 -> 396 passed (+20 since the original v0.1.36-dev wave).
- Verified `npm run build`, `npm run build:daemon`, and a live wrapper
  restart triggered from the real Electron app via
  `window.synapse.restart()`.

## [0.1.34] -- 2026-06-16

### ADR-0003 Phase F -- AI quick-action templates

A "Quick-actions" rail on the Sessions page. One click opens a workbench
PTY in the auto-created **scratch** project with a templated prompt
pre-loaded so the Claude / Codex session sees it on prompt 1. The button
ships the shortcut; the AI does the work.

#### Added -- daemon
- `quick_actions.py` -- template loader. Reads
  `templates/quick-actions/*.json`; validates kebab-case ids; sorts by
  name; first-id wins on duplicates; one bad file never takes the list
  down.
- `routes_quick_actions.py` -- `GET /api/v1/quick-actions` lists curated
  templates; `POST /api/v1/quick-actions/{id}/launch` lazy-creates the
  `scratch` project (kind='other'), writes `PROMPT.md` + `PROMPT-<id>.md`
  into its cwd, spawns a workbench PTY with
  `SYNAPSE_QUICK_ACTION_{ID,PROMPT,PROMPT_FILE}` injected. Audited as
  `quick_action.launch`.
- `templates/quick-actions/new-mcp-server.json`,
  `templates/quick-actions/new-synapse-tool.json` -- shipped defaults.

#### Added -- renderer
- `lib/quick-actions-client.ts` -- `listQuickActions()` +
  `launchQuickAction()`.
- `pages/Sessions.tsx` -- "AI Quick-actions" row under the existing
  quick-launch buttons. Each tile shows the template name + 2-line
  description; clicking spawns the workbench session and opens it as
  a tab. Single in-flight guard.

#### Tests
- `test_quick_actions.py` (10 tests): parser, kebab-case, malformed
  files, duplicate ids, bundled defaults load cleanly.
- `test_routes_quick_actions.py` (6 tests): list, auth, launch with
  monkey-patched spawn so it runs on Windows, unknown-action 404,
  missing-binary 422, scratch project reused across calls.
- Full suite: 368 passed, 9 skipped.

## [0.1.33] -- 2026-06-15

### ADR-0003 Phase E -- ChatGPT export.zip import

Drop the user's ChatGPT *Settings → Data Controls → Export Data* zip into
Synapse; every conversation lands as a Markdown file under the
auto-created **imported-chatgpt** project. One-shot ingest -- no
scraping, no live ChatGPT API, no third-party network (Contract #15).

#### Added -- daemon
- `chatgpt_import.py` -- parses `conversations.json`, walks each
  conversation's mapping tree from root to `current_node` so forked
  retries render the branch the user kept. Deterministic Markdown so
  re-imports dedup by sha256.
- `routes_imports.py` -- `POST /api/v1/imports/chatgpt` multipart upload.
  Lazy-creates the `imported-chatgpt` project on first call. Each
  conversation lands as `<date>_<slug>.md` tagged
  `source='chatgpt-import'`. Duplicate-of reconciliation under
  transaction. Audited as `chatgpt.import`.

#### Added -- renderer
- `lib/imports-client.ts` -- multipart `importChatgpt(file)` returning
  the daemon's `imported / duplicates / skipped_empty / project_id`
  summary.
- `pages/Apps.tsx` -- "Import ChatGPT export" header button + hidden
  file input + dismissible success/error banner.

#### Tests
- `test_chatgpt_import.py` (15 tests): fork branches, missing
  `current_node`, empty parts, slugify, filename_for, malformed zips.
- `test_routes_imports.py` (6 tests): synthetic zip via stdlib
  `zipfile`, dedup reconciliation, empty/non-zip rejection,
  empty-conversation skip count.

#### Fixed (suite hygiene during the v0.1.33 cycle)
- `routes_marketplace.py`: `_BUNDLED_SAMPLE` was cwd-relative; resolved
  it against the package location so the 9 marketplace tests pass
  regardless of where pytest is launched.
- `app.py`: mobile-UI mount used the same cwd-relative bug; now
  anchored to the package.
- `models.py`: `BaseEntity` declared three independent
  `default_factory=_utcnow` fields that drifted by a few microseconds on
  Python 3.12 and broke the "nothing has changed yet" invariant.
  `model_validator(mode='before')` coalesces them to one `_utcnow()`.

## [0.1.32] -- 2026-05-19

### ADR-0003 Phase C -- always-on AV scanning

Every uploaded file is scanned before it lands on disk.
**Windows: Microsoft Defender** via `MpCmdRun.exe -Scan -ScanType 3
-File <path> -DisableRemediation`; the result comes from **stdout
parsing** (`Threat   : ...`) because exit codes drift across
Defender versions. **POSIX: ClamAV** via `clamscan` (exit codes 0/1/2
are stable). No engine on the host -> the upload still lands with
`scan_result='unavailable'` and a banner makes that explicit. No
third-party APIs (Contract #15).

#### Added
- `files_av.py` -- engine detection, scanner spawn, 30s timeout,
  anchored regex for the Defender `Threat :` line, real-time
  protection fall-through ("file vanished while we were looking ->
  blocked").
- Upload flow scans the quarantine bytes before dedup/finalize.
  Blocked uploads insert a row with `scan_result='blocked'` and
  `deleted_at=now` so the audit trail records them, then return
  `ok=false`.
- `tests/conftest.py` autouse fixture mocks scan_file as always-clean
  so the rest of the suite doesn't spawn Defender.

#### Tests
- `test_files_av.py` (8 tests) for the Defender classifier + engine
  detection.
- `test_routes_files.py` extended (3 tests) for blocked / unavailable /
  clean roundtrips.

## [0.1.31.5] -- 2026-05-08

### ADR-0003 Phase B -- pre-upload inspection dialog

Browser-side magic-byte detection of every picked file before the POST.
Filename, size, detected MIME, first 30 lines if it's printable text;
red banner if it looks executable (PE / ELF / Mach-O). Bulk-select mode
for many files at once.

## [0.1.31] -- 2026-05-05

### ADR-0003 Phase A complete -- renderer FilesPanel

- `lib/files-client.ts` -- multipart upload, list, download, soft
  delete. XHR for progress events.
- `<FilesPanel>` component wired into the project workbench landing:
  drag-drop, multi-file picker, per-row metadata, delete confirm.

## [0.1.30.5] -- 2026-05-01

### ADR-0003 Phase D + step 6 -- workbench transcripts + AI context

- PTY session exits in workbench-tagged sessions write their scrollback
  to `project_files` rows with `source='transcript'`.
- `GET /api/v1/projects/{id}/transcripts` lists them.
- `/api/v1/ai/context` inlines the current project's files (and the
  shared scope) so a Claude session sees them on prompt 1.

## [0.1.30] -- 2026-04-28

### ADR-0003 Phase A -- project files REST surface

- Migration 006: `project_files` table (id, project_id, original_name,
  on_disk_name, mime, size_bytes, sha256, source, uploaded_at,
  deleted_at, scan_result, scan_engine, duplicate_of).
- `files_storage.py` -- on-disk write / move / soft-delete / hash module.
  Pure functions, no FastAPI.
- `routes_files.py` -- multipart POST, list, download, delete. Per-project
  AND shared (`project_id IS NULL`) scopes. 100 files / request and
  256 MiB / file caps via env. Reference-counted dedup with after-write
  reconciliation under transaction.

## [0.1.29] -- 2026-06-09

### ADR-0002 Phase B + "Built for AI agents too" surfaces

The Apps tiles now have an **Open in workbench** button that spawns a
PTY session pre-`cd`'d into the project's working directory, picking
Claude → Codex → shell automatically based on what's on PATH. And the
app now has an explicit AI-facing layer: `GET /api/v1/ai/context`
returns a compact orientation digest so a Claude / Codex session in a
Sessions tab can read what's running, what's installed, and which REST
endpoints are designed for it to call.

#### Added -- daemon
- `routes_workbench.py` -- `POST /api/v1/projects/{id}/workbench`. Body
  is optional `{argv?, rows?, cols?, source?}`; if `argv` is omitted the
  daemon picks **`claude` → `codex` → `powershell.exe`/`zsh`/`bash`**
  via `shutil.which`. Spawns under the project's `cwd`, audits as
  `workbench.open` (Contract #11), returns the PTY summary plus
  `project_id` + `project_name` so the UI knows where to land.
- `routes_ai.py` -- `GET /api/v1/ai/context`. Compact digest with schema
  `synapse.ai.context/v1`: projects (id / name / path / kind / status
  / launch_cmd / port / health), tools (id / runnable / actions
  metadata), live PTY sessions, the last 25 audit rows, and an
  `endpoints_for_ai` field that explicitly maps "what you want to do
  next" -> REST path. This is the orientation surface for an AI session.

#### Added -- renderer
- `lib/workbench-client.ts` -- typed `openProjectWorkbench(id, opts?)`.
- `components/ProjectTile.tsx` -- new ghost-style **Open in workbench**
  button next to *Open folder* / *Open in VS Code* / *Terminal*. It
  POSTs the workbench endpoint and dispatches the v0.1.27 deep-link
  event; the user lands in the Sessions tab with the coder already
  running in the project's directory.
- `pages/Home.tsx` -- a "Built for AI agents too" callout card making
  the dual-audience design explicit, plus a new **Sessions** quick-jump
  button in the existing "Jump in" rail.

#### Added -- docs
- `AGENTS.md` gets an **AI-facing surfaces** section: how to use
  `/ai/context` for orientation, the workbench launcher, the
  marketplace install API, and (honestly) what's *not* AI-callable yet
  with the planned versions.

#### Verified
- 297 tests pass (+4: workbench POSIX-only spawn + workbench unknown
  project 404 + workbench auth-gated, AI context returns versioned
  digest + AI context auth-gated). Typecheck green.
- E2E live: `POST /projects/anchor/workbench {"argv":["cmd.exe"]}`
  returned `session_id=46d8b92ccfaa`, `cwd=C:\Users\justi\Anchor`,
  `project=Anchor` (proof of pre-`cd`). `/ai/context` returned a digest
  for 21 projects, 1 tool, 25 audit rows, 8 endpoint pointers.

#### Why this matters

Phase B was always the "useful framing for the AI workbench" -- the AI
sits **inside** your project, not next to it. Combined with the AI
context endpoint, a Claude session opened from a tile can introspect
what Synapse knows about its current project on its first prompt and
act accordingly. No bespoke handoff -- just JSON over REST.

#### What's still gated per the ADRs

- Phase C (Apple / Google OAuth refactor of pairing) is still in
  ADR-0003 territory and not happening without an explicit go-ahead.
- Per-project file upload + transcript history, ChatGPT folder
  migration, malware scanning, and AI-driven "build me an MCP / a tool"
  quick-actions all need ADR-0003 first.

## [0.1.28] -- 2026-06-09

### Sessions install dialog + Help panel

The Claude / Codex quick-launch buttons used to surface a raw "command not
found on PATH" error if the binary wasn't installed. Now they detect
that, offer an Install dialog with the exact npm command, and run the
install as a real Synapse session so the user can watch the output live.

#### Added
- `routes_pty.py` -- `GET /api/v1/pty/probe?cmd=X`. Cheap `shutil.which`
  wrapper; returns `{cmd, available, resolved}`. Lets the renderer decide
  whether to spawn or offer an install before the daemon errors.
- `lib/pty-client.ts` -- typed `probeCommand` helper.
- `pages/Sessions.tsx`:
  - `INSTALL_RECIPES` table for the known coders (Claude Code, OpenAI
    Codex CLI). Each entry has the install argv, prerequisites, docs URL,
    and a friendly note about auth (CLI manages its own).
  - Probe before spawn for quick-launch buttons. If unavailable, an
    Install modal pops with the exact command + a "Run install" button
    that spawns the install in a new tab.
  - Help panel (toggle button next to the quick-launches) explaining how
    sessions work, Claude Code's runtime controls (`/permissions`,
    `/tools`, `--dangerously-skip-permissions`), and the **Built for AI
    agents too** stance — the dashboard exposes its state through REST
    so a Claude session in a tab can introspect what's running.

#### Verified
- 293 tests pass (+2 probe-route cases); typecheck green. Live probe on
  Windows: `claude` -> `available: false`, `python` -> `available: true,
  resolved: ".../python.EXE"`. Clicking Claude in the UI no longer raw-
  errors; it opens the Install dialog.

## [0.1.27] -- 2026-06-09

### Marketplace ships Claude + Codex (ADR-0002 Phase A complete)

The loop closes: a JSON-only manifest in the bundled registry installs as
a real Synapse tool whose action opens a live AI coder session in the
dashboard. **No bespoke code for Claude or Codex** -- they ride on the
v0.1.22 declarative tier (`pty.spawn` primitive), v0.1.21 hot reload,
v0.1.24 marketplace install, and v0.1.26 xterm.js renderer.

#### Added
- `docs/marketplace-sample.json` -- two new bundled entries:
  - **Claude Code** (`claude`, verified) -- `pty.spawn ["claude"]`, opens
    a Claude Code session. Uses the user's existing `claude` CLI
    credentials, per ADR-0002 (we store no new secrets).
  - **OpenAI Codex CLI** (`codex`, verified) -- `pty.spawn ["codex"]`,
    same model. Inherits the user's Codex login.
- `components/ToolCard.tsx` -- when an action returns a `session_id` in
  its result (i.e. a `pty.spawn` primitive landed), the card sprouts an
  **Open in Sessions** button. It fires a `synapse:open-session` window
  event with the id; no nav coupling inside ToolCard.
- `App.tsx` -- catches that event, switches the active page to
  `sessions`, and threads the id to `<SessionsPage initialSessionId>`.
- `pages/Sessions.tsx` -- new `initialSessionId` + `onConsumedInitial`
  props. On mount, looks up the session via `GET /pty/{id}` to learn its
  argv, opens a tab, and consumes the id so a re-mount doesn't loop.

#### Verified
- 291 tests pass; typecheck green. E2E live: `GET /marketplace` listed
  Claude + Codex with `tier=declarative, verified=True`; `POST
  /marketplace/install/claude` returned `installed=claude,
  reload.added=[claude]`; `GET /tools` then listed `claude` with
  `runnable=True` -- proof the declarative tier from v0.1.22 makes
  Claude runnable without a Python handler. `DELETE` cleaned up. The
  Tools card → **Open in Sessions** deep link routes to the xterm panel
  with no extra clicks.

### ADR-0002 Phase A: done

Phases A1 (PTY foundation), A2 (xterm.js renderer) and A3 (marketplace
bundling) are all shipped:

- Drop into Synapse, open **Tools → Browse**, install **Claude Code**,
  hit **Open Claude session**, and a live AI coder appears in a
  **Sessions** tab.
- No new secrets to hand Synapse, no new auth flow, no agent loop
  re-implementation -- the existing `claude` CLI handles all of that and
  we host it.

Phase B (project-scoped workspace) and Phase C (Apple / Google OAuth)
are still gated on explicit go-aheads per the ADR.

## [0.1.26] -- 2026-06-09

### Live AI / shell sessions in the dashboard (ADR-0002 Phase A step 2)

The xterm.js half of the AI workbench. **Click Sessions → Python REPL,
get a real Python REPL in a tab.** Or PowerShell, or any binary on PATH.
Each session is a real PTY with colours, line editing and Ctrl+C; the
daemon's `pty.spawn` from `v0.1.25` plus xterm.js v5 here closes the
loop end-to-end.

#### Added -- renderer
- `lib/pty-client.ts` + `Pty*` types in `generated-types.ts` -- typed
  REST clients for spawn / list / get / input / resize / close.
- `components/SessionTerminal.tsx` -- xterm.js v5 + `@xterm/addon-fit`
  bound to a Synapse PTY session. Subscribes to the bus event stream and
  base64-decodes `v1.pty.session_output` straight onto the terminal;
  `term.onData` POSTs keystrokes to `/pty/{id}/input`; `term.onResize`
  POSTs to `/pty/{id}/resize`. Lifecycle is wired so the daemon's
  `v1.pty.session_exited` event prints `[synapse] session exited (code N)`
  and disables further input.
- `pages/Sessions.tsx` -- a new top-level page (also a new sidebar entry
  with a sparkles icon). Quick-launch row for **Claude / Codex / Python
  REPL / PowerShell** (or shell-of-the-day on POSIX), a custom-argv
  spawn form, and a tab strip per open session. Sessions spawned
  out-of-band (curl, other windows) appear under a "Re-attach to" rail.
- `lib/nav.ts` + `App.tsx` -- new `sessions` page id wired through the
  shell.
- `package.json` -- `@xterm/xterm@^5.5` + `@xterm/addon-fit@^0.10`.

#### Fixed
- **Late-binding bug in `DaemonProvider.subscribeRaw`.** React runs child
  effects before parent effects on mount, so `SessionTerminal`'s effect
  ran *before* the provider's WS-init effect populated `wsRef.current`.
  The provider used to read `wsRef.current` at subscribe time and hand
  back a no-op unsubscriber when the ref was still `null`. Now raw
  handlers go into a `Set<>` on a ref; `subscribeRaw` is stable across
  renders; the WS effect fans every event out to that set as soon as it
  arrives. Output (and input via the same wiring) now reaches the
  terminal from the first frame.
- **xterm dimensions race.** Calling `fit.fit()` synchronously after
  `term.open()` threw "Cannot read properties of undefined (reading
  'dimensions')" because the Viewport isn't measurable yet. Fits now
  defer to `requestAnimationFrame` and bail out if the host bounding
  rect is below a 4 px minimum.

#### Verified
- 291 tests pass (daemon-side suites unchanged); typecheck green.
- E2E live in the browser at 1280×800: clicked **Sessions → Python
  REPL**, the prompt `>>>` painted; pressed `2+2` + Enter; the terminal
  rendered `>>> 2+2 / 4 / >>>`. 0 console errors. Session lifecycle
  verified -- new sessions appear in `GET /pty` and clean up on DELETE.

#### What's next
v0.1.27 ships `claude` and `codex` manifests in the bundled marketplace
registry so the user can install them from Tools → Browse and open
sessions from the marketplace card.

## [0.1.25] -- 2026-06-09

### ADR-0002 + PTY session foundation (Phase A step 1)

The first piece of the AI workbench from the new ADR-0002. The daemon
can now host real interactive child processes -- `claude`, `codex`,
`python -i`, `psql`, anything -- under a true pseudo-terminal. v0.1.26
adds the renderer (xterm.js + a sessions tab); this version ships the
control plane so curl can already drive it.

#### Added -- docs
- `docs/adr/0002-ai-workbench.md` -- the design. Three phases (CLI
  passthrough → AI workspace → account auth), what's in scope, what's
  honest about not happening (VS Code Copilot can't be CLI-driven; we're
  not re-implementing an agent loop). Auth is **inherited** from the
  user's existing Claude/Codex CLI sessions -- Synapse stores no new
  secrets.

#### Added -- daemon
- `pty_sessions.py` -- `PtySession` + `PtySessionManager`. POSIX backend
  via stdlib `pty.fork` + `loop.add_reader`; Windows backend via
  `pywinpty` on a reader thread that posts to the event loop. Output is
  base64-fanned-out on the bus as `v1.pty.session_output`; lifecycle
  rides `v1.pty.session_started` / `v1.pty.session_exited`. Bounded 64
  KiB scrollback ring; fresh subscribers get the tail on `GET /pty/{id}`.
- `routes_pty.py` -- token-guarded REST control plane:
  `POST /pty` (spawn) · `GET /pty` (list) · `GET /pty/{id}` (summary +
  scrollback) · `POST /pty/{id}/input` (base64 OR text) ·
  `POST /pty/{id}/resize` · `DELETE /pty/{id}` (close).
- `tools_primitives.py` -- third primitive `pty.spawn`. A declarative
  manifest can now ship an interactive coder as pure JSON; the
  marketplace install/uninstall loop from v0.1.24 already covers it.
- `app.py` wires the manager onto `bus._pty_manager` so the primitive
  finds it without an import cycle, and on `app.state` for tests.
- `__main__.py` lifespan shuts every live session down on daemon exit.
- `pyproject.toml` -- `pywinpty>=2.0.0; sys_platform == "win32"` (POSIX
  uses stdlib).

#### Verified
- 291 tests pass (+6 PTY + 6 routes; 7 POSIX-only end-to-end cases skip
  cleanly on Windows so CI works either way). Typecheck green.
- E2E live on Windows: `POST /api/v1/pty {"argv":["python","-i","-q"]}`
  returned `session_id=39554f35fbb9`; sending `print(2*21)\r\n` via
  `/input` reported 13 bytes written; `GET /pty/{id}` returned base64
  scrollback containing real terminal control bytes (xterm.js will
  render those in v0.1.26); `DELETE /pty/{id}` returned 204.

#### What's next
v0.1.26 adds xterm.js + a `<SessionTerminal>` component bound to the
WS stream; v0.1.27 ships `claude` and `codex` manifests in the bundled
marketplace registry so a user can click *Install → Open session* and
have a working AI coder tab.

## [0.1.24] -- 2026-06-08

### Marketplace install / uninstall (ADR-0001 step 4 — loop closed)

The Browse cards now have **Install** and **Uninstall** buttons. Click
Install and the daemon writes the manifest into `tools/<id>/manifest.json`;
the watchdog reload from `v0.1.21` picks it up; the declarative primitives
from `v0.1.22` make its actions runnable. **No daemon code touches the
tool. No restart.** End-to-end live install ↔ uninstall is verified.

#### Added -- daemon
- `routes_marketplace.py` (v0.1.23 file extended):
  - `_fetch_manifest_payload(entry)` -- prefers `manifest_inline` from the
    registry, else fetches `manifest_url` via httpx with the same 10 s
    timeout the listing uses. Either way the JSON body is the manifest the
    user will run.
  - `POST /api/v1/marketplace/install/{tool_id}?force=bool` -- validates
    the payload against `ToolManifest`, **refuses if the manifest's `id`
    doesn't match the registry id** (the registry id is the trust anchor
    against malicious or misnamed payloads), refuses to clobber an
    existing folder unless `?force=true`, writes
    `tools/<tool_id>/manifest.json`, then triggers a synchronous
    `registry.reload()` so the response carries `{added, removed, kept}`.
  - `DELETE /api/v1/marketplace/install/{tool_id}` -- removes the manifest
    and the folder if it has no other files. Hot reload (already wired)
    drops the tool from the in-memory registry.
- `docs/marketplace-sample.json` now ships `manifest_inline` bodies for
  the two declarative sample tools (`open-synapse-docs` runs `url.open`
  to the README; `git-status` runs `process.spawn ["git", "-C", "{path}",
  "status", "--short"]`). They install + run **for real** off the
  bundled registry without an external network round-trip.

#### Added -- renderer
- `lib/marketplace-client.ts` -- `installTool(id, force?)` /
  `uninstallTool(id)` typed REST clients.
- `lib/generated-types.ts` -- `RegistryEntry.manifest_inline`,
  `InstallReport`, `UninstallReport`.
- `components/MarketplaceBrowser.tsx` -- each card now sprouts an
  **Install** button (with a spinner during the round-trip) or an
  **Uninstall** button (red ghost, with a confirm prompt) depending on
  whether the id is already in `installed_ids`. Optimistic local update
  on success plus the existing `v1.tool.reloaded` event makes the
  **Installed** tab counter tick up the same instant.

#### Verified
- 285 tests pass (+6 in `test_routes_marketplace.py`: install writes the
  manifest + reload + runnable; install refuses-without-force then
  forced overwrite; install unknown id is 404; install rejects a
  manifest whose id disagrees with the registry id; uninstall removes
  manifest + folder; uninstall unknown is 404). Typecheck green.
- E2E live (curl + browser):
  - `POST /api/v1/marketplace/install/open-synapse-docs` returned
    `installed=open-synapse-docs, tier=declarative, reload.added=[
    "open-synapse-docs"]`. The file landed at
    `tools/open-synapse-docs/manifest.json`. `/api/v1/tools` listed it
    with `runnable=True`. `POST .../tools/open-synapse-docs/actions/open`
    returned `status=launched, message="Opened
    https://github.com/jross32/synapse#readme"` -- the primitive ran.
  - Clicking **Install** on Git status in the Browse UI flipped the card
    to "Already installed", swapped the button to **Uninstall**, and the
    **Installed** tab counter went from 1 → 2 -- all within one paint.
  - `DELETE` then returned `reload.removed=["git-status"]`, folder was
    cleaned up, registry dropped the id.

#### Why this matters

This is the **loop close** for the in-app tool marketplace from
ADR-0001. A third party can now publish a single JSON manifest, a user
clicks Install, and Synapse runs it without ever touching Python. The
remaining v0.1.25+ work (Install-from-URL, scaffolder, registry index
domain) is purely about polish + reach.

## [0.1.23] -- 2026-06-08

### Tools → Browse (ADR-0001 step 3)

A read-only catalogue of tools available to install, served by the daemon
and rendered on the Tools page behind a new **Installed / Browse** tab
toggle. Cards show tier (Declarative / Handler), Verified badge, version,
publisher, and an **Already installed** indicator for any tool whose id
matches one already in `tools/`.

#### Added -- daemon
- `routes_marketplace.py` -- `GET /api/v1/marketplace?refresh=bool`.
  Resolves the registry source from `SYNAPSE_TOOL_REGISTRY_URL` (live
  `httpx` fetch, 10 s timeout) or the bundled
  `docs/marketplace-sample.json` if unset. 60 s in-memory TTL cache
  (`?refresh=true` busts it). Returns `{source, registry, installed_ids,
  cached}` so the renderer can mark "Already installed" and surface the
  source URL in the corner. Shallow validation drops malformed entries
  rather than failing the whole feed.
- `docs/marketplace-sample.json` -- bundled fallback index with three
  example tools: `cloudtap` (handler, verified), `open-synapse-docs`
  (declarative, verified), and `git-status` (declarative, unverified
  community entry). Exercises every UI state.
- `app.py` wires the router (token-guarded).

#### Added -- renderer
- `lib/marketplace-client.ts` + `RegistryEntry` / `RegistryIndex` /
  `MarketplaceResponse` types.
- `components/MarketplaceBrowser.tsx` -- card grid with tier + verified +
  installed badges + a Homepage link. Refresh button bypasses the cache.
- `pages/Tools.tsx` -- a **tablist** at the top: **Installed** (with the
  loaded-tool count) and **Browse**. Each tab swaps the content panel
  underneath; the existing live event refetch logic is unchanged.

#### Verified
- 279 tests pass (+6 in `test_routes_marketplace.py`: bundled-sample
  served, installed_ids marked, in-memory cache hit + `?refresh` bust,
  validator drops malformed entries, route is token-guarded). Typecheck
  green.
- E2E live: navigated to **Tools → Browse**; the three sample tools
  rendered with correct tier colours, Verified pills on the first two,
  Git status without one, and Cloudtap correctly green-checked as
  *Already installed*. Source label read **"bundled sample"** since no
  `SYNAPSE_TOOL_REGISTRY_URL` was set.

#### Why this matters

This is the **discovery half** of the marketplace from ADR-0001. v0.1.24
adds the *Install* button on each card -- which, thanks to v0.1.21's hot
reload and v0.1.22's primitives, just needs to fetch the manifest and
write it to `tools/<id>/manifest.json` for the loop to close.

## [0.1.22] -- 2026-06-08

### Declarative tool primitives (ADR-0001 step 2)

A tool can now ship as a **pure-JSON manifest** with no Python handler. An
action declares ``primitive`` + ``params`` and the daemon dispatches to a
vetted built-in primitive. That's the "third-party tools just drop in" property
the marketplace needs -- no curated handler review, no daemon rebuild.

#### Added
- `synapse_daemon/models.py` -- `ToolAction.primitive: str | None` and
  `ToolAction.params: dict`. The TS mirror in `lib/generated-types.ts`
  picks them up.
- `synapse_daemon/tools_primitives.py` -- the runtime:
  - `PRIMITIVES` -- the audited set. v0.1.22 ships **two**:
    - `url.open` -- opens a URL in the default browser. Refuses non-`http(s)`
      schemes. Substitutes `{field}` placeholders in the template.
    - `process.spawn` -- spawns a one-shot subprocess (argv list, **no shell**,
      so values like `"; rm -rf /"` cannot inject a command). Combined
      stdout/stderr is captured, with a default 5 s timeout (cap 30 s).
      Output is tail-trimmed to 4 KB so a chatty process doesn't blow the
      response.
  - `substitute(template, fields)` -- the field substitution rule.
    `{field_name}` is replaced by `str(fields[field_name])`; missing fields
    become empty strings. Not a template language -- no expressions, no
    chains, no shell.
  - `run_primitive(name, params, fields, bus, tool_id) -> ToolState` --
    publishes a `v1.tool.primitive_ran` event on success.
- `synapse_daemon/tools_registry.py`:
  - `load()` / `reload()` mark a manifest **runnable** when any of its
    actions has a `primitive`, even if no handler is bound in
    `_BUILTIN_HANDLER_FACTORIES`. That's how third-party tools light up
    without a Synapse build.
  - `run_action()` dispatches to `run_primitive` whenever the action has
    a `primitive`; the handler path is only taken when it doesn't.

#### Verified
- 273 tests pass (+18 in `test_tools_primitives.py`: catalogue,
  substitution, url.open success / non-http rejection / missing-param /
  failed-open, process.spawn success / non-zero exit / missing-argv /
  missing-binary / timeout, unknown primitive, and the registry
  integration: declarative manifest is runnable + dispatch + bad-primitive
  rejection). Typecheck green.
- E2E live: wrote `tools/_primitives-demo/manifest.json` with a single
  action `{primitive: "process.spawn", params: {argv: ["python", "-c",
  "print('synapse says: {message}')"]}}` -- watchdog hot-reloaded it,
  `runnable=true`, and `POST /api/v1/tools/primitives-demo/actions/echo`
  with `fields.message="hello from v0.1.22"` returned
  `status: launched`, output `synapse says: hello from v0.1.22`. **No
  daemon code touched the tool.** Deleted the folder; the daemon dropped
  it within a beat.

#### Why this matters

This is the load-bearing chunk of ADR-0001: with primitives + hot reload,
ADR-0001's "Install / Uninstall a declarative tool" flow is essentially
**already possible by hand** -- a marketplace can write the manifest to
`tools/<id>/` and the daemon picks it up. The Browse / Install UI in
v0.1.23 mostly wraps that loop in a discovery + click-to-install layer.

## [0.1.21] -- 2026-06-08

### Hot manifest reload for tools (Contract #26 · ADR-0001 step 1)

Drop a `tools/<id>/manifest.json` into the running daemon and it appears
in the UI within ~250 ms. Delete the folder, it disappears. No daemon
restart, no UI refresh. This is the foundation for the tool marketplace
laid out in ADR-0001 — install/uninstall flows now have a sub-second
live-reload story to plug into.

#### Added
- `synapse_daemon/tools_registry.py`:
  - `async reload()` — re-scans `tools/` in place. Preserves the live handler
    instance for any tool whose id is unchanged (so a running Cloudtap tunnel
    doesn't die just because someone wrote a different tool's manifest).
    Shuts down handlers for removed tools, instantiates new ones, swaps the
    manifest dict last so concurrent readers always see a coherent state.
    Returns `{added, removed, kept}` and broadcasts
    `v1.tool.reloaded` on the bus.
  - `start_watching(loop)` / `stop_watching()` — a `watchdog.Observer`
    on the tools directory. Coalesces a flurry of FS events into one
    reload via a 250 ms debounce + `asyncio.run_coroutine_threadsafe`
    back to the main loop. Idempotent; a missing `tools/` is a no-op.
- `synapse_daemon/__main__.py` lifespan starts the watcher after the
  initial `registry.load()`; `shutdown_all()` now stops it.

#### Verified
- 255 tests pass (+7 in `test_tools_hot_reload.py`: add / remove / kept /
  field-update / event-broadcast / idempotent-start / handler-shutdown).
  Typecheck green.
- E2E: live daemon serving `['cloudtap']`. Ran `mkdir tools/_hotreload-test`
  and wrote a `manifest.json`; ~250 ms later the daemon logged
  `ToolRegistry reload: +1 added` and `/api/v1/tools` returned
  `['cloudtap', 'hotreload-demo']`. Deleted the folder and the daemon
  reported `-1 removed` and the API dropped back to `['cloudtap']` --
  all without restarting the daemon.

#### Why this matters

The renderer's Tools page already auto-refetches on any `v1.tool.*` event
(wired in v0.1.9.5), so the new `v1.tool.reloaded` ping makes the UI
update live too — no extra renderer code required. That's the
"hot install/uninstall" property ADR-0001 needs for the marketplace.

## [0.1.20] -- 2026-06-08

### Open-in-Terminal tile button + responsive sidebar

#### Added
- `electron/main.ts` -- `synapse:open-in-terminal` IPC. Prefers Windows
  Terminal (`wt.exe -d <path>`) and falls back to a hidden-parent `cmd /K cd`
  popup when `wt` isn't on PATH. macOS uses `open -a Terminal`; Linux uses
  `x-terminal-emulator`.
- `electron/preload.ts` + `renderer/lib/electron-bridge.ts` --
  `openInTerminal(path)` + `canOpenInTerminal()` helpers.
- `renderer/components/ProjectTile.tsx` -- a new **Terminal** quick-action
  button alongside *Open folder* + *Open in VS Code* + *Open in browser*.

### Changed
- `renderer/components/Sidebar.tsx` -- responsive collapse. Below the `sm`
  breakpoint (< 640px) the rail narrows from **84px to 56px** and the labels
  drop to `sr-only` so only the icons + brand mark show. Above `sm` everything
  expands back. Verified at 400px (rail = 56px, no horizontal overflow, labels
  hidden) and 1280px (rail = 84px, labels visible).

#### Verified
- 248 tests pass; typecheck green. E2E: sidebar measured 56px at 400px
  viewport (labels hidden), 84px at 1280px (labels visible). Terminal IPC
  is wired the same way as v0.1.16's Open-in-VS Code (which we proved live).

## [0.1.19] -- 2026-06-08

### Project kinds + filtering

Tame the 21-projects-is-a-mess problem: every project now carries a *kind*
(App / UI / Service / MCP server / Library / Script / Other). Discovery
infers it automatically; the Apps page has a chips row above the grid that
filters by kind. A small kind badge appears on each tile. The edit dialog
exposes a kind picker.

This is the foundation the user asked for ("I want to be able to separate
[wbscrper UI from its MCP backend], or have it auto-detect if it's an MCP
server as well as a project or app, and organize/filter for that under
projects, so it's not a huge list of stuff").

#### Added -- daemon
- `migration 005_project_kinds.sql` -- adds a `kind` column to projects
  (default `'app'`) and an index.
- `synapse_daemon/projects.py` -- `ProjectKind` enum (`app` / `ui` / `service`
  / `mcp-server` / `library` / `script` / `other`); `Project` + `ProjectUpdate`
  gain `kind`; row reader/writer round-trip it; unknown values fall back to
  `'app'` so a future kind can land in the DB without breaking an older daemon.
- `synapse_daemon/discovery.py` -- `DetectedProject.kind`; a `_classify`
  pass after each per-stack detector maps the result to a kind. MCP server
  detection looks at file naming (`mcp-server.js`, `mcp_server.py`, `mcp/__main__.py`),
  Node deps/scripts/keywords/bin entries containing `mcp` or
  `@modelcontextprotocol/*`, and Python `pyproject.toml` deps mentioning `mcp`.
- `synapse_daemon/routes_discovery.py` -- `ImportRequestItem.kind` is passed
  through on bulk-import so detection results stick.

#### Added -- renderer
- `lib/project-kinds.ts` -- single source of truth (label / icon / badge
  tone) so a new kind drops in one place.
- `pages/Apps.tsx` -- a chips row above the tile grid (only the kinds with
  at least one project show up, each with a live count). Clicking a chip
  filters; combined with the existing text search.
- `components/ProjectTile.tsx` -- a small coloured kind badge next to the
  group / tag row. Hidden when the kind is the default `'app'`.
- `components/ProjectFormDialog.tsx` -- a Kind select; PATCH passes it
  through on edit.
- `components/DiscoveryDialog.tsx` -- detected kind shows as a coloured pill
  on each row and is sent on import.
- `lib/discovery-client.ts` + `lib/projects-client.ts` + `lib/generated-types.ts`
  -- types updated.

#### Added -- docs
- `docs/adr/0001-tool-marketplace.md` -- design ADR for the tool marketplace
  the user asked for: a two-tier model (declarative tools the daemon can
  auto-install + curated handler tools that ship in trusted builds), a
  registry index, hot install/uninstall via `watchdog`, and an Install-from-URL
  flow. Lays out the v0.1.20 -> v0.1.25+ roadmap to land it.

#### Verified
- 248 tests pass (+13: new `test_project_kinds.py` covering Node UI / Express
  service / MCP detection by dep, filename, script name / Python FastAPI /
  Python MCP by dep / Python single-file script / static / docker-compose
  service / Rust app, plus sqlite round-trip and the default fallback).
  Typecheck green. E2E: PATCHed `wbscrper` to `mcp-server` and a few others
  to `ui`; the Apps chips read **All 21 / App 17 / UI 3 / MCP server 1** with
  accurate filtering, and Web Scraper's tile now wears a violet MCP-server
  badge.

## [0.1.18] -- 2026-05-20

### Light / Dark theme (Contract #14)

A real, working light theme. Pick Light, Dark, or System on Settings → Theme,
or hit `Ctrl+K → "Toggle light / dark theme"`. The choice persists; "System"
follows your OS preference live.

#### Added
- `styles.css` -- a full `html.light` block with the inverted shadcn HSL
  palette (background / foreground / card / popover / primary / secondary /
  muted / accent / destructive / border / input / ring + the status colours
  re-keyed for legibility on a light background).
- `renderer/lib/theme.ts` -- `Theme` type, `getStoredTheme()`,
  `setStoredTheme()`, `applyTheme()`, `watchOsTheme()`. The class lives on
  `<html>`, choice in `localStorage["synapse.theme"]`.
- `renderer/App.tsx` -- applies the stored theme on mount and re-applies
  when the OS preference flips (only while in "system" mode).
- `renderer/components/ThemePanel.tsx` -- a 3-way Light / Dark / System
  selector in Settings.
- `renderer/components/CommandPalette.tsx` -- "Toggle light / dark theme"
  action so the palette can flip themes too.

#### Fixed
- `renderer/index.html` -- removed the hardcoded `text-slate-100 bg-nucleus`
  classes from `<body>`. They were overriding the theme tokens with the
  dark palette, which made the light theme look broken (light background,
  light text). The body now leans on the CSS variables in `styles.css`.

#### Verified
- 235 tests pass; typecheck green. E2E: `Ctrl+K → "theme" → Enter` flipped
  `<html>` to `class="light"`, swapped the body to a light background with
  dark text, and persisted to localStorage. Doing it again flipped back.

## [0.1.17] -- 2026-05-20

### Audit log viewer

The daemon's audit_log table (Contract #11) is now visible in the UI. Every
state-changing action -- launches, stops, project edits, tool actions,
device pairings, snapshot restores -- shows up newest-first on Settings,
including which source triggered it (Desktop / Mobile / Tray / CLI / Auto).

#### Added -- daemon
- `routes_audit.py` -- `GET /api/v1/audit?limit&offset` returns the audit
  rows newest-first with `total`, `limit`, `offset`. Token-guarded.
- `app.py` wires it under `/api/v1`.

#### Added -- renderer
- `lib/audit-client.ts` -- typed `listAudit(limit, offset)`.
- `lib/generated-types.ts` -- `AuditEntry` + `AuditListResponse`.
- `components/AuditLogPanel.tsx` -- a Settings card with a refresh button,
  a free-text filter (matches entity / id / action / source / result /
  error_code), live counts ("3 of 75 shown · 75 total"), and a scrollable
  log of entries. Each row shows local time, entity, action, source, and a
  green/red result pill.

#### Fixed
- A subtle bug found while wiring this in: the panel's old `mounted` ref
  pattern interacted with React 18 Strict Mode's double-effect to leave
  state-setters short-circuited and the panel permanently "Loading…".
  Removed the ref -- React 18 no longer warns about unmounted setState.

#### Verified
- 235 tests pass (+4 audit-route cases); typecheck green. E2E: the panel
  loaded 75 real audit entries from the daemon; typing "mobile" filtered to
  the 3 mobile-sourced actions.

## [0.1.16] -- 2026-05-20

### Open-in-VS Code tile action

A one-click "Open in VS Code" button on every project tile -- launches the
project's folder in VS Code via the `code` CLI. Daily-use ergonomics for a
dev's command center.

#### Added
- `electron/main.ts` -- `synapse:open-in-vscode` IPC: probes `code --version`
  synchronously first so the user gets a meaningful error ("install the CLI
  via Cmd+Shift+P -> Shell Command") instead of a silent no-op when VS Code
  isn't installed. Then spawns `code <path>` detached so the editor outlives
  Electron.
- `electron/preload.ts` -- exposes `synapse.openInVscode(path)`.
- `renderer/lib/electron-bridge.ts` -- `canOpenInVscode()` + `openInVscode()`.
- `renderer/components/ProjectTile.tsx` -- a new **Open in VS Code** button
  alongside *Open folder* and *Open in browser*. Hidden in browser dev mode
  where the IPC isn't available.

#### Verified
- 231 tests pass; typecheck green. Rebooted Electron -- 0 console errors;
  all 21 project tiles show the new button; `code --version` returns
  1.118.1 on this machine.

## [0.1.15] -- 2026-05-20

### Apps page filter

A search box on the Apps page so finding a tile in a 21-project registry is
one keystroke -- complements the `Ctrl+K` palette (which is for *execution*)
with a stay-in-place way to *browse* and *edit*.

#### Added -- renderer
- `pages/Apps.tsx` -- a filter input above the tile grid (with a leading
  search icon + clear button) and an "N of M projects" counter. Matches each
  query word against the project's name, id, path, description, group, tags,
  and `launch_cmd`. Empty query = show everything. Empty result = a "Nothing
  matches ..." hint with a nudge to clear.

#### Verified
- 231 tests pass; typecheck green. E2E: typing "scrap" narrowed 21 projects
  to the 4 scraping-related ones; "zzz-no-match" shows the empty state;
  clearing restores everything.

## [0.1.14] -- 2026-05-20

### Universal command palette (Contract #21)

`Ctrl+K` (or `Cmd+K`) opens a Synapse-wide command palette: launch any
project, jump to any page, or trigger an action -- all from one shortcut.

#### Added -- renderer
- `components/CommandPalette.tsx` -- a modal command palette with a search
  input + keyboard-navigated result list. Filters across:
  - **Projects** (one entry each, **Launch** when idle, **Stop** when
    running -- the action contextualises by status; matches on name, id,
    path, group, tags).
  - **Pages** (Home / Apps / Tools / Processes / Settings).
  - **Actions** (Add a project, Scan for projects, Pair a device, Download
    snapshot, Open mobile UI in browser).
  - Symmetric word-prefix matching, so "paired" still finds **Pair a
    device** and "set" still finds **Go to Settings** -- useful mid-typing.
- `App.tsx` -- a global `Ctrl+K` / `Cmd+K` keyboard listener toggles the
  palette. `↑` / `↓` to navigate, `Enter` to run, `Esc` to close.
- `components/Sidebar.tsx` -- a small `Ctrl+K` (or `⌘K` on macOS) button at
  the bottom of the rail, so the shortcut is discoverable. Click it too.

#### Verified
- 231 tests pass; typecheck green. E2E: `Ctrl+K` opened the palette;
  typing "paired" filtered to **Pair a device** alone; `Enter` ran it and
  navigated to Settings. 0 console errors.

## [0.1.13] -- 2026-05-19

### Auto-start + tray polish -- Milestone I

#### Added
- **Start with Windows.** `electron/main.ts` exposes `synapse:get-autostart` /
  `synapse:set-autostart` IPC over `app.getLoginItemSettings()` /
  `setLoginItemSettings()`. `components/StartupPanel.tsx` -- a Settings card
  with a toggle; outside Electron it degrades to a "Desktop app only" note.
- **Richer tray menu.** The tray now carries a **Projects** submenu (every
  project, a checkmark on the running ones, click to launch an idle one or
  surface the window), an **Open mobile UI** entry, a **Start with Windows**
  checkbox, daemon health, and Quit. The Projects submenu is refreshed from
  the daemon every 20 s -- the main process reads the local auth token off
  disk to make those calls.

#### Changed
- **Probe-before-spawn.** On launch the Electron app checks `/health` first:
  if a daemon is already running (one that survived an Electron crash, or was
  started by `synapse.cmd`) it **attaches** instead of spawning a second one
  -- no more port `7878` conflicts. A daemon we only attached to is left
  running on quit; one we spawned is still stopped.

#### Verified
- 231 tests pass; typecheck green. E2E: Electron rebooted on the new main
  process -- log shows "a daemon is already running -- attaching to it" and
  exactly one daemon holds `:7878`; 0 renderer console errors; the Startup
  toggle renders in the desktop app (and shows "Desktop app only" in a plain
  browser).

## [0.1.12] -- 2026-05-19

### Mobile Web UI -- Milestone H complete

The daemon now serves a responsive Web UI to your phone. Pair the device once,
then launch/stop projects and drive Cloudtap from anywhere -- on the LAN with
`--bind-lan`, or off-network through a Cloudflare tunnel.

#### Added
- `mobile/index.html` -- a self-contained mobile Web UI (HTML + CSS + vanilla
  JS in one file, zero external resources -- Contract #15). Dark theme
  matching the desktop.
  - **Pair screen** -- enter the 6-digit code from desktop Settings; the
    device token is kept in `localStorage` so the phone stays paired.
  - **Dashboard** -- every project as a card with live status + Launch/Stop;
    `:port` links open the running app; a Cloudtap section opens/closes
    tunnels. A WebSocket keeps it live; "Unpair this device" clears the token.
  - A revoked or invalid token drops the phone straight back to the pair
    screen.
- `app.py` -- mounts `mobile/` as static files at `/mobile` (open, so a phone
  can load the page before it has a token).

#### Verified
- 231 tests pass (+1: the mobile UI is served without a token); typecheck
  green. E2E (Playwright at a 390x844 phone viewport): paired with a live
  code, the dashboard listed all 21 projects, and a real Cloudflare tunnel
  was opened **and** closed from the phone UI -- 0 console errors.

## [0.1.11] -- 2026-05-19

### Device auth + pairing foundation (Milestone H, part 1)

The daemon is now authenticated. Every `/api/v1` data route requires a bearer
token -- the groundwork for safely exposing Synapse to a phone (and, over a
Cloudflare tunnel, off-network).

**Why every request, not just "trust localhost":** a Cloudflare tunnel runs
`cloudflared` on this machine, so tunnelled requests reach the daemon from
`127.0.0.1` -- they look local. Trusting loopback would let anyone with the
tunnel URL bypass auth. So nothing is trusted by IP; every request carries a
token.

#### Added -- daemon
- `migration 004_paired_devices.sql` -- `paired_devices` table (a device is
  remembered by the SHA-256 of its token; the raw token is shown once).
- `auth.py` -- `AuthManager`: a **local token** written to `data/auth-token`
  on boot (the desktop's credential) and **device tokens** minted when a
  phone redeems a 6-digit pairing code (10-min expiry, single-use, codes live
  in memory only). `is_trusted_local()` -- loopback AND no proxy/tunnel
  headers -- gates exactly one bootstrap endpoint. `require_token()` -- the
  FastAPI dependency that 401s every protected route.
- `routes_auth.py` -- `GET /auth/local-token` (trusted-local only),
  `POST /pair/code` (mint a code), `POST /pair` (redeem -> device token),
  `GET`/`DELETE /pair/devices` (list / revoke). Pair + revoke are audited.
- `app.py` -- the `X-Synapse-Token` guard is applied to the projects /
  discovery / tools / snapshot routers; `/health` + `/auth/local-token` +
  `/pair` stay open. `X-Synapse-Token` added to CORS allowed headers.
- `ws.py` -- the WebSocket resume frame accepts a `token`; a non-local socket
  must present a valid one or the daemon closes it (code 1008).

#### Added -- renderer
- `api-client.ts` -- `bootstrapLocalToken()` fetches the local token at
  startup; every request then carries `X-Synapse-Token`.
- `ws-client.ts` -- the resume frame carries the token.
- `lib/pairing-client.ts` + `components/PairedDevicesPanel.tsx` -- a Settings
  card to generate a pairing code (with a live expiry countdown) and
  list / revoke paired devices.

#### Verified
- 230 tests pass (+14 auth cases: local-token verify, pairing redeem / wrong
  code / single-use / revoke, trusted-local gating, full pair flow over
  REST); typecheck green. E2E: desktop app bootstraps its token and runs
  normally (21 projects); a pairing code generates with a countdown;
  unauthenticated `/projects` returns 401.

## [0.1.10.5] -- 2026-05-19

### Snapshot / restore (Contract #28)

The project registry is now portable: export it as one JSON file, restore it
on any machine. This finishes Milestone F's contract coverage.

#### Added -- daemon
- `snapshot.py` -- `build_snapshot()` reads the live registry (every project,
  the loaded tool ids, an audit-log tail, and the *keys* of secret env vars)
  into a `SnapshotPayload`. `restore_snapshot()` merges a payload back:
  creates projects that don't exist, updates those that do — by id, never
  deletes. Restored projects come back `idle` with secret values blanked
  (DPAPI-bound secrets never travel; the report lists the keys to re-enter).
- `routes_snapshot.py` -- `GET /api/v1/snapshot` (export) and
  `POST /api/v1/restore` (restore). Restore checks `format_version` +
  `schema_migration` compatibility first and audits the result (Contract #11).

#### Added -- renderer
- `lib/snapshot-client.ts` -- typed `exportSnapshot` / `restoreSnapshot`.
- `components/SnapshotPanel.tsx` -- a **Backup & restore** card on Settings:
  "Download snapshot" saves a timestamped JSON file; "Restore from file"
  reads one back and shows a report (created / updated counts, warnings, and
  any secret keys that need re-entering).

#### Changed -- renderer
- `pages/Settings.tsx` -- hosts the new panel; snapshot/restore dropped from
  the "Coming soon" list.

#### Verified
- 216 tests pass (+6 snapshot-route cases: round-trip, idempotent merge,
  incompatible-format rejection, secret blanking, status reset); typecheck
  green. E2E: downloaded a 21-project snapshot from the Settings UI and
  restored it back — "0 created, 21 updated", no duplicates.

## [0.1.10] -- 2026-05-19

### Home featured slideshow

The Home page gets a Microsoft-Store-style hero: a rotating banner over the
user's featured projects, replacing the top-heavy empty space the UI/UX
audits flagged.

#### Added -- renderer
- `components/FeaturedSlideshow.tsx` -- the Home hero. Rotates through
  featured projects (pinned first, then most-recently-active), auto-advances
  every ~6.5s, pauses on hover, and exposes prev/next arrows + dot
  navigation. Each slide shows the project's name, status, description,
  group/tags, and a **Launch** button that starts the project straight from
  the hero plus a "View in Apps" jump.

#### Changed -- renderer
- `pages/Home.tsx` -- restructured around the slideshow: hero, then the
  heartbeat HUD, then a wider "Recent activity" feed beside a stacked
  "Jump in" panel. Recent activity now shows 10 events. When no projects are
  registered the hero is replaced by a "Welcome to Synapse" empty state.

#### Verified
- 210 tests pass; typecheck green. E2E: slideshow renders + auto-advances in
  browser + Electron; no responsive overflow at 400px.

## [0.1.9.5] -- 2026-05-19

### Multi-tunnel Cloudtap + multi-instance tool model

Cloudtap can now hold **any number of tunnels open at once** — open one per
app, close whichever you want individually. The old single global "Close
tunnel" button (which looked like it closed everything) is gone.

#### Added -- daemon
- `models.py` -- `ToolItem` (one live instance of a tool) and
  `ToolState.items`. `ToolActionScope` + `ToolAction.scope` (`tool` =
  card-level button, `item` = rendered per instance). This makes the plugin
  model generically multi-instance -- any future tool (terminal sessions,
  multiple servers) reuses it.
- `routes_tools.py` -- the action POST body accepts `item_id` to target one
  instance; an item-scoped action with no `item_id` is a 422.
- `tools_registry.py` -- `run_action` validates action scope and forwards
  `item_id`; handlers are now constructed with `(bus, storage)`.

#### Changed -- Cloudtap (v0.2.0 manifest)
- Rewritten around a `dict` of `_Tunnel` instances. `tunnel` (tool-scoped)
  opens a new one; `close` (item-scoped) terminates exactly the targeted
  tunnel and leaves the rest running. All tunnels close on daemon shutdown.
- **Auto-labels each tunnel** with the registered project whose
  `expected_port` matches the tunnelled port (e.g. a tunnel on `:5173` shows
  as "Synapse"); falls back to `localhost:<port>`.
- A tunnel that drops on its own is marked errored in its own row instead of
  taking the whole tool down.

#### Changed -- renderer
- `ToolCard.tsx` renders an **Active (N)** list -- one row per live instance
  with its label, port badge, public URL, status, and its own per-instance
  action buttons (Close). `tool`-scoped actions stay as the card's buttons.
- `tools-client.ts` -- `runToolAction` takes an optional `itemId`.
- `generated-types.ts` -- `ToolItem`, `ToolActionScope`, `ToolAction.scope`,
  `ToolState.items`.

#### Verified
- 210 tests pass (+4 new multi-tunnel / labeling cases); typecheck green.
- E2E: opened two real tunnels at once (`:7878` + `:5173`), closed one,
  confirmed the other kept serving traffic over the public internet; the
  `:5173` tunnel auto-labelled "Synapse" from the project registry.

## [0.1.9] -- 2026-05-18

### Tool plugin system + Cloudtap

Milestone F's plugin surface. A tool is a folder under `tools/` with a
`manifest.json` -- pure data. The daemon **never imports code from a tool
folder**: actions run via *curated built-in handlers* compiled into the
daemon (the hybrid model). "Drop a folder in, get a card" plugin ergonomics
with zero untrusted-code execution.

#### Added -- daemon
- `synapse_daemon/models.py` -- `ToolManifest`, `ToolField`, `ToolAction`,
  `ToolState`, `ToolFieldType`. `ToolAction.available_in` lists the statuses
  in which an action is enabled so the UI can grey out buttons by state.
- `synapse_daemon/tools_registry.py` -- `ToolRegistry`: scans
  `tools/*/manifest.json`, validates each against `ToolManifest`, and binds a
  curated handler where one exists. A manifest with no compiled-in handler is
  still listed (`runnable=false`) -- its actions are simply inert. One bad
  manifest never blocks the rest.
- `synapse_daemon/tools/` -- new package. `ToolHandler` base class +
  `cloudtap.py`, the first built-in tool: spawns `cloudflared` as a quick
  tunnel, parses the public `*.trycloudflare.com` URL from its output, and
  kills the tunnel on daemon shutdown (an exposed tunnel never outlives its
  owner). One tunnel at a time; honest error states for bad port / missing
  cloudflared / no-URL timeout / early exit / dropped tunnel.
- `synapse_daemon/routes_tools.py` -- `GET /api/v1/tools`,
  `GET /api/v1/tools/{id}`, `POST /api/v1/tools/{id}/actions/{action}`. Every
  action is audited (Contract #11).
- `__main__.py` -- `--tools-dir` flag (default `tools/`); the registry loads
  in the lifespan and `shutdown_all()` runs on exit.

#### Added -- renderer
- `lib/generated-types.ts` -- `ToolManifest` / `ToolField` / `ToolAction` /
  `ToolState` / `ToolEntry` types.
- `lib/tools-client.ts` -- typed REST client (`listTools`, `getTool`,
  `runToolAction`).
- `components/ToolCard.tsx` -- one generic, manifest-driven card renders
  every tool: fields from the manifest, action buttons, status badge, and a
  `public_url` result rendered as an openable + copyable link. **No
  tool-specific UI code.**
- `pages/Tools.tsx` -- replaces the v0.1.8 placeholder; renders a card per
  loaded tool, with loading / empty / error states.

#### Fixed (from the v0.1.9 UI/UX audit)
- Tool action buttons are now state-aware -- "Open tunnel" greys out while a
  tunnel is running, "Close tunnel" greys out when none is, driven by the
  manifest's `available_in`. Previously both were always clickable and a
  second "Open" returned an `already_running` error.
- The Tools page now refetches on `v1.tool.*` WebSocket events, so a tunnel
  that drops on its own no longer leaves a stale "running" card.

#### Verified
- 206 tests pass (+23: `test_tools_registry`, `test_cloudtap`,
  `test_routes_tools`); typecheck green.
- E2E: opened a real Cloudflare tunnel from the UI; web-scraper MCP fetched
  `<tunnel-url>/api/v1/health` over the public internet -> HTTP 200.

## [0.1.8.6] -- 2026-05-18

### UI/UX audit fixes

A full UI/UX audit (Playwright browser walk + Electron CDP inspector + os-bridge
native capture across every page and viewport) surfaced two real bugs and a
handful of polish items. All fixed here.

#### Fixed
- **WebSocket replay events were silently discarded.** `ws-client.ts` `parse()`
  only accepted top-level `{id,name,timestamp_utc}` frames, so the
  `{type:"replay",events:[...]}` envelope the daemon sends once after every
  (re)connect was dropped. Every event that occurred before the renderer
  connected -- or during any reconnect gap -- never reached the UI, leaving
  Home's "Recent activity" permanently empty. `parse()` now unwraps the replay
  envelope and yields every buffered event; the message handler iterates.
- **Horizontal overflow below ~700px.** `Apps.tsx` tile grid used a fixed
  `minmax(320px,1fr)` floor that could not shrink; now
  `minmax(min(100%,320px),1fr)` so tiles collapse cleanly on narrow viewports.
- Stale UI version: `daemon-context.tsx` hardcoded a `'0.1.8'` fallback. It now
  prefers the Electron bundle version, then the live daemon's reported version,
  then a neutral `'dev'` -- never a stale literal.

#### Changed
- App shell padding is now responsive (`p-4 sm:p-6 lg:p-8`) instead of a flat
  `p-8` that crowded small screens.
- Project / log / discovery paths and launch commands wrap with `break-words`
  instead of `break-all`, so paths no longer shatter mid-segment.
- Settings shows a human-readable connection label (Connected / Connecting… /
  Reconnecting… / Disconnected) instead of the raw `connState` word.

## [0.1.8.5] -- 2026-05-17

### Project auto-discovery + groups + pinning

Point Synapse at a folder; it fingerprints every project inside and bulk-imports
your picks -- no more adding each project by hand.

#### Added -- daemon
- `synapse_daemon/discovery.py` -- a marker-file-driven multi-stack project
  detector. `detect_project()` recognises Node (+ framework: vite / next /
  react-scripts / angular / nuxt / astro / svelte / nest / express),
  Python (Django / FastAPI / Flask / entry-point / `python -m`), Rust, Go,
  .NET, Java (Maven / Gradle), Ruby (+ Rails), Deno, PHP, Docker Compose,
  Makefile, static sites, and bare git repos. Each result carries a stack,
  a suggested launch command, alternative `candidates`, a guessed port, and
  an honest `confidence`. `scan_directory()` walks a workspace root, skipping
  `node_modules` / `venv` / build output / hidden + system folders.
- `migration 003_discovery_groups.sql` -- adds `discovered`, `pinned`,
  `group_name`, and `tags_json` columns to `projects` (+ indexes).
- `synapse_daemon/routes_discovery.py` -- `GET /api/v1/discovery/scan` and
  `POST /api/v1/discovery/import` (bulk-create as `discovered=True`, with
  automatic id-collision suffixing).
- `Project` / `ProjectUpdate` gain `group`, `tags`, `pinned`, `discovered`;
  CRUD round-trips them.

#### Added -- renderer
- `components/DiscoveryDialog.tsx` -- the "Scan for projects" flow: enter a
  folder + depth, scan, review every detected project (stack badge,
  confidence, editable launch command, "already added" markers), bulk-import.
- `lib/discovery-client.ts` -- typed `scanForProjects()` + `importProjects()`.
- `ProjectTile` -- a pin toggle (pinned tiles float to the top) and group +
  tag badges.
- `ProjectFormDialog` -- a "Group" field; the Apps page sorts pinned-first.

#### Fixed
- **Stale "running" project status after a hard daemon kill** (Contract #6):
  if the daemon was killed mid-run, `reconcile()` marked the dead
  `managed_processes` row stopped but the *project* row stayed `launched`.
  New `reconcile_project_statuses()` sweep runs at boot after `reconcile()`
  and resets any project stuck in `launching`/`launched`/`stopping` with no
  live process back to `stopped`.

#### Tests
- `test_discovery.py` (20) -- per-stack detection, the loose-`.py`-files
  guard, scanning, skip-dirs, root-not-a-project, confidence sort.
- `test_routes_discovery.py` (5) -- scan, already-registered flagging, bad
  root, import, id-collision suffixing.
- `test_orphan_reconciler.py` -- 2 new tests for the stale-status sweep.
- `test_migrations.py` -- migration 003 presence. **183 tests passing.**

#### Verified (Rule #6 E2E)
- Browser (Playwright MCP): scanned `C:\Users\justi` -> 28 projects found,
  24 importable; imported 17 -> all land as `discovered`. Pinned "Web Scraper"
  -> it jumps to the top of the grid. 0 console errors throughout.
- Electron (`inspect-electron.js`): real window screenshotted -- Home shows
  "21 projects registered", 0 errored (the stale-status sweep cleaned a
  previously-stuck project), 0 console errors.
- `npm run typecheck` clean; `pytest` 183 passed, 1 platform-conditional skip.

## [0.1.8.1] -- 2026-05-17

### Hotfix -- synapse.cmd hung waiting for Vite

`synapse.cmd` failed at "[3/4] Starting Vite" with "Vite did not respond
within 30s". Root cause: Vite 5 binds the dev server to `localhost`, which
Windows resolves to `[::1]` (IPv6) first -- but the launcher's health poll
hit `http://127.0.0.1:5173` (IPv4), so it never matched.

#### Fixed
- `vite.config.ts`: `server.host` pinned to `127.0.0.1` so the dev server
  binds IPv4 loopback explicitly. Electron's `loadURL('http://localhost:5173')`
  still works (Chromium falls back from `::1` to `127.0.0.1`).
- `synapse.cmd`: the Vite wait loop now polls both `127.0.0.1` and `localhost`
  and allows 60s (the first run after a dependency change re-optimizes deps).

#### Verified
- `npx vite` now listens on `127.0.0.1:5173` (confirmed via `netstat`);
  `curl http://127.0.0.1:5173` returns 200.

## [0.1.8] -- 2026-05-16

### Milestone F (shell) -- the real Synapse UI

The flat single-page renderer is replaced by a proper app shell: a left
icon-rail sidebar with five destinations, built on shadcn/ui + Tailwind.

#### Added -- UI foundation
- shadcn/ui + Tailwind wired up properly: `components.json`, `cn()` helper
  (`renderer/lib/utils.ts`), the shadcn HSL colour-variable system in
  `styles.css`, and a Tailwind config mapping it (plus a Synapse `status-*`
  palette + `tailwindcss-animate`).
- Hand-vendored shadcn components in `renderer/components/ui/`: `button`,
  `card`, `badge`, `input`, `separator`, plus a lightweight `modal`. (The
  shadcn registry was unreachable from this environment; the components are
  the standard new-york source, which is shadcn's intended "code in your
  repo" model anyway.)
- Deps: `class-variance-authority`, `clsx`, `tailwind-merge`,
  `tailwindcss-animate`, `lucide-react` (icons), `@radix-ui/react-slot`,
  `sonner`.

#### Added -- shell + pages
- `renderer/components/Sidebar.tsx` -- fixed icon rail (brand mark, five
  nav buttons, a live connection indicator).
- `renderer/lib/nav.ts` -- the `PageId` model + nav metadata.
- `renderer/lib/daemon-context.tsx` -- `DaemonProvider` / `useDaemon()`:
  ONE shared `SynapseWsClient` + one source of truth for health, projects,
  live resource snapshots, and recent events. Replaces the 2-3 per-page
  WebSocket connections.
- Five pages under `renderer/pages/`: **Home** (heartbeat HUD with
  running/idle/errored/total stat cards + recent-activity feed + quick
  jumps), **Apps** (project tiles, refactored to context), **Tools**
  (shell + "arrives in v0.1.9" state), **Processes** (full-page live
  monitor), **Settings** (daemon diagnostics + About + GitHub link).
- `renderer/App.tsx` -- the shell: `DaemonProvider` > `Sidebar` + active
  page; "routing" is an `activePage` enum (no URL router needed in Electron).

#### Added -- polish items (Milestone F batch 1)
- **Log viewer** (`components/LogViewer.tsx`) -- a "Logs" button on every
  tile opens a modal that polls `GET /api/v1/projects/{id}/logs` (Contract #3).
- **Tile quick-actions** -- "Open folder" (OS file manager) and "Open in
  browser" (when a port is set) on each tile, via a new
  `synapse:open-external` IPC handler in the Electron main + a typed
  `openExternal()` bridge that degrades gracefully in a plain browser.

#### Changed
- Every renderer component rebuilt on shadcn/Tailwind: `StatusBadge`,
  `ProjectTile`, `ProcessMonitor`, `ProjectFormDialog`, `ConfirmDialog`
  (extracted from Apps), `PageHeader` (new shared header).
- `electron/preload.ts` exposes `openExternal`; `electron/main.ts` handles
  the IPC and drops the unused `fileURLToPath` import.
- Version files: `0.1.7` -> `0.1.8`.

#### Verified (Rule #6 E2E)
- Browser (Playwright MCP): all five pages render, 0 console errors;
  launched Web Scraper from Apps -> Processes table shows it live (PID,
  208 MB) -> Stop. shadcn styling applies correctly.
- Electron (`inspect-electron.js` @ CDP 9222): real window screenshotted --
  sidebar rail + Home HUD, 0 console errors.
- `npm run typecheck` clean; `pytest` 158 passed, 1 platform-conditional skip.

## [0.1.7] -- 2026-05-16

### Milestone E -- Live process monitor

Synapse now actively watches everything it launches: it detects crashes,
streams CPU% + RAM, can auto-restart per policy, and serves log tails. The
window gained a live process table, per-tile CPU/RAM, and "+ Add Project".

#### Added -- daemon
- `ProcessManager` background **watcher** (Contract #18): each spawned child
  gets an `asyncio` task awaiting its exit. Expected exits (via `stop()`) stay
  quiet; unexpected exits transition the project to `error` (non-zero code) or
  `stopped` (clean exit 0), write the audit log, and emit `v1.project.errored`
  / `v1.project.stopped`.
- **Heartbeat broadcaster** (Contract #19): a single `asyncio` loop samples
  CPU% + RSS for every live child every ~2s and broadcasts
  `v1.process.heartbeat`. CPU/RAM are summed across the whole process tree
  (the `cmd.exe -> npm -> node` chain), using a persistent `psutil.Process`
  cache so `cpu_percent()` deltas are meaningful. Soft caps from
  `resource_caps` surface as `over_budget` warnings.
- **Auto-restart** (Contract #18): on an unexpected crash, if the project's
  `RestartPolicy` allows, the daemon schedules a backed-off restart
  (`v1.project.restart_scheduled`) and gives up at `max_retries`
  (`v1.project.restart_exhausted`).
- `GET /api/v1/projects/{id}/logs?lines=N` -- tail of the project's most
  recent per-spawn log file (Contract #3).
- `ProcessManager.start_monitoring()` / `tail_log()` / `is_running()`.
- 11 new daemon tests (`test_process_monitor.py`) -- crash classification,
  expected-stop quiet path, auto-restart + exhaustion, heartbeat sampling +
  broadcast, log tail.

#### Added -- renderer
- `components/ProcessMonitor.tsx` -- "Live Processes" table: project, status,
  PID, uptime, an inline CPU gauge, RAM, and a Stop button. Empty-state when
  nothing runs (Contract #13).
- `components/ProjectFormDialog.tsx` -- one dialog, two modes. **create** is
  the new **"+ Add Project"** flow (collects a kebab-case id + name + path +
  launch command); **edit** replaces the old `ProjectEditDialog`. Explicit
  copy reassures the user that projects stay local and never reach GitHub.
- `ProjectTile` -- shows live `cpu / ram` while a project runs.
- `Apps.tsx` -- one WS subscription now feeds both the tiles and the process
  table; "+ Add Project" button in the header and the empty state.
- `projects-client.ts` -- `createProject` takes a `ProjectCreateInput`;
  `getProjectLogs()` added.

#### Fixed
- **Process logs were always empty** (Contract #3 broken): spawning with the
  Windows `DETACHED_PROCESS` flag silently dropped the inherited stdout/stderr
  handles, so every `data/logs/<id>/*.log` file was 0 bytes. Earlier tests
  only asserted the log file *existed*. `_spawn` now uses `CREATE_NO_WINDOW`
  instead -- a hidden console that still honours redirected handles. The
  process still outlives the daemon (Contract #6 holds). Caught by the new
  log-content test.
- **`projects.update()` corrupted nested models**: `model_copy(update=...)`
  does not coerce, so PATCHing `health` / `restart` / `resource_caps` / `env`
  left a raw `dict` in place and the next `.model_dump()` crashed with
  `AttributeError`. `update()` now re-validates the merged payload through
  `Project.model_validate()`. Caught by the auto-restart test.
- `_terminate_tree` is now run via `asyncio.to_thread` so the 5s grace wait
  doesn't block the event loop during Stop.

#### Changed
- FastAPI lifespan calls `ProcessManager.start_monitoring()` after boot.
- Version files + UI fallback: `0.1.6` -> `0.1.7`.

#### Verified (Rule #6 E2E)
- Browser (Playwright MCP): launch wbscrper -> tile shows `running` + live
  `cpu / ram`, "Live Processes" table populates (PID, uptime, 207 MB RAM),
  Stop -> table empties, no orphan on port 12345, "+ Add Project" dialog
  opens. 0 console errors throughout.
- Electron (`inspect-electron.js` @ CDP 9222): real window screenshotted with
  4 project tiles in a 3-column grid, "connected", 0 console errors.
- Registered 3 of the user's real apps (APA UI, Pool Hall, Ticket Vault) via
  the API into the local DB to populate the command center for testing --
  these live only in the gitignored `data/synapse.sqlite`, never committed.
- `npm run typecheck` clean; `pytest` 158 passed, 1 platform-conditional skip.

## [0.1.6] -- 2026-05-15

### Clickable launcher + Electron inspection + E2E-caught fixes

This bump makes Synapse runnable without PowerShell and gives the verification process eyes on the *actual* Electron window. Running the new Electron inspector immediately caught a real bug the browser-only test couldn't see.

#### Added
- `synapse.cmd` -- pure-`cmd` launcher (double-click in Explorer or run from `cmd`). Boots daemon + Vite + Electron, polls health, tails logs to `data/*-runtime.log`, cleans up ports on exit. No PowerShell.
- `install-shortcut.cmd` -- one-shot Desktop shortcut creator via `cscript` + a temp VBS (no PowerShell). Points the `.lnk` at `synapse.cmd` with the generated `.ico`.
- `scripts/inspect-electron.js` -- generic Electron renderer inspector. Connects to a running Electron app over the Chrome DevTools Protocol (`chromium.connectOverCDP`) and supports `screenshot` / `console` / `snapshot` / `html` / `click` / `eval` / `title`. App-agnostic -- rebuilt from the capability that lived in the app-specific `nexus-mcp-server`, now generic for any Electron app.
- `electron/main.ts` -- `--inspect-renderer` flag (or `SYNAPSE_INSPECT=1`) enables a CDP port (default 9222) so the inspector can attach. OFF by default -- a CDP port lets any local process drive the app.
- `playwright` added as a devDependency (drives `inspect-electron.js`; future E2E test infra).
- `scripts/gen-icon.py` -- now also emits a multi-resolution `electron/icons/synapse.ico` (16-256 px) and a `renderer/public/favicon.ico`.
- `AGENTS.md` -- new Rule #6: every code version bump must close with a real E2E pass (daemon boot -> renderer load via Playwright -> click-through -> teardown). Documents the Electron-inspection option.

#### Fixed
- **Daemon unreachable in the packaged/Electron renderer** (caught by `inspect-electron.js`): the preload bridge returned `http://127.0.0.1:7878` but `index.html`'s CSP `connect-src` only whitelisted `localhost:7878`, so every REST fetch + the WebSocket were silently CSP-blocked ("Failed to fetch", badge stuck on "connecting..."). The browser-only Playwright test passed because, without the Electron bridge, it fell back to the `localhost` default. Fix: preload `DAEMON_BASE` now uses `localhost`; CSP also whitelists the `127.0.0.1` variants as defence-in-depth.
- **Orphaned child processes on Stop**: Windows `shell=True` spawns put `cmd.exe` at the root with `npm`/`node` as grandchildren; terminating only the root left `node.exe` holding the port. `ProcessManager._terminate_tree()` now walks the full process tree via `psutil` (collected before terminating, since children get reparented) and escalates terminate -> kill.
- **React shorthand-style warning** in `ProjectTile`/`ProjectEditDialog`/`Apps`: mixing the `border` shorthand with a later `borderColor` override tripped React's "Removing borderColor border" warning on re-render. Switched to discrete `borderWidth`/`borderStyle`/`borderColor`.
- **Favicon 404** in the renderer console -- `renderer/public/favicon.ico` now generated + linked from `index.html`.
- **Base URL showed "--"** in the daemon card when no Electron bridge was present -- now falls back to the api-client default.

#### Changed
- `renderer/App.tsx` UI-version fallback bumped to `0.1.6`.
- `index.html` CSP also allows `data:` images (for future inline icons).
- Three version files: `0.1.5.5` -> `0.1.6`.

#### Verified (E2E, per Rule #6)
- Browser E2E (Playwright MCP @ `localhost:5173`): page mounts with 0 console errors, daemon card + Apps tile render, `Launch` -> `running` -> `Stop` -> `stopped` round-trip with live badge updates.
- **Electron E2E** (`inspect-electron.js` @ CDP 9222): real Synapse window screenshotted -- "connected" badge, daemon card populated (v0.1.5.5, 28 contracts, uptime, `http://localhost:7878`), Web Scraper tile rendering. This run is what caught + confirmed the CSP fix.
- `npm run typecheck` clean; `pytest` 149 passed, 1 platform-conditional skip.

## [0.1.5.5] -- 2026-05-13

### Hotfix -- ASCII-only PowerShell scripts (run-blocker)

`.\scripts\dev.ps1` failed to parse on Windows PowerShell 5.1 with `"The string is missing the terminator: '."` and `Missing closing '}'`. Root cause: the scripts contained multi-byte Unicode glyphs (`→`, `═`, `—`, `•`, `·`); PS 5.1 reads `.ps1` files as Windows-1252 unless they begin with a UTF-8 BOM, and the Write tool used to author them does not emit one. The mangled bytes broke string + brace tokenisation.

#### Fixed
- `scripts/dev.ps1`: rewritten in pure ASCII -- arrows `→` → `->`, box `═` → `=`, em-dashes `—` → `--`, bullets `•` → `*`. Added a header note explaining the constraint.
- `scripts/version-bump.ps1`: same substitutions; header note updated.
- `scripts/gen-types.ps1`: same substitutions; header note updated.
- `daemon/synapse_daemon/__main__.py`: the ready-line log string used `·` separators that rendered as `�` on Windows consoles (cp1252). Replaced with `|`.

#### Added
- `AGENTS.md` "Forbidden" section gains an explicit rule against non-ASCII characters in `.ps1` files, including the canonical substitution table. Daemon log strings written to console must also stay ASCII (Windows console = cp1252 by default).

#### Verified
- All three `.ps1` files parse cleanly via `[System.Management.Automation.Language.Parser]::ParseFile(...)` against `powershell -NoProfile`.
- `grep -P '[^\x00-\x7F]' scripts/*.ps1` returns no matches.
- 149 tests still pass; typecheck still clean.

#### Notes
- This is a half-step (`.5`) bump because the change is small and not a feature; Milestone E continues to be earmarked for `0.1.6`.

## [0.1.5] — 2026-05-13

### Milestone D — Project registry + launcher (click → launch)

You can now click a tile in the Synapse window and the corresponding app actually launches. State updates live over WebSocket; click again to stop. The seeded `wbscrper` project means there's something to click on first run.

#### Added — daemon
- `daemon/synapse_daemon/projects.py` (Contracts #1, #2, #10): `Project` + `ProjectUpdate` Pydantic models with kebab-case id validation (single-letter ids and full hyphenated ids allowed; underscore + caps rejected). Full CRUD against the `projects` table: `list_projects`, `get`, `get_or_none`, `create`, `update`, `soft_delete`. State writers `set_status` + `set_health` that guarantee strictly monotonic `last_transition_at` / `updated_at` even on coarse Windows microsecond clocks. `model_dump_for_client` redacts secret env values to `"(set)"` (Contract #25).
- `daemon/synapse_daemon/process_manager.py` (Contracts #2, #3, #6, #11): `ProcessManager` class — `launch(project_id, source)` transitions `idle → launching → launched`, spawns subprocess detached (Windows: `CREATE_NEW_PROCESS_GROUP | DETACHED_PROCESS`; POSIX: `start_new_session=True`) with stdout+stderr teed to a per-spawn log file under `data/logs/<id>/`, inserts a `managed_processes` row, emits `v1.project.launching` + `v1.project.launched` on the WS bus. `stop(project_id, source)` sends `terminate`, falls back to `kill` after 5 s, marks the row stopped with reason `user`, emits `v1.project.stopping` + `v1.project.stopped`. Spawn failures land in `EntityStatus.ERROR` with a `project.spawn_failed` `ErrorRef` and a `v1.project.errored` event. Audit log entries written for `launch.attempt`, `launch`, `stop.attempt`, `stop` (Contract #11). `shutdown()` closes log handles but does NOT kill children — Contract #6 wants them to survive daemon restart.
- `daemon/synapse_daemon/seed.py`: idempotent first-run insert of the `wbscrper` project at `C:\Users\justi\wbscrper` with `npm start` + an HTTP health probe on `/api/status`. Skips if the row already exists; preserves user edits across re-seeds.
- `daemon/synapse_daemon/routes_projects.py` (Contract #7): `build_projects_router(storage, pm)` factory exposing `GET /projects`, `GET /projects/{id}`, `POST /projects` (201), `PATCH /projects/{id}`, `DELETE /projects/{id}` (204), `POST /projects/{id}/launch`, `POST /projects/{id}/stop`. Every write path also writes the audit log (Contract #11).
- `app.build_app()` gained an optional `process_manager` parameter, mounts the projects router under `/api/v1`, and stashes the PM on `app.state.process_manager` for handlers + lifespan.
- `__main__.py` lifespan now calls `seed_default_projects(storage)` before the bus starts publishing, instantiates a `ProcessManager`, hands it to `build_app`, and tears it down on shutdown.

#### Added — renderer
- `renderer/lib/projects-client.ts`: typed wrappers for every project endpoint (`listProjects`, `getProject`, `createProject`, `patchProject`, `deleteProject`, `launchProject`, `stopProject`). All throw `SynapseApiError` carrying the daemon's `ErrorEnvelope`.
- `renderer/lib/generated-types.ts`: extended with `Project`, `ProjectUpdate`, `ProjectListResponse` types mirroring the Pydantic models.
- `renderer/components/StatusBadge.tsx`: reusable status pill with token-based colour + an animated pulse during transitions (`launching`, `stopping`). Uses `--synapse-status-*` tokens exclusively (Contract #14); marked `aria-live='polite'` for screen readers (Contract #23).
- `renderer/components/ProjectTile.tsx`: per-project tile — name, path, live `StatusBadge`, description, `cmd`/`port`/`updated` metadata grid, error banner if the project is in `error` state, **Launch**/**Stop** button that swaps based on current status, **Edit** and **Delete** affordances. Delete is disabled while the project is running (UI mirror of the daemon's 409 guard).
- `renderer/components/ProjectEditDialog.tsx`: modal edit form for name / path / launch_cmd / description / expected_port — Esc to close, click-outside to dismiss when not busy, focus trapped on first field. POSTs the diff via `patchProject` (Contract #1).
- `renderer/pages/Apps.tsx`: tile grid (`auto-fill, minmax(320px, 1fr)`), subscribes to `v1.project.*` events and refreshes on any change, ships an empty-state (Contract #13) and an inline `ConfirmDialog` for delete (Contract #12).
- `renderer/styles.css`: shared `@keyframes synapse-pulse` used by `StatusBadge`.
- `renderer/App.tsx`: keeps the daemon-status header from v0.1.4, now embeds `<AppsPage />` below it. Sidebar layout still arrives in Milestone F.

#### Added — tests (32 new, total 149)
- `daemon/tests/test_projects.py` (13): id validation, create/get/list/update/delete, conflict on duplicate, not-found 404, empty-update 422, refuses delete-while-running, strict monotonic transitions even on coarse clocks, error storage + clearing, health writer, secret redaction in client view.
- `daemon/tests/test_process_manager.py` (7): real subprocess `python -c "time.sleep(60)"` end-to-end — status transitions, log file created, managed_processes row + status_of mapping, audit rows for attempt + success, WS events emitted in order; double-launch guard; missing-project guard; stop terminates + finalises; stop-when-not-running guard; empty cmd raises; spawn failure path emits `v1.project.errored` with `project.spawn_failed`.
- `daemon/tests/test_seed.py` (3): seeds wbscrper on first run, idempotent on second run, preserves user renames across re-seeds.
- `daemon/tests/test_routes_projects.py` (9): list empty, list seeded, get 404, patch rename, patch empty 422, launch → stop round-trip with real subprocess, POST 201, POST duplicate 409, DELETE 204.

#### Changed
- `daemon/synapse_daemon/projects.set_status` + `update`: now guarantee strictly monotonic `last_transition_at` / `updated_at` (max(now, prev + 1µs)) so callers can rely on ordering even when Windows hands out the same wall-clock microsecond twice.
- Three version files: `0.1.4` → `0.1.5`.

#### Docs (per Rule #4 + #5)
- `README.md`: status line → "Milestone D complete: click → launch · 149 tests"; tests-pass number bumped; roadmap row D ✅, row E 🟡 next.
- `docs/api-changes.md`: 11 new endpoint/event rows under a v0.1.5 (Milestone D) heading; pending table trimmed to what actually remains.
- `PROGRESS.md`: version → 0.1.5, phase table marks D done, what's-done lists every new module + test + UI piece, what's-next breaks Milestone E into concrete sub-tasks.
- `CHANGELOG.md`: full 0.1.5 entry (this one).

#### Notes
- 149 tests passing · 1 platform-conditional skip ✅ · `npm run typecheck` ✅ · `npm run build:electron` clean.
- Full smoke-test path: `.\scripts\dev.ps1` → daemon boots → seeds wbscrper → Electron window opens with the wbscrper tile visible → click **Launch** → tile flashes "launching…" then "running" → `npm start` is now running in `C:\Users\justi\wbscrper` → click **Stop** → tile returns to "stopped".
- Crash auto-detection (Popen.poll() watcher + auto-restart per Contract #18) lands with Milestone E together with `v1.process.heartbeat`.

## [0.1.4] — 2026-05-13

### Milestone C — Electron skeleton (Synapse opens)

`.\scripts\dev.ps1` now launches the full stack: daemon → Vite → Electron window, all wired together. Closing the window hides to a system tray; right-click → **Quit Synapse** is the only thing that actually exits.

#### Added
- `scripts/gen-icon.py` — pure-stdlib PNG generator (no Pillow dep) that draws the Synapse mark — nucleus dot + accent ring + six cyan sparks — at 32 × 32 (tray) and 256 × 256 (installer / About). Run once with `python scripts/gen-icon.py`; both PNGs are checked in so dev machines don't need to regenerate.
- `electron/icons/synapse.png` (936 B) and `electron/icons/synapse-256.png` (16 KB) — generated placeholder marks. Designer-drawn final lands in Milestone J without touching consumer code.

#### Changed — Electron main process
- `electron/main.ts` rewritten end-to-end (Contract #2 hide-to-tray, Contract #6 daemon child, Contract #16 admin refusal):
  · Single-instance lock — second launch focuses the existing window.
  · Spawns `python -m synapse_daemon --port 7878 --data-dir data` on `app.whenReady`, polls `/api/v1/health` for up to 15 s before opening the window so the renderer never sees a connect-failure flash.
  · Tray icon with **Show Synapse** / **Open daemon health page** / **Quit Synapse**. Single-click + double-click both show the window.
  · `mainWindow.on('close', ...)` prevents default and hides to tray unless `isQuitting` is set. Only the tray's Quit item flips that flag.
  · External links open in the user's browser via `shell.openExternal`, never inside an Electron BrowserWindow.
  · `app.on('will-quit')` kills the daemon child cleanly. Daemon stdout/stderr is prefixed with `[daemon]` in the Electron console.

#### Changed — preload bridge
- `electron/preload.ts` exposes a typed `window.synapse.*` surface: `version()`, `daemonBase()`, `daemonWsBase()`, `platform()`. Raw Node APIs stay off the renderer's window.

#### Changed — renderer
- `renderer/App.tsx` rewritten as the Milestone C proof of life:
  · Calls `setDaemonBase(window.synapse.daemonBase())` so `api-client.ts` aims at the right host even in packaged mode.
  · Fetches `GET /api/v1/health` and renders version / uptime / start time / contracts-honoured count.
  · Starts a `SynapseWsClient`, displays the colour-coded conn-state badge (idle / connecting / connected / reconnecting / closed) using `--synapse-status-*` tokens.
  · Renders the last 5 received WS events with id + name + local time (Contract #24 — `formatLocal` shared helper).
  · All colour, spacing, type, and radius values come from `theme-tokens.css` (Contract #14 — no hardcoded values).

#### Notes
- `npm run typecheck` ✅ · `npm run build:electron` produces `dist-electron/main.js` + `preload.js` cleanly.
- `pytest` 117 passing · 1 platform-conditional skip — daemon code untouched in this commit.
- Smoke-test path: run `.\scripts\dev.ps1` — you should see daemon boot logs, a Synapse window showing "connected" + the `v1.daemon.started` event, and a tray icon. Close the window → hides to tray. Right-click → Quit Synapse → both Electron and the daemon child exit cleanly.

#### Next
- Milestone D wires real projects (CRUD endpoints + Apps page with tiles + launch button). First tile = `wbscrper`.

## [0.1.3] — 2026-05-13

### Milestone B — Daemon skeleton (the daemon is alive)

`python -m synapse_daemon` now boots a FastAPI server on `localhost:7878`, applies all SQLite migrations, runs orphan reconciliation, and emits a `v1.daemon.started` event onto the WebSocket bus. `GET /api/v1/health` returns the contract shape; `WS /api/v1/ws` honours the full replay + ping protocol.

#### Added — daemon modules
- `synapse_daemon/storage.py` (Contracts #8, #9, #11): `Storage` class wrapping a single SQLite connection in autocommit mode with WAL + foreign keys + 5 s busy timeout; `migrate()`, `applied_migration_numbers()`, `schema_migration()`, `transaction()` ctx manager.
- `synapse_daemon/migrations/_runner.py` (Contract #9): atomic per-migration application — splits SQL on `;`, runs every statement plus the `schema_migrations` INSERT inside a single `BEGIN IMMEDIATE` / `COMMIT`. Idempotent on re-run.
- `synapse_daemon/ws.py` (Contract #5): `Event` model, `EventBus` (monotonic IDs, 1 000-event ring buffer, async-locked `publish`/`subscribe`, `replay_since`, `replay_window_exceeded`), `WsHub` (FastAPI WebSocket handler with `resume` + `ping` + `error` envelopes, per-connection `asyncio.Queue` fan-out, cancellation-safe cleanup).
- `synapse_daemon/orphan_reconciler.py` (Contract #6): `reconcile()` reads `managed_processes` where `stopped_at IS NULL`, classifies each row as `re-attached` / `pid-recycled` / `daemon-restart` via `psutil`, writes the non-re-attached rows to `stopped`; `summarise()` rolls outcomes up into a `ReconciliationReport`.
- `synapse_daemon/app.py` (Contracts #4, #5, #7, #15): `build_app(storage, bus)` factory mounts CORS for Vite + Electron `null` origin, registers `SynapseError` → `ErrorEnvelope` handler + fallback handler that hides internals, exposes `GET /api/v1/health` returning `HealthResponse`, mounts `WS /api/v1/ws` via `WsHub`. Helpers `boot_publish_daemon_started()` and `boot_publish_reconciliation()` for lifespan use.

#### Changed — daemon entry point
- `synapse_daemon/__main__.py` rewritten: argparse with `--host`, `--port`, `--bind-lan`, `--data-dir`, `--allow-admin`, `--log-level`. Calls `assert_not_admin()` (Contract #16) → opens storage → applies migrations → builds app → wires lifespan that runs `reconcile()` in a thread + publishes the boot events → hands off to uvicorn. Daemon prints "ready · schema=N · contracts 1-28 · port=P" on startup.
- `scripts/dev.ps1` now actually orchestrates: spawns daemon as a background job, polls `/api/v1/health` for up to 10 s before launching Vite + Electron, cleans up jobs on exit. Supports `-DaemonOnly`, `-AppOnly`, `-BindLan`.

#### Added — tests (32 new, 0 regressions)
- `daemon/tests/test_storage.py` (10): file creation, WAL + FK pragmas, migration application, idempotency on re-run, schema-migration reporter, transaction commit + rollback, pre-open guard, idempotent close.
- `daemon/tests/test_ws.py` (9): monotonic IDs, replay slicing, ring-buffer eviction, window-exceeded boundary, subscriber fan-out + unsubscribe, default buffer size, failing-subscriber isolation, concurrent publishers get unique IDs.
- `daemon/tests/test_orphan_reconciler.py` (5): empty table, dead PID → `daemon-restart`, alive matching cmdline → `re-attached` without touching row, alive different cmdline → `pid-recycled`, `summarise()` bucket totals.
- `daemon/tests/test_app.py` (8): `/health` shape, versioned-path enforcement (unversioned 404), `SynapseError` → 4xx envelope, fallback handler hides internals, CORS preflight, WS resume + replay, WS replay-window-exceeded boundary, ping/pong.

#### Smoke-tested end-to-end
- Launched `python -m synapse_daemon --port 7878 --data-dir data`.
- `curl http://localhost:7878/api/v1/health` returned `{ok:true, version:"0.1.3", contracts:[1..28], ...}`.
- `curl http://localhost:7878/health` returned 404 (Contract #7 enforcement).
- Connected Python `websockets` client: resume handshake delivered the `v1.daemon.started` event; ping → pong worked.
- Migrations 1 + 2 applied cleanly on a fresh DB; second boot was a no-op.

#### Docs
- `README.md`: version line → `v0.1.3`; status reflects "daemon is alive · 117 tests"; "Getting started" now shows real boot + curl commands; roadmap table updated with Milestone B done + Milestone C as next.
- `docs/api-changes.md`: `/api/v1/health`, `WS /api/v1/ws`, `v1.daemon.started`, `v1.process.reconciled`, `v1.daemon.reconciliation_complete` documented as shipped in 0.1.3; pending endpoints regrouped by milestone.

#### Notes
- 117 tests passing · 1 platform-conditional skip (Fernet fallback on Windows; DPAPI ran natively).
- The daemon now satisfies the "always-on backend" half of the architecture. Milestone C wires Electron to it.

## [0.1.2.5] — 2026-05-13

### Docs sync — README + commit rule hardening

#### Added
- `AGENTS.md` "Commit rules" section now requires:
  - **Rule #4** — every commit syncs `README.md` whenever version, milestone, test count, roadmap status, tech stack, advertised features, or getting-started commands change.
  - **Rule #5** — affected `docs/` files sync alongside the change that touched them (`api-changes.md` for new endpoints/events, `security.md` for security-relevant code, ADRs for contract-touching decisions).
  - New "Docs-sync pre-flight" mental check: re-read the first 30 lines of `README.md` and `PROGRESS.md` before every commit.

#### Changed
- `README.md` fully rewritten to reflect current state:
  - Version line now `v0.1.2.5` (was stale at `v0.1.0-alpha.1`).
  - Status reflects "pre-Milestone-B contract pass complete · 85 tests passing".
  - New "Design contracts (28)" section linking to AGENTS.md and listing both rounds inline.
  - "Live status feedback" and "Editable from the UI" added to features bullets.
  - Tech stack table updated (watchdog + cryptography deps added in v0.1.2 are now visible).
  - "Getting started" now mentions running typecheck + pytest as a sanity check.
  - Roadmap table inserts the two contract-pass rows (`v0.1.0.5/0.1.1` + `v0.1.1.5/0.1.2`) between Milestone A and Milestone B with done status.
- `PROGRESS.md`: current version → `0.1.2.5`, current milestone wording updated.
- All three version files: `0.1.2` → `0.1.2.5`.

#### Notes
- No code changes; toolchain green unchanged (typecheck ✅, pytest 85/1 ✅).
- Rule #4 (README sync) and Rule #5 (docs sync) are now load-bearing — any future commit that violates them is a regression.

## [0.1.2] — 2026-05-13

### Contract scaffolding — Round 2 (code)

Operationalises Round 2 contracts (#17–#28) locked in `v0.1.1.5`. Every Round 2 contract now has a real Pydantic/Python/TS shape; runtime wiring follows in Milestones B–E.

#### Added — daemon modules
- `synapse_daemon/time_utils.py` (#24): `utc_now`, `to_iso`, `from_iso` with Z-suffix tolerance.
- `synapse_daemon/health.py` (#17): `HealthProbe`, `HealthState` enum, `HealthSnapshot`, `is_terminal()`.
- `synapse_daemon/restart_policy.py` (#18): `RestartPolicy` + `should_restart()` + `next_backoff_seconds()` exponential backoff with cap.
- `synapse_daemon/resources.py` (#19): `ResourceSnapshot`, `ResourceCaps`, `over_budget()`.
- `synapse_daemon/dependencies.py` (#20): Kahn-based topological sort restricted to the reachable subgraph + cycle detection + `reverse_dependents()`.
- `synapse_daemon/search.py` (#21): `tokenise()`, `build_search_tokens()`, `Indexable` protocol — identical tokenisation rules client+server.
- `synapse_daemon/notifications.py` (#22): `Notification` model + `KNOWN_EVENT_KINDS` frozenset + `assert_known_event_kind()` guard.
- `synapse_daemon/secrets.py` (#25): `EnvVar`, `SecretStore` protocol, `encrypt`/`decrypt` (Windows DPAPI + Fernet fallback), `redact()`, `SECRET_PLACEHOLDER` ("(set)"), `generate_token()`.
- `synapse_daemon/manifest_watcher.py` (#26): `ManifestWatcher` class wrapping `watchdog` Observer — picks up `manifest.json` changes, ignores other files.
- `synapse_daemon/cli.py` (#27): `synapse list | status | start | stop | logs | snapshot | restore | doctor` argparse-based parser; doctor runs without daemon.
- `synapse_daemon/snapshot.py` (#28): `SnapshotPayload`, `RestoreReport`, `assert_compatible()` with format + schema version guards.

#### Added — daemon migrations
- `migrations/002_round2_schema.sql`: adds `health_probe_json` / `restart_policy_json` / `max_rss_mb` / `max_cpu_percent` / `current_health` / `last_health_at` columns to `projects`; new tables `project_dependencies`, `search_index`, `notification_preferences`, `project_secrets`.

#### Added — renderer
- `renderer/lib/format-time.ts` (#24): `formatLocal(ts, kind)` + `formatUptime()` — single conversion point UTC → local.
- `renderer/lib/search-client.ts` (#21): `search(query, limit)` wrapper + `tokenise()` matching the daemon.
- `renderer/lib/generated-types.ts`: extended with all Round 2 types (`HealthProbe`, `HealthSnapshot`, `HealthState`, `RestartPolicy`, `RestartMode`, `ResourceSnapshot`, `ResourceCaps`, `Notification`, `NotificationLevel`, `EnvVar`, `SnapshotPayload`, `RestoreReport`).

#### Added — tests (10 new files, all 85 passing)
- `test_time_utils.py`, `test_health.py`, `test_restart_policy.py`, `test_resources.py`, `test_dependencies.py`, `test_search.py`, `test_notifications.py`, `test_secrets.py`, `test_manifest_watcher.py`, `test_cli.py`, `test_snapshot.py`.
- Updated `test_migrations.py` to assert migration 002 + required tables.
- Updated `test_models.py` to assert `HealthResponse.contracts` covers 1–28 and `model_registry()` exports every new model.

#### Changed
- `daemon/synapse_daemon/models.py`: `HealthResponse.contracts` default bumped to `range(1, 29)`; `model_registry()` now includes 11 Round 2 models.
- `pyproject.toml`: added `watchdog>=4,<7` and `cryptography>=43,<46` deps; registered `synapse` console script alongside `synapsed`.
- All three version files: `0.1.1.5` → `0.1.2`.

#### Notes
- `npm run typecheck` ✅ · `pytest` 85 passed + 1 skipped (Fernet test on Windows; DPAPI test ran on Windows) ✅.
- All 28 contracts now have code shapes backing them. Milestone B can begin wiring them into a running daemon.

## [0.1.1.5] — 2026-05-13

### Design contracts — Round 2 (docs only)

Locked the following 12 contracts into `AGENTS.md`, taking the total to 28. Code scaffolding lands in `v0.1.2`.

#### Added — operational lifecycle
- **#17** Health-check protocol per project (`http | tcp | command | none` probe, separate `health` field alongside `status` so we don't lie when a process is hung).
- **#18** Restart policy per project (`never | on-failure | always`, max-retries, exponential backoff). Default `never`.
- **#19** Resource observability per process (CPU% + RSS MB on heartbeat, optional soft caps with warning).
- **#20** Project dependencies (`requires: [id]` in manifest, topological launch with confirm, cycle detection).

#### Added — UX primitives
- **#21** Universal search / `Ctrl+K` command palette. Reserves keybind + `GET /api/v1/search` + `search_tokens` model field.
- **#22** Native system notifications (Electron toast for crash/health-flip/tunnel-live/scheduled-launch, per-event opt-out table).
- **#23** Accessibility minimums (WCAG AA contrast, visible focus rings, ARIA labels on icon-only buttons, full keyboard nav, `prefers-reduced-motion` already done).
- **#24** Timestamps UTC in DB, local in UI (single shared `formatLocal()` helper; no ad-hoc `.toLocaleString()`).

#### Added — data + control
- **#25** Secrets management (`secret: true` env vars, DPAPI-encrypted at rest, never logged, never round-tripped in plaintext after save).
- **#26** Hot manifest reload (`watchdog` file watcher on `tools/` + project manifest paths; `v1.manifest.reloaded` / `v1.manifest.error` events).
- **#27** CLI surface (`synapse list | status | start | stop | logs | snapshot | restore | doctor` mapped 1-to-1 with REST).
- **#28** Snapshot / restore (single JSON dump containing projects + tools + settings + audit tail; secrets excluded, surfaced as re-enter list on restore).

#### Changed
- `AGENTS.md` header: 16 → 28 contracts, references Round 1 (`v0.1.0.5` → `v0.1.1`) and Round 2 (`v0.1.1.5` → `v0.1.2`) cycle.
- All three version files: `0.1.1` → `0.1.1.5`.

#### Notes
- `HealthResponse.contracts` model field still reports 1–16; bumps to 1–28 in `v0.1.2` when round-2 models exist.
- `npm run typecheck` ✅ · `pytest` 31/31 ✅ (no runtime changes).
- Round 2 implementation (v0.1.2) follows immediately.

## [0.1.1] — 2026-05-13

### Contract scaffolding — Round 1 (code)

Operationalises the 16 design contracts locked in `v0.1.0.5`. Every contract now has a real code shape backing it; runtime wiring follows in Milestone B onwards.

#### Added — daemon
- `daemon/synapse_daemon/api_versions.py` (Contract #7): `API_VERSION`, `API_PREFIX`, `WS_EVENT_PREFIX`, `event_name()` helper.
- `daemon/synapse_daemon/errors.py` (Contract #4): `ErrorEnvelope` Pydantic model + `SynapseError` exception + helper constructors (`not_found`, `conflict`, `invalid`).
- `daemon/synapse_daemon/models.py` (Contracts #2, #8): `BaseEntity` with the universal live-status fields, `EntityStatus`, `AuditSource`, `ErrorRef`, `StateTransition`, `HealthResponse`, plus `model_registry()` so `gen-types.ps1` knows what to export.
- `daemon/synapse_daemon/migrations/__init__.py` + `001_initial.sql` (Contracts #9, #11): schema_migrations, audit_log, projects, tools, managed_processes, confirm_preferences, settings tables.
- `daemon/synapse_daemon/audit.py` (Contract #11): `AuditRecord` Pydantic + `audit(db, record)` writer.
- `daemon/synapse_daemon/process_log.py` (Contract #3): rotation constants (10 MB × 5), per-entity log dir layout, `new_log_path`, `latest_log`, `list_logs`.
- `daemon/synapse_daemon/security.py` (Contract #16): `is_admin`, `assert_not_admin(allow_admin=False)`.

#### Added — renderer
- `renderer/lib/error-types.ts` (Contract #4): `ErrorEnvelope` TS interface + `isErrorEnvelope` guard + `formatError`.
- `renderer/lib/api-client.ts` (Contract #7): `apiFetch<T>()` wrapper that prepends `/api/v1`, throws `SynapseApiError` carrying an `ErrorEnvelope`.
- `renderer/lib/ws-client.ts` (Contract #5): `SynapseWsClient` class with backoff (1, 2, 4, 8, 16, 30 s cap), event-id cursor, `{type: "resume", since}` handshake, conn-state events.
- `renderer/lib/theme-tokens.css` (Contract #14): full CSS-variable palette + dark/light/prefers-reduced-motion.
- `renderer/lib/generated-types.ts` (Contract #8): hand-written TS mirroring the Pydantic models; CI will compare to generator output once active.
- `renderer/styles.css` now imports theme tokens; body uses `var(--synapse-bg-nucleus)` etc.

#### Added — scripts + docs
- `scripts/gen-types.ps1` (Contract #8): placeholder generator entry point; activates in Milestone B.
- `scripts/version-bump.ps1`: now supports `-Kind design` (appends `.5`) and updates `daemon/synapse_daemon/__init__.py` too.
- `docs/api-changes.md` (Contract #7): versioning rules + pending v1 endpoint table.
- `docs/security.md` (Contracts #15, #16): threat model, no-telemetry posture, LAN exposure caveats, secrets stance.
- `docs/adr/README.md`: ADR folder + template for any future contract amendments.

#### Added — tests
- `daemon/tests/test_errors.py` (Contract #4): envelope validation, helper constructors, status codes.
- `daemon/tests/test_models.py` (Contracts #2, #7, #10): status enum coverage, audit source values, kebab-case pattern, API version constants, registry completeness, validate-on-assignment.
- `daemon/tests/test_migrations.py` (Contract #9): file naming, monotonic ordering, required tables present.
- `daemon/tests/test_process_log.py` (Contract #3): rotation constants, log dir creation, timestamp format, list+latest ordering.
- `daemon/tests/test_audit.py` (Contract #11): inserts one row per record, serialises details as JSON.
- `daemon/tests/test_security.py` (Contract #16): refuses on elevation, allows with flag.

#### Changed
- All three version files: `0.1.0.5` → `0.1.1`.
- `daemon/synapse_daemon/__init__.py`: bumped `__version__` to `0.1.1`.

#### Notes
- `npm run typecheck` ✅ · `pytest` (full suite) ✅.
- Next step in the user's review cycle: pause to draft Round 2 design contracts.

## [0.1.0.5] — 2026-05-13

### Design contracts — Round 1 (docs only)

Locked the following 14 design contracts into `AGENTS.md` so they apply to every future milestone. No runtime changes; scaffolding implementation lands in `v0.1.1`.

#### Added
- `AGENTS.md`: renamed "Cross-cutting requirements" to "Design Contracts" and expanded from 2 items to 16. New entries:
  - **#3** Log capture for every managed process (rotating per-process log files + live tail).
  - **#4** Single error envelope (`{code, message, details?, retryable}`) across REST + WS.
  - **#5** WebSocket reconnect protocol with monotonic event IDs + ring buffer replay.
  - **#6** Daemon orphan reconciliation on startup (re-attach / mark-stopped based on `psutil`).
  - **#7** Versioned API surface (`/api/v1/...`, `v1.entity.event`).
  - **#8** Single schema source of truth (Pydantic → TS via `scripts/gen-types.ps1`).
  - **#9** DB migrations from day 1 (numbered SQL files, `schema_migrations` table).
  - **#10** Naming conventions (IDs kebab-case, Python snake_case, TS camelCase, events `noun.verb`).
  - **#11** Audit log table for every state-changing action.
  - **#12** Confirm-before-destructive (with "don't ask again" toggle).
  - **#13** Empty states on every list/grid.
  - **#14** Theming via CSS tokens (no hardcoded colours in components).
  - **#15** No telemetry by default.
  - **#16** Refuse Administrator unless `--allow-admin`.

#### Changed
- `package.json` version: `0.1.0-alpha.1` → `0.1.0.5` (4-component scheme honoured by both PEP 440 and npm-as-non-publisher).
- `pyproject.toml` version: `0.1.0a1` → `0.1.0.5`.
- `daemon/synapse_daemon/__init__.py` `__version__`: same bump.
- `daemon/tests/test_smoke.py`: regex relaxed to allow 4+ component versions.
- `PROGRESS.md`: now lists all 16 contracts as standing requirements.

#### Notes
- `npm run typecheck` ✅ · `pytest` ✅.
- `scripts/version-bump.ps1` only handles 3-component + alpha-tag bumps today; will be updated to support the `.5` design-bump pattern in `v0.1.1`.

## [0.1.0-alpha.1] — 2026-05-13

### Milestone A — Repo scaffolding

#### Added
- Initial folder structure for the three layers: `electron/`, `renderer/`, `daemon/`, `mobile/`, plus `tools/`, `installer/`, `scripts/`.
- Root config files: `package.json`, `pyproject.toml`, `tsconfig.json`, `vite.config.ts`, `tailwind.config.ts`, `postcss.config.js`.
- Docs: `README.md`, `LICENSE` (MIT), `CHANGELOG.md`, `PROGRESS.md`, `AGENTS.md`.
- `.gitignore` covering Node, Python, Electron build artefacts, and OS metadata.
- GitHub Actions CI workflow: lint + typecheck + pytest on every push.
- Dev orchestration script `scripts/dev.ps1` and version-bump helper `scripts/version-bump.ps1`.
- First plugin manifest: `tools/cloudtap/manifest.json` (handler ships in Milestone G).
- Placeholder Electron main, renderer entry, and daemon entry so `npm run typecheck` and `pytest` pass green.

#### Notes
- Repo pushed to GitHub at this commit.
- No runtime functionality yet — full daemon and UI come in Milestones B and C.




