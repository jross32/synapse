# Changelog

All notable changes to Synapse will be documented in this file.
Format roughly follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
This project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Every commit must append an entry under the in-progress version header.

---

## [Unreleased]

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
