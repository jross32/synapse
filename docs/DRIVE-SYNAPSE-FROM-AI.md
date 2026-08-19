# Drive Synapse from an AI

**Audience:** an AI agent (e.g. a Claude Code session, or a remote AI over the WAN tunnel) that wants to
**drive Synapse** — spin up AI squads, run workflows, harvest the web, register + evaluate an app — through
Synapse's HTTP API. This is the practical companion to `AGENTS.md` (which covers the coordination + idea-filing
habits) and ADR-0027 (the AI-drivable design).

> **Golden rule:** the endpoints below are the map; **`GET /api/v1/openapi.json` is the source of truth** for
> exact request/response shapes. When in doubt about a body, read the live schema — it never drifts from the code.

---

## 1. Connect + authenticate

- **Base URL (same machine):** `http://127.0.0.1:7878`
- **Base URL (remote / from anywhere):** the WAN tunnel URL. Get it from `GET /api/v1/mcp/connector`
  (`connector_url` / `tunnel_url`) — the Cloudtap tunnel now auto-opens on daemon start (ADR-0026), so a
  `*.trycloudflare.com` URL is usually already live.
- **Auth (same machine):** every call needs `X-Synapse-Token`. A trusted local operator may read the
  daemon token from `data/auth-token`. Synapse-launched workers receive a narrower task credential.
- **Remote warning:** the current WAN REST path still accepts the desktop root token for compatibility.
  That is legacy, high-risk, operator-supervised access—not project-scoped public automation. Do not hand
  the root token to a routine or third-party AI. ADR-0036 requires scoped, expiring credentials before
  public unattended drive is considered safe.

```bash
SYN=http://127.0.0.1:7878/api/v1
TOK=$(cat data/auth-token)          # same-machine
curl -s "$SYN/health" -H "X-Synapse-Token: $TOK"
```

## 2. Orient before acting

Always start here so you know what exists:

- `GET /api/v1/ai/context` — capability digest: projects (with paths, ports, health), per-project AI-context
  files, and how to call things. **Read this first.**
- `GET /api/v1/openapi.json` — the complete live endpoint surface (currently 226 paths / 290 operations)
  plus every request/response schema. Treat the live document, not these counts, as canonical.
  `GET /api/v1/docs` is the same as browsable Swagger UI.
- `GET /api/v1/coordination/snapshot` — who else (other AIs) is working + which files are claimed. Register
  yourself + claim a lane before editing shared files (see `AGENTS.md`).

## 2b. Your session — you are visible, and that's the point (ADR-0028)

When you register (`POST /api/v1/coordination/sessions`) Synapse gives you a **session number**
(`seq` → shown to the operator as `#007`) and grades your connection:

| level | code | means |
|---|---|---|
| 🟢 green | `ok` | you're connected with full control |
| 🟡 yellow | `degraded.mcp_unavailable` | an enabled MCP server you may need is offline |
| 🟡 yellow | `degraded.no_project` | you registered without a `project_id`, so project-scoped work is unavailable |
| 🔴 red | `failed.internal` | registration failed |

**Register with a `project_id` to come up green.** The register response carries your `seq`,
`connection_level`, and `connection_code` — read them back to know how you look to the operator.

The human sees this immediately: a **notification** ("Session #007 — Claude connected"), a bell badge, and
a **Live** tab. Deep View (the default) shows current focus, detailed deliberate reasoning summaries,
decisions, searches/findings, action/evidence receipts, MCP/tool use, squads, workers, token evidence, and
correlated terminal output; Summary View keeps only the major story. So use meaningful `agent_label`, `task`,
and heartbeat `last_intent` values.

Registration returns `id` (the session id), `resume_key`, and a one-time `session_key`.
After registration, add both `X-Synapse-Session: <id>` and
`X-Synapse-Session-Key: <session_key>` to other Synapse API calls. The daemon will record
safe method/result receipts automatically. Report richer boundaries explicitly:

