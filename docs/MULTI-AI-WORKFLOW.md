# Multi-AI workflow — coordination protocol + audit

**Audience:** every AI coder that edits Synapse — Claude Code, Codex CLI,
GitHub Copilot CLI, Cursor, or a human. Read this *in addition to*
[`AGENTS.md`](../AGENTS.md) (conventions) and [`PROGRESS.md`](../PROGRESS.md)
(where the project is).

**Why this exists:** Justin runs more than one AI coder against this repo,
sometimes at the same time (e.g. Claude committing while Codex edits the
profile feature). `AGENTS.md` assumes one AI per session. This doc covers
the part that breaks when two agents share a working tree — so the project
moves forward *without causing mess*.

---

## The one rule that prevents 90% of the mess

**Never commit a working tree you didn't just verify compiles.** Another
agent may have a half-written file on disk this second. Before any
`git add`/`commit`:

```
npx tsc --noEmit -p tsconfig.json          # renderer
npx tsc --noEmit -p electron/tsconfig.json # electron
cd daemon && python -m pytest -q           # daemon
```

All three green → the tree is coherent right now → safe to snapshot. Red →
**stop**: someone is mid-edit, or you broke something. Do not commit. A
broken intermediate file fails `tsc`/`pytest` loudly, which is exactly the
tripwire you want.

Re-run the *fast* gate (renderer `tsc`, ~15 s) one more time immediately
before `git commit` to shrink the race window between "I verified" and "I
committed."

---

## Before you start editing

