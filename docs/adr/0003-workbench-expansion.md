# ADR-0003 — Workbench Expansion

Date: 2026-06-09
Status: Proposed
Supersedes: —
Related: ADR-0001 (tool marketplace), ADR-0002 (AI workbench)

## Context

ADR-0002 shipped the AI workbench Phases A and B: PTY sessions, xterm.js,
Claude / Codex in the marketplace, project-scoped *Open in workbench*, and
`/api/v1/ai/context` for AI orientation. The user followed up asking for
much more on top of that base:

1. **Per-project files** — upload any file type, unlimited count, multi-file
   batches, per-project or multi-project.
2. **File inspection before upload** — "are you sure you want to upload
   this?" dialog with a preview/description.
3. **Malware sweep** — every uploaded file scanned before it's added.
4. **Per-project transcripts** — save Sessions scrollback so a coder can
   pick up where it left off across closes.
5. **ChatGPT migration** — see folders / chats, download conversations,
   import them into the dashboard, AI-readable.
6. **AI-driven quick-actions** — a button that says "make me an MCP server"
   or "make me a tool" and the AI executes the repetitive steps for the
   user.
7. **CLI sign-in for Claude / Codex** — not API; the user invokes the CLI
   and the CLI handles its own auth (already covered by ADR-0002).
8. **Sign in with Apple / Google** — OAuth refactor of pairing.
9. **Built-for-AI-too** stance documented everywhere — already shipped in
   v0.1.29.

This ADR scopes 1–8 into phases, says what we **will not** build, and
sequences the work so each phase is verifiable on its own.

## Decision

Six phases. Phase A is the obvious next ship after v0.1.29. Each later
phase is shipped only after the previous one is **in use** by the user
for at least a few sessions — feedback compounds.

### Phase A — Per-project files (v0.1.30–v0.1.31)

A "Files" surface on each project that holds anything the user (or an AI
session) uploads against it. The storage is on disk under the daemon's
data directory; the index is in SQLite for fast listing and per-file
metadata.

**Storage layout:**
```
data/projects/<project_id>/files/
  ├── abc123.pdf
  ├── notes.md
  └── ...
data/transcripts/<project_id>/
  └── <session_id>.log
```

**Daemon:**
- Migration 006 -- `project_files` table (id, project_id, original_name,
  mime, size_bytes, sha256, uploaded_at, source [`upload` /
  `transcript` / `chatgpt-import`], deleted_at).
- `POST /api/v1/projects/{id}/files` -- multipart upload, accepts many
  files in one request. Returns the list of created `ProjectFile` rows
  plus per-file warnings (oversized? rejected by scanner? duplicate
  sha256?).
- `GET /api/v1/projects/{id}/files` -- list with metadata.
- `GET /api/v1/projects/{id}/files/{file_id}` -- download.
- `GET /api/v1/projects/{id}/files/{file_id}/inspect` -- the safe
  metadata + the first 64 KiB tail, for the "are you sure?" preview.
- `DELETE /api/v1/projects/{id}/files/{file_id}` -- soft-delete.
- Multi-project files (the user asked): later. For Phase A files are
  per-project. Cross-project sharing comes in Phase E.

**Renderer:**
- A new **Files** tab on the project detail/workbench view (the
  workbench landing area introduced in Phase B). Lists uploaded files
  with size / type / uploaded-at; drag-drop and a multi-file picker.
- The upload flow goes: pick → **Pre-upload Inspection Dialog** (see
  Phase B) → confirm → multipart POST → toast on success.

**AI access:**
- `/api/v1/projects/{id}/files` becomes part of `/api/v1/ai/context`
  for the active project so a Claude session knows what's there without
  asking.
- A Sessions tab opened via *Open in workbench* gets the project's
  files exposed to its **child process's cwd** via a symlink at
  `./.synapse-files/` -- so the AI can `ls`/`cat` like normal.

**Audit:** every upload / delete writes `file.upload` / `file.delete`
audit rows with the file id, size, sha256.

### Phase B — Pre-upload inspection + safer upload UX (v0.1.31)

The "are you sure?" surface the user asked for. Pure UX on top of
Phase A's storage.

- Read each picked file's first 64 KiB **in the browser**, before the
  POST. Detect MIME via magic bytes (we ship a tiny detector --
  `application/pdf`, plain text, common image formats, JSON, ZIP,
  scripts, executables). Show: filename, size, detected type, first 30
  lines if it's printable text.
- Special UX for executables: a red "this looks executable" banner
  before the user even sees the *Upload* button.
- Bulk-select mode for many files: a single "Review N files" dialog with
  a checklist; the user can untick any before confirming.
- Drag-drop hints on the project landing.

### Phase C — Malware sweep (v0.1.32)

Every accepted upload is scanned against a local AV engine before the
write to disk is final. **Honest scope:** we use what the OS already
gives us, and we tell the user clearly when scanning isn't available.

| Platform | Engine | Probe | Invocation |
|---|---|---|---|
| Windows | Microsoft Defender | `MpCmdRun.exe` present? | `MpCmdRun.exe -Scan -ScanType 3 -File <path>` |
| macOS | ClamAV (optional) | `clamscan` on PATH? | `clamscan --no-summary <path>` |
| Linux | ClamAV (optional) | `clamscan` on PATH? | `clamscan --no-summary <path>` |

Behaviour:
- Spawn the scan in a thread with a 30 s timeout.
- A non-zero exit / detected signature blocks the upload, records a
  `file.upload_blocked` audit row, surfaces the threat name in the UI.
