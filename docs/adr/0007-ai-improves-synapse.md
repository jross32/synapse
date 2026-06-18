# ADR-0007 — AI-improves-Synapse via REST endpoints

Date: 2026-06-18
Status: Proposed (gated on user "go" per phase)
Supersedes: —
Related: ADR-0002 (workbench), ADR-0006 (project objectives),
         `plans/how-is-it-that-staged-meteor.md`

## Context

Synapse's stated stance since v0.1.29 is **"built for AI agents
too"** — a Claude / Codex / Copilot session running in a Sessions
tab is treated as a first-class user. Today that promise is mostly
*read-only*: an AI can introspect projects, tools, audit, transcripts
through `GET /api/v1/ai/context`. It can't easily *act on* Synapse
itself.

The user's wishlist explicitly asked: *"how can the AI when I'm
using it in the sessions be more impactful to the synapse app itself
in editing it, making improvements, monitoring it, fixing bugs"*.
The clarifying-question answer (Q4) was **"REST endpoints AI can
call"**.

This ADR scopes a small, audited, token-guarded set of
`/api/v1/synapse-dev/*` endpoints that let any in-session AI run
the developer loop (test → commit → PR) on the Synapse repo itself,
plus a `/ai/health-report` endpoint that lets the AI diagnose what's
broken before it acts.

## Decision

Four sub-phases. **C1 must ship before any of C2–C4** because the
quick-action template is the documented entrypoint.

### C1 — Bundled "Improve Synapse" quick-action (templates only)

The smallest, lowest-blast-radius starting point. Ships **before**
any new daemon code.

A new file `templates/quick-actions/improve-synapse.json` whose
prompt:
- Explains the Synapse repo layout (citing CLAUDE.md + AGENTS.md +
  PROGRESS.md).
- Names the autosave commit pattern (`node autosave.js "message"`).
- Names the test pattern (`pytest` + `npx tsc --noEmit`).
- Names where ADRs live and the naming pattern.
- Names where the IDEAS list + AUDIT punch list live so the AI can
  pick something user-prioritised.
- Sets the bar: "Make one small, type-checked, suite-clean
  improvement. Commit only if all checks pass. Otherwise leave a
  draft note in IDEAS.md for the user to triage."

Spawns Claude (per the bundled-template default) in the Synapse
repo's working copy. The `cwd` ships via the quick-actions launcher's
existing `_ensure_scratch_project` logic — we'd add a second auto-
project `synapse-self` whose path resolves to the actual Synapse
checkout. (Same lazy-create pattern as `imported-chatgpt` from
ADR-0003 Phase E.)

**Honest scope:** this template does NOT yet expose the C2 endpoints.
The AI does the developer loop the same way a human does — through
the shell. C2 is purely an acceleration.

### C2 — `/api/v1/synapse-dev/*` developer-loop endpoints

All token-guarded. All audited (`synapse_dev.{test,commit,pr,...}`).
All require an explicit `SYNAPSE_DEV_ENABLED=1` env gate on the
daemon — opt-in so a stray AI can't act on a user who hasn't
enabled the feature. The gate is read on each request, not at boot,
so the user can flip it from a Settings UI later.

#### `POST /api/v1/synapse-dev/test/full`

Body: optional `{ python_args?: [string], tsc_args?: [string] }`.

Runs `python -m pytest` + `npx tsc --noEmit` in parallel.
Streams output via the existing process-manager primitives.
Returns:

```jsonc
{
  "ok": true | false,
  "pytest": { "passed": N, "failed": N, "skipped": N, "duration_s": F, "tail": "..." },
  "tsc":    { "ok": bool, "duration_s": F, "errors": ["..."] }
}
```

Caps `tail` at 8 KB so a million-line output doesn't blow context.

#### `POST /api/v1/synapse-dev/test/file`

Body: `{ path: string }`. Path must resolve under `daemon/tests/` —
defensive against path traversal. Same response shape as above
without the `tsc` block.

#### `POST /api/v1/synapse-dev/commit`

Body: `{ message: string, files?: [string] }`.
- `message`: required. Maximum 1 KB. Pre-pended with a
  `[AI]` marker so the user can audit which commits the AI made.
- `files`: optional explicit allowlist. Without it, equivalent to
  `git add -u` (staged tracked changes only — no new files unless
  named).

Wraps the existing `autosave.js` so the secret-check + co-author
rules from CLAUDE.md still run.

Refuses if:
- Working tree has unstaged user changes the AI didn't author
  (detect by reading reflog or git status).
- Branch is `main` AND no PR exists yet (require staging via `pr`).

#### `POST /api/v1/synapse-dev/pr`

Body: `{ title, body, base?, draft? }`.
Uses `gh pr create` under the hood. Requires `gh auth status` to be
green (the daemon checks once at startup; refuses if the check fails).

Audited with the full title + the base branch.

#### Common refusal envelope

All four endpoints return `403 Forbidden` with code
`synapse_dev.disabled` when the env gate is missing. The error body
explicitly mentions setting `SYNAPSE_DEV_ENABLED=1` so a misconfigured
session sees the right next step.

