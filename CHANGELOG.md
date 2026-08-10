# Changelog

All notable changes to Synapse will be documented in this file.
Format roughly follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
This project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Every commit must append an entry under the in-progress version header.

---

## [Unreleased]

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




