# Synapse API Finds — Complete AI Capability Audit

> **Purpose:** Every API, event, env var, file path, and capability that an AI
> session running inside Synapse could use — and that it commonly misses. Use
> this as a reference before starting any work session, and as a checklist
> before declaring work done.
>
> Base URL: `http://127.0.0.1:7878/api/v1`  
> Auth: `X-Synapse-Token: <token>` (token from `$SYNAPSE_TOKEN` or
> `GET /api/v1/auth/local-token`)
>
> **Always start a session with:** `GET /api/v1/ai/context`  
> **Always check health with:** `GET /api/v1/ai/health-report`

---

## Table of Contents

1. [AI-First Orientation Endpoints](#1-ai-first-orientation-endpoints)
2. [WebSocket Event Bus](#2-websocket-event-bus)
3. [Environment Variables Injected Into AI Sessions](#3-environment-variables-injected-into-ai-sessions)
4. [AI Context Memory Files](#4-ai-context-memory-files)
5. [Complete REST API Inventory](#5-complete-rest-api-inventory)
   - [5A. Projects](#5a-projects)
   - [5B. PTY Sessions](#5b-pty-sessions)
   - [5C. Workbench](#5c-workbench)
   - [5D. Files (Project + Shared)](#5d-files-project--shared)
   - [5E. Agent Squads & Work Items](#5e-agent-squads--work-items)
   - [5F. Coder Workspace Threads](#5f-coder-workspace-threads)
   - [5G. AI Cases (AI Operating System)](#5g-ai-cases-ai-operating-system)
   - [5H. Benchmarks](#5h-benchmarks)
   - [5I. Quality OS (Gates, Contracts, Evidence)](#5i-quality-os-gates-contracts-evidence)
   - [5J. Project Records (ADRs, Backlog, Versions)](#5j-project-records-adrs-backlog-versions)
   - [5K. Multi-AI Coordination](#5k-multi-ai-coordination)
   - [5L. AI Bundles](#5l-ai-bundles)
   - [5M. AI Factory (Recipe Builder)](#5m-ai-factory-recipe-builder)
   - [5N. Quick Actions](#5n-quick-actions)
   - [5O. Capture Inbox](#5o-capture-inbox)
   - [5P. Installed Pages & Web Scraper Proxy](#5p-installed-pages--web-scraper-proxy)
   - [5Q. MCP Servers](#5q-mcp-servers)
   - [5R. MCP Protocol Endpoint (Streamable HTTP)](#5r-mcp-protocol-endpoint-streamable-http)
   - [5S. Models (Ollama)](#5s-models-ollama)
   - [5T. Local LLM Assistant](#5t-local-llm-assistant)
   - [5U. Marketplace (Tools)](#5u-marketplace-tools)
   - [5V. Discovery](#5v-discovery)
   - [5W. Snapshot / Restore](#5w-snapshot--restore)
   - [5X. Review Inbox](#5x-review-inbox)
   - [5Y. Token Ledger](#5y-token-ledger)
   - [5Z. Synapse Dev (Self-Test Loop)](#5z-synapse-dev-self-test-loop)
   - [5AA. Personalities](#5aa-personalities)
   - [5AB. Audit Log](#5ab-audit-log)
   - [5AC. About / Roadmap](#5ac-about--roadmap)
   - [5AD. System & Remote Access](#5ad-system--remote-access)
   - [5AE. Auth & Pairing](#5ae-auth--pairing)
   - [5AF. Profile](#5af-profile)
   - [5AG. Imports (ChatGPT)](#5ag-imports-chatgpt)
   - [5AH. Search](#5ah-search)
6. [Gaps Analysis — What AIs Miss and Why](#6-gaps-analysis--what-ais-miss-and-why)
7. [Recommended AI Session Start Protocol](#7-recommended-ai-session-start-protocol)

---

## 1. AI-First Orientation Endpoints

These two endpoints exist specifically to help an AI understand what it is looking at.
**Read them before doing anything else.**

### `GET /api/v1/ai/context`
**The single most useful call.** Returns a versioned digest (`synapse.ai.context/v1`) with:
- `projects` — all projects with id, name, path, kind, status, launch_cmd, port, group, tags, pinned, description, current_health, `ai_context` metadata (path + exists + size), and up to 25 files inlined per project
- `tools` — installed tools with id, name, version, runnable, description, and action list
- `sessions` — live PTY sessions (session_id, argv, cwd, started_at, exit_code)
- `agent_squads` — all squads with embedded work items
- `ai_cases` — all AI OS cases with status, phase, blocking gate count
- `coder_threads` — all coder threads across all projects with last message preview
- `benchmark_runs` — benchmark runs with attempt gate count
- `agent_role_templates` — all role templates (planner, coder, reviewer, boss, etc.)
- `ai_factory.counts` — component/recipe/source counts + installed bundles
- `ai_factory.mission_profiles` — available mission profiles for AI cases
- `ai_factory.installed_bundles` — installed bundle list
- `shared_files` — shared-scope uploaded files (up to 25)
- `audit_tail` — last 25 audit entries (what just happened)
- `quality.summary` — quality OS summary with blocking gate count
- `quality.ui_surfaces` — declared UI surfaces
- `endpoints_for_ai` — curated list of what REST endpoints to use for what

### `GET /api/v1/ai/health-report`
Lighter than full context. Returns:
- `version`, `uptime_s`
- `daemon.schema_migration` (current migration number), `daemon.contracts_honoured` ([1..28])
- Last 5 error-only audit entries
- Git status of the repo
- Last test run result (if `synapse_dev` is enabled)

---

## 2. WebSocket Event Bus

**Connection:** `WS ws://127.0.0.1:7878/api/v1/ws`

**Protocol after connect — send immediately:**
```json
{"type": "resume", "since": <last_event_id_or_0>}
```
Daemon replies with `{"type": "replay", "events": [...], "buffer_min_id": N}` then live events.

**Keep-alive:**
```json
{"type": "ping"}
```
Daemon replies `{"type": "pong"}`.

**Event shape:**
```json
{"id": 42, "name": "v1.entity.verb", "payload": {...}, "timestamp_utc": "..."}
```

**Buffer:** last 1,000 events. If `since` is older than `buffer_min_id` a
`v1.ws.replay_window_exceeded` error event is sent; refetch state from REST.

### Complete Event List

| Event | Payload Keys |
|-------|-------------|
| `v1.daemon.started` | version, contracts |
| `v1.daemon.reconciliation_complete` | outcomes |
| `v1.project.launching` | project_id, name |
| `v1.project.launched` | project_id, pid |
| `v1.project.stopping` | project_id |
| `v1.project.stopped` | project_id, exit_code |
| `v1.project.errored` | project_id, error |
| `v1.project.restart_scheduled` | project_id, attempt, delay_s |
| `v1.project.restart_exhausted` | project_id, max_retries |
| `v1.process.heartbeat` | project_id, pid, cpu_percent, rss_mb |
| `v1.process.reconciled` | project_id, outcome |
| `v1.pty.session_started` | session_id, argv, cwd |
| `v1.pty.session_output` | session_id, data (base64) |
| `v1.pty.session_input` | session_id, data (base64) |
| `v1.pty.session_exited` | session_id, exit_code |
| `v1.pty.session_finalized` | session_id, exit_code |
| `v1.agent_squad.created` | squad |
| `v1.agent_squad.updated` | squad |
| `v1.agent_work_item.created` | work_item |
| `v1.agent_work_item.updated` | work_item |
| `v1.agent_work_item.handoff` | work_item |
| `v1.agent_run.started` | squad_id, work_item_id, role_id, session_id, runtime |
| `v1.agent_run.ended` | squad_id, work_item_id, role_id, session_id, exit_code |
| `v1.ai_case.created` | case_id (+ parent_case_id if child) |
| `v1.ai_case.updated` | case_id, status |
| `v1.tool.reloaded` | tool_id |
| `v1.tool.primitive_ran` | tool_id, action_id, result |
| `v1.model.pull_progress` | name, status, percent |
| `v1.mcp_server.updated` | reason, server_id |
| `v1.device.paired` | device_id |
| `v1.device.reconnected` | device_id |
| `v1.device.revoked` | device_id |
| `v1.remote_access.updated` | enabled |
| `v1.coordination.session_registered` | session_id, project_id |
| `v1.coordination.session_heartbeat` | session_id, status |
| `v1.coordination.session_ended` | session_id |
| `v1.coordination.lane_*` | lane details |
| `v1.profile.updated` | fields |
| `v1.profile.sync.updated` | sync state |
| `v1.service_connection.updated` | provider |
| `v1.review.resolved` | work_item_id, resolution |
| `v1.ws.replay_window_exceeded` | since, buffer_min_id |

---

## 3. Environment Variables Injected Into AI Sessions

These are set automatically when a session is launched through Synapse. **If you
see these vars in your environment, use them — they are your connection to Synapse's
API and your project context.**

### Workbench Sessions (`POST /api/v1/projects/{id}/workbench`)
| Variable | Value | Use |
|----------|-------|-----|
| `SYNAPSE_PROJECT_ID` | project id | Know which project you're working on |
| `SYNAPSE_API` | `http://127.0.0.1:7878/api/v1` | Make daemon calls |
| `SYNAPSE_TOKEN` | auth token | Auth header for daemon calls |
| `SYNAPSE_FILES` | `<data_dir>/projects/<id>/files/` | Project file storage root |
| `SYNAPSE_SHARED_FILES` | `<data_dir>/files/` | Shared file storage root |

### Agent Work Item Sessions (`POST /api/v1/agent-work-items/{id}/launch`)
| Variable | Value | Use |
|----------|-------|-----|
| `SYNAPSE_SQUAD_ID` | squad id | Know which squad you belong to |
| `SYNAPSE_WORK_ITEM_ID` | work item id | Report your own status / handoff |
| `SYNAPSE_ROLE_ID` | role id (planner/coder/reviewer/boss) | Know your role |
| `SYNAPSE_LEAD_SESSION_ID` | lead PTY session id | Communicate with lead |
| `SYNAPSE_ROLE_PROMPT_FILE` | path to role prompt `.md` | Read your instructions |
| `SYNAPSE_AI_CONTEXT` | path to `.synapse-ai-context.md` | **Shared project memory** |
| `SYNAPSE_AI_CONTEXT_DIRECTION_PROMPT` | reminder text | Read context before starting |

### AI Case Sessions (`POST /api/v1/ai-cases/{id}/run`)
| Variable | Value | Use |
|----------|-------|-----|
| `SYNAPSE_AI_CASE_ID` | case id | Reference case in API calls |
| `SYNAPSE_AI_CASE_DIR` | case directory | Where case files live |
| `SYNAPSE_AI_CASE_BUNDLE` | bundle JSON path | Full case context |
| `SYNAPSE_AI_CASE_PROMPT_FILE` | lead prompt path | Your instructions |
| `SYNAPSE_AI_CASE_BRANCH` | git branch name | Work on this branch |
| `SYNAPSE_AI_CASE_WORKTREE` | git worktree path | `cd` here for all edits |
| `SYNAPSE_AI_CASE_PRIMARY_PROJECT_ID` | primary project | Which project to edit |
| `SYNAPSE_AI_CASE_MODE` | case mode (generate/research/etc.) | Your mission type |
| `SYNAPSE_AI_CASE_MISSION_PROFILE` | mission profile id | Strategy preset |
| `SYNAPSE_AI_CASE_DRAFT_PR` | draft PR stub path | Where to write PR summary |
| `SYNAPSE_ROLE_PROMPT_FILE` | role prompt path | Your squad role instructions |
| `SYNAPSE_API` | daemon base URL | Make daemon calls |
| `SYNAPSE_TOKEN` | auth token | Auth header |

### CLI Auth (any session)
| Variable | Value |
|----------|-------|
| `SYNAPSE_TOKEN` | If set, the CLI uses this for auth (highest precedence) |

---

## 4. AI Context Memory Files

### Per-Project Shared Memory
**Path:** `<data_dir>/projects/<project_id>/.synapse-ai-context.md`  
**Env var:** `$SYNAPSE_AI_CONTEXT`

This file is the **shared context between all AI sessions** on a project.
- Read it before starting work
- Append to it via `POST /api/v1/capture` with `destination: "ai_context"`
- Update it at the end via `POST /api/v1/agent-work-items/{id}/handoff`

### Role Prompt Files
**Path:** `<data_dir>/projects/<project_id>/agent-prompts/<role-slug>-<session_id>.md`  
**Env var:** `$SYNAPSE_ROLE_PROMPT_FILE`

Read this file for your role-specific instructions, squad goal, work item context,
and any prior handoff notes.

### AI Case Bundle
**Path:** `<data_dir>/ai-cases/<case_id>/bundle.json`  
**Env var:** `$SYNAPSE_AI_CASE_BUNDLE`  
**API:** `GET /api/v1/ai-cases/{id}/bundle`

The full case context: intent, directives, timeline, quality scorecard, candidate
leaderboard, failure matrix, contradiction docket, claim cards, promotions.

### AI Case Context Metadata
**Path:** `<data_dir>/ai-cases/<case_id>/context.json`

Flattened case metadata written on every case run / state change.

---

## 5. Complete REST API Inventory

All paths are relative to `http://127.0.0.1:7878/api/v1`.  
Auth header: `X-Synapse-Token: <token>`

### 5A. Projects

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/projects` | List all registered projects |
| GET | `/projects/{id}` | Get project detail (status, health, config) |
| POST | `/projects` | Create/register a project |
| PATCH | `/projects/{id}` | Update project config (name, cmd, port, tags, etc.) |
| DELETE | `/projects/{id}` | Remove project |
| POST | `/projects/{id}/launch` | Start the project process |
| POST | `/projects/{id}/stop` | Stop the project process |
| GET | `/projects/{id}/logs` | Tail log file |
| GET | `/projects/{id}/disk-usage` | Disk usage for project directory |

### 5B. PTY Sessions

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/pty/probe` | Check if PTY subsystem is available |
| GET | `/pty` | List all live PTY sessions |
| POST | `/pty` | Spawn new PTY session. Body: `{argv, cwd, rows?, cols?, env?}` |
| GET | `/pty/{session_id}` | Get session metadata |
| POST | `/pty/{session_id}/input` | Send input bytes to the session |
| POST | `/pty/{session_id}/resize` | Resize terminal `{rows, cols}` |

**Note:** PTY output is pushed as `v1.pty.session_output` WS events (base64 data).

### 5C. Workbench

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/projects/{id}/workbench` | Open a coder pre-cd'd into the project |

**Body (all optional):**
```json
{
  "argv": ["claude"],
  "rows": 24,
  "cols": 80,
  "source": "desktop"
}
```
Omit `argv` to auto-pick `claude` → `codex` → `powershell.exe`/`bash`.  
**Returns:** PTY summary + `project_id` + `project_name`.  
**Sets env vars:** SYNAPSE_PROJECT_ID, SYNAPSE_API, SYNAPSE_TOKEN, SYNAPSE_FILES, SYNAPSE_SHARED_FILES.

### 5D. Files (Project + Shared)

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/projects/{id}/files` | Upload file to project scope (multipart) |
| GET | `/projects/{id}/files` | List project files |
| GET | `/projects/{id}/files/{file_id}` | Download file |
| DELETE | `/projects/{id}/files/{file_id}` | Delete file |
| POST | `/files` | Upload to shared scope (project_id=null) |
| GET | `/files` | List shared files |
| GET | `/files/{file_id}` | Download shared file |
| DELETE | `/files/{file_id}` | Delete shared file |
| GET | `/projects/{id}/transcripts` | List AI session transcripts for project |

**File fields:** id, original_name, size_bytes, mime, source, uploaded_at,
scan_result (clean/blocked/unavailable), scan_engine.  
**Blocked files** are scanned by Windows Defender / ClamAV; never stored for download.

### 5E. Agent Squads & Work Items

The multi-AI team system. A Squad contains Work Items; each Work Item runs as
one PTY session with a role-specific prompt.

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/agent-role-templates` | List role templates (planner/coder/reviewer/boss) |
| POST | `/agent-role-templates` | Create custom role |
| PATCH | `/agent-role-templates/{id}` | Update role |
| DELETE | `/agent-role-templates/{id}` | Delete role |
| GET | `/agent-squads` | List all squads |
| POST | `/agent-squads` | Create squad for a project |
| GET | `/agent-squads/{id}` | Get squad + all work items |
| GET | `/agent-squads/{id}/capacity` | Headroom vs the launch gates: `running`/`max_concurrent`, `tokens_spent`/`token_budget`, `can_launch` — check before delegating a new worker |
| PATCH | `/agent-squads/{id}` | Update squad (goal, status, concurrency cap, token budget) |
| DELETE | `/agent-squads/{id}` | Delete squad |
| POST | `/agent-squads/{id}/stop` | Kill all running workers immediately |
| POST | `/agent-squads/{id}/work-items` | Create work item in squad |
| POST | `/agent-work-items/{id}/launch` | **Launch work item** (spawns AI with role prompt, MCP config, env vars) |
| POST | `/agent-work-items/{id}/delegate` | Create a child work item delegated from this one; pass `auto_launch: true` to launch it immediately (bounded by the squad's concurrency cap + token budget — over-limit children stay QUEUED with a `queued_reason`) |
| POST | `/agent-work-items/{id}/handoff` | Complete/hand off work item with summary + blockers + files_touched + verdict |
| POST | `/agent-work-items/{id}/status` | Update work item status |
| POST | `/agent-work-items/{id}/tokens` | **Record token usage** (AI self-reports) |
| GET | `/agent-work-items/{id}/tokens` | Get token usage for work item |
| GET | `/agent-squads/{id}/token-usage` | Squad-level token rollup |

**Launch body:**
```json
{
  "preferred_runtime": "claude",
  "cwd_override": "/path/to/dir",
  "env": {"EXTRA_VAR": "value"},
  "rows": 24, "cols": 80,
  "open_in_tab": true,
  "source": "desktop"
}
```

**Handoff body:**
```json
{
  "status": "completed",
  "summary_md": "What I did...",
  "blockers_md": "What's left...",
  "files_touched": ["src/foo.ts"],
  "suggested_next_role": "reviewer",
  "input_tokens": 12000,
  "output_tokens": 3500,
  "verdict": {
    "blocking": false,
    "severity": "info",
    "surface_ids": [],
    "contract_ids": [],
    "recommended_next_step": "..."
  },
  "source": "auto"
}
```

**Token record body:**
```json
{"input_tokens": 5000, "output_tokens": 1200, "model": "claude-opus-4-5", "note": "..."}
```

### 5F. Coder Workspace Threads

Chat-first coder sessions with message history, review passes, and runtime switching.

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/coder-workspace/preferences` | Get workspace prefs |
| PATCH | `/coder-workspace/preferences` | Update prefs (advanced_terminal_enabled, raw_pty_enabled) |
| GET | `/projects/{id}/coder-threads` | List threads for project |
| POST | `/projects/{id}/coder-threads` | Create new thread |
| GET | `/coder-threads/general` | List project-free ("General" scope) threads |
| POST | `/coder-threads/general` | Create a "New chat" with no project (`project_id` stays null) |
| GET | `/coder-threads/{id}` | Get thread detail |
| PATCH | `/coder-threads/{id}` | Update thread (title, status, workspace_context_mode) |
| DELETE | `/coder-threads/{id}` | Delete thread |
| GET | `/coder-threads/{id}/messages` | List thread messages |
| POST | `/coder-threads/{id}/messages` | Add message (logging only, no PTY spawn) |
| POST | `/coder-threads/{id}/dispatch` | **Send message AND spawn PTY session** |
| POST | `/coder-threads/{id}/runtime` | Switch runtime (claude/codex/copilot/python/shell) |
| POST | `/coder-threads/{id}/review-passes` | Create review pass record |
| POST | `/coder-threads/{id}/review-passes/{rid}/launch` | **Launch sidecar AI reviewer** |
| POST | `/coder-review-passes/{id}/verdict` | Submit review verdict (creates quality gate if blocking) |
| GET | `/coder-threads/{id}/context` | Full thread context (messages, review passes, runs, files, records) |

**Dispatch body:**
```json
{
  "content_md": "Implement the feature described in the backlog...",
  "runtime_id": "claude",
  "provider": "anthropic",
  "model": "claude-opus-4-5",
  "workspace_context_mode": "full",
  "metadata": {}
}
```

**Review pass kinds:** `ux`, `qa`, `token-efficiency`, `judge`, `general`

### 5G. AI Cases (AI Operating System)

A boss AI orchestrates workers in a git worktree. Case modes:
`generate`, `research`, `audit`, `repair`, `migrate`, `harvest`, `benchmark`, `portfolio`, `challenge`

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/ai-cases/meta` | Mission profiles + case types metadata |
| GET | `/ai-cases` | List all AI cases |
| POST | `/ai-cases` | Create new AI case |
| GET | `/ai-cases/{id}` | Get case detail (jobs, active workers, bundle summary) |
| GET | `/ai-cases/{id}/bundle` | Get full case bundle JSON |
| GET | `/ai-cases/{id}/graph` | Get case dependency graph |
| POST | `/ai-cases/{id}/spawn` | Spawn child case (for benchmark/portfolio/challenge comparisons) |
| POST | `/ai-cases/{id}/run` | **Run the case** (creates worktree, spawns boss AI) |
| POST | `/ai-cases/{id}/stop` | Stop running case and all workers |
| POST | `/ai-cases/{id}/export/{kind}` | Export results |
| POST | `/projects/{id}/open-ai-os` | Launch AI OS app for a project |

**Export kinds:** `adr`, `backlog`, `memory`, `preset`, `recipe`, `scorecard`, `benchmark`

**Run body:**
```json
{
  "preferred_runtime": "claude",
  "open_in_tab": true
}
```

**IMPORTANT:** A running case sets up a git worktree at a separate branch.
The boss AI should work exclusively in `$SYNAPSE_AI_CASE_WORKTREE` and
write its PR summary to `$SYNAPSE_AI_CASE_DRAFT_PR`.

### 5H. Benchmarks

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/benchmarks/specs` | List benchmark specs |
| POST | `/benchmarks/specs` | Create benchmark spec |
| GET | `/benchmarks/runs` | List benchmark runs |
| POST | `/benchmarks/runs` | Create benchmark run |
| GET | `/benchmarks/runs/{id}` | Get run detail (attempts, gates, quality) |
| POST | `/benchmarks/runs/{id}/launch` | Launch benchmark (spawns AI session with scenario prompt) |
| POST | `/benchmarks/ingest-direct` | Ingest externally-run benchmark results |
| POST | `/benchmarks/runs/{id}/rescore` | Rescore a run |
| POST | `/benchmarks/runs/{id}/export` | Export benchmark report |
| GET | `/benchmarks/bug-hunt-fixtures` | List shipped bug-hunt fixtures (`name` / `fixture` / `total_bugs`) — the valid `fixture` names for score-bug-hunt |
| POST | `/benchmarks/score-bug-hunt` | Grade bug-hunt findings → `true_positives` / `false_positive_rate` / `bugs_per_1k_tokens` (stateless; Plan 3 Phase 2). Pass the answer key inline via `answer_key`, or by name via `fixture` (e.g. `"bug-hunt-fixture"`) to load the shipped key |

### 5I. Quality OS (Gates, Contracts, Evidence)

Blocking quality gates prevent work items and AI cases from completing until resolved.

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/quality-gates` | List gates. Params: `subject_type`, `subject_id`, `status`, `blocking` |
| POST | `/quality-gates` | Create quality gate |
| GET | `/quality-gates/{id}` | Get gate detail |
| POST | `/quality-gates/{id}/resolve` | Resolve gate (pass/fail + evidence) |
| POST | `/quality-gates/{id}/waive` | Waive gate with reason |
| GET | `/ui-contracts` | List UI contracts |
| POST | `/ui-contracts` | Create UI contract |
| GET | `/ui-contracts/{id}` | Get contract |
| POST | `/ui-contracts/{id}/run` | Run contract check (creates evidence + gate if failing) |
| POST | `/ui-contracts/promote` | Promote contract to persistent |
| GET | `/ui-surface-map` | Get declared UI surfaces |
| POST | `/ui-impact-audit` | Run impact audit for a list of changed files |

**Check before claiming done:**
```
GET /api/v1/quality-gates?subject_type=agent_work_item&subject_id={id}&blocking=true
```
If any gates have `status=open` and `blocking=true`, you cannot complete.

### 5J. Project Records (ADRs, Backlog, Versions)

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/projects/{id}/records` | Get all records (ADRs + backlog + versions) in one call |
| GET | `/projects/{id}/adrs` | List ADRs |
| POST | `/projects/{id}/adrs` | **Draft new ADR** (status=idea, can promote later) |
| GET | `/project-adrs/{id}` | Get ADR |
| PATCH | `/project-adrs/{id}` | Update ADR |
| DELETE | `/project-adrs/{id}` | Delete ADR |
| POST | `/project-adrs/{id}/promote` | Promote idea to numbered ADR |
| GET | `/projects/{id}/backlog` | List backlog items |
| POST | `/projects/{id}/backlog` | Add backlog item |
| PATCH | `/project-backlog/{id}` | Update item |
| DELETE | `/project-backlog/{id}` | Delete item |
| GET | `/projects/{id}/versions` | Version history |
| POST | `/projects/{id}/versions` | Add version entry |
| PATCH | `/project-versions/{id}` | Update version entry |
| DELETE | `/project-versions/{id}` | Delete version entry |

### 5K. Multi-AI Coordination

Designed for multiple AI agents running concurrently to avoid file conflicts.
**Use these when working alongside another AI session on the same project.**

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/coordination/sessions` | Register your presence |
| POST | `/coordination/sessions/{id}/heartbeat` | Keep registration alive |
| DELETE | `/coordination/sessions/{id}` | Deregister when done |
| GET | `/coordination/sessions` | See all active AI sessions on a project |
| POST | `/coordination/lanes` | Claim exclusive file editing lane |
| DELETE | `/coordination/lanes/{id}` | Release lane when done |
| GET | `/coordination/lanes` | List claimed lanes |
| POST | `/coordination/overlap` | Check if your planned files overlap with active lanes |
| GET | `/coordination/snapshot` | Full picture: all sessions + lanes |
| POST | `/coordination/detect-collisions` | Detect git working-tree collisions |

**Register body:**
```json
{
  "runtime_id": "claude",
  "project_id": "my-project",
  "role": "coder",
  "description": "Implementing feature X"
}
```

**Claim lane body:**
```json
{
  "file_paths": ["src/foo.ts", "src/bar.ts"],
  "project_id": "my-project",
  "session_id": "<your session id>"
}
```

### 5L. AI Bundles

Curated bundles that install roles, personalities, quick actions, and factory assets at once.

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/ai-bundles` | List all available bundles (installed + available) |
| POST | `/ai-bundles/install/{id}` | Install a bundle |
| DELETE | `/ai-bundles/install/{id}` | Uninstall a bundle |

### 5M. AI Factory (Recipe Builder)

Build and store reusable AI workflow components, recipes, and reference sources.

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/ai-factory/catalog` | Full catalog (components + recipes + sources) |
| GET | `/ai-components` | List components |
| POST | `/ai-components` | Create component |
| PATCH | `/ai-components/{id}` | Update component |
| DELETE | `/ai-components/{id}` | Delete component |
| GET | `/ai-recipes` | List recipes (complete AI workflows) |
| POST | `/ai-recipes` | Create recipe |
| PATCH | `/ai-recipes/{id}` | Update recipe |
| DELETE | `/ai-recipes/{id}` | Delete recipe |
| GET | `/ai-sources` | List reference sources |
| POST | `/ai-sources` | Create source (web URL, file, inspiration) |
| PATCH | `/ai-sources/{id}` | Update source |
| DELETE | `/ai-sources/{id}` | Delete source |

### 5N. Quick Actions

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/quick-actions` | List curated AI workflow templates |
| POST | `/quick-actions/{id}/launch` | Launch quick action (spawns session in `scratch` project with PROMPT.md pre-loaded) |

### 5O. Capture Inbox

The simplest way to add a note to a project without constructing a full handoff.

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/capture` | Capture quick note to backlog OR to ai_context file |

**Body:**
```json
{
  "content": "Note text here",
  "destination": "ai_context",
  "project_id": "my-project",
  "title": "Optional title",
  "source": "auto"
}
```
`destination` is `"ai_context"` or `"backlog"`. `title` only applies to backlog items.

### 5P. Installed Pages & Web Scraper Proxy

The web scraper MCP server, when installed, can be used through these proxy endpoints.

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/installed-pages` | List installed dedicated pages |
| GET | `/installed-pages/web-scraper` | Web scraper overview (connected/disconnected, base URL) |
| GET | `/installed-pages/web-scraper/harvest-capabilities` | List available harvest actions |
| GET | `/installed-pages/web-scraper/saves` | Saved pages |
| GET | `/installed-pages/web-scraper/schedules` | Scheduled scrape jobs |
| GET | `/installed-pages/web-scraper/active` | Active scrape tasks |
| POST | `/installed-pages/web-scraper/scrape-url` | Scrape a URL immediately |
| POST | `/installed-pages/web-scraper/actions/{action}` | Run a harvest action |
| POST | `/installed-pages/save-artifacts` | Save harvested artifacts to a project |

**Harvest action IDs:** `capture`, `research_url`, `to_markdown`, `extract_styles`,
`extract_structure`, `generate_react`, `generate_css`, `infer_schema`

**Harvest action body:**
```json
{
  "url": "https://example.com",
  "goal": "Understand the layout",
  "project_id": "my-project"
}
```

**Save artifacts body:**
```json
{
  "project_id": "my-project",
  "reference_urls": ["https://example.com"],
  "provenance_mode": "inspiration-only",
  "originality_notes": "Used only as inspiration",
  "benchmark_attempt_id": null,
  "artifacts": [
    {"name": "layout.md", "kind": "artifact", "mime": "text/plain", "content": "..."}
  ]
}
```

### 5Q. MCP Servers

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/mcp-servers/registry` | Browse catalog of installable MCP servers |
| GET | `/mcp-servers` | List installed MCP servers + their status |
| POST | `/mcp-servers/install` | Install an MCP server |
| PATCH | `/mcp-servers/{id}` | Update / enable / disable server |
| POST | `/mcp-servers/{id}/start` | Start server |
| POST | `/mcp-servers/{id}/stop` | Stop server |

### 5R. MCP Protocol Endpoint (Streamable HTTP)

Synapse exposes itself as an MCP server for Claude.ai custom connectors.
**Used via Cloudtap tunnel, not directly from inside PTY sessions.**

**Endpoint:** `POST /mcp/{token}`  
**Protocol:** Streamable HTTP JSON-RPC 2.0

**Available MCP tools:**
- `synapse_get_context` — orientation digest (read-only)
- `synapse_list_projects` — list projects
- `synapse_get_project_records` — ADRs, backlog, versions for a project
- `synapse_list_tools` — installed tools
- `synapse_list_quick_actions` — quick action templates
- `synapse_list_agent_squads` — agent squads
- `synapse_add_project_idea` — draft idea ADR **(only when `SYNAPSE_MCP_ALLOW_WRITES=1`)**

### 5S. Models (Ollama)

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/models/registry` | Browse curated model catalog with install status |
| GET | `/models/pulls` | List in-flight model downloads |
| POST | `/models/pull` | Start pulling a model (`{name: "llama3.2"}`) |
| POST | `/models/pull/cancel` | Cancel an in-flight pull |
| POST | `/models/remove` | Delete an installed model |

**Progress:** streamed as `v1.model.pull_progress` WS events.

### 5T. Local LLM Assistant

Built-in assistant powered by Ollama. Wraps Synapse context into a system prompt.

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/assistant/status` | Ollama installed? Server up? Available models? |
| GET | `/assistant/settings` | Get settings (enabled, default_model) |
| PATCH | `/assistant/settings` | Update settings |
| POST | `/assistant/engine/start` | Start Ollama engine |
| POST | `/assistant/engine/stop` | Stop Ollama engine |
| GET | `/assistant/chats` | List persistent chats |
| POST | `/assistant/chats` | Create chat |
| GET | `/assistant/chats/{id}` | Get chat |
| PATCH | `/assistant/chats/{id}` | Update chat |
| DELETE | `/assistant/chats/{id}` | Delete chat |
| POST | `/assistant/ask` | One-shot question (no history) |
| POST | `/assistant/chats/{id}/ask` | Ask within persistent chat |

### 5U. Marketplace (Tools)

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/marketplace` | Browse installable tool manifests |
| POST | `/marketplace/install/{id}` | **Install a tool** (downloads manifest to `tools/<id>/`) |
| DELETE | `/marketplace/install/{id}` | Uninstall tool |

### 5V. Discovery

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/discovery/scan?root=<path>&depth=<n>` | Scan filesystem for unregistered projects |
| POST | `/discovery/import` | Bulk-import selected discovered projects |

### 5W. Snapshot / Restore

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/snapshot` | Export full system snapshot to JSON (no secrets) |
| POST | `/restore` | Restore from snapshot (merge or replace) |

### 5X. Review Inbox

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/review/inbox` | Get work-item handoffs + AI-filed improvement proposals awaiting human review |
| POST | `/review/items/{id}/approve` | Approve item |
| POST | `/review/items/{id}/revise` | Request revision |
| POST | `/review/items/{id}/reject` | Reject item |
| POST | `/review/proposals` | **File an improvement proposal** — an idea for the user to approve (ADR-0025) |
| GET | `/review/proposals` | List proposals (optional `?status=open\|approved\|rejected`) |
| GET | `/review/proposals/{id}` | Get one proposal |
| POST | `/review/proposals/{id}/approve` | Approve a proposal |
| POST | `/review/proposals/{id}/reject` | Reject a proposal |
| POST | `/review/proposals/{id}/promote` | Approve + turn a project-scoped proposal into a project **backlog item** (the actionable "yes, do this"). 400 if the proposal is Synapse-wide (no project) |

**Proposal body:** `{"title": "...", "rationale_md": "...", "project_id": "...", "source_runtime": "claude", "est_effort": "S", "est_token_cost": 20000}`.
The safe **"agents brainstorm, you approve"** path — an AI files an idea here instead of acting on it unilaterally. Open proposals appear in `GET /review/inbox` under `proposals`.

### 5Y. Token Ledger

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/agent-work-items/{id}/tokens` | Record token usage for a work item |
| GET | `/agent-work-items/{id}/tokens` | Get token usage history |
| GET | `/agent-squads/{id}/token-usage` | Squad-level rollup |

### 5Z. Synapse Dev (Self-Test Loop)

Requires `SYNAPSE_DEV_ENABLED=1` in the daemon's environment.

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/synapse-dev/test/full` | Run full test suite (pytest + tsc) |
| POST | `/synapse-dev/test/file` | Run tests for a specific file |

**Full test body:**
```json
{"python_args": ["-x", "-v"], "tsc_args": []}
```

### 5AA. Personalities

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/personalities` | List AI personalities |
| POST | `/personalities` | Create personality |
| PATCH | `/personalities/{id}` | Update personality |
| DELETE | `/personalities/{id}` | Delete personality |

### 5AB. Audit Log

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/audit` | Paginated full audit log |

### 5AC. About / Roadmap

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/about/changelog` | Changelog entries |
| GET | `/about/roadmap` | Roadmap items with status |

### 5AD. System & Remote Access

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/system/network` | Network interfaces and LAN IP |
| GET | `/remote-access` | Remote access (Cloudtap) status |
| PATCH | `/system/network` | Toggle LAN exposure |

### 5AE. Auth & Pairing

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/auth/local-token` | Get local auth token |
| POST | `/pair/code` | Generate pairing code for mobile |
| POST | `/pair` | Pair a new device |
| POST | `/pair/resume` | Resume pairing |
| POST | `/pair/handoff` | Handoff pairing claim |
| POST | `/pair/claim` | Claim pairing |
| GET | `/pair/devices` | List paired devices |
| DELETE | `/pair/devices/{id}` | Revoke device |

### 5AF. Profile

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/profile` | Get profile |
| PATCH | `/profile` | Update profile |
| GET | `/profile/preferences` | Get preferences |
| PATCH | `/profile/preferences` | Update preferences |
| POST | `/profile/signup` | Sign up with Synapse accounts |
| POST | `/profile/signin` | Sign in |
| POST | `/profile/signout` | Sign out |
| GET | `/profile/catalog-state` | Catalog state for profile |
| GET | `/profile/service-connections` | List third-party connections |
| POST | `/profile/service-connections/{provider}/connect` | Connect service |
| POST | `/profile/service-connections/{provider}/verify` | Verify connection |
| DELETE | `/profile/providers/{provider}` | Disconnect provider |

### 5AG. Imports (ChatGPT)

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/imports/chatgpt` | Import ChatGPT export.zip as Markdown conversations |

**Body:** multipart with `file` (the export zip).  
Creates `imported-chatgpt` project (kind=other) with deterministic Markdown files.

### 5AH. Search

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/search?q={query}` | Global search (projects, tools, actions, settings) |

---

## 6. Gaps Analysis — What AIs Miss and Why

This section documents the **most commonly missed capabilities** by AI sessions
working inside Synapse, why they're missed, and what to do instead.

---

### GAP-01: Not reading `$SYNAPSE_AI_CONTEXT` before starting

**What's missed:** Every project has a shared memory file at `$SYNAPSE_AI_CONTEXT`
(`.synapse-ai-context.md`). It contains the project direction, active objectives,
and a log of what every previous AI session did and what was left unfinished.

**Why missed:** AIs start work immediately without checking for orientation files.

**Fix:** First thing after any PTY session starts — if `$SYNAPSE_AI_CONTEXT` is
set, read the file. If `$SYNAPSE_ROLE_PROMPT_FILE` is set, read it too.

```bash
cat "$SYNAPSE_AI_CONTEXT"
cat "$SYNAPSE_ROLE_PROMPT_FILE"
```

---

### GAP-02: Not calling `GET /api/v1/ai/context` at the start

**What's missed:** The AI context endpoint provides a complete snapshot of all
projects, tools, sessions, squads, pending work, quality gates, and recent audit
activity in one call. AIs relying only on the filesystem miss this entirely.

**Why missed:** The endpoint is not documented in the system prompt of most AI
tools; it's only in AGENTS.md.

**Fix:** On any new session where `$SYNAPSE_API` is set:
```bash
curl -s -H "X-Synapse-Token: $SYNAPSE_TOKEN" "$SYNAPSE_API/ai/context" | jq .
```

---

### GAP-03: Not checking quality gates before declaring work done

**What's missed:** Quality gates can be in a blocking state on a work item or
AI case, preventing it from completing. An AI that doesn't check will call
handoff with `status: "completed"` and get a `SynapseError` back.

**Why missed:** AIs don't know the quality gate system exists.

**Fix:** Before handoff:
```bash
curl -s -H "X-Synapse-Token: $SYNAPSE_TOKEN" \
  "$SYNAPSE_API/quality-gates?subject_type=agent_work_item&subject_id=$SYNAPSE_WORK_ITEM_ID&blocking=true" \
  | jq '.gates[] | select(.status == "open")'
```

---

### GAP-04: Not performing a handoff via API (just exiting)

**What's missed:** When an AI session ends, it should call
`POST /api/v1/agent-work-items/{id}/handoff` with a summary, the list of files
it touched, any blockers for the next agent, and a suggested next role. Without
this, the shared context file doesn't get updated and the squad doesn't know
the work is done.

**Why missed:** AIs exit their PTY session and that's it — the handoff protocol
is not taught.

**Fix:** Before exiting a squad work item session:
```bash
curl -s -X POST -H "X-Synapse-Token: $SYNAPSE_TOKEN" \
  -H "Content-Type: application/json" \
  "$SYNAPSE_API/agent-work-items/$SYNAPSE_WORK_ITEM_ID/handoff" \
  -d '{
    "status": "completed",
    "summary_md": "Implemented X, Y, Z. Tests pass.",
    "blockers_md": "",
    "files_touched": ["src/foo.ts", "tests/test_foo.py"],
    "suggested_next_role": "reviewer",
    "verdict": {
      "blocking": false,
      "severity": "info",
      "surface_ids": [],
      "contract_ids": [],
      "recommended_next_step": "Run reviewer pass"
    },
    "source": "auto"
  }'
```

---

### GAP-05: Not recording token usage

**What's missed:** Every AI worker is expected to self-report its token usage to
the token ledger so Synapse can prove efficiency vs. a baseline.

**Why missed:** No AI tool does this automatically.

**Fix:** After a work session completes (check the CLI usage summary):
```bash
curl -s -X POST -H "X-Synapse-Token: $SYNAPSE_TOKEN" \
  -H "Content-Type: application/json" \
  "$SYNAPSE_API/agent-work-items/$SYNAPSE_WORK_ITEM_ID/tokens" \
  -d '{"input_tokens": 12000, "output_tokens": 3500, "model": "claude-opus-4-5"}'
```

---

### GAP-06: Not using multi-AI coordination when working alongside others

**What's missed:** If another AI is editing Synapse concurrently, file lane
collisions cause merge conflicts. The coordination API lets you register your
presence, claim exclusive lanes for files you're editing, and detect collisions
before they happen.

**Why missed:** AIs don't know other AIs might be active; they assume they're alone.

**Fix:** At start of a session when `$SYNAPSE_API` is set:
```bash
# 1. Check if anyone else is editing
curl -s -H "X-Synapse-Token: $SYNAPSE_TOKEN" \
  "$SYNAPSE_API/coordination/sessions?project_id=$SYNAPSE_PROJECT_ID"

# 2. Register your session
SESSION_REG=$(curl -s -X POST -H "X-Synapse-Token: $SYNAPSE_TOKEN" \
  -H "Content-Type: application/json" \
  "$SYNAPSE_API/coordination/sessions" \
  -d "{\"runtime_id\": \"claude\", \"project_id\": \"$SYNAPSE_PROJECT_ID\", \"role\": \"coder\"}")
COORD_SESSION_ID=$(echo $SESSION_REG | jq -r .id)

# 3. Before editing files, check overlaps
curl -s -X POST -H "X-Synapse-Token: $SYNAPSE_TOKEN" \
  -H "Content-Type: application/json" \
  "$SYNAPSE_API/coordination/overlap" \
  -d "{\"paths\": [\"src/foo.ts\"], \"project_id\": \"$SYNAPSE_PROJECT_ID\", \"exclude_session_id\": \"$COORD_SESSION_ID\"}"

# 4. Claim lanes
curl -s -X POST -H "X-Synapse-Token: $SYNAPSE_TOKEN" \
  -H "Content-Type: application/json" \
  "$SYNAPSE_API/coordination/lanes" \
  -d "{\"file_paths\": [\"src/foo.ts\"], \"project_id\": \"$SYNAPSE_PROJECT_ID\", \"session_id\": \"$COORD_SESSION_ID\"}"

# 5. Clean up at end
curl -s -X DELETE -H "X-Synapse-Token: $SYNAPSE_TOKEN" \
  "$SYNAPSE_API/coordination/sessions/$COORD_SESSION_ID"
```

---

### GAP-07: Not using the Coder Thread dispatch (just spawning raw PTY)

**What's missed:** `POST /coder-threads/{id}/dispatch` creates a full audit trail:
a message record, a run record linked to the session, automatic token + I/O
tracking, and linkage to benchmark attempts. A raw PTY spawn via `/pty` or
`/workbench` has none of this.

**Why missed:** AIs use the simpler workbench endpoint.

**Fix:** For structured work on a project, prefer creating a coder thread first:
```bash
THREAD=$(curl -s -X POST -H "X-Synapse-Token: $SYNAPSE_TOKEN" \
  -H "Content-Type: application/json" \
  "$SYNAPSE_API/projects/$SYNAPSE_PROJECT_ID/coder-threads" \
  -d '{"title": "Feature: auth flow"}')
THREAD_ID=$(echo $THREAD | jq -r .id)

# Then dispatch
curl -s -X POST -H "X-Synapse-Token: $SYNAPSE_TOKEN" \
  -H "Content-Type: application/json" \
  "$SYNAPSE_API/coder-threads/$THREAD_ID/dispatch" \
  -d '{"content_md": "Implement the auth flow per the ADR.", "runtime_id": "claude"}'
```

---

### GAP-08: Not checking the review inbox before starting new work

**What's missed:** If the user left feedback via the Review Inbox (approve/revise/reject),
an AI that starts fresh work misses this and may redo or contradict the user's direction.

**Why missed:** AIs don't know a review inbox exists.

**Fix:**
```bash
curl -s -H "X-Synapse-Token: $SYNAPSE_TOKEN" "$SYNAPSE_API/review/inbox"
```

---

### GAP-09: Not using `POST /capture` to append quick context notes

**What's missed:** `POST /capture` is the simplest way to append a note to the
shared AI context file without constructing a full handoff. Useful mid-session
for noting a decision or a risk.

**Why missed:** AIs directly edit files instead.

**Fix:**
```bash
curl -s -X POST -H "X-Synapse-Token: $SYNAPSE_TOKEN" \
  -H "Content-Type: application/json" \
  "$SYNAPSE_API/capture" \
  -d "{\"content\": \"Decided to use DPAPI for secrets storage (Contract 25).\", \"destination\": \"ai_context\", \"project_id\": \"$SYNAPSE_PROJECT_ID\", \"source\": \"auto\"}"
```

---

### GAP-10: Not drafting ADRs via API when making architectural decisions

**What's missed:** `POST /api/v1/projects/{id}/adrs` lets an AI create a draft ADR
(status=idea) that gets promoted to a numbered ADR later. This is the proper way to
document architectural decisions — not by writing a `.md` file manually.

**Why missed:** AIs write ADR markdown files directly, bypassing the DB records.

**Fix:**
```bash
curl -s -X POST -H "X-Synapse-Token: $SYNAPSE_TOKEN" \
  -H "Content-Type: application/json" \
  "$SYNAPSE_API/projects/$SYNAPSE_PROJECT_ID/adrs" \
  -d '{
    "title": "Use DPAPI for secrets at rest",
    "status": "idea",
    "content_md": "## Context\nContract 25 requires secrets to be encrypted...\n## Decision\nUse Windows DPAPI...",
    "source": "auto"
  }'
```

---

### GAP-11: Not running self-tests via `synapse-dev` after changes

**What's missed:** `POST /api/v1/synapse-dev/test/full` runs pytest + tsc and returns
a structured pass/fail report. AIs that skip this leave broken code.

**Why missed:** AIs run `pytest` in the terminal but don't report results back to Synapse.

**Fix:** After completing changes (requires `SYNAPSE_DEV_ENABLED=1`):
```bash
curl -s -X POST -H "X-Synapse-Token: $SYNAPSE_TOKEN" \
  -H "Content-Type: application/json" \
  "$SYNAPSE_API/synapse-dev/test/full" \
  -d '{"python_args": ["-x"]}' | jq '{ok: .ok, failed: .pytest.failed, tsc_ok: .tsc.ok}'
```

---

### GAP-12: Not using the web scraper harvest actions when researching

**What's missed:** The web scraper proxy at
`POST /installed-pages/web-scraper/actions/{action}` can turn a URL into:
- `to_markdown` — a reusable reference brief
- `extract_styles` — design tokens
- `extract_structure` — layout notes
- `generate_react` — a React component candidate
- `infer_schema` — typed data contracts

All results can be saved to a project via `save-artifacts`.

**Why missed:** AIs don't know the web scraper is installed or proxied.

**Fix:** First check if the scraper is available:
```bash
curl -s -H "X-Synapse-Token: $SYNAPSE_TOKEN" \
  "$SYNAPSE_API/installed-pages/web-scraper" | jq .status
# If "connected":
curl -s -X POST -H "X-Synapse-Token: $SYNAPSE_TOKEN" \
  -H "Content-Type: application/json" \
  "$SYNAPSE_API/installed-pages/web-scraper/actions/to_markdown" \
  -d '{"url": "https://example.com", "goal": "Understand the layout"}'
```

---

### GAP-13: Not using backlog items to track work discovered mid-session

**What's missed:** When an AI discovers a TODO or a follow-up task, it either
adds a code comment or ignores it. The proper path is to add a backlog item.

**Fix:**
```bash
curl -s -X POST -H "X-Synapse-Token: $SYNAPSE_TOKEN" \
  -H "Content-Type: application/json" \
  "$SYNAPSE_API/projects/$SYNAPSE_PROJECT_ID/backlog" \
  -d '{"title": "Add integration tests for auth flow", "status": "todo", "source": "auto"}'
```

---

### GAP-14: Not using coordination preflight numbers (ADR/migration numbering)

**What's missed:** New ADR and migration numbers should be claimed via
`scripts/preflight.ps1` (or `GET /coordination/snapshot`) to avoid number
collisions when two AI sessions are active.

**Why missed:** AIs pick numbers by scanning the filesystem themselves.

**Fix:**
```bash
# From repo root in a PTY session:
pwsh -NoProfile -File scripts/preflight.ps1
# Returns: next-free ADR number, next migration number, uncommitted footprint
```

---

### GAP-15: Not using the AI health report to detect pre-existing failures

**What's missed:** `GET /api/v1/ai/health-report` returns the last 5 error audit
entries. If the daemon was already in an error state before your session started,
you should know.

**Fix:**
```bash
curl -s -H "X-Synapse-Token: $SYNAPSE_TOKEN" \
  "$SYNAPSE_API/ai/health-report" | jq '{version: .version, errors: .audit_tail}'
```

---

### GAP-16: Not understanding the `ai_context` metadata field in context response

**What's missed:** In `GET /api/v1/ai/context`, each project has an `ai_context`
field: `{path, exists, size_bytes, last_modified}`. If `exists: true` and
`size_bytes > 0`, there is prior context to read. If `exists: false`, you should
create the file — the daemon creates it automatically on squad creation.

---

### GAP-17: Not delegating sub-tasks via `POST /agent-work-items/{id}/delegate`

**What's missed:** A planner or boss work item can spawn child work items for
specialists (coder, reviewer) via the delegate endpoint instead of trying to do
everything itself. This keeps each session focused.

**Fix:** From within a planner session:
```bash
curl -s -X POST -H "X-Synapse-Token: $SYNAPSE_TOKEN" \
  -H "Content-Type: application/json" \
  "$SYNAPSE_API/agent-work-items/$SYNAPSE_WORK_ITEM_ID/delegate" \
  -d '{
    "title": "Implement authentication middleware",
    "instructions_md": "## Task\nAdd JWT middleware per ADR-0015...",
    "assigned_role_id": "coder",
    "preferred_runtime": "claude",
    "source": "auto"
  }'
```

---

### GAP-18: Not using AI case export to capture results durably

**What's missed:** After a completed AI case, `POST /ai-cases/{id}/export/{kind}`
converts the case results into ADRs, backlog items, memory updates, recipes, scorecards,
or benchmark specs. Results vanish if not exported before the case is deleted.

**Fix:** After a case is complete:
```bash
curl -s -X POST -H "X-Synapse-Token: $SYNAPSE_TOKEN" \
  "$SYNAPSE_API/ai-cases/$SYNAPSE_AI_CASE_ID/export/adr"
curl -s -X POST -H "X-Synapse-Token: $SYNAPSE_TOKEN" \
  "$SYNAPSE_API/ai-cases/$SYNAPSE_AI_CASE_ID/export/memory"
```
Export kinds: `adr`, `backlog`, `memory`, `preset`, `recipe`, `scorecard`, `benchmark`

---

## 7. Recommended AI Session Start Protocol

Copy this as a startup script for any Synapse PTY session:

```bash
#!/bin/bash
# Synapse AI Session Startup
# Run this at the start of every session where $SYNAPSE_API is set.

if [ -z "$SYNAPSE_API" ]; then
  echo "[synapse] No SYNAPSE_API env var -- skipping orientation."
  exit 0
fi

AUTH_HEADER="X-Synapse-Token: $SYNAPSE_TOKEN"

# 1. Read role prompt if available
if [ -n "$SYNAPSE_ROLE_PROMPT_FILE" ] && [ -f "$SYNAPSE_ROLE_PROMPT_FILE" ]; then
  echo "=== ROLE PROMPT ==="
  cat "$SYNAPSE_ROLE_PROMPT_FILE"
fi

# 2. Read shared project memory
if [ -n "$SYNAPSE_AI_CONTEXT" ] && [ -f "$SYNAPSE_AI_CONTEXT" ]; then
  echo "=== PROJECT AI CONTEXT ==="
  cat "$SYNAPSE_AI_CONTEXT"
fi

# 3. Fetch AI context digest
echo "=== SYNAPSE STATE ==="
curl -s -H "$AUTH_HEADER" "$SYNAPSE_API/ai/context" | jq '{
  projects: [.projects[] | {id, name, status, kind}],
  active_sessions: (.sessions | length),
  blocking_gates: .quality.open_blocking_gate_count,
  audit_tail: [.audit_tail[:3][] | {at, action, result}]
}'

# 4. Check review inbox
INBOX=$(curl -s -H "$AUTH_HEADER" "$SYNAPSE_API/review/inbox")
PENDING=$(echo $INBOX | jq '.work_items | length')
if [ "$PENDING" -gt "0" ]; then
  echo "=== REVIEW INBOX: $PENDING items pending ==="
  echo $INBOX | jq '.work_items[] | {id, title, status}'
fi

# 5. Check for concurrent AI sessions (multi-AI safety)
if [ -n "$SYNAPSE_PROJECT_ID" ]; then
  SESSIONS=$(curl -s -H "$AUTH_HEADER" \
    "$SYNAPSE_API/coordination/sessions?project_id=$SYNAPSE_PROJECT_ID")
  SESSION_COUNT=$(echo $SESSIONS | jq '. | length')
  if [ "$SESSION_COUNT" -gt "0" ]; then
    echo "=== WARNING: $SESSION_COUNT other AI session(s) active on this project ==="
    echo $SESSIONS | jq '.[] | {id, runtime_id, role, description}'
  fi
fi

echo "=== Startup complete. Begin work. ==="
```

---

*Document generated by full codebase audit on 2026-07-06.*  
*Source: `daemon/synapse_daemon/routes_*.py`, `ws.py`, `app.py`, `ai_context_memory.py`*  
*Re-audit when new `routes_*.py` files are added to `daemon/synapse_daemon/`.*
