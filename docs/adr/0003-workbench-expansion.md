# ADR-0003 — Workbench Expansion

Date: 2026-06-09
Status: Accepted (2026-06-09 after the tightening pass)
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
- **Multi-project / shared files are in Phase A, not deferred.** The
  schema treats a NULL `project_id` as "shared workspace" -- files
  accessible from any project context. Implementation drops out of the
  same table; we just allow `project_id` to be nullable and route the
  shared endpoint at `/api/v1/files`. (See *Detailed design* below.)

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

## Detailed design (Phase A + D, locked at acceptance)

The tightening pass added during the move from Proposed → Accepted. These
are the concrete decisions implementation will follow; deviations need an
ADR amendment.

### Storage layout (on disk)

```
data/
  projects/
    <project_id>/
      files/
        <file_id><.ext>         # the actual bytes; ext preserved for tools that sniff it
      transcripts/
        <session_id>.log        # PTY scrollback; also indexed in project_files w/ source='transcript'
  files/
    _shared/
      <file_id><.ext>           # files whose project_id IS NULL
  quarantine/
    <file_id><.ext>             # temp landing during AV scan (Phase C); deleted on pass or fail
```

- `file_id` is a 12-hex-char identifier (`secrets.token_hex(6)`); same
  alphabet as PTY session ids for consistency.
- The on-disk extension is best-effort cosmetic so `cat`/`code` open the
  right tool; the source of truth for type is the `mime` column.

### Migration 006 -- `project_files`

```sql
CREATE TABLE project_files (
  id              TEXT PRIMARY KEY,                 -- file_id (12 hex chars)
  project_id      TEXT,                             -- NULL = shared workspace
  original_name   TEXT NOT NULL,                    -- as picked by the user
  on_disk_name    TEXT NOT NULL,                    -- <file_id><.ext> under data/...
  mime            TEXT NOT NULL,                    -- magic-byte detected (Phase B) or "application/octet-stream"
  size_bytes      INTEGER NOT NULL,
  sha256          TEXT NOT NULL,                    -- hex digest; indexed for dedup checks
  source          TEXT NOT NULL,                    -- 'upload' | 'transcript' | 'chatgpt-import'
  source_session  TEXT,                             -- the PTY session_id for source='transcript'
  uploaded_at     TEXT NOT NULL,                    -- ISO 8601 UTC (Contract #24)
  deleted_at      TEXT,                             -- soft delete; purge 30 d later
  scan_result     TEXT,                             -- 'clean' | 'blocked' | 'unavailable' | NULL (pre-scan)
  scan_engine     TEXT,                             -- 'defender' | 'clamav' | NULL
  FOREIGN KEY (project_id) REFERENCES projects(id)
);
CREATE INDEX project_files_project_idx ON project_files (project_id) WHERE deleted_at IS NULL;
CREATE INDEX project_files_sha256_idx ON project_files (sha256);
```

### Multipart upload limits (Phase A defaults)

- **100 files per request** (effectively unlimited for normal workflows;
  cap is to keep request memory bounded).
- **256 MiB per file** (the daemon streams to disk; not in memory).
- **No total-request cap** beyond the per-file × per-request product
  (~25 GiB) -- the user wanted "unlimited".
- Configurable from the start via env vars
  `SYNAPSE_MAX_FILES_PER_REQUEST` and `SYNAPSE_MAX_FILE_BYTES` so
  later versions can lower them for cloud / multi-tenant cases without
  another migration.

### Upload happy-path flow

1. Renderer POSTs `multipart/form-data` to
   `/api/v1/projects/{id}/files` (or `/api/v1/files` for shared).
2. Daemon streams each part to `data/quarantine/<file_id><ext>` as
   bytes arrive, hashing with SHA-256 on the fly.
3. After write closes:
   - If Phase C is shipped: run the platform AV (see below). On block,
     delete the quarantine file, write a `project_files` row with
     `source='upload', scan_result='blocked'`, audit
     `file.upload_blocked`, return per-file warning in the response.
     Pre-Phase-C: write `scan_result=NULL`.
   - On pass / pre-Phase-C: `os.replace()` to the final location, write
     the `project_files` row with `scan_result='clean'`/`NULL`, audit
     `file.upload`.
