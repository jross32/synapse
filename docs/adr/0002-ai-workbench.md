# ADR-0002 — AI Workbench

Date: 2026-06-08
Status: Proposed
Supersedes: —
Related: ADR-0001 (tool marketplace)

## Context

The user wants AI coding agents inside Synapse — specifically:

1. Launch `claude` / `codex` (and other AI CLI coders) from inside the app and
   interact with them in their own tab, "just like talking to me".
2. An **AI workspace** tab where the AI itself can operate: workflows,
   UI components, backend / frontend tools, deep-research tools, "tools that
   AI can use itself so it does stuff better and faster".
3. Re-use the user's existing Claude / Codex credentials.
4. Maybe integrate VS Code's built-in AI coders.
5. Sign in with Apple / Google.

This ADR scopes those asks honestly, decides what we **can** build, what we
**won't**, and stages the work so each phase is verifiable on its own.

## Decision

Three phases, each behind an explicit go-ahead from the user. Phase A is
proposed for `v0.1.25`–`v0.1.27`; B and C are sketched, not promised.

### Phase A — CLI passthrough (v0.1.25–v0.1.27)

Spawn `claude`, `codex`, or any configured AI CLI from inside Synapse as a
**fully interactive PTY session**, rendered in a real terminal panel in the
renderer. The user types, the CLI streams back. Nothing else. This is the
useful minimum and the foundation for everything else.

**New daemon primitive: `pty.spawn`.**

`process.spawn` (v0.1.22) is one-shot — argv in, stdout out, exit code,
done. `pty.spawn` is the same idea but **interactive**:

- Spawn the child under a real pseudo-terminal (`pywinpty` on Windows,
  `pty` on POSIX) so ANSI escape codes, colour, raw mode and line editing
  all work.
- Hold a long-running session identified by a server-generated `session_id`.
- Stream the child's output to subscribers over the existing WebSocket bus
  as `v1.pty.<session_id>.output` events (chunks of bytes).
- Accept input over a new daemon endpoint `POST /api/v1/pty/{session_id}/input`
  (or as a WebSocket message; REST is simpler and matches the rest of the
  surface).