1. **Read `PROGRESS.md`** (current version, milestone, what's in flight).
2. **Check the working tree for another agent's footprints:**
   ```
   git status --short
   ls *.pid 2>/dev/null        # a *.pid means another agent's daemon is live
   ```
   - A `.codex-daemon.pid` (or similar) means a Codex/other session has a
     daemon running. **Don't kill it.** Don't spin a second daemon on
     7878 — attach to the running one or use a sandbox port + data dir.
   - Uncommitted changes you didn't make → another agent is mid-task. Pick
     a **different file lane** (see below) or coordinate via the scratchpad.
3. **Pick a lane.** Loosely partition by area so two agents rarely touch the
   same file at once:
   - daemon routes/models (`daemon/synapse_daemon/`)
   - renderer pages/components (`renderer/`)
   - electron shell (`electron/`)
   - docs/ADRs (`docs/`, `*.md`)

   If you must edit a file another agent is actively in, leave it and say so
   in your summary — don't race the same file.

---

## Before you commit

1. **The three gates above are green.**
2. **Stage your lane, not the world.** `git add -A` will sweep up another
   agent's half-written files and runtime junk. Prefer staging the files you
   changed. If you do use `-A`, immediately `git status --short` and
   `git reset HEAD <path>` anything that isn't yours.
3. **Never commit another agent's scratch.** Leave untracked:
   - `*.pid` (live daemon PIDs) — gitignored
   - `.playwright-mcp/`, screenshots (`*.png` at repo root) — verification scratch
   - `found_bugs.md` / ad-hoc notes another agent is writing
   - `installer/daemon-dist/`, `*.exe` — build output, gitignored
4. **Secret scan the diff** (`git diff | grep -iE "(password|secret|api[_-]?key|token)\s*[:=]\s*['\"][A-Za-z0-9_/+-]{16,}"`).
   Synapse stores nothing sensitive in source; a hit is a mistake.
5. **Attribution.** Commit author stays `jross32 <justinwross32@gmail.com>`
   (never change git config). Add a co-author trailer so we can tell which
   AI did what:
   ```
   Co-Authored-By: Codex <noreply@openai.com>
   Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
   ```
   If you committed another agent's uncommitted work, credit both: them as
   author-in-spirit (trailer), you as the verifier (trailer).

---

## Collision-prone resources — allocation rules

These are the things where two agents independently "take the next one" and
clobber each other. **Check the current max before you claim.**

| Resource | Hazard | Rule |
|---|---|---|
| **DB migrations** `daemon/synapse_daemon/migrations/NNN_*.sql` | Both grab `010` | `ls migrations/` first. Claim `max+1`. If you see your number got taken on rebase, renumber yours — **never edit a shipped migration** (Contract #9). |
| **Version string** | Both bump to the same `X.Y.Z` | During a `-dev` wave we stay on `X.Y.Z-dev` and do **not** bump per-commit (see "Version policy" below). Bump only on a named release. |
| **ADRs** `docs/adr/NNNN-*.md` | Two `0010-` files | `ls docs/adr/` first; claim `max+1`. |
| **Port 7878** | Two daemons fight for it | One daemon per machine. Tests + sandboxes use a temp port + temp `--data-dir`. |
| **`renderer/lib/generated-types.ts`** | Hand-edits drift from Pydantic | Never hand-edit. It's generated from daemon models (Contract #8). |

---

## Version policy (clarifies AGENTS.md Rule #1)

AGENTS.md Rule #1 says "every commit bumps a version." In practice, during a
multi-commit `-dev` wave with more than one agent, per-commit bumps collide
and churn. **Reality, codified:**

- **During a `-dev` wave:** stay on the current `X.Y.Z-dev`. Commit freely
  without bumping. Keep `package.json`, `pyproject.toml`, and
  `daemon/synapse_daemon/__init__.py` in sync at the *same* `-dev` value.
- **On release:** run `scripts/version-bump.ps1` once to move `X.Y.Z-dev` →
  `X.Y.Z`, tag, then open the next `-dev`.

This is what the last several commits actually did (all stayed
`0.1.36-dev`). Following the literal per-commit-bump rule with two agents is
the *cause* of version collisions, not the fix.

---

## Canonical patterns (use these, don't reinvent)

- **Resolving bundled resources** (tools/, templates/, mobile/, docs/):
  use `daemon/synapse_daemon/runtime_paths.py`
  (`repo_root()`, `bundled_tools_dir()`, `resources_root()`, …). **Never**
  write a bare relative `Path("tools")` — it resolves against the daemon's
  CWD, which is `electron/` when Electron spawns it, so the lookup silently
  finds nothing. This bug bit both Claude and Codex independently; the
  resolver is the cure.
- **Cross-AI session memory:** `.synapse-ai-context.md` per project
  (ADR-0006). Append a short handoff note when you finish so the next agent
  — possibly a different CLI — picks up the thread.
- **Error envelope, status enum, audit log, timestamps:** Contracts #4, #2,
  #11, #24 in AGENTS.md. Don't invent parallel shapes.
- **AI Council Review — don't work alone (ADR-0023).** For meaningful work,
  run a **pre-work council** (a small panel of reviewers critiques your plan
  before you build) and a **post-work council** (they hunt bugs/gaps before
  you claim done); synthesize their prioritized findings, revise, repeat.
  **Adaptive size:** 2 reviewers for tiny tasks, 3–5 for a normal feature/fix/
  doc, 6–10 only for complex/risky/architectural/benchmark/security/automation
  work. Lenses: Architect · Skeptic · Tester/QA · Security · UX/UI ·
  Performance/Token-Efficiency · Product · DevOps · MCP/Tooling · Documentation.
  Ask for **critical / important / optional** findings only; you synthesize,
  you don't blindly follow. **Mechanism:** run the reviewers yourself as
  parallel/sequential prompt passes (the always-available path) — **do NOT
  spawn reviewer squad-workers on Windows** until the multi-arg `.CMD`
  squad-launch bug is fixed. Launchable as the `ai-council-review` quick-action.

---

## Audit findings (2026-06-21) — current cross-AI risk

A read-only sweep for "what causes mess when two agents share this tree":

| Finding | Severity | Status |
|---|---|---|
| Version-bump rule (AGENTS #1) contradicted reality (8 commits, 0 bumps) | Med — an agent following the letter collides | **Resolved** by the Version policy section above |
| Migration numbering has no allocation rule (001–009 sequential) | Med — two agents grab `010` | **Resolved** by the allocation table |
| No concurrent-edit / scratch-hygiene protocol | High — commit races, junk commits | **Resolved** by this doc + gitignore (`*.pid`, `.playwright-mcp/`, `installer/daemon-dist/`, `*.exe`) |
| `runtime_paths.py` exists but a few modules still default to relative paths (`__main__` DEFAULT_TOOLS_DIR, `secrets.py` `Path("data")`) | Low — fallbacks, work in practice | Open — migrate remaining defaults to `runtime_paths` opportunistically |
| `manifest_watcher.py:59` shows `Path("tools")` | None — docstring example only, real wiring uses the resolved dir | Verified non-issue |

No data-loss or correctness collisions found. The tree is multi-agent-safe
as long as the gates + lane discipline above are followed.

---

## TL;DR for a fresh agent

1. `PROGRESS.md` → know where we are.
2. `git status` + `ls *.pid` → know who else is here.
3. Pick a lane away from active edits.
4. Build it. `tsc` ×2 + `pytest` green before you stage.
5. Stage your lane; leave scratch + others' files untracked.
6. Commit as `jross32` with a co-author trailer naming your model.
7. Append a handoff line to the project's `.synapse-ai-context.md`.
8. Update `PROGRESS.md` / `CHANGELOG.md` so the next agent isn't guessing.