- On platforms with no scanner: surface a clear banner in the upload
  dialog (*"Scanning is unavailable on this machine — uploading
  unscanned"*) so the user makes an informed choice. We do **not**
  pretend to scan. We do **not** ship our own AV.
- **No third-party API calls** (no VirusTotal): Contract #15 (no
  third-party network calls without opt-in). Defender + ClamAV are
  local.

### Phase D — Per-project transcripts (v0.1.30, alongside A)

When a PTY session opened via *Open in workbench* exits, write its
scrollback to `data/projects/<project_id>/transcripts/<session_id>.log`
and create a `project_files` row tagged `source=transcript`.

- `GET /api/v1/projects/{id}/transcripts` lists them.
- Sessions tab gets a *Recent transcripts* rail under each project's
  workbench launcher so the user (and any future Claude session)
  can re-read what was discussed.
- Transcripts are a special case of files -- same storage / audit /
  download flow.

### Phase E — ChatGPT data import (v0.1.33, opt-in feature)

The user asked to "see folders / chats" of their ChatGPT and migrate
into the dashboard. The honest scope is **the official export**, not
browser scraping.

The flow:

1. User in ChatGPT goes to *Settings → Data Controls → Export Data*.
   OpenAI emails them a `.zip` with all conversations as JSON.
2. User drops the `.zip` into Synapse's new **Import** flow (a top-level
   button, not project-scoped).
3. Daemon parses `conversations.json`, breaks each conversation into a
   Markdown file:
   ```
   data/projects/_imported-chatgpt/files/
     ├── 2025-11-03_brainstorm-ideas.md
     ├── 2025-11-12_helping-with-essay.md
     └── ...
   ```
4. Files land in a special `_imported-chatgpt` project (auto-created on
   first import) so they show up wherever the rest of Phase A's files
   show up.
5. `/api/v1/ai/context` exposes them by id so a Claude session can be
   pointed at them on prompt 1.

**What is NOT happening here:**
- Browser-automation of `chat.openai.com` (against ToS, brittle, NO).
- OpenAI's API hitting `/conversations` (no public docs for this, would
  need a user-supplied session token, brittle, NO).
- Live two-way sync with ChatGPT (NO -- one-shot import only).

### Phase F — AI-driven quick-actions (v0.1.34)

The user described buttons like *"make me an MCP server"* / *"make me a
tool"* that bundle the repetitive setup steps. The honest framing: the
button **doesn't** invoke an embedded LLM. It launches a Claude session
in a scratch project with a **templated first prompt** loaded so the
AI immediately knows what to build.

- A new **Quick-actions** rail on the Sessions page with curated
  templates:
  - **New MCP server** — opens a workbench in a fresh scratch project,
    pre-loads a prompt of the form *"I want to build an MCP server that
    does X. Use the @modelcontextprotocol/sdk; scaffold the project,
    add tool definitions, and walk me through testing it."*
  - **New Synapse tool** — pre-loads *"Create a new tool manifest at
    `tools/<name>/manifest.json` using the declarative tier (`url.open`
    or `process.spawn`)..."*
- Templates live in `templates/quick-actions/<id>.json` so a user (or a
  future marketplace) can add their own.
- The actual *doing* of the work is Claude's job, not ours. We ship the
  shortcut.

### Phase G — Sign in with Apple / Google

**Still deferred to its own ADR-0004.** No movement here without an
explicit go-ahead from the user. The reasons stay the same as in
ADR-0002 Phase C: registered OAuth clients on each provider, redirect
URIs, JWKS verification, migration from pairing-code devices. Real work,
real provisioning, separate doc.

## Consequences

### Positive

- The user's biggest concrete asks (files, transcripts, ChatGPT import,
  quick-actions) become honest, sequenced work with clear "done" tests.
- Phase A's `project_files` table generalises: transcripts are files,
  imported ChatGPT conversations are files, future things land as files.
  One storage / audit / download surface for everything.
- Local-only AV via Defender / ClamAV respects Contract #15 (no
  unsolicited third-party calls).
- AI sessions (a Claude tab in the workbench) see everything by id via
  `/ai/context`, so the dual-audience design from v0.1.29 keeps paying
  off as we add surfaces.

### Negative / honest trade-offs

- File upload + AV scanning means real disk + real network I/O paths to
  test. Phase A ships without AV so the file UX gets exercised before
  the scan tax is added in Phase C.
- The ChatGPT import is one-way. Users with a "live link to my ChatGPT"
  mental model will be disappointed; we surface clearly that this is a
  manual export → import.
- Quick-actions feel magical but aren't. The button pre-fills a Claude
  prompt; Claude does the work. If the user expects "Synapse generates
  the MCP server entirely on its own," that's not what's shipping --
  call it out in the UI copy.
- Cross-platform AV is uneven. Mac / Linux without ClamAV installed
  will upload unscanned. The UX banner is the answer; we don't pretend.

## Status

ADR is approved into `docs/adr/0003-workbench-expansion.md`. Implementation
does **not** start until the user gives the go on Phase A. Phases C, E, F
have additional explicit gates: each one is enough work that the user
should re-confirm before it starts. ADR-0004 (OAuth) remains its own
separate doc to be written when needed.

## Suggested next step

If the user says "go", start with **Phase A + D together** (the file +
transcript storage is one table, one set of endpoints; transcripts are
just files with a tag). One version, one set of tests, one shipping
cycle. Then sit on it for a session or two before Phase B's inspection
UI lands -- the file storage being already there makes the upload UX
much easier to get right.
