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
from typing import Any

from fastapi import APIRouter

from . import projects as projects_module
from . import agent_squads as agent_squads_module
from . import ai_bundles as ai_bundles_module
from . import ai_cases as ai_cases_module
from . import ai_factory as ai_factory_module
from . import benchmarks as benchmarks_module
from . import coder_workspace as coder_workspace_module
from .ai_context_memory import ai_context_metadata
from .files_storage import list_for_project
from .storage import Storage
from .pty_sessions import PtySessionManager
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
) -> APIRouter:
    router = APIRouter(prefix="/ai", tags=["ai"])

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
                    "updated_at": case.updated_at,
                }
            )
        coder_threads = []
        for project in projects_module.list_projects(storage.conn):
            for summary in coder_workspace_module.list_threads(storage.conn, project.id):
                coder_threads.append(
                    {
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
                        "last_message_preview": summary.last_message_preview,
                        "updated_at": summary.thread.updated_at,
                    }
                )
        benchmark_runs = []
        for run in benchmarks_module.list_runs(storage.conn):
            attempts = benchmarks_module.list_attempts_for_run(storage.conn, run.id)
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

        return {
            "schema": "synapse.ai.context/v1",
            "projects": projects,
            "tools": tools,
            "sessions": sessions,
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
            "endpoints_for_ai": [
                {
                    "purpose": "list registered projects",
                    "method": "GET",
                    "path": "/api/v1/projects",
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
                    "purpose": "list project-scoped coder threads and create a new one",
                    "method": "GET | POST",
                    "path": "/api/v1/projects/{id}/coder-threads",
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
                    "purpose": "create, launch, hand off, or update agent work items",
                    "method": "POST",
                    "path": "/api/v1/agent-squads/{id}/work-items | /api/v1/agent-work-items/{id}/launch | /handoff | /status",
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
                    "purpose": "list benchmark specs, create runs, launch benchmark attempts, ingest direct runs, and export reports",
                    "method": "GET | POST",
                    "path": "/api/v1/benchmarks/specs | /api/v1/benchmarks/runs | /api/v1/benchmarks/runs/{id} | /launch | /rescore | /export | /api/v1/benchmarks/ingest-direct",
                },
                {
                    "purpose": "install or inspect AI-first bundles for roles, personalities, quick actions, and factory assets",
                    "method": "GET | POST | DELETE",
                    "path": "/api/v1/ai-bundles | /api/v1/ai-bundles/install/{id}",
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
            ],
        }

    return router
