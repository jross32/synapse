# Changelog

All notable changes to Synapse will be documented in this file.
Format roughly follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
This project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Every commit must append an entry under the in-progress version header.

---

## [Unreleased]\n\n## [0.1.218-rc.1] -- 2026-10-11\n\n### Added\n- Integration candidate for account-scoped machine inventory, device onboarding, fail-closed routing, and local project-copy preview/checksum protections.\n- Isolated packaged daemon smoke harness and fixes for shared SQLite transaction handling and child-process cleanup.\n\n### Known limitations\n- Premium installer and new dashboard UI are not yet merged into this clean integration candidate.\n- Cross-device transfer, live two-device authentication, remote project synchronization, installer upgrade/rollback and signing are not production-verified.\n- Release candidate only; do not promote to stable without all gates in docs/SYNAPSE_MESH_RELEASE_GATES.md.\n

## [0.1.217] -- 2026-10-10

### Added
- First installer visual journey milestone: branded System Readiness and Whats New NSIS screens inspired by the approved eight-screen Synapse Setup design, alongside existing branded installer art and repair page.
- Native NSIS remains the reliable extraction and silent-install path. Full-window animations and integrated account handoff remain future work for a custom installer shell.
## [0.1.216] -- 2026-10-10

### Fixed
- Packaged Windows clients now ignore stale loopback account endpoint overrides from old installs unless SYNAPSE_ALLOW_LOCAL_ACCOUNTS=1 is explicitly set. This prevents retired localhost:8788 configurations from blocking Railway-hosted Synapse sign-in with WinError 10061.
- Repair diagnostic output explains the safe fallback and reports remaining custom account endpoints.

## [0.1.215] -- 2026-10-10
### Added
- Branded Windows Setup with dark violet gradient, glowing Synapse neural artwork, matched installer header, and clearer repair/update screens.
- Detects lingering installed Synapse desktop processes by exact executable path, waits for graceful exit and offers consent-based desktop shutdown before retrying setup. Development daemons and other applications remain untouched.

## [0.1.214] -- 2026-10-10


### Added
- Expanded safe installer repair health report: 19 diagnostics covering executable/daemon/UI files, installed version consistency, Windows user-data and temporary-folder writability, configuration JSON validity, TLS certificate trust, account service reachability/DNS, disk capacity, old daemons on port 7878, account endpoint overrides and data preservation.
- Rerunning Setup repairs missing or damaged packaged application files without removing projects, SQLite data, account files, or previous bundle selections. The report explains which conditions require user action and never deletes credentials, changes proxies/firewall, or forcibly terminates active agents.
- The repair smoke test verifies diagnostic report generation in addition to restoring a missing packaged daemon and preserving existing user preferences.
## [0.1.213] -- 2026-10-10

### Added
- Re-running the Windows installer detects an existing installation and offers an update/repair option; the default preserves the existing installation location, user data, credentials, and previously selected AI bundles.
- Packaged Windows installer diagnostics assess executable, daemon, Electron UI and package integrity, installed version, available disk space, account cloud HTTPS reachability, DNS, localhost MCP daemon port conflicts and version mismatches, account endpoint overrides, and user application folders.
- Automatic safe repair creates missing application data directories only; setup reinstalls missing or damaged bundled application files. It never deletes project databases, purges credentials, terminates user processes, changes firewall or DNS settings, or silently resets the account.
- A timestamped JSON repair report is saved to the user's local Synapse repair-reports directory after setup.

### Fixed
- Account sign-in and sign-up now remain actionable when a stale account-service health probe says offline, and report the real remote request error rather than disabling the login form.
- Daemon account credential requests run off the event loop, preventing stalled sign-ins from blocking other desktop requests.
## [0.1.212] -- 2026-10-09

### Added
- **Unified account-wide MCP connector:** a stable HTTPS URL for ChatGPT and Claude, recoverable on every signed-in computer, with rotation to revoke an exposed link.
- **Outbound multi-device relay:** enrolled Windows Synapse daemons long-poll the shared cloud service for MCP JSON-RPC requests and execute via their own existing localhost MCP dispatcher; no new inbound firewall rules or device-specific tunnel links are required.
- **Device selector:** choose the active computer using the signed-in Profile hub, without reconfiguring the ChatGPT/Claude connector URL.
- **Per-device Remote write access switch:** automatically enabled when a machine joins the Synapse account; switching Off pins new jobs to read-only, with a second live policy check immediately before dispatch. Switching On allows full MCP tools including permitted file changes and shell commands.
- Separate revocable credentials for user login, cloud MCP links, and each locally enrolled device; device credentials encrypted at rest with OS-scoped secret storage. Cloud queue deletes delivered requests and replies.
- Enforced a central allowlist of read-only MCP tools whenever a device or connector is read-only, fixing seven legacy write-tool branches that previously ignored URL/device read-only mode. Added regression coverage across all seven.

