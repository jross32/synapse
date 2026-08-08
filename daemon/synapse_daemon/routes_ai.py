"""AI-facing context endpoint (v0.1.29 · ADR-0002 Phase B).

  GET /api/v1/ai/context
      Returns a compact, AI-readable digest of the running Synapse instance:
      projects, installed tools, active PTY sessions, recent audit entries.
      Designed for a Claude / Codex session running inside a Sessions tab to
      grab so it can introspect "what's here" without sifting through the
      individual REST endpoints.

The shape stays small and deliberately flat: the AI is the consumer, not a
TS-codegen target. Anything noisy (full transcripts, full audit log) is
linked by id so the AI can fetch on demand.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from fastapi import APIRouter

from . import __version__
from . import projects as projects_module
from . import agent_squads as agent_squads_module
from . import ai_bundles as ai_bundles_module
from . import ai_cases as ai_cases_module
from . import ai_factory as ai_factory_module
from . import benchmarks as benchmarks_module
from . import coder_workspace as coder_workspace_module
from . import local_models as local_models_module
from . import mcp_servers as mcp_servers_module
from . import quality_os as quality_os_module
from .ai_context_memory import ai_context_metadata
from .files_storage import list_for_project
from .storage import Storage
from .pty_sessions import PtySessionManager
from .synapse_dev import SynapseDevManager
from .time_utils import utc_now
from .tools_registry import ToolRegistry

#: Cap inlined files per project so the AI context payload stays small.
#: A Claude session can hit /api/v1/projects/{id}/files for the full list.
_INLINE_FILE_CAP = 25


def _file_to_inline(row) -> dict[str, Any]:  # noqa: ANN001
    return {
        "id": row.id,
        "original_name": row.original_name,
        "size_bytes": row.size_bytes,
        "mime": row.mime,
        "source": row.source,
        "uploaded_at": row.uploaded_at,
    }


def build_ai_router(
    storage: Storage,
    registry: ToolRegistry,
    manager: PtySessionManager,
    *,
    synapse_dev_manager: SynapseDevManager | None = None,
    started_at: datetime | None = None,
) -> APIRouter:
    router = APIRouter(prefix="/ai", tags=["ai"])

    @router.get("/health-report", response_model=None)
    async def health_report() -> dict[str, Any]:
        projects = projects_module.list_projects(storage.conn)
        cursor = storage.conn.execute(
            "SELECT id, timestamp_utc, entity_type, entity_id, action, source, result, error_code, details_json "
            "FROM audit_log WHERE result = 'error' OR error_code IS NOT NULL "
            "ORDER BY id DESC LIMIT 5"
        )
        audit_tail = []
        for row in cursor.fetchall():
            details = json.loads(row["details_json"]) if row["details_json"] else None
            audit_tail.append(
                {
                    "id": row["id"],
                    "at": row["timestamp_utc"],
                    "entity_type": row["entity_type"],
                    "entity_id": row["entity_id"],
                    "action": row["action"],
                    "source": row["source"],
                    "result": row["result"],
                    "error_code": row["error_code"],
                    "details": details,
                }
            )
        now = utc_now()
        uptime_s = 0.0
        if started_at is not None:
            uptime_s = max(0.0, (now - started_at).total_seconds())
        latest_successful_review_pass = None
        review_row = storage.conn.execute(
            "SELECT r.id, r.thread_id, r.title, r.summary_md, r.updated_at, "
            "t.title AS thread_title, t.project_id AS project_id "
            "FROM coder_review_passes r "
            "LEFT JOIN coder_threads t ON t.id = r.thread_id "
            "WHERE r.status = ? "
            "ORDER BY r.updated_at DESC LIMIT 1",
            (coder_workspace_module.CoderReviewPassStatus.COMPLETED.value,),
        ).fetchone()
        if review_row is not None:
            latest_successful_review_pass = {
                "id": review_row["id"],
                "thread_id": review_row["thread_id"],
                "thread_title": review_row["thread_title"] or "Untitled thread",
                "project_id": review_row["project_id"],
                "title": review_row["title"] or "Review pass",
                "summary_md": review_row["summary_md"] or "",
                "updated_at": review_row["updated_at"],
            }
        return {
            "version": __version__,
            "uptime_s": round(uptime_s, 3),
            "daemon": {
                "schema_migration": storage.schema_migration(),
                "contracts_honoured": list(range(1, 29)),
            },
            "projects": {
                "total": len(projects),
                "launched": sum(1 for project in projects if project.status.value == "launched"),
                "errored": sum(
                    1
                    for project in projects
                    if project.status.value == "error" or project.last_error is not None
                ),
            },
            "audit_tail": audit_tail,
            "tests": synapse_dev_manager.tests_summary() if synapse_dev_manager is not None else {
                "last_run_ok": None,
                "last_run_at": None,
                "passed": 0,
                "failed": 0,
                "skipped": 0,
                "mode": None,
            },
            "git": synapse_dev_manager.git_summary() if synapse_dev_manager is not None else {},
            "quality": quality_os_module.quality_summary(storage.conn),
            "review": {
                "latest_successful_pass": latest_successful_review_pass,
            },
        }

    @router.get("/context", response_model=None)
    async def context() -> dict[str, Any]:
        projects = []
        for p in projects_module.list_projects(storage.conn):
            files = list_for_project(storage.conn, p.id)[:_INLINE_FILE_CAP]
            projects.append(
                {
                    "id": p.id,
                    "name": p.name,
                    "path": p.path,
                    "kind": p.kind.value,
                    "status": p.status.value,
                    "launch_cmd": p.launch_cmd,
                    "expected_port": p.expected_port,
                    "group": p.group,
                    "tags": p.tags,
                    "pinned": p.pinned,
                    "description": p.description,
                    "current_health": p.current_health.value,
                    "ai_context": ai_context_metadata(storage.data_dir, p.id),
                    # Phase A + D inline: files (uploads, transcripts,
                    # ChatGPT imports) and the count if it ran past the cap.
                    "files": [_file_to_inline(f) for f in files],
                    "files_count": len(files),
                }
            )
        shared_files = list_for_project(storage.conn, None)[:_INLINE_FILE_CAP]

        tools = [
            {
                "id": m.id,
                "name": m.name,
                "version": m.version,
                "runnable": m.runnable,
                "description": m.description,
                "actions": [
                    {"id": a.id, "label": a.label, "scope": a.scope.value}
                    for a in m.actions
                ],
            }
            for m in registry.list_manifests()
        ]

        sessions = [
            {
                "session_id": s.session_id,
                "argv": s.argv,
                "cwd": s.cwd,
                "started_at": s.summary().started_at,
                "exit_code": s.exit_code,
            }
            for s in manager.list()
        ]
        agent_squads = []
        for squad in agent_squads_module.list_squads(storage.conn):
            items = agent_squads_module.list_work_items(storage.conn, squad.id)
            agent_squads.append(
                {
                    **squad.model_dump(mode="json"),
                    "work_items": [
                        {
                            "id": item.id,
                            "title": item.title,
                            "status": item.status.value,
                            "assigned_role_id": item.assigned_role_id,
                            "preferred_runtime": item.preferred_runtime,
                            "pty_session_id": item.pty_session_id,
                            "updated_at": item.updated_at,
                        }
                        for item in items
                    ],
                }
            )

        ai_cases = []
        for case in ai_cases_module.list_cases(storage.conn):
            ai_cases.append(
                {
                    "id": case.id,
                    "primary_project_id": case.primary_project_id,
                    "case_mode": case.case_mode.value,
                    "status": case.status.value,
                    "phase": case.phase.value,
                    "squad_id": case.squad_id,
                    "branch_name": case.branch_name,
                    "worktree_path": case.worktree_path,
                    "blocking_gate_count": len(
                        quality_os_module.blocking_gates_for_subject(
                            storage.conn, "ai_case", case.id
                        )
                    ),
                    "updated_at": case.updated_at,
                }
            )
        def _thread_row(summary: Any) -> dict[str, Any]:
            return {
                "id": summary.thread.id,
                "project_id": summary.thread.project_id,
                "title": summary.thread.title,
                "status": summary.thread.status.value,
                "active_runtime_id": summary.thread.active_runtime_id,
                "active_provider": summary.thread.active_provider,
                "active_model": summary.thread.active_model,
                "workspace_context_mode": summary.thread.workspace_context_mode,
                "message_count": summary.message_count,
                "run_count": summary.run_count,
                "review_pass_count": summary.review_pass_count,
                "blocking_gate_count": len(
                    quality_os_module.blocking_gates_for_subject(
                        storage.conn, "coder_thread", summary.thread.id
                    )
                ),
                "last_message_preview": summary.last_message_preview,
                "updated_at": summary.thread.updated_at,
            }

        coder_threads = []
        for project in projects_module.list_projects(storage.conn):
            for summary in coder_workspace_module.list_threads(storage.conn, project.id):
                coder_threads.append(_thread_row(summary))
        # Project-free General threads (Plan 2 Phase A) are visible in the AI overview too.
        for summary in coder_workspace_module.list_general_threads(storage.conn):
            coder_threads.append(_thread_row(summary))
        benchmark_runs = []
        for run in benchmarks_module.list_runs(storage.conn):
            attempts = benchmarks_module.list_attempts_for_run(storage.conn, run.id)
            attempt_gate_count = sum(
                len(
                    quality_os_module.blocking_gates_for_subject(
                        storage.conn, "benchmark_attempt", attempt.id
                    )
                )
                for attempt in attempts
            )
            benchmark_runs.append(
                {
                    "id": run.id,
                    "spec_id": run.spec_id,
                    "project_id": run.project_id,
                    "title": run.title,
                    "status": run.status.value,
                    "execution_mode": run.execution_mode.value,
                    "repeat_count": run.repeat_count,
                    "attempt_count": len(attempts),
                    "blocking_gate_count": attempt_gate_count,
                    "updated_at": run.updated_at,
                }
            )
        factory_counts = ai_factory_module.counts(storage.conn)
        installed_bundle_ids = set(ai_bundles_module.list_installed_bundle_ids(storage.conn))

        # Tail of audit so the AI can spot "what just happened" without
        # pulling the whole table.
        cursor = storage.conn.execute(
            "SELECT id, timestamp_utc, entity_type, entity_id, action, source, "
            "result, error_code, details_json "
            "FROM audit_log ORDER BY id DESC LIMIT 25"
        )
        audit_tail = []
        for row in cursor.fetchall():
            details = (
                json.loads(row["details_json"]) if row["details_json"] else None
            )
            audit_tail.append(
                {
                    "id": row["id"],
                    "at": row["timestamp_utc"],
                    "entity_type": row["entity_type"],
                    "entity_id": row["entity_id"],
                    "action": row["action"],
                    "source": row["source"],
                    "result": row["result"],
                    "error_code": row["error_code"],
                    "details": details,
                }
            )

        # AI activity (ADR-0028): who else is connected right now (with their #NNN
        # session number + green/yellow/red connection grade) and the recent operator
        # feed -- so an AI orienting itself knows its peers and what just happened.
        from . import activity as _activity
        from . import coordination as _coordination

        ai_sessions = _coordination.list_all_sessions(storage.conn)
        activity_block = {
            "sessions": [
                {
                    "id": s.id,
                    "seq": s.seq,
                    "runtime_id": s.runtime_id,
                    "agent_label": s.agent_label,
                    "task": s.task,
                    "last_intent": s.last_intent,
                    "status": s.status.value,
                    "stale": s.stale,
                    "connection_level": s.connection_level,
                    "connection_code": s.connection_code,
                    "project_id": s.project_id,
                }
                for s in ai_sessions[:15]
            ],
            "recent": [
                {
                    "title": n.title,
                    "kind": n.kind,
                    "level": n.level,
                    "seq": n.seq,
                    "created_at": n.created_at.isoformat(),
                }
                for n in _activity.list_notifications(storage.conn, limit=10)
            ],
            "recent_journal": [
                {
                    "session_id": event.session_id,
                    "category": event.category.value,
                    "status": event.status.value,
                    "title": event.title,
                    "squad_id": event.squad_id,
                    "mcp_server_id": event.mcp_server_id,
                    "authority": event.authority.value,
                    "created_at": event.created_at.isoformat(),
                }
                for event in _activity.list_journal_events(storage.conn, limit=10)
            ],
            "hint": (
                "Register yourself with POST /api/v1/coordination/sessions, and PASS A project_id -- "
                "pick the project you are working in from the `projects` list above (register a new one "
                "through POST /api/v1/projects first if it is missing). Registering without a project_id "
                "grades the connection yellow (`degraded.no_project`) and costs you project memory, the "
                "files surface, and per-project scoping. Keep the returned resume_key: if you drop and "
                "come back, RESUME with it instead of registering again, so you keep one session number "
                "rather than adding a new row to the operator's Live tab every time. "
                "Registering gets you your own "
                "session number, connection grade, and one-time session_key (squad workers are already "
                "registered in SYNAPSE_SESSION_ID); update last_intent on heartbeats; report deliberate "
                "operator summaries to POST /api/v1/activity/sessions/{id}/events; keep the shared "
                "milestone list current through /activity/sessions/{id}/goals. Include "
                "X-Synapse-Session plus X-Synapse-Session-Key on later API calls so activity revives "
                "the session after a restart and rolls squad/reviewer receipts into the parent. If a "
                "legacy worker registered before reading its injected identity, correct it through "
                "PATCH /coordination/sessions/{id}. "
                "Never report secrets or hidden "
                "chain-of-thought."
            ),
        }

        # Which MCP servers this install has, so a connecting AI can DISCOVER its
        # equipment instead of guessing. Without this block an external AI had no
        # way to learn that Reflex (real mouse/keyboard/screen control), the web
        # scraper, or Playwright were installed -- it would have had to be told.
        # Synapse-launched workers get these injected via --mcp-config; every other
        # AI reads them here.
        mcp_block: dict[str, Any] = {"servers": [], "how_to_use": "", "note": ""}
        try:
            installed = mcp_servers_module.list_servers(storage.conn)
            mcp_block["servers"] = [
                {
                    "id": server.id,
                    "name": server.name,
                    "enabled": server.enabled,
                    "transport": server.transport.value,
                    "description": server.description,
                }
                for server in installed
                if server.enabled
            ]
        except Exception:  # noqa: BLE001 -- discovery must never break /ai/context
            mcp_block["note"] = "MCP server list unavailable on this install."
        mcp_block["how_to_use"] = (
            "These are installed on this machine and are yours to use -- they are equipment, "
            "not extras that need permission. If you were launched by Synapse they are already "
            "wired into your runtime. If you are an AI the user started themselves (a Claude Code "
            "or Codex chat), the same servers are configured in the user's own MCP config, so call "
            "them as mcp__<server-id>__<tool>. Reflex drives this machine's real mouse, keyboard "
            "and screen; playwright drives a real browser; web-scraper does structured page, DOM "
            "and network extraction. Use them to VERIFY your work end to end -- look at the running "
            "app the way the user would rather than assuming it works."
        )

        # Local models are free to run. Any AI reading this context should know what is
        # installed on this machine and what each model is *measured* to be good at, so it
        # can offload work that doesn't need a frontier model instead of burning tokens.
        local_ai_block: dict[str, Any] = {}
        try:
            local_ai_block = local_models_module.summarize_for_ai()
        except Exception:  # noqa: BLE001 -- discovery must never break /ai/context
            local_ai_block = {"note": "Local model discovery unavailable on this install."}

        return {
            "schema": "synapse.ai.context/v1",
            "projects": projects,
            "tools": tools,
            "mcp_servers": mcp_block,
            "local_ai": local_ai_block,
            "sessions": sessions,
            "ai_activity": activity_block,
            "agent_squads": agent_squads,
            "ai_cases": ai_cases,
            "coder_threads": coder_threads,
            "benchmark_runs": benchmark_runs,
            "agent_role_templates": [
                role.model_dump(mode="json")
                for role in agent_squads_module.list_role_templates(storage.conn)
            ],
            "ai_factory": {
                "counts": {
                    **factory_counts,
                    "installed_bundles": len(installed_bundle_ids),
                },
                "mission_profiles": [
                    profile.model_dump(mode="json")
                    for profile in ai_cases_module.mission_profiles()
                ],
                "installed_bundles": [
                    bundle.model_dump(mode="json")
                    for bundle in ai_bundles_module.list_installed_bundles(storage.conn)
                ],
            },
            "shared_files": [_file_to_inline(f) for f in shared_files],
            "audit_tail": audit_tail,
            "quality": {
                **quality_os_module.quality_summary(storage.conn),
                "ui_surfaces": [
                    surface.model_dump(mode="json")
                    for surface in quality_os_module.list_surfaces(storage.conn)
                ],
            },
            "endpoints_for_ai": [
                {
                    "purpose": "list registered projects",
                    "method": "GET",
                    "path": "/api/v1/projects",
                },
                {
                    "purpose": "read the current daemon, git, and last-test health report for Synapse itself",
                    "method": "GET",
                    "path": "/api/v1/ai/health-report",
                },
                {
                    "purpose": "launch / stop a project",
                    "method": "POST",
                    "path": "/api/v1/projects/{id}/launch | /stop",
                },
                {
                    "purpose": "open a coder pre-cd'd into a project",
                    "method": "POST",
                    "path": "/api/v1/projects/{id}/workbench",
                },
                {
                    "purpose": "list project-scoped coder threads and create a new one; also the project-free General scope (list/create at /coder-threads/general)",
                    "method": "GET | POST",
                    "path": "/api/v1/projects/{id}/coder-threads | /api/v1/coder-threads/general",
                },
                {
                    "purpose": "read, update, delete, and inspect thread context",
                    "method": "GET | PATCH | DELETE | POST",
                    "path": "/api/v1/coder-threads/{id} | /messages | /runtime | /review-passes | /review-passes/{reviewId}/launch | /context | /dispatch",
                },
                {
                    "purpose": "read or update coder workspace preferences",
                    "method": "GET | PATCH",
                    "path": "/api/v1/coder-workspace/preferences",
                },
                {
                    "purpose": "list installed tools (declarative + handler tiers)",
                    "method": "GET",
                    "path": "/api/v1/tools",
                },
                {
                    "purpose": "run gated Synapse self-improvement test loops",
                    "method": "POST",
                    "path": "/api/v1/synapse-dev/test/full | /api/v1/synapse-dev/test/file",
                },
                {
                    "purpose": "inspect or resolve durable quality gates, browser proof, and UI contracts",
                    "method": "GET | POST",
                    "path": "/api/v1/quality-gates | /api/v1/ui-contracts | /api/v1/ui-contracts/{id}/run | /api/v1/ui-impact-audit | /api/v1/ui-surface-map",
                },
                {
                    "purpose": "run an action on a tool",
                    "method": "POST",
                    "path": "/api/v1/tools/{id}/actions/{action}",
                },
                {
                    "purpose": "list / spawn PTY sessions",
                    "method": "GET | POST",
                    "path": "/api/v1/pty",
                },
                {
                    "purpose": "install a tool from the marketplace by id",
                    "method": "POST",
                    "path": "/api/v1/marketplace/install/{id}",
                },
                {
                    "purpose": "list or create AI squads for a project",
                    "method": "GET | POST",
                    "path": "/api/v1/agent-squads",
                },
                {
                    "purpose": "harvest authorized references, proxy design-oriented web-scraper actions, and save artifacts into a project",
                    "method": "GET | POST",
                    "path": "/api/v1/installed-pages/web-scraper | /harvest-capabilities | /actions/{action} | /save-artifacts",
                },
                {
                    "purpose": "list, create, launch, hand off, or update agent work items",
                    "method": "GET | POST",
                    "path": "/api/v1/agent-squads/{id}/work-items | /api/v1/agent-work-items/{id}/launch | /handoff | /status",
                },
                {
                    "purpose": "launch a Claude, Codex, or GitHub Copilot worker with the role-scoped enabled MCP set translated automatically for that runtime",
                    "method": "POST",
                    "path": "/api/v1/agent-work-items/{id}/launch (uses /api/v1/mcp-servers + agent_role_templates.mcp_server_ids)",
                },
                {
                    "purpose": "create, run, inspect, stop, and export AI Operating System cases",
                    "method": "GET | POST",
                    "path": "/api/v1/ai-cases | /api/v1/ai-cases/meta | /api/v1/ai-cases/{id} | /graph | /spawn | /run | /stop | /bundle | /export/{kind}",
                },
                {
                    "purpose": "browse and manage the AI Factory catalog",
                    "method": "GET | POST | PATCH | DELETE",
                    "path": "/api/v1/ai-factory/catalog | /api/v1/ai-components | /api/v1/ai-recipes | /api/v1/ai-sources",
                },
                {
                    "purpose": "list benchmark specs, create runs, launch benchmark attempts, ingest direct runs, export reports, list bug-hunt fixtures, and grade bug-hunt findings against a fixture answer key (returns bugs_per_1k_tokens)",
                    "method": "GET | POST",
                    "path": "/api/v1/benchmarks/specs | /api/v1/benchmarks/runs | /api/v1/benchmarks/runs/{id} | /launch | /rescore | /export | /api/v1/benchmarks/ingest-direct | /api/v1/benchmarks/bug-hunt-fixtures | /api/v1/benchmarks/score-bug-hunt",
                },
                {
                    "purpose": "install or inspect AI-first bundles, portable skill packs, their instructions/resources, roles, personalities, quick actions, and factory assets",
                    "method": "GET | POST | DELETE",
                    "path": "/api/v1/ai-bundles | /api/v1/ai-bundles/install/{id} | /api/v1/ai-bundles/skills | /skills/{skill_id} | /skills/{skill_id}/resources/{resource_path}",
                },
                {
                    "purpose": "read a project's ADRs, backlog, and version history",
                    "method": "GET",
                    "path": "/api/v1/projects/{id}/records",
                },
                {
                    "purpose": "capture a quick idea/ADR on a project, then promote it to a numbered ADR",
                    "method": "POST",
                    "path": "/api/v1/projects/{id}/adrs | /api/v1/project-adrs/{adr_id}/promote",
                },
                {
                    "purpose": "add backlog items or version-history entries to a project",
                    "method": "POST",
                    "path": "/api/v1/projects/{id}/backlog | /api/v1/projects/{id}/versions",
                },
                {
                    "purpose": "the full audit log (paginated)",
                    "method": "GET",
                    "path": "/api/v1/audit",
                },
                {
                    "purpose": "coordinate with other AI sessions on this repo (ADR-0024): register presence, claim advisory file lanes, check path overlaps, detect git collisions, and get the true next-free migration/ADR number from disk",
                    "method": "GET | POST | PATCH | DELETE",
                    "path": "/api/v1/coordination/sessions | /coordination/sessions/{id} | /coordination/lanes | /coordination/overlap | /coordination/snapshot | /coordination/detect-collisions | /coordination/next-numbers",
                },
                {
                    "purpose": "keep the operator-facing Live View current with structured plans, deliberate reasoning summaries, decisions, actions, evidence, blockers, squad/reviewer state, MCP/tool receipts, and an editable milestone list; never send secrets or private hidden chain-of-thought",
                    "method": "GET | POST | PATCH | DELETE",
                    "path": "/api/v1/activity/sessions | /api/v1/activity/sessions/{id} | /api/v1/activity/sessions/{id}/events | /api/v1/activity/sessions/{id}/goals | /goals/{goal_id}",
                },
                {
                    "purpose": "self-report token usage per work item and read the squad-level token roll-up so Synapse can prove efficiency (ADR-0025)",
                    "method": "GET | POST",
                    "path": "/api/v1/agent-work-items/{id}/tokens | /api/v1/agent-squads/{id}/token-usage | /api/v1/agent-squads/{id}/capacity (can_launch headroom vs cap+budget)",
                },
                {
                    "purpose": "stop all of a squad's workers (kill switch); set a squad's concurrency cap + token budget via PATCH; delegate a child work item to a specialist (auto_launch:true launches it immediately, bounded by the cap + budget); record a review-pass verdict (opens a quality gate if blocking)",
                    "method": "POST | PATCH",
                    "path": "/api/v1/agent-squads/{id}/stop | /api/v1/agent-squads/{id} | /api/v1/agent-work-items/{id}/delegate | /api/v1/coder-review-passes/{id}/verdict",
                },
                {
                    "purpose": "append a quick note to a project's shared AI memory (.synapse-ai-context.md) or backlog without a full handoff",
                    "method": "POST",
                    "path": "/api/v1/capture",
                },
                {
                    "purpose": "read the human review inbox (work-item handoffs + AI-filed improvement proposals awaiting approval) -- check before starting new work; approve/revise/reject items; and FILE an improvement idea for the user to approve instead of acting unilaterally (agents brainstorm, you approve), then approve/reject proposals",
                    "method": "GET | POST",
                    "path": "/api/v1/review/inbox | /api/v1/review/items/{id}/approve | /revise | /reject | /api/v1/review/proposals | /api/v1/review/proposals/{id}/approve | /reject | /promote (approve + create a project backlog item) | /api/v1/review/proposals/reconcile (flag open ideas addressed by recent commits)",
                },
                {
                    "purpose": "upload, list, download, and delete project or shared files, and list a project's AI session transcripts",
                    "method": "GET | POST | DELETE",
                    "path": "/api/v1/projects/{id}/files | /api/v1/files | /api/v1/projects/{id}/transcripts",
                },
                {
                    "purpose": "list and launch curated AI quick-action workflow templates (e.g. autonomous-boss, bug-hunt-squad, ai-council-review)",
                    "method": "GET | POST",
                    "path": "/api/v1/quick-actions | /api/v1/quick-actions/{id}/launch",
                },
                {
                    "purpose": "list / create / update AI personalities layered onto roles so two same-role workers differ",
                    "method": "GET | POST | PATCH | DELETE",
                    "path": "/api/v1/personalities",
                },
                {
                    "purpose": "install + manage MCP servers, manage local Ollama models, and use the local-LLM assistant for cheap on-box chat",
                    "method": "GET | POST | PATCH",
                    "path": "/api/v1/mcp-servers | /api/v1/models | /api/v1/assistant",
                },
                {
                    "purpose": "inspect, sync, update, or roll back the optional version-pinned Warden MCP search/router; direct MCP access remains enabled alongside Warden",
                    "method": "GET | POST",
                    "path": "/api/v1/mcp-servers/warden/status | /sync | /update | /rollback",
                },
                {
                    "purpose": "request a visible whole-Synapse restart, follow its measured stages, or read stable restart error meanings",
                    "method": "GET | POST",
                    "path": "/api/v1/system/restart | /api/v1/system/restart/{operation_id}/stage | /api/v1/system/restart/errors",
                },
                {
                    "purpose": "global search across projects, tools, actions, and settings",
                    "method": "GET",
                    "path": "/api/v1/search?q={query}",
                },
                {
                    "purpose": "THE COMPLETE AI CAPABILITY REFERENCE -- every REST endpoint, WS event, injected env var, memory file, and the gaps AIs commonly miss. Read this repo file for the full inventory beyond this curated list.",
                    "method": "DOC",
                    "path": "docs/api-finds.md",
                },
            ],
        }

    return router