```bash
curl -s "$SYN/activity/sessions/$SESSION_ID/events" -X POST \
  -H "X-Synapse-Token: $TOK" \
  -H "X-Synapse-Session: $SESSION_ID" \
  -H "X-Synapse-Session-Key: $SESSION_KEY" \
  -H 'Content-Type: application/json' \
  -d '{"category":"decision","status":"success","title":"Kept Reflex per-worker",\
"summary_md":"A shared fixed-port controller could create stale ownership; isolated stdio children preserve automatic availability without cross-AI contention.",\
"authority":"none"}'
```

Deep View is intentionally rich, but it is a deliberate operator summary—not private hidden model
chain-of-thought. Never place credentials, auth tokens, secret values, or raw sensitive tool output in it.

Read the same picture yourself:

```bash
curl -s "$SYN/activity/sessions"        -H "X-Synapse-Token: $TOK"   # every session, #-numbered
curl -s "$SYN/activity/notifications"   -H "X-Synapse-Token: $TOK"   # the operator's feed
curl -s "$SYN/coordination/snapshot"    -H "X-Synapse-Token: $TOK"   # live peers + claimed file lanes
```
`GET /api/v1/ai/context` also carries an `ai_activity` block (connected sessions + the recent feed).
Over MCP: `synapse_list_sessions` and `synapse_recent_activity` (read-only, always available) — see
section 8 for the full always-on read-tool list, including `synapse_list_playbooks` / `synapse_get_playbook`.

## 3. Drive an AI squad (build / debug / review an app)

A **squad** is a team of role-based AI workers. Canonical flow:

```bash
# a) create the squad on a project (roles: planner/implementer/reviewer/researcher/... — GET /agent-role-templates)
SQUAD=$(curl -s "$SYN/agent-squads" -H "X-Synapse-Token: $TOK" -H 'Content-Type: application/json' \
  -d '{"project_id":"my-app","name":"Backend hardening","lead_role_id":"planner"}' | jq -r .id)

# b) add a work item (a unit of work assigned to a role)
WI=$(curl -s "$SYN/agent-squads/$SQUAD/work-items" -H "X-Synapse-Token: $TOK" -H 'Content-Type: application/json' \
  -d '{"title":"Add input validation to the /orders endpoint","assigned_role_id":"implementer"}' | jq -r .id)

# c) launch it (spawns the worker; MCP servers the role is bound to are auto-wired in)
curl -s "$SYN/agent-work-items/$WI/launch" -X POST -H "X-Synapse-Token: $TOK"

# d) monitor
curl -s "$SYN/agent-squads/$SQUAD" -H "X-Synapse-Token: $TOK"           # squad + work-item states
curl -s "$SYN/agent-squads/$SQUAD/capacity" -H "X-Synapse-Token: $TOK"  # concurrency / budget

# e) hand off / delegate / set status as work progresses
#    POST /agent-work-items/{id}/handoff   (append a structured handoff to the project AI-context)
#    POST /agent-work-items/{id}/delegate  (spawn a supervised child)
#    POST /agent-work-items/{id}/status

# f) KILL SWITCH — stop the whole squad at any time
curl -s "$SYN/agent-squads/$SQUAD/stop" -X POST -H "X-Synapse-Token: $TOK"
```

The same installed MCP list is translated at launch for Synapse's three built-in CLI runtimes: Claude,
Codex, and GitHub Copilot. Role binding still applies. A newly enabled MCP appears in the **next** worker;
an already-running AI process cannot acquire a new MCP dynamically.

## 4. Run a workflow (quick-action)

"Workflows" are **quick-actions** — curated, one-call AI recipes (e.g. `autonomous-boss`, `bug-hunt-squad`).

```bash
curl -s "$SYN/quick-actions" -H "X-Synapse-Token: $TOK"                 # list available workflows
curl -s "$SYN/quick-actions/bug-hunt-squad/launch" -X POST \
  -H "X-Synapse-Token: $TOK" -H 'Content-Type: application/json' -d '{"project_id":"my-app"}'
```