### Security and limitations
- The MCP link **is a powerful secret**. Anyone holding it can send MCP requests to the selected computer subject to the device's write switch. Store it only in trusted clients and rotate it if exposed.
- Switching Off stops **new** writes, but a command already running may finish. Signing out attempts to revoke the local host's cloud credential and stops the outbound agent.
- The cloud service stores transient routed request/response payloads during delivery. Local project files and daemon authentication secrets are not synced to cloud profile storage.
- Google OAuth still requires separately configured Google credentials. Actual operation with external ChatGPT/Claude accounts and two separately installed Windows computers requires user-device acceptance testing.

### Verification
- Automated identity, relay routing, account isolation, switching/rotation, credential revocation, host worker, and Windows NSIS installer gates. See GitHub Actions for the exact release run.
## [0.1.211] -- 2026-10-09

### Added
- Shared Synapse Accounts HTTPS service, persistent cloud identity storage, and a desktop startup sign-in/signup screen. No local account daemon command is required.
- Account-wide portable profile and device-host synchronization with merge-safe host inventory across multiple computers.
- Public authentication request throttling and strict OAuth handoff callback host validation.

### Known limitations
- Google OAuth sign-in requires a Google OAuth web client ID and secret configured on the hosted account service. The button stays disabled rather than pretending to work before credentials are available.
- Account creation must be completed through the app sign-up form; no user's password is included in a release.
- Shared cloud account identity is not yet a unified routed MCP connection to every device; app/project data remains local to each host.

### Verification
- Backend identity, sync, callback and authentication tests plus Windows installer pipeline must pass before publication.

## [0.1.210] -- 2026-10-09

### Fixed
- Windows installer packaging repairs: omit unnecessary NSIS global variables to fix warnings treated as errors, and use the project virtual environment for the frozen daemon build.
- Restore bundled Synapse installer artwork and wizard configuration for portable Windows setup.

### Verification
- Release automation gates publication on docs/version consistency, renderer/Electron compilation, frozen-daemon startup and health on a new data directory, installer integrity, and a fresh silent Windows installation.

## [0.1.209] -- 2026-08-30

### Fixed
- **Project Doctor Git metadata** -- branch names are now separated from upstream tracking/ahead/behind status, so AI operators receive structured `branch`, `tracking`, `ahead`, and `behind` fields instead of a combined porcelain-status string.

### Verification
- Project Doctor regression suite: **5 passed**.

## [0.1.208] -- 2026-08-30

### Changed
- **Operator Router uses Project Doctor first** -- diagnostic and developer plans now prefer the one-call Project Doctor snapshot before lower-level shell inspection, reducing repeated path/Git/stack/port discovery calls.
- **Project Doctor is a native operator capability** -- automatic capability discovery advertises it even when the caller does not explicitly provide a capability list.

### Verification
- Operator Router + Project Doctor focused tests: **12 passed**.

## [0.1.207] -- 2026-08-30

### Added
- **Project Doctor** -- one-call, read-only diagnostics for registered projects: project path, detected stack markers, Git repository/dirty state, and registered localhost-port reachability.
- **Project Doctor MCP tool** -- `synapse_project_doctor` gives ChatGPT and other connected AI operators the same compact diagnostic snapshot before editing or when a project appears unhealthy.
- **Project Doctor REST route** -- `GET /api/v1/project-doctor/{project_id}` exposes the structured report to Synapse surfaces and local automation.

### Fixed
- **Project Doctor release integrity** -- the previously referenced route/module files are now tracked with the release rather than depending on an untracked working-tree file.

### Verification
- Project Doctor + MCP/full-access focused suite: **10 passed**.
- Ruff on Project Doctor/MCP touched paths: **PASS**.
- Synapse app import with the mounted Project Doctor router: **PASS**.

## [0.1.206] -- 2026-08-29

### Added
- **Synapse Trace / Flight Recorder** -- a first-class, privacy-filtered timeline for observable AI/tool actions, watchdog and runtime events, errors, recoveries, durations, project/session correlation, and explicit action/outcome summaries.
- **Trace analysis** -- highlights repeated failures, restart/recovery churn, slow operations, recent incidents, and actionable recommendations from the recorded evidence.
- **Trace MCP surface** -- `synapse_trace_recent`, `synapse_trace_analyze`, and additive `synapse_trace_record` tools let connected AI workers inspect the same timeline and append concise explicit receipts without exposing hidden reasoning.
- **Automatic MCP tool receipts** -- every `tools/call` records success/failure, duration, correlation id, project/session hints, and privacy-filtered arguments. Trace failures are fail-open and can never break the actual tool call.
- **Watchdogs dashboard** -- a scalable System page that discovers the Synapse, Stock Hunter, and Web Scraper protection chain; shows health, PIDs, uptime, scheduled-task state, console-risk state, and expandable live logs.

