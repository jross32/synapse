# CLAUDE.md — Synapse

Claude Code entry point for the Synapse repo. **The canonical, all-AI contract is
[`AGENTS.md`](./AGENTS.md) — read it first.** It covers repo layout, code style, the non-negotiable
commit rules (version bump + CHANGELOG + PROGRESS + docs sync, commit *and push* per logical change),
the 28 Design Contracts, file sensitivity (Fragile files), and the API-first "build for the AI" rule.

Before you start: run `pwsh -NoProfile -File scripts/preflight.ps1` (prints the next-free ADR/migration
numbers to claim + your uncommitted footprint), and read [`PROGRESS.md`](./PROGRESS.md) to know where
the project is.

## AI Working Agreement (applies to you)

Every AI that touches this repo follows the **AI Working Agreement** in
[`AGENTS.md`](./AGENTS.md#ai-working-agreement--every-ai-every-session) — in every session, even from a
plain terminal outside Synapse:

1. **Check in** via the coordination API so you don't collide with another AI:
   `GET /api/v1/coordination/snapshot` (see who's working) → register a session → claim a file lane
   before editing (ADR-0024).
2. **File improvement ideas** you notice while working to the review inbox:
   `POST /api/v1/review/proposals` with `project_id:"synapse-self"` (ADR-0025) — instead of silently
   dropping them or rabbit-holing into them.

The daemon is on `127.0.0.1:7878`; the token is in `data/auth-token` (`X-Synapse-Token` header). Exact
request shapes are in AGENTS.md.

When another AI (Codex, Copilot, a local model) may be editing concurrently, follow
[`docs/MULTI-AI-WORKFLOW.md`](./docs/MULTI-AI-WORKFLOW.md): stage only your own files, never
`git add -A`, rebase before pushing.