## 5. Harvest the web (web-scraper)

The **web-scraper is its own MCP server**, already auto-wired into Synapse agents and available directly to a
Claude Code session (`mcp__web-scraper__*` — `detect_site`, `scrape_url`, `extract_*`, `crawl_sitemap`, …).
Use it directly for research/extraction; Synapse squads you launch get it wired in automatically when their
role is bound to it. Start with `detect_site` / `preflight_url` before scraping an unknown site.

## 6. Register + evaluate an app (Quality OS + benchmarks)

- **Projects:** `GET/POST /api/v1/projects`, `POST /projects/{id}/launch|stop`, `GET /projects/{id}/logs`,
  `GET /projects/{id}/disk-usage`. Per-project decisions/backlog/versions live under the project records API.
- **Quality gates + UI contracts:** `/api/v1/ui-contracts` (run a contract → evidence), `/api/v1/quality-gates`
  (a FAIL opens a blocking gate; `assert_subject_can_complete` blocks "done" until gates clear).
- **Bug-hunt scoring:** `POST /api/v1/benchmarks/score-bug-hunt` grades findings against a fixture answer key
  (`bugs_per_1k_tokens`, recall, false-positive-rate). `GET /api/v1/benchmarks/bug-hunt-fixtures` lists fixtures.
- **Review inbox:** work handed back + filed improvement ideas land at `GET /api/v1/review/inbox`; approve /
  reject / promote proposals via `/api/v1/review/proposals/{id}/...`.

## 7. Capture a note / idea into a project

```bash
curl -s "$SYN/capture" -X POST -H "X-Synapse-Token: $TOK" -H 'Content-Type: application/json' \
  -d '{"project_id":"my-app","destination":"ai_context","content":"The /orders 500 repros on empty body."}'
```
`destination: "backlog"` files a backlog item instead; `ai_context` appends to the project's shared
`.synapse-ai-context.md` so the next agent run sees it.

## 8. Drive Synapse remotely — two ways

**Legacy/operator-supervised WAN REST:** the tunnel currently exposes the token-guarded REST API, not just
`/mcp`. Using the desktop root token remotely grants root-equivalent Synapse control. This is useful for the
owner's supervised recovery but is not the safe public AI contract. Keep it disabled unless actively used;
scoped public credentials from ADR-0036 must land before unattended remote AI drive.

**For MCP-native clients** (e.g. the claude.ai or ChatGPT custom connector) Synapse also speaks Model Context
Protocol at **`/mcp/<token>`** (ADR-0012, `daemon/synapse_daemon/mcp_connector.py`). Read tools are always
on — `synapse_get_context`, `synapse_list_projects`, `synapse_get_project_records`, `synapse_list_tools`,
`synapse_list_quick_actions`, `synapse_list_skill_packs` / `synapse_get_skill_pack`, `synapse_list_agent_squads`,
`synapse_list_sessions`, `synapse_recent_activity`, and `synapse_list_playbooks` / `synapse_get_playbook`
(step-by-step procedures for driving something outside this codebase, e.g. a third-party web UI — see
`playbooks.py`).

**Write/dispatch tools are on by default**, not off: `boot_config.mcp_writes_enabled` defaults to `True`, with
a Settings UI toggle (`PhoneAccessPanel.tsx`) to turn it off, and `SYNAPSE_MCP_ALLOW_WRITES` still available
as an env override that wins over the persisted setting either way. When writes are enabled, the connector
advertises a much larger set than the original four: `synapse_add_project_idea`, `synapse_capture_note`,
`synapse_create_squad`, `synapse_add_work_item`, `synapse_runtime_status`, `synapse_list_blueprints`,
`synapse_delegate_module` (dispatch a coding runtime to write one module), `synapse_launch_work_item`
(read-only despite the name — it returns the REST call that starts a worker, launching stays on
`POST /agent-work-items/{id}/launch`), `synapse_run_command`, `synapse_read_file`, `synapse_write_file`,
`synapse_http` (localhost/private-IP only), `synapse_list_mcp_tools` / `synapse_call_mcp_tool` (proxy to any
other registered MCP server — Reflex, Playwright, the web scraper), and `synapse_report_playbook_status`.
Every tool carries an explicit `readOnlyHint`/`destructiveHint` annotation (`_TOOL_ANNOTATIONS`) so an MCP
client like ChatGPT can tell which calls are safe to run without confirmation — the genuinely open-ended ones
(`synapse_run_command`, `synapse_call_mcp_tool`, `synapse_http`) are annotated as destructive on purpose,
not softened to slip past a client's safety layer.

