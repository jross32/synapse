"""REST routes for benchmark specs, runs, launches, ingest, and export."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter

from . import benchmarks
from . import coder_workspace
from . import files_storage
from . import project_records
from . import projects as projects_module
from . import quality_os
from .errors import invalid
from .pty_sessions import PtySessionManager
from .storage import Storage
from .time_utils import to_iso, utc_now


_SURFACE_PROFILE_VERSION = {
    benchmarks.BenchmarkSurfaceKind.SYNAPSE_CODER_THREAD: "coder_thread/v1",
    benchmarks.BenchmarkSurfaceKind.SYNAPSE_WORKBENCH: "workbench/v1",
    benchmarks.BenchmarkSurfaceKind.SYNAPSE_RAW_PTY: "raw_pty/v1",
    benchmarks.BenchmarkSurfaceKind.DIRECT_CLI: "direct_cli/v1",
    benchmarks.BenchmarkSurfaceKind.PROJECT_LAUNCHER: "project_launcher/v1",
}


def _default_argv(attempt: benchmarks.BenchmarkAttempt) -> list[str]:
    argv = attempt.metadata.get("argv")
    if isinstance(argv, list) and argv:
        return [str(item) for item in argv]
    return [attempt.intended_runtime_id]


def _scenario_bundle(conn, attempt: benchmarks.BenchmarkAttempt) -> tuple[benchmarks.BenchmarkRun, benchmarks.BenchmarkScenario]:
    run = benchmarks.get_run(conn, attempt.run_id)
    spec_bundle = benchmarks.get_spec_bundle(conn, run.spec_id)
    scenario = next((item for item in spec_bundle.scenarios if item.id == attempt.scenario_id), None)
    if scenario is None:
        raise invalid("benchmark_attempt", f"Scenario '{attempt.scenario_id}' is missing from spec '{run.spec_id}'.")
    return run, scenario


def _context_snapshot(project_id: str, files_count: int, records: project_records.ProjectRecords) -> tuple[str, int]:
    payload = {
        "project_id": project_id,
        "files_count": files_count,
        "adr_count": len(records.adrs),
        "backlog_count": len(records.backlog),
        "version_count": len(records.versions),
    }
    encoded = json.dumps(payload, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:16], len(payload)


def _write_prompt_artifact(storage: Storage, run_id: str, attempt_id: str, scenario: benchmarks.BenchmarkScenario) -> Path:
    target = benchmarks.benchmark_dir(storage.data_dir, run_id) / attempt_id
    target.mkdir(parents=True, exist_ok=True)
    prompt_path = target / "PROMPT.md"
    prompt_path.write_text(scenario.prompt_md + "\n", encoding="utf-8")
    return prompt_path


def _terminal_run_finished(status: benchmarks.BenchmarkAttemptStatus) -> bool:
    return status in {
        benchmarks.BenchmarkAttemptStatus.COMPLETED,
        benchmarks.BenchmarkAttemptStatus.FAILED,
        benchmarks.BenchmarkAttemptStatus.INGESTED,
        benchmarks.BenchmarkAttemptStatus.UNAVAILABLE,
    }


def _run_has_blocking_gates(conn, run_id: str) -> bool:  # noqa: ANN001
    for attempt in benchmarks.list_attempts_for_run(conn, run_id):
        if quality_os.has_blocking_gates(conn, "benchmark_attempt", attempt.id):
            return True
    return False


def _update_run_completion(conn, run_id: str) -> None:
    attempts = benchmarks.list_attempts_for_run(conn, run_id)
    statuses = {attempt.status for attempt in attempts}
    now = to_iso(utc_now())
    if attempts and all(_terminal_run_finished(status) for status in statuses):
        if _run_has_blocking_gates(conn, run_id):
            conn.execute(
                "UPDATE benchmark_runs SET status = ?, completed_at = NULL, updated_at = ? WHERE id = ?",
                (benchmarks.BenchmarkRunStatus.RUNNING.value, now, run_id),
            )
            return
        conn.execute(
            "UPDATE benchmark_runs SET status = ?, completed_at = ?, updated_at = ? WHERE id = ?",
            (benchmarks.BenchmarkRunStatus.COMPLETED.value, now, now, run_id),
        )
    elif attempts and any(status in {benchmarks.BenchmarkAttemptStatus.LAUNCHED, benchmarks.BenchmarkAttemptStatus.RUNNING} for status in statuses):
        conn.execute(
            "UPDATE benchmark_runs SET status = ?, launched_at = COALESCE(launched_at, ?), updated_at = ? WHERE id = ?",
            (benchmarks.BenchmarkRunStatus.RUNNING.value, now, now, run_id),
        )
    else:
        conn.execute(
            "UPDATE benchmark_runs SET updated_at = ? WHERE id = ?",
            (now, run_id),
        )


async def _launch_attempt(
    storage: Storage,
    pty_manager: PtySessionManager,
    attempt: benchmarks.BenchmarkAttempt,
    payload: benchmarks.BenchmarkLaunchRequest,
) -> dict[str, Any]:
    run, scenario = _scenario_bundle(storage.conn, attempt)
    argv = payload.argv or _default_argv(attempt)
    prompt_path = _write_prompt_artifact(storage, run.id, attempt.id, scenario)
    with storage.transaction() as conn:
        benchmarks.add_artifact(
            conn,
            attempt.id,
            kind="prompt-pack",
            label="Scenario prompt",
            path=str(prompt_path),
            mime="text/markdown",
            metadata={"scenario_id": scenario.id, "surface_kind": attempt.surface_kind.value},
        )

    if attempt.surface_kind == benchmarks.BenchmarkSurfaceKind.DIRECT_CLI:
        with storage.transaction() as conn:
            updated = benchmarks.mark_attempt_unavailable(
                conn,
                attempt.id,
                code="direct_cli.ingest_required",
                message="direct_cli attempts are ingest-only. Run the external harness, then call /api/v1/benchmarks/ingest-direct.",
            )
            _update_run_completion(conn, updated.run_id)
        return {
            "attempt": updated.model_dump(mode="json"),
            "prompt_path": str(prompt_path),
            "note": "External direct-cli attempt must be ingested after it finishes.",
        }

    if attempt.surface_kind == benchmarks.BenchmarkSurfaceKind.SYNAPSE_RAW_PTY:
        prefs = coder_workspace.get_preferences(storage.conn)
        if not prefs.raw_pty_enabled:
            with storage.transaction() as conn:
                updated = benchmarks.mark_attempt_unavailable(
                    conn,
                    attempt.id,
                    code="raw_pty.disabled",
                    message="Raw PTY launches are disabled by workspace preferences/capability flags.",
                )
                _update_run_completion(conn, updated.run_id)
            return {"attempt": updated.model_dump(mode="json"), "prompt_path": str(prompt_path)}

    project = None
    if attempt.project_id:
        project = projects_module.get(storage.conn, attempt.project_id)
    if attempt.surface_kind in {
        benchmarks.BenchmarkSurfaceKind.SYNAPSE_CODER_THREAD,
        benchmarks.BenchmarkSurfaceKind.SYNAPSE_WORKBENCH,
    } and project is None:
        raise invalid("benchmark_attempt", "This benchmark surface requires a project_id.")

    files_count = 0
    context_hash = None
    context_items_injected = 0
    if project is not None:
        files = files_storage.list_for_project(storage.conn, project.id)
        records = project_records.get_records(storage.conn, project.id)
        files_count = len(files)
        context_hash, context_items_injected = _context_snapshot(project.id, files_count, records)

    if attempt.surface_kind == benchmarks.BenchmarkSurfaceKind.SYNAPSE_CODER_THREAD:
        with storage.transaction() as conn:
            thread = coder_workspace.create_thread(
                conn,
                project.id,
                coder_workspace.CoderThreadCreate(
                    title=f"Benchmark / {run.title} / {scenario.name}",
                    active_runtime_id=attempt.intended_runtime_id,
                    active_provider=attempt.provider,
                    active_model=attempt.model,
                    workspace_context_mode="project",
                    thread_kind="benchmark",
                    metadata={
                        "benchmark_run_id": run.id,
                        "benchmark_attempt_id": attempt.id,
                        "scenario_id": scenario.id,
                    },
                ),
            )
            message = coder_workspace.add_message(
                conn,
                thread.id,
                coder_workspace.CoderMessageCreate(
                    role=coder_workspace.CoderMessageRole.USER,
                    content_md=scenario.prompt_md,
                    runtime_id=attempt.intended_runtime_id,
                    provider=attempt.provider,
                    model=attempt.model,
                    benchmark_attempt_id=attempt.id,
                    metadata={"prompt_path": str(prompt_path), "scenario_id": scenario.id},
                ),
            )
            run_record = coder_workspace.create_run(
                conn,
                coder_workspace.CoderRunCreate(
                    thread_id=thread.id,
                    message_id=message.id,
                    runtime_id=attempt.intended_runtime_id,
                    provider=attempt.provider,
                    model=attempt.model,
                    surface_kind=attempt.surface_kind.value,
                    surface_profile_version=_SURFACE_PROFILE_VERSION[attempt.surface_kind],
                    project_id=project.id,
                    benchmark_attempt_id=attempt.id,
                    workspace_context_mode="project",
                    attachments_count=files_count,
                    hidden_context_hash=context_hash,
                    workspace_overhead_bytes=len(scenario.prompt_md.encode("utf-8")),
                    context_items_injected=context_items_injected,
                    metadata={"prompt_path": str(prompt_path), "argv": argv},
                ),
            )
            coder_workspace.attach_run_to_message(conn, message.id, run_record.id)
        session = await pty_manager.spawn(argv=argv, cwd=project.path, project_id=project.id)
        with storage.transaction() as conn:
            run_record = coder_workspace.update_run_session(conn, run_record.id, session.session_id)
            updated = benchmarks.update_attempt_after_launch(
                conn,
                attempt.id,
                thread_id=thread.id,
                coder_run_id=run_record.id,
                surface_profile_version=_SURFACE_PROFILE_VERSION[attempt.surface_kind],
                workspace_context_mode="project",
                attachments_count=files_count,
                workspace_context_hash=context_hash,
                hidden_context_hash=context_hash,
                workspace_overhead_bytes=len(scenario.prompt_md.encode("utf-8")),
                context_items_injected=context_items_injected,
            )
            _update_run_completion(conn, updated.run_id)
        return {
            "attempt": updated.model_dump(mode="json"),
            "thread_id": thread.id,
            "message_id": message.id,
            "coder_run_id": run_record.id,
            "session": session.summary().__dict__,
            "prompt_path": str(prompt_path),
        }

    with storage.transaction() as conn:
        run_record = coder_workspace.create_run(
            conn,
            coder_workspace.CoderRunCreate(
                runtime_id=attempt.intended_runtime_id,
                provider=attempt.provider,
                model=attempt.model,
                surface_kind=attempt.surface_kind.value,
                surface_profile_version=_SURFACE_PROFILE_VERSION[attempt.surface_kind],
                project_id=project.id if project is not None else None,
                benchmark_attempt_id=attempt.id,
                workspace_context_mode="project",
                attachments_count=files_count,
                hidden_context_hash=context_hash,
                workspace_overhead_bytes=len(scenario.prompt_md.encode("utf-8")),
                context_items_injected=context_items_injected,
                metadata={"prompt_path": str(prompt_path), "argv": argv},
            ),
        )
    session = await pty_manager.spawn(
        argv=argv,
        cwd=project.path if project is not None else None,
        project_id=project.id if (project is not None and attempt.surface_kind == benchmarks.BenchmarkSurfaceKind.SYNAPSE_WORKBENCH) else None,
    )
    with storage.transaction() as conn:
        run_record = coder_workspace.update_run_session(conn, run_record.id, session.session_id)
        updated = benchmarks.update_attempt_after_launch(
            conn,
            attempt.id,
            coder_run_id=run_record.id,
            surface_profile_version=_SURFACE_PROFILE_VERSION[attempt.surface_kind],
            workspace_context_mode="project",
            attachments_count=files_count,
            workspace_context_hash=context_hash,
            hidden_context_hash=context_hash,
            workspace_overhead_bytes=len(scenario.prompt_md.encode("utf-8")),
            context_items_injected=context_items_injected,
        )
        _update_run_completion(conn, updated.run_id)
    return {
        "attempt": updated.model_dump(mode="json"),
        "coder_run_id": run_record.id,
        "session": session.summary().__dict__,
        "prompt_path": str(prompt_path),
    }


def build_benchmarks_router(storage: Storage, pty_manager: PtySessionManager) -> APIRouter:
    router = APIRouter(prefix="/benchmarks", tags=["benchmarks"])

    @router.get("/specs", response_model=None)
    async def list_specs() -> dict[str, Any]:
        return {
            "specs": [item.model_dump(mode="json") for item in benchmarks.list_spec_bundles(storage.conn)]
        }

    @router.post("/specs", response_model=None, status_code=201)
    async def create_spec(payload: benchmarks.BenchmarkSpecCreate) -> dict[str, Any]:
        with storage.transaction() as conn:
            created = benchmarks.create_spec(conn, payload)
        return created.model_dump(mode="json")

    @router.get("/runs", response_model=None)
    async def list_runs() -> dict[str, Any]:
        return {"runs": [item.model_dump(mode="json") for item in benchmarks.list_runs(storage.conn)]}

    @router.post("/runs", response_model=None, status_code=201)
    async def create_run(payload: benchmarks.BenchmarkRunCreate) -> dict[str, Any]:
        if payload.project_id:
            projects_module.get(storage.conn, payload.project_id)
        with storage.transaction() as conn:
            created = benchmarks.create_run(conn, payload)
        return created.model_dump(mode="json")

    @router.get("/runs/{run_id}", response_model=None)
    async def get_run(run_id: str) -> dict[str, Any]:
        report = benchmarks.build_run_report(storage.conn, run_id)
        artifacts: dict[str, list[dict[str, Any]]] = {}
        for attempt in report.all_attempts:
            artifacts[attempt.id] = [
                item.model_dump(mode="json") for item in benchmarks.list_artifacts(storage.conn, attempt.id)
            ]
        return {
            "run": report.run.model_dump(mode="json"),
            "report": report.model_dump(mode="json"),
            "artifacts": artifacts,
        }

    @router.post("/runs/{run_id}/launch", response_model=None)
    async def launch_run(run_id: str, payload: benchmarks.BenchmarkLaunchRequest | None = None) -> dict[str, Any]:
        body = payload or benchmarks.BenchmarkLaunchRequest()
        attempt = (
            benchmarks.get_attempt(storage.conn, body.attempt_id)
            if body.attempt_id
            else benchmarks.next_launchable_attempt(storage.conn, run_id)
        )
        if attempt is None:
            raise invalid("benchmark_run", "No launchable attempts remain for this run.")
        if attempt.run_id != run_id:
            raise invalid("benchmark_run", "Attempt does not belong to this run.")
        with storage.transaction() as conn:
            benchmarks.mark_run_launched(conn, run_id)
        return await _launch_attempt(storage, pty_manager, attempt, body)

    @router.post("/ingest-direct", response_model=None)
    async def ingest_direct(payload: benchmarks.BenchmarkDirectIngestRequest) -> dict[str, Any]:
        with storage.transaction() as conn:
            updated = benchmarks.ingest_direct_attempt(conn, payload)
            _update_run_completion(conn, updated.run_id)
        return {
            "attempt": updated.model_dump(mode="json"),
            "artifacts": [item.model_dump(mode="json") for item in benchmarks.list_artifacts(storage.conn, updated.id)],
        }

    @router.post("/runs/{run_id}/rescore", response_model=None)
    async def rescore_run(run_id: str) -> dict[str, Any]:
        attempts = benchmarks.list_attempts_for_run(storage.conn, run_id)
        with storage.transaction() as conn:
            rescored = [benchmarks.recompute_attempt_metrics(conn, attempt.id) for attempt in attempts]
            _update_run_completion(conn, run_id)
        report = benchmarks.build_run_report(storage.conn, run_id)
        return {
            "run": report.run.model_dump(mode="json"),
            "attempts": [item.model_dump(mode="json") for item in rescored],
            "report": report.model_dump(mode="json"),
        }

    @router.post("/runs/{run_id}/export", response_model=None)
    async def export_run(run_id: str) -> dict[str, Any]:
        with storage.transaction() as conn:
            _update_run_completion(conn, run_id)
            if _run_has_blocking_gates(conn, run_id):
                raise invalid(
                    "benchmark_run",
                    "This benchmark still has blocking quality gates on one or more attempts.",
                )
        paths = benchmarks.export_run_report(storage.data_dir, storage.conn, run_id)
        return {
            "json_path": str(paths.json_path),
            "md_path": str(paths.md_path),
            "lessons_path": str(paths.lessons_path),
        }

    return router
