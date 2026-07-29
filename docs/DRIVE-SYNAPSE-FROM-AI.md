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
- **Auth:** every call needs the header `X-Synapse-Token: <token>`. The token is the daemon's local token —
  read it from `data/auth-token` in the repo (same machine), or the operator hands it to you (remote).

```bash
SYN=http://127.0.0.1:7878/api/v1
TOK=$(cat data/auth-token)          # same-machine
curl -s "$SYN/health" -H "X-Synapse-Token: $TOK"
```

## 2. Orient before acting

Always start here so you know what exists:

- `GET /api/v1/ai/context` — capability digest: projects (with paths, ports, health), per-project AI-context
  files, and how to call things. **Read this first.**
- `GET /api/v1/openapi.json` — the full endpoint surface (235+ routes) + every request/response schema.
  `GET /api/v1/docs` is the same as browsable Swagger UI.
- `GET /api/v1/coordination/snapshot` — who else (other AIs) is working + which files are claimed. Register
  yourself + claim a lane before editing shared files (see `AGENTS.md`).

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

## 8. Drive Synapse remotely — the MCP connector

Synapse exposes a Model Context Protocol server at **`/mcp/<token>`** (ADR-0012), reachable over the auto-on
WAN tunnel. Today it is **read-only** (`synapse_get_context`, `synapse_list_projects/tools/quick_actions/agent_squads`,
`synapse_get_project_records`). Drive tools (create/launch squad, run quick-action) are gated behind
`SYNAPSE_MCP_ALLOW_WRITES` and are being added incrementally (ADR-0027). `GET /api/v1/mcp/connector` returns the
ready-made connector URL (tunnel URL + path token).

> **Security:** the `X-Synapse-Token` (and the connector's path token) is the whole trust boundary — with the
> WAN tunnel on, anyone holding the token can drive Synapse. Treat it like a password; don't paste it into
> untrusted places. Turn WAN off in Settings → Network (or `PATCH /api/v1/system/network {"wan_auto_start":false}`)
> if you don't want remote exposure.

---

## Quick reference

| Goal | Call |
|---|---|
| Orient | `GET /ai/context`, `GET /openapi.json`, `GET /coordination/snapshot` |
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

_All paths are under `/api/v1` unless noted. Exact bodies: `GET /api/v1/openapi.json`._