4. Response shape (per file):
   ```json
   {
     "ok": true,
     "id": "abc123def456",
     "original_name": "notes.md",
     "size_bytes": 4096,
     "mime": "text/markdown",
     "sha256": "...",
     "scan_result": "clean",
     "duplicate_of": null
   }
   ```
   On rejection: `"ok": false`, `"reason": "...", "duplicate_of": null`.

### Deduplication policy (Phase A)

- We **record** every upload (no silent skip).
- If `sha256` matches an existing not-deleted row in the same scope
  (same `project_id`, including the shared scope), the new row sets
  `duplicate_of` -> the existing `file_id` AND still keeps a fresh row
  (zero-length on-disk content; the actual bytes are referenced from
  the original). Lets the user re-upload the same file under a
  different name without paying the disk cost.
- Phase B's "Are you sure?" dialog also surfaces the duplicate up
  front so the user can cancel.

### Soft delete + purge

- `DELETE /api/v1/projects/{id}/files/{file_id}` flips `deleted_at`
  and renames the on-disk file to `<file_id><ext>.deleted-<iso>`.
- A background sweep on daemon boot deletes any `*.deleted-*` files
  older than 30 days.
- Restore is a future ADR -- no API for it in Phase A.

### AV quarantine flow (Phase C, anchored here so the schema covers it)

- Defender on Windows: `MpCmdRun.exe -Scan -ScanType 3 -File <path>`.
  Exit code 0 = clean, 2 = signature found, 3 = engine error. We
  classify (0 -> clean), (2 -> blocked, parse stdout for threat name),
  (3 -> unavailable + warn).
- ClamAV on POSIX: `clamscan --no-summary <path>`. Exit code 0 = clean,
  1 = signature found, 2 = engine error. Same mapping.
- 30 s timeout; engine-error or timeout records `scan_result='unavailable'`
  and surfaces the banner the UX promised. The file still uploads.
- Result lands in `scan_result` + `scan_engine` -- always visible in
  the file metadata so the user (and any AI session) knows the
  provenance.

### AI access to project files

The cross-project / per-project files are exposed two ways:

1. **REST list inside `/api/v1/ai/context`** -- each project's
   `files` is added inline (file_id, name, size, mime, scan_result),
   so a Claude session reads its current project's file inventory on
   prompt 1.
2. **Filesystem mirror inside the session's cwd** -- when *Open in
   workbench* spawns the PTY (v0.1.29), the daemon ensures
   `<project_path>/.synapse-files/` exists and is a **Windows
   directory junction** (POSIX: symlink) pointing at
   `data/projects/<project_id>/files/`. Directory junctions don't need
   admin or developer mode on Windows -- this was a deliberate choice
   over symlinks. The shared workspace is mirrored at
   `<project_path>/.synapse-files-shared/`.

### `_imported-chatgpt` "auto-project"

Phase E introduces this. To avoid special-casing the schema, it's just
a real `projects` row created lazily on first ChatGPT import (kind=
`'other'`, path=`data/projects/_imported-chatgpt`). The user can
inspect / delete it like any other project.

### Phase F "scratch project"

Same idea: a `_scratch` lazy-created `projects` row used as the cwd for
quick-action sessions that don't belong to one of the user's real
projects. Lives at `data/projects/_scratch`.

### Implementation order inside Phase A + D

This is the order the code actually drops in -- written here so
implementation is mechanical:

1. **Migration 006** + `_safe_kind` style hydration for source enum
   (one PR, lands first).
2. **`files_storage.py`** -- the on-disk write / move / soft-delete /
   hash module. Pure functions, no FastAPI. Unit-tested.
3. **`routes_files.py`** -- multipart POST, GET (list + download),
   DELETE. Uses files_storage. Token-guarded.
4. **`routes_transcripts.py`** -- a wrapper that turns Sessions
   close-events into `project_files` rows with `source='transcript'`.
   Lives separately so deleting it doesn't take the file API with it.
5. **PTY session-exit hook** in `pty_sessions.py` -- when a workbench
   session ends, persist its scrollback through the transcript wrapper.
6. **`/api/v1/ai/context` extension** -- inline the current project's
   files (and shared) into the existing payload.
7. **Renderer**: `lib/files-client.ts`, a `<FilesPanel>` component, and
   wire it into the project workbench landing.

After step 7 ships as `v0.1.30`, sit on it for a few sessions. Phase B
(inspection dialog) only starts after real upload workflows show what
the "are you sure?" surface actually needs.

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
