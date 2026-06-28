"""REST routes for AI Operating System advanced cases."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from . import agent_squads as squads
from . import ai_bundles
from . import ai_cases
from . import ai_factory
from . import project_records as records
from . import projects as projects_module
from .ai_context_memory import append_capture_note, ensure_ai_context_file, write_role_prompt
from .api_versions import event_name
from .audit import AuditRecord, audit
from .auth import AuthManager
from .errors import invalid
from .git_worktrees import ensure_worktree
from .health import HealthProbe
from .models import AuditSource
from .process_manager import ProcessManager
from .projects import Project, ProjectKind, ProjectUpdate
from .pty_sessions import PtySessionManager
from .runtime_paths import bundled_ai_os_dir, bundled_quick_actions_dir
from .secrets import EnvVar
from .storage import Storage
from .time_utils import utc_now
from .ws import Event, EventBus

_AI_OS_PROJECT_ID = "ai-operating-system"
_AI_OS_PROJECT_NAME = "AI Operating System"
_AI_OS_PORT = 4312


class OpenAiOsRequest(BaseModel):
    neighbor_project_ids: list[str] = Field(default_factory=list)
    case_id: str | None = None


def build_ai_cases_router(
    storage: Storage,
    manager: PtySessionManager,
    process_manager: ProcessManager,
    bus: EventBus,
    auth: AuthManager,
) -> APIRouter:
    router = APIRouter(tags=["ai-cases"])

    @router.get("/ai-cases/meta", response_model=None)
    async def ai_case_meta() -> dict[str, Any]:
        installed_bundle_ids = set(ai_bundles.list_installed_bundle_ids(storage.conn))
        return {
            "case_modes": [mode.value for mode in ai_cases.AiCaseMode],
            "generation_modes": [mode.value for mode in ai_cases.AiGenerationMode],
            "mission_profiles": [profile.model_dump(mode="json") for profile in ai_cases.mission_profiles()],
            "write_policies": [policy.value for policy in ai_cases.AiWritePolicy],
            "recipes": [recipe.model_dump(mode="json") for recipe in ai_factory.list_recipes(storage.conn)],
            "component_families": [family.value for family in ai_factory.AiComponentFamily],
            "available_bundles": [
                {
                    "id": bundle.id,
                    "name": bundle.name,
                    "installed": bundle.id in installed_bundle_ids,
                }
                for bundle in ai_bundles.load_catalog()
            ],
        }

    @router.get("/ai-cases", response_model=None)
    async def list_ai_cases() -> dict[str, Any]:
        cases = [_case_detail(storage, manager, case) for case in ai_cases.list_cases(storage.conn)]
        return {"cases": [detail.model_dump(mode="json") for detail in cases]}

    @router.post("/ai-cases", response_model=None, status_code=201)
    async def create_ai_case(payload: ai_cases.AiCaseCreate) -> dict[str, Any]:
        primary = projects_module.get(storage.conn, payload.targets.primary_project_id)
        _validate_case_targets(storage, payload.targets)
        case_id = ai_cases._new_id()
        bundle_path = ai_cases.bundle_file_path(storage.data_dir, case_id)
        with storage.transaction() as conn:
            case = ai_cases.create_case(conn, payload, case_id=case_id, bundle_path=bundle_path)
            audit(
                conn,
                AuditRecord(
                    entity_type="ai_case",
                    entity_id=case.id,
                    action="create",
                    source=AuditSource.DESKTOP,
                    result="success",
                    details={
                        "primary_project_id": case.primary_project_id,
                        "case_mode": case.case_mode.value,
                        "mission_profile_id": case.mission_profile_id,
                    },
                ),
            )
        bundle = ai_cases.ensure_bundle(storage.data_dir, case, primary, _neighbor_projects(storage, case))
        _write_case_metadata_files(storage, case, bundle)
        await bus.publish("v1.ai_case.created", {"case_id": case.id})
        return _case_detail(storage, manager, case).model_dump(mode="json")

    @router.get("/ai-cases/{case_id}", response_model=None)
    async def get_ai_case(case_id: str) -> dict[str, Any]:
        case = ai_cases.get_case(storage.conn, case_id)
        return _case_detail(storage, manager, case).model_dump(mode="json")

    @router.get("/ai-cases/{case_id}/bundle", response_model=None)
    async def get_ai_case_bundle(case_id: str) -> dict[str, Any]:
        ai_cases.get_case(storage.conn, case_id)
        return ai_cases.load_bundle(storage.data_dir, case_id).model_dump(mode="json")

    @router.get("/ai-cases/{case_id}/graph", response_model=None)
    async def get_ai_case_graph(case_id: str) -> dict[str, Any]:
        ai_cases.get_case(storage.conn, case_id)
        return ai_cases.case_graph(storage.conn, case_id).model_dump(mode="json")

    @router.post("/ai-cases/{case_id}/spawn", response_model=None, status_code=201)
    async def spawn_ai_case(case_id: str, payload: ai_cases.AiCaseSpawnRequest) -> dict[str, Any]:
        parent = ai_cases.get_case(storage.conn, case_id)
        targets = payload.targets or parent.targets
        _validate_case_targets(storage, targets)
        child_id = ai_cases._new_id()
        bundle_path = ai_cases.bundle_file_path(storage.data_dir, child_id)
        with storage.transaction() as conn:
            child = ai_cases.spawn_child_case(
                conn,
                parent,
                payload,
                case_id=child_id,
                bundle_path=bundle_path,
            )
            audit(
                conn,
                AuditRecord(
                    entity_type="ai_case",
                    entity_id=child.id,
                    action="spawn",
                    source=AuditSource.DESKTOP,
                    result="success",
                    details={"parent_case_id": parent.id, "comparison_set_id": child.comparison_set_id},
                ),
            )
        primary = projects_module.get(storage.conn, child.primary_project_id)
        bundle = ai_cases.ensure_bundle(storage.data_dir, child, primary, _neighbor_projects(storage, child))
        _write_case_metadata_files(storage, child, bundle)
        await bus.publish("v1.ai_case.created", {"case_id": child.id, "parent_case_id": parent.id})
        return _case_detail(storage, manager, child).model_dump(mode="json")

    @router.post("/ai-cases/{case_id}/run", response_model=None)
    async def run_ai_case(
        case_id: str,
        payload: ai_cases.AiCaseRunRequest | None = None,
    ) -> dict[str, Any]:
        body = payload or ai_cases.AiCaseRunRequest()
        case = ai_cases.get_case(storage.conn, case_id)
        live_lead = manager.get(case.lead_session_id) if case.lead_session_id else None
        if live_lead is not None and live_lead.exit_code is None:
            raise invalid("ai_case", "This case already has a running lead session.")
        primary = projects_module.get(storage.conn, case.primary_project_id)
        neighbors = _neighbor_projects(storage, case)
        bundle = ai_cases.ensure_bundle(storage.data_dir, case, primary, neighbors)

        branch_name = case.branch_name or f"synapse/ai-case-{case.id}"
        worktree_path = (
            Path(case.worktree_path)
            if case.worktree_path
            else ai_cases.case_dir(storage.data_dir, case.id) / "worktree"
        )
        _repo_root, ensured_worktree = ensure_worktree(
            primary_project_path=primary.path,
            worktree_path=worktree_path,
            branch_name=branch_name,
        )
        case_phase = _phase_for_run(case.case_mode)
        prepared_children: list[ai_cases.AiCase] = []

        with storage.transaction() as conn:
            case, bundle, prepared_children = _prepare_mode_specific_case_plan(
                storage,
                conn,
                case,
                primary,
                neighbors,
                bundle,
            )
            role = squads.get_role_template(conn, "boss")
            squad = _ensure_case_squad(storage, conn, case, primary, neighbors, str(ensured_worktree), branch_name)
            work_items = squads.list_work_items(conn, squad.id)
            lead_item = next((item for item in work_items if item.title == "Judge / Boss"), None)
            if lead_item is None:
                raise invalid("ai_case", "The case lead work item could not be prepared.")

            lead_prompt = ai_cases.build_lead_prompt(
                case,
                primary,
                neighbors,
                worktree_path=str(ensured_worktree),
                branch_name=branch_name,
                bundle_path=ai_cases.bundle_file_path(storage.data_dir, case.id),
            )
            prompt_path = ai_cases.lead_prompt_path(storage.data_dir, case.id)
            prompt_path.parent.mkdir(parents=True, exist_ok=True)
            prompt_path.write_text(lead_prompt, encoding="utf-8")
            _write_case_metadata_files(storage, case, bundle)
            _write_draft_pr_stub(storage, case, primary, ensured_worktree, branch_name)

            chosen_runtime = squads.pick_runtime(role, body.preferred_runtime)
            argv = squads.argv_for_runtime(chosen_runtime)
            role_prompt_path = write_role_prompt(
                data_dir=storage.data_dir,
                project_id=primary.id,
                project_name=primary.name,
                squad_name=squad.name,
                squad_goal_md=squad.goal_md,
                work_item_title=lead_item.title,
                instructions_md=lead_item.instructions_md,
                role_name=role.name,
                role_description=role.description,
                prompt_preamble_md=role.prompt_preamble_md,
                context_mode=role.context_mode.value,
                handoff_summary_md=lead_item.summary_md,
                handoff_blockers_md=lead_item.blockers_md,
                files_touched=lead_item.files_touched,
            )
            env = {
                "SYNAPSE_AI_CASE_ID": case.id,
                "SYNAPSE_AI_CASE_DIR": str(ai_cases.case_dir(storage.data_dir, case.id)),
                "SYNAPSE_AI_CASE_BUNDLE": str(ai_cases.bundle_file_path(storage.data_dir, case.id)),
                "SYNAPSE_AI_CASE_PROMPT_FILE": str(prompt_path),
                "SYNAPSE_AI_CASE_BRANCH": branch_name,
                "SYNAPSE_AI_CASE_WORKTREE": str(ensured_worktree),
                "SYNAPSE_AI_CASE_PRIMARY_PROJECT_ID": primary.id,
                "SYNAPSE_AI_CASE_MODE": case.case_mode.value,
                "SYNAPSE_AI_CASE_MISSION_PROFILE": case.mission_profile_id or "",
                "SYNAPSE_AI_CASE_DRAFT_PR": str(ai_cases.draft_pr_path(storage.data_dir, case.id)),
                "SYNAPSE_ROLE_PROMPT_FILE": str(role_prompt_path),
            }
            session = await manager.spawn(
                argv=argv,
                cwd=str(ensured_worktree),
                env=env,
                rows=24,
                cols=80,
                project_id=primary.id,
            )
            lead_item = squads.set_work_item_session(
                conn,
                lead_item.id,
                status=squads.AgentWorkItemStatus.RUNNING,
                pty_session_id=session.session_id,
                chosen_runtime=chosen_runtime,
                opened_in_tab=body.open_in_tab,
            )
            job = ai_cases.create_job(
                conn,
                case_id=case.id,
                phase=case_phase,
                label="Judge / Boss",
                status=ai_cases.AiJobStatus.RUNNING,
                worker_role_id="boss",
                runtime=chosen_runtime,
                session_id=session.session_id,
                cwd=str(ensured_worktree),
                artifact_path=str(ai_cases.bundle_file_path(storage.data_dir, case.id)),
                notes_md=f"Mission profile: {case.mission_profile_id or ''}",
            )
            case = ai_cases.update_case(
                conn,
                case.id,
                status=ai_cases.AiCaseStatus.RUNNING,
                phase=case_phase,
                squad_id=squad.id,
                lead_work_item_id=lead_item.id,
                lead_session_id=session.session_id,
                branch_name=branch_name,
                worktree_path=str(ensured_worktree),
                started_at=utc_now(),
                stopped_at=None,
                last_error_code=None,
                last_error_message=None,
            )
            audit(
                conn,
                AuditRecord(
                    entity_type="ai_case",
                    entity_id=case.id,
                    action="run",
                    source=AuditSource.DESKTOP,
                    result="success",
                    details={
                        "squad_id": squad.id,
                        "lead_work_item_id": lead_item.id,
                        "lead_session_id": session.session_id,
                        "case_job_id": job.id,
                        "worktree_path": str(ensured_worktree),
                        "branch_name": branch_name,
                    },
                ),
            )
        await bus.publish("v1.ai_case.updated", {"case_id": case.id, "status": case.status.value})
        for child in prepared_children:
            child_primary = projects_module.get(storage.conn, child.primary_project_id)
            child_bundle = ai_cases.ensure_bundle(
                storage.data_dir,
                child,
                child_primary,
                _neighbor_projects(storage, child),
            )
            _write_case_metadata_files(storage, child, child_bundle)
            await bus.publish(
                "v1.ai_case.created",
                {"case_id": child.id, "parent_case_id": case.id},
            )
        detail = _case_detail(storage, manager, case)
        return {
            "case": detail.model_dump(mode="json"),
            "session": {
                **session.summary().__dict__,
                "work_item_id": lead_item.id,
                "runtime": chosen_runtime,
                "job_id": job.id,
            },
        }

    @router.post("/ai-cases/{case_id}/stop", response_model=None)
    async def stop_ai_case(case_id: str) -> dict[str, Any]:
        case = ai_cases.get_case(storage.conn, case_id)
        stopped_sessions = 0
        closed_work_item_ids: list[str] = []
        with storage.transaction() as conn:
            if case.squad_id:
                for item in squads.list_work_items(conn, case.squad_id):
                    if not item.pty_session_id:
                        continue
                    if await manager.close(item.pty_session_id):
                        stopped_sessions += 1
                        closed_work_item_ids.append(item.id)
                        squads.complete_work_item_from_session_exit(
                            conn,
                            session_id=item.pty_session_id,
                            exit_code=-1,
                        )
                        job = ai_cases.update_job_for_session_finalization(
                            conn,
                            session_id=item.pty_session_id,
                            exit_code=-1,
                        )
                        if job is not None:
                            ai_cases.update_job(
                                conn,
                                job.id,
                                status=ai_cases.AiJobStatus.STOPPED,
                                completed_at=utc_now(),
                                exit_code=-1,
                            )
            case = ai_cases.update_case(
                conn,
                case.id,
                status=ai_cases.AiCaseStatus.STOPPED,
                phase=ai_cases.AiCasePhase.STOPPED,
                stopped_at=utc_now(),
                last_error_code=None,
                last_error_message=None,
            )
            audit(
                conn,
                AuditRecord(
                    entity_type="ai_case",
                    entity_id=case.id,
                    action="stop",
                    source=AuditSource.DESKTOP,
                    result="success",
                    details={"stopped_sessions": stopped_sessions},
                ),
            )
        await bus.publish("v1.ai_case.updated", {"case_id": case.id, "status": case.status.value})
        return {
            "case_id": case.id,
            "status": case.status.value,
            "stopped_sessions": stopped_sessions,
            "work_item_ids": closed_work_item_ids,
        }

    @router.post("/projects/{project_id}/open-ai-os", response_model=None)
    async def open_project_in_ai_os(
        project_id: str,
        request: Request,
        payload: OpenAiOsRequest | None = None,
    ) -> dict[str, Any]:
        projects_module.get(storage.conn, project_id)
        body = payload or OpenAiOsRequest()
        ai_os_project = _ensure_ai_os_project(storage, auth, request)
        if process_manager.status_of(ai_os_project.id) is None:
            try:
                await process_manager.launch(ai_os_project.id, source=AuditSource.DESKTOP)
            except Exception:
                pass
        url = f"http://127.0.0.1:{_AI_OS_PORT}/?primary_project_id={project_id}"
        if body.case_id:
            url += f"&case_id={body.case_id}"
        if body.neighbor_project_ids:
            neighbors = ",".join(pid for pid in body.neighbor_project_ids if pid and pid != project_id)
            if neighbors:
                url += f"&neighbor_project_ids={neighbors}"
        return {
            "app_project_id": ai_os_project.id,
            "url": url,
            "expected_port": _AI_OS_PORT,
        }

    @router.post("/ai-cases/{case_id}/export/{kind}", response_model=None)
    async def export_ai_case(case_id: str, kind: str) -> dict[str, Any]:
        case = ai_cases.get_case(storage.conn, case_id)
        primary = projects_module.get(storage.conn, case.primary_project_id)
        bundle = ai_cases.load_bundle(storage.data_dir, case.id)
        kind = kind.lower()
        if kind == "adr":
            created = _export_to_adr(storage, primary.id, case, bundle)
            return {"kind": kind, "created": created}
        if kind == "backlog":
            created = _export_to_backlog(storage, primary.id, case, bundle)
            return {"kind": kind, "created": created}
        if kind == "memory":
            path = _export_to_memory(storage, primary, case, bundle)
            return {"kind": kind, "path": str(path)}
        if kind == "preset":
            path = _export_to_preset(case, primary, bundle)
            return {"kind": kind, "path": str(path)}
        if kind == "recipe":
            path = _export_to_recipe(storage, case, bundle)
            return {"kind": kind, "path": str(path)}
        if kind == "scorecard":
            path = _export_to_scorecard(storage, case, bundle)
            return {"kind": kind, "path": str(path)}
        if kind == "benchmark":
            path = _export_to_benchmark(storage, case, bundle)
            return {"kind": kind, "path": str(path)}
        raise invalid("ai_case", "Export kind must be one of adr, backlog, memory, preset, recipe, scorecard, or benchmark.")

    return router


def _phase_for_run(mode: ai_cases.AiCaseMode) -> ai_cases.AiCasePhase:
    if mode in {ai_cases.AiCaseMode.BENCHMARK, ai_cases.AiCaseMode.PORTFOLIO}:
        return ai_cases.AiCasePhase.COMPARE
    return ai_cases._phase_for_mode(mode)


def _validate_case_targets(storage: Storage, targets: ai_cases.AiCaseTargets) -> None:
    projects_module.get(storage.conn, targets.primary_project_id)
    for collection in (targets.neighbor_project_ids, targets.reference_project_ids, targets.integration_target_ids):
        for project_id in collection:
            if project_id:
                projects_module.get(storage.conn, project_id)


def _neighbor_projects(storage: Storage, case: ai_cases.AiCase) -> list[Project]:
    neighbors: list[Project] = []
    for target in ai_cases.list_targets(storage.conn, case.id):
        if target.relation == ai_cases.AiCaseTargetRelation.NEIGHBOR:
            neighbors.append(projects_module.get(storage.conn, target.project_id))
    return neighbors


def _prepare_mode_specific_case_plan(
    storage: Storage,
    conn,
    case: ai_cases.AiCase,
    primary: Project,
    neighbors: list[Project],
    bundle: ai_cases.AiCaseBundle,
) -> tuple[ai_cases.AiCase, ai_cases.AiCaseBundle, list[ai_cases.AiCase]]:
    created_children: list[ai_cases.AiCase] = []
    existing_children = _child_cases(conn, case.id)

    if case.case_mode == ai_cases.AiCaseMode.BENCHMARK:
        created_children.extend(
            _ensure_benchmark_children(storage, conn, case, existing_children)
        )
        _sync_benchmark_bundle(bundle, [*existing_children, *created_children])
    elif case.case_mode == ai_cases.AiCaseMode.HARVEST:
        case = _ingest_harvest_sources(conn, case)
        bundle.targets = case.targets
        _sync_harvest_bundle(bundle, case.targets.attached_source_ids)
    elif case.case_mode == ai_cases.AiCaseMode.PORTFOLIO:
        created_children.extend(
            _ensure_portfolio_children(storage, conn, case, primary, neighbors, existing_children)
        )
        _sync_portfolio_bundle(bundle, primary, neighbors, [*existing_children, *created_children])
    elif case.case_mode == ai_cases.AiCaseMode.CHALLENGE:
        created_children.extend(
            _ensure_challenge_children(storage, conn, case, existing_children)
        )
        _sync_challenge_bundle(bundle, [*existing_children, *created_children])
    elif case.case_mode == ai_cases.AiCaseMode.REPAIR:
        _append_ledger_once(
            bundle.stabilization_ledger,
            entry_id=f"{case.id}-stabilize",
            title="Stabilization lane opened",
            summary="Restore the primary repo to a runnable, tested baseline before deeper cleanup.",
        )
    elif case.case_mode == ai_cases.AiCaseMode.MIGRATE:
        _append_ledger_once(
            bundle.migration_ledger,
            entry_id=f"{case.id}-migrate",
            title="Migration ledger opened",
            summary="Track compatibility notes, checkpoints, and rollback moves throughout the upgrade.",
        )
    elif case.case_mode == ai_cases.AiCaseMode.AUDIT:
        if not bundle.scorecard.prioritized_backlog:
            bundle.scorecard.prioritized_backlog = [
                "Capture the top UX issue and the top architecture issue before verdict.",
                "Record whether browser coverage is present or missing.",
                "List the first three fixes with the highest risk-reduction per token.",
            ]

    for child in created_children:
        ai_cases.create_job(
            conn,
            case_id=case.id,
            phase=ai_cases.AiCasePhase.COMPARE if case.case_mode in {ai_cases.AiCaseMode.BENCHMARK, ai_cases.AiCaseMode.PORTFOLIO} else ai_cases.AiCasePhase.RESEARCH,
            label=f"Child case queued: {child.title or child.id}",
            status=ai_cases.AiJobStatus.QUEUED,
            worker_role_id="boss",
            notes_md=f"Spawned child case {child.id} for {case.case_mode.value}.",
        )
        audit(
            conn,
            AuditRecord(
                entity_type="ai_case",
                entity_id=child.id,
                action="spawn",
                source=AuditSource.DESKTOP,
                result="success",
                details={"parent_case_id": case.id, "spawn_reason": child.spawn_reason},
            ),
        )

    bundle.updated_at = utc_now()
    return case, bundle, created_children


def _child_cases(conn, parent_case_id: str) -> list[ai_cases.AiCase]:
    return [
        case
        for case in ai_cases.list_cases(conn)
        if case.parent_case_id == parent_case_id
    ]


def _ensure_benchmark_children(
    storage: Storage,
    conn,
    case: ai_cases.AiCase,
    existing_children: list[ai_cases.AiCase],
) -> list[ai_cases.AiCase]:
    existing_recipe_ids = {
        child.directives.selected_recipe_id
        for child in existing_children
        if child.directives.selected_recipe_id
    }
    created: list[ai_cases.AiCase] = []
    for recipe_id in _benchmark_candidate_recipe_ids(conn, case):
        if recipe_id in existing_recipe_ids:
            continue
        recipe_name = recipe_id
        try:
            recipe_name = ai_factory.get_recipe(conn, recipe_id).name
        except Exception:
            pass
        child_id = ai_cases._new_id()
        child = ai_cases.spawn_child_case(
            conn,
            case,
            ai_cases.AiCaseSpawnRequest(
                case_mode=ai_cases.AiCaseMode.GENERATE,
                mission_profile_id="new-app-from-brief",
                directives=case.directives.model_copy(
                    update={
                        "selected_recipe_id": recipe_id,
                        "candidate_recipe_ids": [],
                        "recipe_selection_mode": ai_cases.AiRecipeSelectionMode.MANUAL,
                    }
                ),
                candidate_label=recipe_name,
                spawn_reason=f"Benchmark candidate for recipe {recipe_id}",
                title=f"{case.title or case.intent.goal_md or 'Benchmark'} / {recipe_name}",
            ),
            case_id=child_id,
            bundle_path=ai_cases.bundle_file_path(storage.data_dir, child_id),
        )
        created.append(child)
    return created


def _benchmark_candidate_recipe_ids(conn, case: ai_cases.AiCase) -> list[str]:
    candidates: list[str] = []
    if case.directives.selected_recipe_id:
        candidates.append(case.directives.selected_recipe_id)
    candidates.extend(case.directives.candidate_recipe_ids)
    if not candidates:
        candidates = [recipe.id for recipe in ai_factory.list_recipes(conn)[:3]]
    deduped = list(dict.fromkeys(item for item in candidates if item))
    return deduped[:4]


def _sync_benchmark_bundle(
    bundle: ai_cases.AiCaseBundle,
    children: list[ai_cases.AiCase],
) -> None:
    seen = {candidate.case_id for candidate in bundle.candidate_leaderboard if candidate.case_id}
    for child in children:
        if child.id in seen:
            continue
        bundle.candidate_leaderboard.append(
            ai_cases.AiCandidateResult(
                case_id=child.id,
                candidate_label=child.candidate_label or child.directives.selected_recipe_id or child.id,
                summary="Candidate queued for benchmark comparison.",
            )
        )
    _append_timeline_once(
        bundle,
        entry_id=f"{bundle.case_id}-benchmark",
        phase=ai_cases.AiCasePhase.COMPARE,
        label="Benchmark candidates prepared",
        summary=f"{len(children)} candidate case(s) are available for side-by-side comparison.",
    )
    if not bundle.verdict.summary:
        bundle.verdict.summary = "Benchmark pending. Compare child candidates before choosing the winner."


def _ensure_portfolio_children(
    storage: Storage,
    conn,
    case: ai_cases.AiCase,
    primary: Project,
    neighbors: list[Project],
    existing_children: list[ai_cases.AiCase],
) -> list[ai_cases.AiCase]:
    existing_targets = {child.primary_project_id for child in existing_children}
    sequence = [primary, *neighbors]
    created: list[ai_cases.AiCase] = []
    for project in sequence:
        if project.id in existing_targets:
            continue
        references = [item.id for item in sequence if item.id != project.id]
        child_id = ai_cases._new_id()
        child = ai_cases.spawn_child_case(
            conn,
            case,
            ai_cases.AiCaseSpawnRequest(
                case_mode=ai_cases.AiCaseMode.RESEARCH,
                mission_profile_id="repo-decision" if project.id == primary.id else "portfolio-sweep",
                targets=case.targets.model_copy(
                    update={
                        "primary_project_id": project.id,
                        "neighbor_project_ids": [],
                        "reference_project_ids": references,
                    }
                ),
                candidate_label=project.name,
                spawn_reason=f"Portfolio execution slice for {project.id}",
                title=f"{case.title or case.intent.goal_md or 'Portfolio'} / {project.name}",
            ),
            case_id=child_id,
            bundle_path=ai_cases.bundle_file_path(storage.data_dir, child_id),
        )
        created.append(child)
    return created


def _sync_portfolio_bundle(
    bundle: ai_cases.AiCaseBundle,
    primary: Project,
    neighbors: list[Project],
    children: list[ai_cases.AiCase],
) -> None:
    for project in [primary, *neighbors]:
        if any(card.project_id == project.id for card in bundle.claim_cards):
            continue
        bundle.claim_cards.append(
            ai_cases.ClaimCard(
                id=f"{bundle.case_id}-{project.id}",
                title=f"Portfolio slice: {project.name}",
                kind=ai_cases.ClaimCardKind.REPO_BACKED,
                summary="Treat this repo as an ordered single-write-target slice inside the broader portfolio run.",
                project_id=project.id,
                evidence=[project.path],
            )
        )
    _append_timeline_once(
        bundle,
        entry_id=f"{bundle.case_id}-portfolio",
        phase=ai_cases.AiCasePhase.COMPARE,
        label="Portfolio slices prepared",
        summary=f"{len(children)} child case(s) sequence the portfolio into explicit execution slices.",
    )


def _ensure_challenge_children(
    storage: Storage,
    conn,
    case: ai_cases.AiCase,
    existing_children: list[ai_cases.AiCase],
) -> list[ai_cases.AiCase]:
    if any(child.candidate_label == "minority-path" for child in existing_children):
        return []
    child_id = ai_cases._new_id()
    child = ai_cases.spawn_child_case(
        conn,
        case,
        ai_cases.AiCaseSpawnRequest(
            case_mode=ai_cases.AiCaseMode.RESEARCH,
            mission_profile_id="challenge-pass",
            candidate_label="minority-path",
            spawn_reason="Force a credible alternative path before the case settles.",
            title=f"{case.title or case.intent.goal_md or 'Challenge'} / Minority path",
        ),
        case_id=child_id,
        bundle_path=ai_cases.bundle_file_path(storage.data_dir, child_id),
    )
    return [child]


def _sync_challenge_bundle(
    bundle: ai_cases.AiCaseBundle,
    children: list[ai_cases.AiCase],
) -> None:
    if not bundle.contradiction_docket:
        bundle.contradiction_docket.append(
            ai_cases.ContradictionDocketItem(
                id=f"{bundle.case_id}-challenge",
                question="What is the strongest credible alternative path?",
                stakes="Without a recorded alternative, the case may lock onto the first plausible answer.",
                left=ai_cases.ContradictionSide(label="Current path"),
                right=ai_cases.ContradictionSide(label="Minority path"),
            )
        )
    if len(bundle.failure_matrix) < 3:
        existing_risks = {item.risk for item in bundle.failure_matrix}
        additions = [
            ("User workflow stays harder than necessary", "A technically correct answer still feels clumsy in practice.", "Force a UX and movement pass before verdict."),
            ("Hidden dependency was ignored", "A change lands cleanly in one repo but breaks another seam later.", "Require blast-radius and dependency mapping before handoff."),
            ("Testing signal is too weak", "The winner looks good but regresses under real use.", "Require reviewer/tester notes and at least one runnable check."),
        ]
        for risk, consequence, mitigation in additions:
            if risk in existing_risks:
                continue
            bundle.failure_matrix.append(
                ai_cases.AiFailureMatrixItem(
                    risk=risk,
                    consequence=consequence,
                    mitigation=mitigation,
                )
            )
    _append_timeline_once(
        bundle,
        entry_id=f"{bundle.case_id}-challenge",
        phase=ai_cases.AiCasePhase.RESEARCH,
        label="Challenge lane prepared",
        summary=f"{len(children)} alternate child case(s) preserve dissent before verdict.",
    )


def _ingest_harvest_sources(conn, case: ai_cases.AiCase) -> ai_cases.AiCase:
    targets = case.targets.model_copy(deep=True)
    attached = list(targets.attached_source_ids)
    for index, url in enumerate(targets.reference_urls, start=1):
        source_id = f"harvest-{case.id}-{index}"
        if source_id not in attached:
            if conn.execute(
                "SELECT 1 FROM ai_factory_sources WHERE id = ?",
                (source_id,),
            ).fetchone() is None:
                ai_factory.create_source(
                    conn,
                    ai_factory.AiSourceCreate(
                        id=source_id,
                        label=f"Harvest reference {index}",
                        source_type=ai_factory.AiSourceType.WEB,
                        url=url,
                        reuse_posture=ai_factory.AiReusePosture.REFERENCE_ONLY,
                        provenance_summary="Reference captured from the case's harvest input URLs.",
                        metadata={"captured_by_case_id": case.id},
                        notes_md=f"Captured from harvest reference URL: {url}",
                    ),
                )
            attached.append(source_id)
    targets.attached_source_ids = list(dict.fromkeys(attached))
    if targets.attached_source_ids == case.targets.attached_source_ids:
        return case
    return ai_cases.update_case(conn, case.id, targets=targets)


def _sync_harvest_bundle(bundle: ai_cases.AiCaseBundle, source_ids: list[str]) -> None:
    existing_sources = {proposal.source_id for proposal in bundle.promotions if proposal.source_id}
    for source_id in source_ids:
        if source_id in existing_sources:
            continue
        bundle.promotions.append(
            ai_cases.AiPromotionProposal(
                source_id=source_id,
                asset_family="recipe",
                suggested_id=f"{source_id}-recipe",
                title=f"Promote {source_id}",
                rationale="Captured during harvest so future runs can reuse the pattern instead of rediscovering it.",
            )
        )
    _append_timeline_once(
        bundle,
        entry_id=f"{bundle.case_id}-harvest",
        phase=ai_cases.AiCasePhase.RESEARCH,
        label="Harvest intake prepared",
        summary=f"{len(source_ids)} source(s) are attached for promotion and provenance-aware reuse.",
    )


def _append_timeline_once(
    bundle: ai_cases.AiCaseBundle,
    *,
    entry_id: str,
    phase: ai_cases.AiCasePhase,
    label: str,
    summary: str,
) -> None:
    if any(item.id == entry_id for item in bundle.timeline):
        return
    bundle.timeline.append(
        ai_cases.TimelineEntry(
            id=entry_id,
            phase=phase,
            label=label,
            summary=summary,
        )
    )


def _append_ledger_once(
    ledger: list[ai_cases.AiLedgerEntry],
    *,
    entry_id: str,
    title: str,
    summary: str,
) -> None:
    if any(item.id == entry_id for item in ledger):
        return
    ledger.append(
        ai_cases.AiLedgerEntry(
            id=entry_id,
            title=title,
            summary=summary,
        )
    )


def _write_case_metadata_files(
    storage: Storage,
    case: ai_cases.AiCase,
    bundle: ai_cases.AiCaseBundle,
) -> None:
    case_root = ai_cases.case_dir(storage.data_dir, case.id)
    case_root.mkdir(parents=True, exist_ok=True)
    ai_cases.write_bundle(storage.data_dir, bundle)
    metadata = {
        "case_id": case.id,
        "primary_project_id": case.primary_project_id,
        "mission_profile_id": case.mission_profile_id,
        "case_mode": case.case_mode.value,
        "status": case.status.value,
        "phase": case.phase.value,
        "title": case.title,
        "intent": case.intent.model_dump(mode="json"),
        "targets": case.targets.model_dump(mode="json"),
        "directives": case.directives.model_dump(mode="json"),
        "policies": case.policies.model_dump(mode="json"),
        "graph": ai_cases.case_graph(storage.conn, case.id).model_dump(mode="json"),
    }
    (case_root / "context.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")


def _case_detail(
    storage: Storage,
    manager: PtySessionManager,
    case: ai_cases.AiCase,
) -> ai_cases.AiCaseDetail:
    primary = projects_module.get(storage.conn, case.primary_project_id)
    neighbors = _neighbor_projects(storage, case)
    bundle = ai_cases.ensure_bundle(storage.data_dir, case, primary, neighbors)
    jobs = ai_cases.list_jobs(storage.conn, case.id)
    active_jobs = [job for job in jobs if job.status in {ai_cases.AiJobStatus.STARTING, ai_cases.AiJobStatus.RUNNING, ai_cases.AiJobStatus.REVIEWING, ai_cases.AiJobStatus.TESTING}]
    active_workers: list[ai_cases.AiCaseWorkerSummary] = []
    if case.squad_id:
        for item in squads.list_work_items(storage.conn, case.squad_id):
            session = manager.get(item.pty_session_id) if item.pty_session_id else None
            if session is not None and session.exit_code is None:
                active_workers.append(
                    ai_cases.AiCaseWorkerSummary(
                        work_item_id=item.id,
                        title=item.title,
                        status=item.status.value,
                        assigned_role_id=item.assigned_role_id,
                        pty_session_id=item.pty_session_id,
                        transcript_file_id=item.transcript_file_id,
                    )
                )
    if case.status == ai_cases.AiCaseStatus.RUNNING and not active_jobs and not active_workers:
        with storage.transaction() as conn:
            case = ai_cases.update_case(
                conn,
                case.id,
                status=ai_cases.AiCaseStatus.COMPLETED,
                phase=ai_cases.AiCasePhase.HANDOFF,
                completed_at=utc_now(),
                last_error_code=None,
                last_error_message=None,
            )
    return ai_cases.AiCaseDetail(
        case=case,
        targets=ai_cases.list_targets(storage.conn, case.id),
        bundle_summary=ai_cases.summarize_bundle(bundle, active_job_count=len(active_jobs)),
        active_workers=active_workers,
        jobs=jobs,
        graph=ai_cases.case_graph(storage.conn, case.id),
    )


def _ensure_case_squad(
    storage: Storage,
    conn,
    case: ai_cases.AiCase,
    primary: Project,
    neighbors: list[Project],
    worktree_path: str,
    branch_name: str,
) -> squads.AgentSquad:
    if case.squad_id:
        return squads.get_squad(conn, case.squad_id)
    goal_md = "\n".join(
        [
            f"# AI OS case {case.id}",
            "",
            case.intent.goal_md.strip() or "Drive the case from setup to handoff.",
            "",
            f"- Mission profile: `{case.mission_profile_id or ai_cases.default_mission_profile_id(case.case_mode)}`",
            f"- Case mode: `{case.case_mode.value}`",
            f"- Primary project: `{primary.id}`",
            f"- Writable worktree: `{worktree_path}`",
            f"- Case branch: `{branch_name}`",
            f"- Neighbor projects: `{', '.join(project.id for project in neighbors) or 'none'}`",
        ]
    )
    squad = squads.create_squad(
        conn,
        squads.AgentSquadCreate(
            project_id=primary.id,
            name=f"AI OS Case {case.id}",
            goal_md=goal_md,
            lead_role_id="boss",
            source=AuditSource.DESKTOP,
        ),
    )
    ensure_ai_context_file(storage.data_dir, primary.id, primary.name)
    if not squads.list_work_items(conn, squad.id):
        for contract in ai_cases.angle_contracts(
            case,
            primary,
            neighbors,
            worktree_path=worktree_path,
            branch_name=branch_name,
        ):
            assigned_role_id = _resolve_role_id(
                conn,
                contract.assigned_role_id,
                contract.fallback_role_ids,
            )
            personality_id = _resolve_personality_id(
                conn,
                contract.preferred_personality_id,
                contract.fallback_personality_ids,
            )
            squads.create_work_item(
                conn,
                squad.id,
                squads.AgentWorkItemCreate(
                    title=contract.title,
                    instructions_md=contract.instructions_md,
                    assigned_role_id=assigned_role_id,
                    personality_id=personality_id,
                    source=AuditSource.DESKTOP,
                ),
            )
    return squad


def _resolve_role_id(conn, preferred_id: str | None, fallbacks: list[str]) -> str | None:
    for candidate in [preferred_id, *fallbacks]:
        if not candidate:
            continue
        row = conn.execute(
            "SELECT 1 FROM agent_role_templates WHERE id = ?",
            (candidate,),
        ).fetchone()
        if row is not None:
            return candidate
    return preferred_id


def _resolve_personality_id(conn, preferred_id: str | None, fallbacks: list[str]) -> str | None:
    for candidate in [preferred_id, *fallbacks]:
        if not candidate:
            continue
        row = conn.execute(
            "SELECT 1 FROM personalities WHERE id = ?",
            (candidate,),
        ).fetchone()
        if row is not None:
            return candidate
    return None


def _ensure_ai_os_project(
    storage: Storage,
    auth: AuthManager,
    request: Request,
) -> Project:
    project_path = bundled_ai_os_dir()
    project_path.mkdir(parents=True, exist_ok=True)
    daemon_host = "127.0.0.1"
    daemon_port = int(getattr(request.app.state, "bound_port", 7878) or 7878)
    project = projects_module.get_or_none(storage.conn, _AI_OS_PROJECT_ID)
    launch_cmd = f'"{sys.executable}" server.py'
    env = [
        EnvVar(key="AI_OS_PORT", value=str(_AI_OS_PORT)),
        EnvVar(key="SYNAPSE_API", value=f"http://{daemon_host}:{daemon_port}/api/v1"),
        EnvVar(key="SYNAPSE_TOKEN", value=auth.local_token),
    ]
    if project is None:
        with storage.transaction() as conn:
            created = projects_module.create(
                conn,
                Project(
                    id=_AI_OS_PROJECT_ID,
                    name=_AI_OS_PROJECT_NAME,
                    path=str(project_path),
                    launch_cmd=launch_cmd,
                    kind=ProjectKind.UI,
                    expected_port=_AI_OS_PORT,
                    description="Case-board UI for Synapse AI Operating System v1.2.",
                    env=env,
                    health=HealthProbe(kind="http", target=f"http://127.0.0.1:{_AI_OS_PORT}/health"),
                ),
            )
            audit(
                conn,
                AuditRecord(
                    entity_type="project",
                    entity_id=created.id,
                    action="create",
                    source=AuditSource.AUTO,
                    result="success",
                    details={"reason": "ai-os.ensure"},
                ),
            )
        return created
    patch = ProjectUpdate(
        path=str(project_path),
        launch_cmd=launch_cmd,
        expected_port=_AI_OS_PORT,
        description="Case-board UI for Synapse AI Operating System v1.2.",
        env=env,
        kind=ProjectKind.UI,
        health=HealthProbe(kind="http", target=f"http://127.0.0.1:{_AI_OS_PORT}/health"),
    )
    with storage.transaction() as conn:
        return projects_module.update(conn, project.id, patch)


def _write_draft_pr_stub(
    storage: Storage,
    case: ai_cases.AiCase,
    primary: Project,
    worktree_path: Path,
    branch_name: str,
) -> Path:
    path = ai_cases.draft_pr_path(storage.data_dir, case.id)
    if path.exists():
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(
            [
                f"# Draft PR · case {case.id}",
                "",
                f"Title: {case.title or case.intent.goal_md or 'AI case'}",
                f"Mission profile: `{case.mission_profile_id or ''}`",
                f"Case mode: `{case.case_mode.value}`",
                f"Primary project: `{primary.id}`",
                f"Branch: `{branch_name}`",
                f"Worktree: `{worktree_path}`",
                "",
                "## Summary",
                "_Fill in the chosen direction and implementation summary._",
                "",
                "## Tests",
                "- _List the checks run for this case._",
                "",
                "## Risks / follow-ups",
                "- _Document residual risk, neighbor follow-up work, and rollback notes._",
            ]
        ),
        encoding="utf-8",
    )
    return path


def _export_to_adr(
    storage: Storage,
    project_id: str,
    case: ai_cases.AiCase,
    bundle: ai_cases.AiCaseBundle,
) -> list[dict[str, Any]]:
    created: list[dict[str, Any]] = []
    title = bundle.verdict.summary or f"AI OS case {case.id} verdict"
    blast_radius_lines = [f"- {item}" for item in bundle.blast_radius.touched_areas] or ["- _No touched areas recorded._"]
    body = "\n".join(
        [
            f"# Verdict from AI OS case {case.id}",
            "",
            f"- Mission profile: `{case.mission_profile_id or ''}`",
            f"- Case mode: `{case.case_mode.value}`",
            "",
            "## Chosen direction",
            bundle.verdict.chosen_direction or "_Not yet captured._",
            "",
            "## Rationale",
            bundle.verdict.rationale or "_Not yet captured._",
            "",
            "## Minority report",
            bundle.minority_report.strongest_losing_argument or "_No minority argument recorded._",
            "",
            "## Blast radius",
            *blast_radius_lines,
        ]
    )
    with storage.transaction() as conn:
        adr = records.create_adr(
            conn,
            project_id,
            records.ProjectAdrCreate(title=title, body_md=body, status=records.ProjectAdrStatus.DRAFT),
        )
        created.append(adr.model_dump(mode="json"))
    return created


def _export_to_backlog(
    storage: Storage,
    project_id: str,
    case: ai_cases.AiCase,
    bundle: ai_cases.AiCaseBundle,
) -> list[dict[str, Any]]:
    created: list[dict[str, Any]] = []
    items = bundle.scorecard.prioritized_backlog or bundle.handoff_pack.unresolved_questions or bundle.handoff_pack.first_steps or [f"Follow up AI OS case {case.id}"]
    with storage.transaction() as conn:
        for text in items:
            item = records.create_backlog_item(
                conn,
                project_id,
                records.ProjectBacklogItemCreate(
                    title=text[:120],
                    body_md=f"Exported from AI OS case {case.id}.",
                    priority=records.ProjectBacklogPriority.MEDIUM,
                ),
            )
            created.append(item.model_dump(mode="json"))
    return created


def _export_to_memory(
    storage: Storage,
    primary: Project,
    case: ai_cases.AiCase,
    bundle: ai_cases.AiCaseBundle,
) -> Path:
    next_steps = [f"- {step}" for step in bundle.handoff_pack.first_steps] or ["- None recorded."]
    note = "\n".join(
        [
            f"AI OS case {case.id}",
            "",
            f"Title: {case.title or case.intent.goal_md or 'AI case'}",
            f"Mission profile: {case.mission_profile_id or 'n/a'}",
            f"Verdict: {bundle.verdict.summary or bundle.verdict.chosen_direction or 'No verdict recorded.'}",
            f"Direction: {bundle.verdict.chosen_direction or 'No direction recorded.'}",
            "",
            "Next steps:",
            *next_steps,
        ]
    )
    return append_capture_note(
        data_dir=storage.data_dir,
        project_id=primary.id,
        project_name=primary.name,
        note=note,
        source="ai-os",
    )


def _export_to_preset(
    case: ai_cases.AiCase,
    primary: Project,
    bundle: ai_cases.AiCaseBundle,
) -> Path:
    quick_actions = bundled_quick_actions_dir()
    quick_actions.mkdir(parents=True, exist_ok=True)
    quick_action_id = f"ai-case-{case.id}"
    path = quick_actions / f"{quick_action_id}.json"
    payload = {
        "id": quick_action_id,
        "name": f"AI OS preset · {primary.name}",
        "description": "Relaunch this case pattern as a quick-action.",
        "icon": "crown",
        "category": "workflows",
        "tags": ["ai-os", "case", primary.id, case.case_mode.value],
        "prompt": "\n".join(
            [
                f"Re-run the AI OS case pattern for project `{primary.id}`.",
                "",
                f"Original case id: {case.id}",
                f"Mission profile: {case.mission_profile_id or ''}",
                f"Original goal: {case.intent.goal_md}",
                "",
                "Most recent verdict summary:",
                bundle.verdict.summary or bundle.verdict.chosen_direction or "No verdict recorded.",
            ]
        ),
        "default_argv": ["codex"],
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def _export_to_recipe(
    storage: Storage,
    case: ai_cases.AiCase,
    bundle: ai_cases.AiCaseBundle,
) -> Path:
    path = ai_cases.export_file_path(storage.data_dir, case.id, "EXPORTED_RECIPE.json")
    payload = {
        "case_id": case.id,
        "selected_recipe_id": case.directives.selected_recipe_id,
        "candidate_recipe_ids": case.directives.candidate_recipe_ids,
        "component_overrides": [override.model_dump(mode="json") for override in case.directives.component_overrides],
        "similarity_report": bundle.similarity_report.model_dump(mode="json"),
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def _export_to_scorecard(
    storage: Storage,
    case: ai_cases.AiCase,
    bundle: ai_cases.AiCaseBundle,
) -> Path:
    path = ai_cases.export_file_path(storage.data_dir, case.id, "SCORECARD.md")
    lines = [
        f"# Scorecard · case {case.id}",
        "",
        bundle.scorecard.summary_md or "_No scorecard summary yet._",
        "",
    ]
    for item in bundle.scorecard.items:
        lines.append(f"- [{item.status}] {item.label}: {item.summary or 'Pending'}")
    if bundle.scorecard.prioritized_backlog:
        lines.extend(["", "## Prioritized backlog", *[f"- {item}" for item in bundle.scorecard.prioritized_backlog]])
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def _export_to_benchmark(
    storage: Storage,
    case: ai_cases.AiCase,
    bundle: ai_cases.AiCaseBundle,
) -> Path:
    path = ai_cases.export_file_path(storage.data_dir, case.id, "BENCHMARK.json")
    payload = {
        "case_id": case.id,
        "winner": case.winning_child_case_id or (next((candidate.case_id for candidate in bundle.candidate_leaderboard if candidate.winner), None)),
        "leaderboard": [candidate.model_dump(mode="json") for candidate in bundle.candidate_leaderboard],
        "graph": ai_cases.case_graph(storage.conn, case.id).model_dump(mode="json"),
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


async def subscribe_ai_case_events(storage: Storage, bus: EventBus) -> None:
    async def _on_event(event: Event) -> None:
        if event.name == event_name("pty", "session_finalized"):
            session_id = str(event.payload.get("session_id") or "")
            if not session_id:
                return
            exit_code_raw = event.payload.get("exit_code")
            exit_code = exit_code_raw if isinstance(exit_code_raw, int) or exit_code_raw is None else None
            with storage.transaction() as conn:
                job = ai_cases.update_job_for_session_finalization(conn, session_id=session_id, exit_code=exit_code)
                if job is None:
                    return
                case = ai_cases.get_case(conn, job.case_id)
                active_jobs = [
                    item for item in ai_cases.list_jobs(conn, case.id)
                    if item.status in {ai_cases.AiJobStatus.STARTING, ai_cases.AiJobStatus.RUNNING, ai_cases.AiJobStatus.REVIEWING, ai_cases.AiJobStatus.TESTING}
                ]
                if not active_jobs and case.status == ai_cases.AiCaseStatus.RUNNING:
                    next_status = ai_cases.AiCaseStatus.COMPLETED if exit_code in (0, None) else ai_cases.AiCaseStatus.ERROR
                    next_phase = ai_cases.AiCasePhase.HANDOFF if next_status == ai_cases.AiCaseStatus.COMPLETED else ai_cases.AiCasePhase.ERROR
                    case = ai_cases.update_case(
                        conn,
                        case.id,
                        status=next_status,
                        phase=next_phase,
                        completed_at=utc_now() if next_status == ai_cases.AiCaseStatus.COMPLETED else None,
                        last_error_code=None if next_status == ai_cases.AiCaseStatus.COMPLETED else "case.job_failed",
                        last_error_message=None if next_status == ai_cases.AiCaseStatus.COMPLETED else "A case-owned job exited with a non-zero status.",
                    )
            await bus.publish("v1.ai_case.updated", {"case_id": job.case_id})
            return
        if event.name != event_name("agent_run", "ended"):
            return
        session_id = str(event.payload.get("session_id") or "")
        transcript_file_id = event.payload.get("transcript_file_id")
        if not session_id:
            return
        with storage.transaction() as conn:
            row = conn.execute(
                "SELECT id FROM ai_case_jobs WHERE session_id = ? ORDER BY created_at DESC LIMIT 1",
                (session_id,),
            ).fetchone()
            if row is None:
                return
            job = ai_cases.update_job(
                conn,
                row["id"],
                transcript_file_id=str(transcript_file_id) if transcript_file_id else None,
            )
        await bus.publish("v1.ai_case.updated", {"case_id": job.case_id})

    await bus.subscribe(_on_event)