There is a **single connector URL**, not two — `GET /api/v1/mcp/connector` returns `connector_url` (tunnel URL
+ path token, full access per the current toggle) and `read_only_url` (the same URL with `?mode=read`
appended). `?mode=read` pins a link to read-only regardless of the server-wide setting, which is what makes a
read-only link worth handing out separately: it stays read-only even while the operator's own link can write.

These MCP writes are a global switch, scoped only by the read-only URL variant, and do not yet share the
scoped ADR-0036 execution service. Do not interpret them as project-scoped write access. The future write
connector will use revocable project capabilities and call the same application services as REST.

> **Security:** the `X-Synapse-Token` (and the connector's path token) is the whole trust boundary — with the
> WAN tunnel on, anyone holding the token can drive Synapse. Treat it like a password; don't paste it into
> untrusted places. Turn WAN off in Settings → Network (or `PATCH /api/v1/system/network {"wan_auto_start":false}`)
> if you don't want remote exposure.

## 9. Restart Synapse and follow the handoff

Use this only when the operator intends to recycle the whole app. It triggers the same visible flow as
**Restart Synapse** in the tray: the user sees each measured stage and a stable code if anything fails.

```bash
OP=$(curl -s "$SYN/system/restart" -X POST \
  -H "X-Synapse-Token: $TOK" -H 'Content-Type: application/json' \
  -d '{"source":"auto"}' | jq -r .operation.operation_id)

# The current connection may drop while services restart. Reconnect, then inspect:
curl -s "$SYN/system/restart" -H "X-Synapse-Token: $TOK" | jq .operation
curl -s "$SYN/system/restart/errors" -H "X-Synapse-Token: $TOK" | jq .error_catalog
```

Do not post stage updates yourself; Electron owns those measured facts. A duplicate live request returns
`SYN-RST-001`, and an abandoned operation expires as `SYN-BOOT-301` after ten minutes.

---

## Quick reference

| Goal | Call |
|---|---|
| Orient | `GET /ai/context`, `GET /openapi.json`, `GET /coordination/snapshot` |
| Runtime readiness + measured usage | `GET /ai/runtimes` |
| Execution receipt | `GET /ai/executions/{execution_id}` |
| Local operator capacity evidence | `POST /ai/runtimes/{runtime_id}/capacity` or `/recheck` |
| Create squad | `POST /agent-squads` |
| Add work | `POST /agent-squads/{id}/work-items` |
| Run work | `POST /agent-work-items/{id}/launch` |
| Monitor | `GET /agent-squads/{id}` |
| Stop (kill switch) | `POST /agent-squads/{id}/stop` |
| Run a workflow | `POST /quick-actions/{id}/launch` |
| Capture a note | `POST /capture` |
| Register/launch app | `POST /projects`, `POST /projects/{id}/launch` |
| Evaluate | `/ui-contracts`, `/quality-gates`, `POST /benchmarks/score-bug-hunt` |
| Review inbox | `GET /review/inbox` |
| Remote connector URL | `GET /mcp/connector` |
| Restart Synapse | `POST /system/restart`, then `GET /system/restart` |

_All paths are under `/api/v1` unless noted. Exact bodies: `GET /api/v1/openapi.json`._
