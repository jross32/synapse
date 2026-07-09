# GitHub Copilot instructions — Synapse

**Read [`AGENTS.md`](../AGENTS.md) first — it is the canonical contract for every AI working this repo**
(Claude, Codex, Copilot, local models). It covers repo layout, code style, the non-negotiable commit
rules, the 28 Design Contracts, Fragile files, and the API-first "build for the AI" rule.

## AI Working Agreement (applies to you)

Follow the **AI Working Agreement** in
[`AGENTS.md`](../AGENTS.md#ai-working-agreement--every-ai-every-session) in every session, even when
editing from outside Synapse:

1. **Check in so agents don't collide** — `GET /api/v1/coordination/snapshot` (who's working) +
   register a session + claim a file lane before editing (coordination API, ADR-0024).
2. **File improvement ideas** you spot while working to the review inbox —
   `POST /api/v1/review/proposals` with `project_id:"synapse-self"` (proposals, ADR-0025) — instead of
   silently dropping them.

Daemon: `127.0.0.1:7878`, token in `data/auth-token` (`X-Synapse-Token` header). Exact request shapes
are in AGENTS.md.

When another AI may be editing concurrently, follow
[`docs/MULTI-AI-WORKFLOW.md`](../docs/MULTI-AI-WORKFLOW.md): stage only your own files, never
`git add -A`, rebase before pushing.