- Resize on `POST /api/v1/pty/{session_id}/resize` with `{cols, rows}`.
- Audit `pty.spawn` / `pty.close` like every other state change (Contract #11).
- Live on the existing managed-process invariants (Contract #6 — orphan
  reconciliation kills surviving PTY children on next boot).

`pty.spawn` is a *new tool primitive* (`tools_primitives.py`), so a manifest
can declare:

```json
{
  "id": "claude",
  "name": "Claude Code",
  "description": "Run Claude Code in a session tab.",
  "icon": "sparkles",
  "actions": [
    {
      "id": "open",
      "label": "Open session",
      "primary": true,
      "primitive": "pty.spawn",
      "params": {"argv": ["claude"]}
    }
  ]
}
```

— and the user installs it from the marketplace the same way they install
`open-synapse-docs` (ADR-0001 step 4 from `v0.1.24`).

**New page: Coders (or a new section on Tools — TBD).**

Renders one tab per live PTY session, plus a list of installed AI-coder
tools as a "launch new session" rail. Each session tab embeds an
**xterm.js** terminal (`xterm` + `xterm-addon-fit` on npm; ~200 kB, no
native deps). The terminal is bound to the session's WS event stream.

**Auth: inherit, don't replace.**

`claude` and `codex` already authenticate against the user's account by
reading their own cached credentials (`~/.claude/`, `~/.codex/`). When the
Synapse daemon spawns them as a child of the user's own desktop session,
they inherit those credentials automatically. We add **nothing**. If the
user hasn't logged into Claude on this machine, the CLI itself walks them
through it inside the PTY, exactly as it would in a regular terminal.

This is the right move: we don't store anybody's API keys, we don't
re-implement Anthropic / OpenAI's auth flow, we don't introduce a new
class of secret to leak. The auth surface is the same one the user
already trusts.

**Built-in tools shipped this phase:**

- `claude` manifest (declarative; spawns `claude` if on PATH).
- `codex` manifest (declarative; spawns `codex` if on PATH).
- Bundled-sample registry gets both as `tier: declarative`,
  `manifest_inline` so they install via the existing Browse → Install flow.

**What "verified" looks like for Phase A:**

- Click *Install* on `claude` in the marketplace; tab appears.
- Click *Open session* on the new card; a terminal panel opens, runs the
  real `claude` binary, the user types prompts and gets responses.
- Daemon-killed sessions surface a closed-tab indicator with a Restart
  button. Crashes don't leak: orphan reconciler cleans surviving PTY
  children on boot (Contract #6).

### Phase B — AI Workspace (v0.1.28+)

A **project-scoped launchpad**. From any registered project (Apps page →
tile), the user clicks *Open in workbench* and lands on a workspace view
that is:

- A terminal session pre-`cd`'d into the project's working directory.
- Pre-selected coder (Claude / Codex / whatever was last used here).
- Session history saved per-project — closing and reopening picks up where
  it left off (the *transcript* is replayed; the PTY itself doesn't
  resume — that's how CLIs work).
- Side panel with project metadata: launch command, expected port,
  recent logs (from the existing log capture in Contract #3).

This is the "AI workspace tab" — it isn't a separate AI universe, it's a
better launchpad for the Phase A capability, scoped to one project. The
useful framing: **the AI sits inside your project, not next to it.**

What this phase **does not** add:

- An "AI uses tools itself" runtime. Claude Code and Codex already have
  their own tool-use loops; Synapse hosts them, it doesn't re-implement
  one. The "deep research / backend / frontend tools" the user mentioned
  are tools the *AI agent* can already call — Claude Code has its full
  toolset when launched from inside Synapse just as much as outside.
- Workflows as a separate object. If we need them later, they're another
  manifest tier (`workflow` actions invoking a sequence of primitives) —
  but that's its own ADR.

### Phase C — Account sign-in (separate ADR-0003, not promised)

The user asked for *Sign in with Apple / Google*. That is a real OAuth
refactor of the current pairing-code auth:

- Register a Google OAuth 2.0 client and an Apple Sign-in Service ID;
  user-side this means a developer account on each provider and
  configured redirect URIs.
- Replace `paired_devices` with a `user_accounts` table; map external
  subject IDs to local sessions.
- A redirect endpoint on the daemon, a callback handler, JWT verification
  against each provider's JWKS.
- Migration story: existing pairing-code devices keep working;
  account-linked devices are an *upgrade*, not a replacement.

This is many days of careful work and has external provisioning steps the
user has to do themselves. **It's a separate ADR-0003** and gets built
when the user explicitly says so. Not happening in the current run.

## Consequences

### Positive

- `pty.spawn` is reusable beyond AI coders: any interactive CLI (`python`,
  `node`, `psql`, `gh repl`, …) can be hosted in a Synapse tab once we
  ship it. The Coders page becomes a *Sessions* page in the natural next
  step.
- Marketplace stays the install path: `claude` + `codex` ship as
  declarative manifests in the bundled registry, validating ADR-0001 with
  real-world tools.
- No new secrets storage. We never hold the user's Anthropic /
  OpenAI / Apple / Google credentials. The PTY child handles its own auth
  against its own provider.

### Negative / honest trade-offs

- xterm.js is a real dependency (`xterm`, `@xterm/addon-fit`). ~250 kB
  gzipped. Worth it for terminal fidelity.
- PTY on Windows requires `pywinpty` (winpty bindings). It's a wheel,
  installs cleanly, but it's a new daemon dep. POSIX uses stdlib `pty`.
- VS Code's built-in AI coders (Copilot, Continue, etc.) **cannot** be
  driven through this. They're extensions in VS Code's renderer; there's
  no CLI hook. The user's existing **Open in VS Code** tile button is the
  right answer for that — let VS Code be VS Code.
- We're not building "an AI workspace where the AI itself uses tools".
  That's Claude Code's job; we host it. The AI **already** has tools
  because it's still itself.

## Status of v0.1.25 work

This ADR is approved into `docs/adr/` (this commit). The Phase A
implementation does **not** start until the user explicitly says go.

When go is given, the proposed split:

- `v0.1.25` — `pty.spawn` primitive in the daemon + REST endpoints +
  tests. No UI yet. The CLI can already be driven via curl.
- `v0.1.26` — xterm.js + a `<SessionTerminal>` component + the new
  Coders / Sessions page wired to v0.1.25's API.
- `v0.1.27` — `claude` and `codex` bundled-sample manifests, marketplace
  install path proven end-to-end.

Phase B (Workspace) starts only after Phase A is fully shipped and used
for at least a week. Phase C (account auth) is on hold until ADR-0003.