### Changed
- **Background supervisors are headless by default** -- known Synapse and Stock Hunter scheduled watchdog/supervisor tasks use hidden `pythonw.exe` launchers so they keep protecting services without leaving terminal windows on the desktop.
- **Runtime evidence is unified** -- Trace idempotently ingests the existing Live Monitor, AI Supervisor, Repair Watchdog, Stock Hunter supervisor/campaign, daemon-watchdog, and tunnel-watchdog logs into one normalized timeline.

### Fixed
- **Desktop console clutter** -- watchdog/supervisor scheduled tasks no longer need interactive CMD/PowerShell windows to remain alive.
- **MCP exception chaining** -- two pre-existing connector error paths now preserve their originating exception context instead of triggering Ruff B904 findings.
- **Trace historical-log timestamps** -- plain watchdog logs now use their logged clock time instead of ingestion time, and transient 1/3 health misses are warnings rather than hard errors. This prevents old watchdog history from flooding the current 24-hour incident count.

### Privacy
- Trace never records private hidden chain-of-thought, keylogging, or continuous screenshots. Secret-like fields are automatically redacted, large nested payloads are bounded, and file-write bodies are omitted from tool receipts.

### Verification
- Trace + Watchdogs focused tests: **21 passed**; relevant MCP connector regressions: **6 passed** (27 focused checks total).
- Python compile and Ruff checks for the changed Trace/MCP paths: **PASS**.
- TypeScript typecheck, renderer production build, and Electron build: **PASS**.


## [0.1.205] -- 2026-08-28

### Changed
- **MCP now reserves a control/read lane under load** -- the v0.1.204 dedicated 16-thread executor is split into 4 reserved control workers and 12 blocking-work workers. Long shell, downstream MCP, repo-watch, HTTP, web-search, runtime-probe, and delegation calls can saturate their lane without consuming the capacity used by local context/session/thread-accounting/recovery calls.
- **Dispatch lane is observable** -- MCP responses now include `X-Synapse-MCP-Lane: control|blocking|mixed`; saturation responses identify the saturated lane alongside the existing retryable 503 and `Retry-After: 1` signal.

### Fixed
- **Recovery calls no longer disappear behind connector-heavy work** -- a burst of long commands/browser/downstream calls cannot occupy every connector dispatch worker and make `synapse_get_context`, session inspection, heartbeats, or result polling wait on the same pool.

### Verification
- Focused lane-routing/saturation/timing regressions: **5 passed**.
- Clean Windows daemon suite: **1195 passed, 14 skipped** in 24m19s (2 existing asyncio subprocess cleanup warnings).
- Clean Node gate: `npm ci`, TypeScript typecheck, renderer build, and Electron build all **PASS**.
- Live isolated-daemon saturation proof: with all 12 blocking workers occupied, `synapse_get_context` returned HTTP 200 on the reserved control lane in **0.08s**; a 13th blocking call failed fast with HTTP 503 in **0.046s** and `Retry-After: 1`; all 12 accepted blocking calls completed HTTP 200.


## [0.1.204] -- 2026-08-27

### Changed
- **MCP dispatch now has its own bounded executor** -- `POST /mcp/{token}` no longer uses
  `asyncio.to_thread` and therefore no longer competes for asyncio's process-wide default executor
  with PTYs, health probes, repo-watch work, or model/code-generation calls. Accepted MCP work runs
  on 16 dedicated `synapse-mcp` workers; when all 16 are occupied, additional calls fail immediately
  with retryable HTTP 503 instead of queuing invisibly until the connector times out.
- **Connector timing is observable without logging secrets** -- successful MCP responses include
  `X-Synapse-MCP-Queue-Ms`, `X-Synapse-MCP-Execution-Ms`, and `Server-Timing`; delayed dispatches log
  only the safe method/tool label plus queue/execution duration, never arguments, URLs, tokens, or bodies.

### Fixed
- **Cross-subsystem executor starvation** -- long MCP calls can no longer consume the same default
  worker pool used by unrelated daemon background work, closing the real failure mode where the daemon
  stayed healthy while a trivial connector call silently waited behind long operations from other sessions.

### Verification
- New executor regressions: **3 passed** (default-executor isolation, bounded fail-fast saturation, timing headers).
- Full MCP connector suite: **40 passed**.


## [0.1.203] - 2026-08-27