### C3 — `/api/v1/ai/health-report`

A single endpoint a session can poll to understand the host's state.
Returns:

```jsonc
{
  "version": "0.1.36",
  "uptime_s": 12345,
  "daemon": { "schema_migration": 7, "contracts_honoured": [1..28] },
  "projects": { "total": 21, "launched": 1, "errored": 0 },
  "audit_tail": [...last 5 'error' rows...],
  "tests": { "last_run_ok": bool, "last_run_at": "...", "passed": N },
  "git": { "branch": "main", "head": "...", "ahead": N, "behind": N }
}
```

No auth beyond the token-guard. The AI calls
`curl $SYNAPSE_API/ai/health-report` from inside its PTY and decides
what to do next.

Caches the **tests** block until the next `synapse_dev.test.*` call
so the AI doesn't have to wait 60 s on every poll.

### C4 — MCP surface (stretch)

The C2 endpoints fronted as an MCP server. Lets Claude Code / Codex
clients **outside** Synapse call them too (e.g. a session running
against a remote machine). Schema mirrors the REST. Each tool is
read-only by default; the `[D]` flag turns on for `commit` + `pr`.

## Consequences

### Positive
- The AI can finally "do the developer loop" — run tests, commit a
  fix, open a PR — without typing the exact same commands a human
  would. Concrete acceleration.
- Token-guard + env-gate + audit + `[AI]` commit marker mean every
  AI action is auditable + reversible.
- The "improve Synapse" quick-action ships standalone (C1) — no new
  daemon code; the AI just does it through the shell. C2 is purely
  for speed.
- The bundled `synapse-self` project ties into the Phase B
  objectives tree naturally: "Ship ADR-0008" becomes a real objective
  the AI can pick up.

### Negative / honest trade-offs
- **`gh` is a hard dependency for C2.** No `gh` → no PR endpoint.
  Reasonable: the user must already have it for their own workflow.
  Document in `AGENTS.md`.
- **The PR endpoint is power.** A misconfigured opt-in could spam
  the user's repo. The env-gate is the brake; we surface a clear
  "AI-issued PR" badge in the audit log row.
- **C3's `tests` block is a real cache surface.** If a PR is in
  flight and the AI polls, it might see stale "tests passing"
  signal. Invalidate aggressively on any `synapse_dev.*` action.
- **MCP (C4) is a stretch.** Don't promise it; just leave a TODO.

## Detailed design (locked at acceptance)

### Env gate

`SYNAPSE_DEV_ENABLED` MUST be exactly `"1"` to enable C2 endpoints.
Anything else (missing, `"0"`, `"true"`, `"yes"`) refuses.
Decision: be strict so users can't accidentally enable via a casual
shell var.

Settings UI gets a row in the Network/About sections later:
"Allow AI-driven developer actions" (toggle), which writes
`boot-config.json` `dev_enabled: bool` — daemon reads + sets the env
internally. (Same pattern as the LAN-bind toggle from Phase A.)

### Audit fields

Each `synapse_dev.*` audit row stores:
- `action`: e.g. `synapse_dev.commit`.
- `details.message` (commit) / `details.title` (pr) / `details.path`
  (test/file).
- `details.result`: ok / failure summary.
- `source`: always `auto` (this is the AI calling).

### Test-output truncation

8 KB tail. The full output is written to
`<data-dir>/synapse-dev/test-<run-id>.log` so the AI can fetch the
rest via a follow-up call:

`GET /api/v1/synapse-dev/test/{run_id}/tail?offset=N&limit=N`.

### Commit guardrails

The `commit` endpoint refuses if:
- `message` contains the literal string `--no-verify` (no hook
  skipping).
- `message` mentions `force` or `reset` (no destructive ops by
  message hint).
- Files outside the repo root are specified.

These are belt-and-suspenders on top of the existing autosave script.

## Status

Proposed. Implementation does NOT start until the user gives the go
on C1 (the template + `synapse-self` auto-project — small ship,
verifiable). C2 + C3 each get their own go.

C4 (MCP) is a stretch — explicit second go after C2 + C3 prove out.

## Verification plan

### C1
- The `synapse-self` auto-project lazy-creates on first quick-action
  launch with the correct path (resolved via
  `Path(__file__).resolve().parent...` from the daemon package).
- The quick-action template loads cleanly via the v0.1.34 loader;
  bundled-templates test gains `improve-synapse` in
  `_EXPECTED_BUNDLED`.
- Live: click the action → Claude opens in the Synapse repo cwd
  with `PROMPT.md` populated.

### C2
- New `daemon/tests/test_routes_synapse_dev.py`: env-gate test
  (refuses without `SYNAPSE_DEV_ENABLED=1`); test/full with a
  stubbed subprocess returns the structured shape;
  commit refuses outside-repo paths.
- Path-traversal test on `test/file`.
- Audit row presence for each action.

### C3
- Health report endpoint returns the expected shape.
- Cache invalidation test.

### C4 (if pursued)
- MCP server registers each tool; SDK round-trip on a real `claude
  mcp test` call.
