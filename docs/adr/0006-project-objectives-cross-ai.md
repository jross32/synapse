# ADR-0006 — Project objectives + cross-AI session continuity

Date: 2026-06-18
Status: Proposed (Phase A polish shipped in v0.1.36; this ADR gates the
        objectives + NOTES-file implementation)
Supersedes: —
Related: ADR-0002 (workbench), ADR-0003 (workbench expansion incl.
         transcripts), `plans/how-is-it-that-staged-meteor.md`

## Context

The user's wishlist (captured in
`plans/how-is-it-that-staged-meteor.md`) included two intertwined asks
that need real schema to ship cleanly:

1. **A project-centric workflow.** Today Synapse can launch a project
   (Apps tab) and start a coder session against it (Sessions tab), but
   there's no concept of "what am I working on inside this project."
   Users want a hierarchical objectives tree per project — parent
   tasks + child tasks + a saved description — so they can come back
   to a project, see what was on the list, click an objective, and
   resume.

2. **Cross-AI session continuity.** Switching between Claude and
   Codex (and now Copilot, per Phase A) currently loses context — the
   new CLI starts cold. Users want the next session, regardless of
   which CLI it is, to *know* what the previous one was working on.

These two ideas reinforce each other: an objective gives the AI a
**purpose** ("keep adding tests for the auth module"), and a NOTES
file gives the AI **memory** ("...and Claude's previous session
already covered the happy path"). Together they let an AI session
pick up exactly where a previous one stopped — even a session from
a different CLI.

Per the user's clarifying answers:
- **Sidebar customization scope:** reorder + hide/show (Phase A shipped).
- **Cross-AI mechanism:** *both* — shared NOTES file first
  (this ADR), transcript replay as a follow-up (B2 below).
- **Idle vs Stopped:** UI merge only — shipped Phase A.
- **AI improves Synapse:** REST endpoints (ADR-0007, follows this one).

## Decision

Four sub-phases — **B1 + B2 must ship together**; B3 + B4 can defer.

### B1 — Shared per-project NOTES file

The smallest mechanism that actually works.

#### On-disk shape

```
data/projects/<project_id>/.synapse-ai-context.md
```

Plain Markdown. Owned by the user; the AI reads + writes it; nothing
in the daemon is allowed to overwrite the whole file without an
explicit user-driven action (delete a project resets it).

Suggested but non-enforced sections:
```markdown
# Project: <name>

## Direction
What this project is for. The "what does keep going mean" prompt.

## Active objectives
- [ ] Open task 1
- [ ] Open task 2

## Session log (newest first)
### 2026-06-18 · claude
2-3 sentences from the AI summarising the just-ended session.

### 2026-06-17 · codex
...
```

The format is **advisory**. Nothing parses it. The next AI session
reads it whole and decides what's relevant. Markdown only because
every CLI knows it.

#### Daemon plumbing

- New env var `SYNAPSE_AI_CONTEXT` injected into every workbench-
  spawned PTY (the existing `routes_workbench.py` + the v0.1.34
  quick-actions launcher already merge env). Points at the absolute
  path of the file.
- New env var `SYNAPSE_AI_CONTEXT_DIRECTION_PROMPT` containing a
  one-line instruction the AI sees on prompt 1:
  > "There's a project memory file at $SYNAPSE_AI_CONTEXT. Read it
  > first. Summarise your work into it before you exit."

  Why a separate var: lets us update the wording without touching
  every quick-action template.

- `GET /api/v1/ai/context` (existing endpoint) gains an inline
  `ai_context: { path, exists, size_bytes, last_modified }` block for
  the active project so an out-of-band caller can find the file
  without env vars.

- `POST /api/v1/projects/{id}/ai-context/append` — a token-guarded
  helper the AI itself can call to append a session summary. Body
  `{ source: 'claude' | 'codex' | 'copilot' | 'other', summary: str }`.
  Writes a fenced `## YYYY-MM-DD · <source>` heading + the summary.
  Atomic write (temp + rename) like `boot_config.py`.

#### Session-exit hook

The existing `on_exit_persist` callback in `pty_sessions.py` already
writes transcripts. We extend it with a tiny AI-summary step **only
for workbench sessions** (tagged with `project_id`):

1. On PTY exit, take the last ~8 KB of scrollback.
2. POST to a new internal endpoint (loopback only) that asks the
   user's CLAUDE_API_KEY (env) or — preferably — runs the user's local
   `claude` CLI in a one-shot mode to summarise.
3. Append the summary to `.synapse-ai-context.md` via the route above.

**Honest scope:** if no Claude/Codex CLI is configured to do the
summarisation, **we skip silently** and just append a header + the
session id. The user can ask the next AI session to read the
transcript file directly. Don't ship anything that pretends to
summarise.

### B2 — Transcript replay (follow-up)

When a user clicks "Resume from previous session" on a tab:

1. Look up the most recent transcript for that project_id.
2. Spawn a new session with the requested CLI.
3. Feed the **last 50 lines** of the previous transcript into the new
   PTY's stdin as base64 chunks via the existing `WriteInput`
   primitive.

The new AI literally sees what the previous CLI said. Plain text.
No magic. Especially valuable when the NOTES summary is too lossy
for the user's particular workflow.

UI surface: a new button next to "Restart session" on a tab,
visible only when transcripts exist for the same project + CLI.

### B3 — Project objectives tree (`project_objectives` table)

Migration `007_project_objectives.sql`:

```sql
CREATE TABLE project_objectives (
  id              TEXT PRIMARY KEY,                  -- secrets.token_hex(6)
  project_id      TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  parent_id       TEXT REFERENCES project_objectives(id) ON DELETE CASCADE,
  title           TEXT NOT NULL,
  body_md         TEXT,
  status          TEXT NOT NULL DEFAULT 'pending',
                  -- pending | in_progress | done | abandoned
  created_at      TEXT NOT NULL,
  completed_at    TEXT,
  sort_order      INTEGER NOT NULL DEFAULT 0,
  -- Optional pointer back to a quick-action template that knows how
  -- to launch a session for this objective.
  default_quick_action TEXT
);
CREATE INDEX project_objectives_project_idx
  ON project_objectives (project_id, status);
```

#### REST surface

- `GET    /api/v1/projects/{id}/objectives` — tree
- `POST   /api/v1/projects/{id}/objectives` — create
  (body: title, body_md?, parent_id?, default_quick_action?)
- `PATCH  /api/v1/projects/{id}/objectives/{obj_id}` — update
- `DELETE /api/v1/projects/{id}/objectives/{obj_id}` — soft-delete
  (status='abandoned')
- `POST   /api/v1/projects/{id}/objectives/{obj_id}/resume` — the
  "click and the AI knows what to do" surface. Spawns a workbench
  session in the project's cwd with the objective's body_md
  injected into a synthesised `PROMPT.md`, marks
  `status = in_progress`, returns the session summary.

Audited as `objective.{create,update,resume,abandon}`.

#### Renderer surface

- New `<ProjectObjectivesPanel>` inside the project's Files modal
  (the same modal that hosts `<FilesPanel>` now). A tree view
  exactly like the body section a project owner would write into the
  README.
- Each leaf has a "Resume" button (the route above).
- Drag to reparent; double-click to edit.

### B4 — "Saved tasks" rail on Sessions

The Sessions page already has a Phase B preview Card from A7.
Replace it with a real rail:

- Lists every objective with `status` ∈ {`pending`, `in_progress`}
  across all projects, grouped by project, sorted by
  `last_transition_at` of the project so recent activity bubbles up.
- Click → calls the resume route → opens the session tab.

This is the "I open Sessions, I see my open work, I click it to
continue" experience the user described.

## Consequences

### Positive
- The objectives table + NOTES file form a **pair of orthogonal
  surfaces**. Objectives are structured ("what" + "where"); NOTES are
  unstructured ("how it's going"). The AI picks the one that fits.
- The NOTES file is **plain Markdown** the user can edit by hand. No
  schema lock-in.
- No new long-running process. Session-exit hook reuses the existing
  `on_exit_persist` callback (already used for transcripts).
- The objectives table is a strict superset of `project_files` from
  Phase A — same migration pattern, same auditing, no schema
  rewrite.
- Compatible with Phase C (AI improves Synapse). The Synapse repo
  itself can be a project with objectives like "Ship ADR-0007".

### Negative / honest trade-offs
- **Session summarisation is fragile.** If the user has no working
  Claude/Codex CLI when a session exits (or it's offline), we
  silently skip — the NOTES file gets less useful over time. Document
  this clearly in `AGENTS.md`.
- **Cross-CLI confusion.** Claude has its own per-cwd `.claude` state
  file; Codex similarly. Our NOTES file is *additional* context, not
  a replacement. Users may end up with both, which can be confusing.
- **Tree reparenting on the UI side** is real work. HTML5 drag/drop
  is acceptable but not great. Acceptable for v0.1.x; consider a
  proper tree library if the experience falls short.
- **Quick-action template prompt drift.** If the NOTES file gets
  long, the AI may not bother to read it all. Mitigation: rotate at
  10 sessions; archive older entries to
  `.synapse-ai-context.archive-YYYYMM.md`.

## Detailed design (locked at acceptance)

### Migration 007 (B3 only — B1/B2 need no migration)

The B3 schema above ships as-is. Foreign-key cascades wipe an
objective tree when a project is hard-deleted; soft delete uses
`status='abandoned'`.

### `.synapse-ai-context.md` lifecycle

- **Created** on first `POST /ai-context/append` call (or first
  workbench session for the project — whichever comes first).
- **Read** on every workbench launch (env var injection).
- **Appended** on every workbench session exit (best-effort).
- **Rotated** when the file grows past 64 KB. Older content moves to
  a date-stamped sibling.
- **Wiped** when the project is hard-deleted (cascades like the
  files dir).

### Quick-action templates that reference objectives

Two new bundled templates:

- `templates/quick-actions/objective-status.json` — opens a session
  with the prompt: "Read $SYNAPSE_AI_CONTEXT, tell me what's left to
  do, and which active objective you'd start with."
- `templates/quick-actions/objective-summarise-and-exit.json` — last
  thing a session does before the user closes the tab. Prompt asks
  the AI to write its summary to `.synapse-ai-context.md`.

Both rely on `$SYNAPSE_AI_CONTEXT` being set.

### Token-guard rule for `/ai-context/append`

The append route accepts the desktop / mobile token like every other
data route. Additionally, **the route only accepts requests from a
process whose pid was spawned by our PTY manager** — we check the
client socket's pid (`/proc/<pid>` on Linux, GetExtendedTcpTable on
Windows) and refuse if the pid isn't on our PTY children list. This
keeps a stray rogue process from corrupting the NOTES file even with
a stolen token. (Stretch — acceptable to defer if pid lookup is
brittle on a given platform.)

## Status

Proposed. Implementation does NOT start until the user gives the go
on B1 + B2 (which ship together). B3 + B4 each get their own
go-ahead.

## Verification plan

### B1
- New `daemon/tests/test_ai_context.py`: writes the NOTES file, calls
  the append route, asserts the appended block lands. Token-guard
  test. Atomic-write test (mid-write SIGKILL recovery).
- Live: a real workbench session whose exit appends a summary block,
  inspected on disk.

### B2
- New `daemon/tests/test_transcript_replay.py`: spawn a session,
  send fake output to its scrollback, exit, spawn a new session with
  `?replay_from=<prev_session_id>`, assert the new PTY's first input
  is the previous tail.

### B3
- Migration 007 runs cleanly on a v0.1.36 data dir.
- Full CRUD test suite for the objectives endpoints.
- Resume route spawns a session with the objective body_md
  observable in the new session's $SYNAPSE_QUICK_ACTION_PROMPT.

### B4
- Playwright: navigate to Sessions, "Saved tasks" rail lists the
  pending objective seeded via the daemon API. Click → tab opens
  with the right argv + cwd + prompt.