### Added
- **Durable ChatGPT UI workers** -- ChatGPT-owned squads can launch real `chatgpt_web` child workers,
  persist each reusable conversation separately from short-lived coordination sessions, link workers to
  current/related work items, archive them without deletion, and resume the same conversation only when
  reuse is explicit or the same work item is relaunched. A dedicated `Synapse2GPT Workers` browser
  profile keeps account-owner sign-in separate from the operator's normal Chrome/Edge profile.
- **Durable thread presence + work-time accounting** -- migrations 038-039 add request/work groups,
  stable AI-thread identity, active/idle/error/gone state, heartbeats, auditable per-turn durations,
  cumulative worked time, and browser observations that attach to the same thread when a ChatGPT tab is
  identified later. Live View now exposes the resulting thread/project/worker state on desktop and mobile.
- **Canonical project chat pointer** -- migration 037 and project-record APIs keep one last-write-wins
  current AI chat/thread URL per project. The writable MCP helper `synapse_set_project_chat_url` mirrors
  the REST operation for remote AI operators.
- **ChatGPT presence companion browser extension** now lives under `browser-extensions/` and can report
  visible ChatGPT tab/generation state without masquerading as a Synapse tool plugin.

### Changed
- **ChatGPT-owned squad launches prefer the actual ChatGPT web worker path** instead of silently falling
  back to a CLI runtime; durable worker records stay distinct from the coordination-session lease used by
  one live execution.
- **Same-project AI collaboration is deduplicated** around one auto-managed room: a second live root AI
  reuses/creates the canonical project room, child workers join the existing room, and newcomers receive
  separate per-peer catch-up packets instead of flattened ambiguous history.
- **AI discoverability now advertises worker, setup, canonical-chat, and thread-presence REST routes** via
  `/api/v1/ai/context`, including the bootstrap -> begin -> heartbeat -> finish protocol.

### Fixed
- **Generic MCP forwarding accepts nested downstream arguments reliably** -- `synapse_call_mcp_tool` now
  explicitly permits free-form nested `arguments` and offers scalar `arguments_json` for connector hosts
  that reject arbitrary nested keys before dispatch. This unblocks Playwright/Reflex proxy calls without
  weakening normal clients.
- **Setup-browser launch is idempotent** -- repeated setup clicks detect a process already using the
  dedicated Synapse ChatGPT profile and return `already_running` instead of spawning another browser.
- **Browser companion placement no longer pollutes the tool registry** -- its Chrome `manifest.json` is no
  longer scanned as a Synapse ToolManifest.
- Corrected migration 039's header so its file and documentation agree on the migration number.
- **Worker conversation URLs are DB-unique once assigned** -- migration 040 adds a partial unique index and the update path returns a clean conflict pointing to the existing durable worker instead of allowing two rows to claim one ChatGPT conversation.

### Verification
- Full mounted-route audit: **328 routes, zero duplicate method/path pairs**; migration-number audit: zero duplicates.
- Live SQLite identity audit: zero duplicate thread keys, current worker/work-item links, worker URLs,
  external work-group keys, browser observations, or canonical project metadata rows.
- Production renderer + Electron build: **PASS**. Full daemon suite and refreshed UI proof are recorded
  before the release commit.

## [0.1.202] - 2026-08-27

### Added
- **Stock Hunter ships as a native portable Synapse skill + quick action** -- a reusable evidence-backed
  equity-research funnel for broad price screening, scalable fundamentals/valuation screening, and
  deep candidate scoring across growth, quality, valuation, revisions, dislocation, catalysts, insiders,
  technicals, and explicit risk penalties. BUY is gated on evidence coverage plus primary-fundamental
  validation; breadth/fundamental convenience data is explicitly not treated as a final recommendation.
- **Deterministic Stock Hunter helpers** (`stock_hunter.py`) provide `prices`, `fundamentals`, and `score`
  commands with no third-party Python dependency, documented candidate/source/scoring contracts, and
  Synapse skill-pack discovery through the existing AI Bundles surface.

### Fixed
- **Portable-skill catalog tests now support more than one bundled skill** instead of hard-coding Super
  Internet Digger as the only possible package. Stock Hunter has its own deterministic evidence-gating test.
- **`scripts/version-bump.ps1` now edits only the package version string** instead of reparsing and
  reserializing `package.json`, eliminating fake Unicode/formatting diffs while retaining the CRLF-safe
  three-source consistency verification added in v0.1.201.

### Verification
- Skill-pack / AI-bundle / quick-action gate: **26 passed**.
- Version-bump raw-preservation regression: **1 passed**.

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
  wrong; the test asserting `tests == ""` now asserts the stronger property inst