# ADR-0013: Autonomous AI-boss (full autonomy + kill switch)

- Status: Accepted (v1 = launchable boss session)
- Date: 2026-06-23
- Deciders: Justin (owner — chose "full autonomy + kill switch"), Claude

## Context

The owner wants an "AI boss" that, given a goal, can autonomously: decide on
(or **create**) a project, plan a team, **pick its own workers**, spin them up,
**use existing tools/workflows instead of writing from scratch** (installing or
authoring them when useful), and **learn as it goes** inside Synapse. The owner
explicitly chose **full autonomy with a kill switch** for the end state.

The substrate already exists after ADR-0010/0011/0012:
- `GET /api/v1/ai/context` — the boss's sense organ (projects, tools, sessions,
  squads, role templates, the records + MCP endpoints, `endpoints_for_ai`).
- Agent Squads — roles with a `boss/supervisor/worker` hierarchy, work items,
  PTY workers, handoffs to `.synapse-ai-context.md`, and a **kill switch**
  (`POST /api/v1/agent-squads/{id}/stop`).
- Write endpoints the boss needs: create project (`POST /projects`), create
  squad + work items, launch workers, install marketplace tools, record
  decisions (`POST /projects/{id}/adrs`), add backlog/versions.
- Workbench/quick-action PTYs already export `$SYNAPSE_API`, `$SYNAPSE_TOKEN`,
  `$SYNAPSE_PROJECT_ID` so a spawned AI can drive the authed REST API.

So the boss does **not** need a new daemon orchestration engine. The boss *is*
an AI session (claude/codex) launched with a strong orchestration prompt that
drives the existing REST surface.

## Decision

Ship the autonomous boss as a **launchable quick-action**:
`templates/quick-actions/autonomous-boss.json`. Launching it spawns an AI
session primed as the boss; the AI then runs the loop autonomously over REST:

1. **Orient** — `GET $SYNAPSE_API/ai/context` (projects, tools, quick-actions,
   squads, roles).
2. **Decide the project** — reuse an existing one or **create** a new project
   (`POST /projects`) for the goal.
3. **Post a plan** — create a squad (lead = `boss`) with a `goal_md`, so the
   plan is visible to the human in the Squads cockpit (transparency without a
   blocking gate).
4. **Staff it** — create work items per role (planner/supervisor/implementer/
   reviewer/tester/...) and **launch** the workers it picks.
5. **Leverage, don't reinvent** — prefer existing tools + quick-actions; install
   a marketplace tool when useful; only author a new tool/manifest if nothing
   fits.
6. **Record + learn** — capture decisions as project ADRs
   (`POST /projects/{id}/adrs`), keep `.synapse-ai-context.md` updated via
   handoffs, and add backlog/version entries so the next run starts smarter.

### Safety
- **Human-initiated.** Nothing auto-starts; the user launches the boss from the
  Sessions quick-actions rail.
- **Kill switch.** The user stops everything with the squad `Stop all` (ADR-0010)
  / "Stop all running" on Processes.
- **No elevation / no admin** (Contract #16 unchanged). The boss operates only
  through the daemon's existing authed REST surface.
- **Transparency.** The boss writes its plan to the squad goal + records
  decisions as ADRs, so the human can watch and intervene.

## Consequences
- Full autonomy is delivered with **no new daemon subsystem** — it composes the
  ADR-0010/0011/0012 primitives. The boss's "learning" is the durable state it
  writes (ADRs, `.synapse-ai-context.md`, backlog) that future runs read.
- The boss can create projects, spawn workers, and install tools on its own;
  the kill switch + human-initiation bound the blast radius.

## Future (not in v1)
- A daemon-side scheduler so the boss can be triggered on a cron / event.
- A "supervisor escalation" protocol when two squads (two bosses) share a
  project — they already share `.synapse-ai-context.md`; formalize a handshake.
- Tighter tool-authoring: a `POST /quick-actions` so the boss can persist a new
  workflow via REST instead of writing the file directly.
