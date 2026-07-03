# Methodology

## What was tested

Both sides were given the same spec for a small static site for a fictional makeup/beauty
business, "Glow Studio": hero + Book Now button, 4+ services with prices, an about blurb,
a client-side-only contact form, and a footer. Plain HTML/CSS/JS, no build step, no backend.
The spec was deliberately small to keep the benchmark itself cheap to run.

## Without Synapse (baseline)

A single, fresh, general-purpose Claude agent, given the spec in one message, with an explicit
instruction to ignore any repo convention files and treat the request as brand-new with no
prior project history — the "just ask a chatbot" experience. No persistent plan, no memory
across turns beyond the one session, no squad, no review pass.

- Runtime: general-purpose Claude agent (single subagent invocation)
- Output dir: `apps/without-synapse/`
- Started (UTC): 2026-07-03T15:13:54Z
- Finished (UTC): 2026-07-03T15:15:41Z (106.584s reported duration)
- Total tokens: **51,314** — self-reported by the harness for the whole session (not estimated)
- Tool calls: 7

## With Synapse

A real Synapse project (`benchmark-with-synapse`) was registered against the daemon
(`POST /api/v1/projects`), and a real Claude Code worker was launched inside it through
Synapse's documented workbench launcher (`POST /api/v1/projects/{id}/workbench`), which spawns
the same `claude` CLI Synapse uses for its Agent Squads feature, `cd`'d into the project's
working directory.

**A note on what changed from the original plan, in the interest of only reporting what's
true:** the original plan was to launch this through the full Agent Squads pipeline
(`agent-squads` → `agent-work-items` → `/launch`). Doing that surfaced a real, reproducible bug:
on this Windows machine, any PTY spawn with more than one `argv` element for a `.CMD`-shimmed
runtime (`claude.CMD`, likely also `codex.CMD`/`copilot.CMD`) fails — the child process never
receives its arguments and cmd.exe reports `'<the second argv item>' is not recognized as an
internal or external command`. Since the Agent Squads launch path always appends
`--mcp-config <path>` for the `claude` runtime whenever the user has any MCP server enabled
(which this machine does), every squad-launched `claude` work item on this machine currently
fails silently this way — the work item's `pty_session_id` process exits immediately, but its
status is left `running` because nothing that path checks the exit code as a failure signal.
That work item (`eef21d828e93`) and its dead session are preserved in the squad history as
honest evidence of the failure; the squad was stopped afterward for cleanup.
A follow-up task has been filed to fix the root cause in the daemon's Windows PTY spawn path.

This is exactly the kind of finding that matters here: **the benchmark is honest about a
Synapse bug it hit, not just about how well the resulting app scores.**

The workaround used to still get a real Synapse-driven build for this benchmark: the workbench
launcher spawns `claude.CMD` with **zero** extra argv (Synapse auto-picks a bare runtime when no
`argv` is given), which sidesteps the multi-arg bug. The prompt was then sent as real PTY input
(`POST /api/v1/pty/{id}/input`) wrapped in a bracketed-paste sequence so the terminal UI treated
it as one paste instead of individual keystrokes — a plain single write without that wrapping
was dropped/garbled by the terminal twice before this was diagnosed (see `raw-logs/` for the
failed attempts). This is still a first-class, documented Synapse AI-operator surface
(`AGENTS.md` → "AI-facing surfaces"), a real project, a real audit trail, and the exact `claude`
binary Synapse's Agent Squads use — just not the multi-arg squad launch endpoint specifically,
because that endpoint is currently broken on Windows in this configuration.

- Runtime: Claude Code CLI (same binary/account as the baseline), launched via Synapse's
  project workbench, inside a real Synapse project directory
- Output dir: `apps/with-synapse/`
- Synapse project: `benchmark-with-synapse` (`POST /api/v1/projects`)
- PTY session: `2df6ce5ad237`
- Prompt actually accepted (UTC): 2026-07-03T15:33:33Z
- See `results/tokens/with-synapse.md` for completion time + token numbers, captured from
  Claude Code's own local session transcript for this run (real usage, not estimated).

## Quality scoring

Both finished apps were scored across independent dimensions (UI/UX, visual design, code
quality/architecture, backend/functional correctness, usability & accessibility, and an
adversarial bug-hunt pass) by independent judge passes rather than a single aggregate number.
See `results/quality/` — one file per dimension, plus `summary.md`.

## Honesty notes

- This is a single run per side, not a repeated/averaged benchmark — Synapse's own benchmark
  engine (`daemon/synapse_daemon/benchmarks.py`) supports repeat counts and confidence labels
  for exactly this reason; a single run is directional, not statistically strong.
- Token counts come from two different reporting mechanisms (the baseline's harness-level
  self-report vs. the with-Synapse side's Claude Code session transcript) — both are real,
  reported numbers, not estimates, but they're not guaranteed to be computed identically token
  for token. Treat the token comparison as approximate, not to the exact token.
- Nothing in this benchmark was fabricated or hand-waved. Where something didn't work as
  planned (the squad-launch bug), that's documented above rather than papered over.
