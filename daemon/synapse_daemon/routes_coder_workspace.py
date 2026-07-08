"""REST routes for the chat-first coder workspace."""

from __future__ import annotations

import asyncio
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
from .ws import Event, EventBus


def _thread_detail(conn, thread_id: str) -> dict[str, Any]:
    return coder_workspace.thread_detail(conn, thread_id).model_dump(mode="json")


def _canonical_runtime_id(runtime_id: str | None) -> str:
    normalized = (runtime_id or "").strip().lower()
    if normalized in {"claude", "claude-code"}:
        return "claude"
    if normalized in {"codex", "openai-codex"}:
        return "codex"
    if normalized in {"copilot", "github-copilot"}:
        return "copilot"
    if normalized in {"python", "python-repl"}:
        return "python"
    if normalized in {"powershell", "shell", "bash", "zsh"}:
        return "shell"
    return "codex"


def _provider_for_runtime(runtime_id: str) -> str:
    return {
        "claude": "anthropic",
        "codex": "openai",
        "copilot": "github",
        "python": "local",
        "shell": "local",
    }.get(runtime_id, "openai")


def _model_for_runtime(runtime_id: str) -> str:
    return {
        "claude": "claude-code",
        "codex": "codex",
        "copilot": "copilot",
        "python": "python",
        "shell": "shell",
    }.get(runtime_id, runtime_id)


def _argv_for_runtime(runtime_id: str) -> list[str]:
    if runtime_id == "claude":
        return ["claude"]
    if runtime_id == "copilot":
        return ["copilot"]
    if runtime_id == "python":
        return ["python", "-i", "-q"]
    if runtime_id == "shell":
        return ["powershell.exe", "-NoLogo"]
    return ["codex"]


async def _write_prompt_to_session(session, prompt_md: str) -> None:  # noqa: ANN001
    prompt = prompt_md.strip()
    if not prompt:
        return
    # The major coder CLIs boot into a prompt-driven PTY. A short delay keeps
    # the first user instruction from racing the runtime banner on slower hosts.
    await asyncio.sleep(0.15)
    await session.write(prompt.encode("utf-8") + b"\r")


def _review_prompt(
    conn,
    thread: coder_workspace.CoderThread,
    review_pass: coder_workspace.CoderReviewPass,
) -> str:
    recent = coder_workspace.list_messages(conn, thread.id)[-10:]
    metadata = review_pass.metadata or {}
    review_kind = str(metadata.get("review_kind") or metadata.get("preset_id") or "general").strip().lower()
    reason = str(metadata.get("reason") or "").strip()
    focus_points = metadata.get("focus_points")
    focus_lines: list[str] = []
    if isinstance(focus_points, list):
        focus_lines = [str(item).strip() for item in focus_points if str(item).strip()]
    escalation_policy = str(metadata.get("escalation_policy") or "").strip()
    lines: list[str] = [
        "You are a sidecar reviewer for a Synapse coder thread.",
        f"Thread title: {thread.title}",
        f"Primary runtime: {thread.active_runtime_id or 'unknown'}",
        f"Review focus: {review_pass.title}",
    ]
    if review_kind:
        lines.append(f"Review kind: {review_kind}")
    if reason:
        lines.append(f"Why this pass ran: {reason}")
    if escalation_policy:
        lines.append(f"Escalation policy: {escalation_policy}")
    if focus_lines:
        lines.extend(["", "Focus points:"])
        lines.extend([f"- {item}" for item in focus_lines])
    if review_pass.summary_md.strip():
        lines.extend(["", "Review instructions:", review_pass.summary_md.strip()])
    lines.extend(["", "Recent thread messages:"])
    if recent:
        for message in recent:
            lines.append(f"- {message.role.value}: {message.content_md.strip()[:800]}")
    else:
        lines.append("- No prior messages yet.")
    lines.append("")
    if review_kind == "ux":
        lines.extend(
            [
                "Audit the interaction, hierarchy, responsiveness, clarity, and overall product feel.",
                "Flag provenance or originality risks if the thread used harvested references.",
                "Recommend the lightest next pass that would materially improve UX quality.",
            ]
        )
    elif review_kind == "qa":
        lines.extend(
            [
                "Hunt for bugs, regressions, missing tests, flaky assumptions, and verification gaps.",
                "Call out the concrete proof that is still missing before the main thread can claim done.",
            ]
        )
    elif review_kind in {"token-efficiency", "token_efficiency"}:
        lines.extend(
            [
                "Evaluate whether the current loop is spending more tokens than needed for the risk level.",
                "Suggest a cheaper next pass when quality can be preserved with tighter scope or targeted review.",
            ]
        )
    elif review_kind == "judge":
        lines.extend(
            [
                "Judge the current direction with explicit tradeoffs between quality, evidence, and token cost.",
                "State whether escalation to a stronger reviewer or multi-candidate bakeoff is justified.",
            ]
        )
    else:
        lines.extend(
            [
                "Please critique the direction, identify bugs or regressions, call out missing tests,",
                "and suggest the strongest next step for the main thread.",
            ]
        )
    return "\n".join(lines)


def build_coder_workspace_router(storage: Storage, pty_manager: PtySessionManager) -> APIRouter:
    router = APIRouter(tags=["coder-workspace"])

    @router.get("/coder-workspace/preferences", response_model=None)
    async def get_workspace_preferences() -> dict[str, Any]:
        return coder_workspace.get_preferences(storage.conn).model_dump(mode="json")

    @router.patch("/coder-workspace/preferences", response_model=None)
    async def patch_workspace_preferences(
        payload: coder_workspace.CoderWorkspacePreferencesUpdate,
    ) -> dict[str, Any]:
        with storage.transaction() as conn:
            preferences = coder_workspace.update_preferences(
                conn,
                advanced_terminal_enabled=payload.advanced_terminal_enabled,
                raw_pty_enabled=payload.raw_pty_enabled,
            )
        return preferences.model_dump(mode="json")

    @router.get("/projects/{project_id}/coder-threads", response_model=None)
    async def list_project_threads(project_id: str) -> dict[str, Any]:
        projects_module.get(storage.conn, project_id)
        return {
            "threads": [
                item.model_dump(mode="json") for item in coder_workspace.list_threads(storage.conn, project_id)
            ]
        }

    @router.post("/projects/{project_id}/coder-threads", response_model=None, status_code=201)
    async def create_project_thread(
        project_id: str, payload: coder_workspace.CoderThreadCreate
    ) -> dict[str, Any]:
        projects_module.get(storage.conn, project_id)
        with storage.transaction() as conn:
            thread = coder_workspace.create_thread(conn, project_id, payload)
        return thread.model_dump(mode="json")

    # Project-free "General" scope (Plan 2 Phase A). Registered BEFORE /coder-threads/{thread_id}
    # so the literal "general" path is not captured as a thread id.
    @router.get("/coder-threads/general", response_model=None)
    async def list_general_coder_threads() -> dict[str, Any]:
        return {
            "threads": [
                item.model_dump(mode="json") for item in coder_workspace.list_general_threads(storage.conn)
            ]
        }

    @router.post("/coder-threads/general", response_model=None, status_code=201)
    async def create_general_coder_thread(payload: coder_workspace.CoderThreadCreate) -> dict[str, Any]:
        # A "New chat" tied to no project -- the thread's project_id stays NULL.
        with storage.transaction() as conn:
            thread = coder_workspace.create_thread(conn, None, payload)
        return thread.model_dump(mode="json")

    @router.get("/coder-threads/{thread_id}", response_model=None)
    async def get_thread(thread_id: str) -> dict[str, Any]:
        return _thread_detail(storage.conn, thread_id)

    @router.patch("/coder-threads/{thread_id}", response_model=None)
    async def patch_thread(
        thread_id: str, payload: coder_workspace.CoderThreadUpdate
    ) -> dict[str, Any]:
        with storage.transaction() as conn:
            thread = coder_workspace.update_thread(conn, thread_id, payload)
        return thread.model_dump(mode="json")

    @router.delete("/coder-threads/{thread_id}", status_code=204, response_model=None)
    async def delete_thread(thread_id: str) -> None:
        with storage.transaction() as conn:
            coder_workspace.delete_thread(conn, thread_id)

    @router.get("/coder-threads/{thread_id}/messages", response_model=None)
    async def list_thread_messages(thread_id: str) -> dict[str, Any]:
        return {
            "messages": [
                item.model_dump(mode="json") for item in coder_workspace.list_messages(storage.conn, thread_id)
            ]
        }

    @router.post("/coder-threads/{thread_id}/messages", response_model=None, status_code=201)
    async def create_thread_message(
        thread_id: str, payload: coder_workspace.CoderMessageCreate
    ) -> dict[str, Any]:
        with storage.transaction() as conn:
            message = coder_workspace.add_message(conn, thread_id, payload)
        return message.model_dump(mode="json")

    @router.post("/coder-threads/{thread_id}/dispatch", response_model=None, status_code=201)
    async def dispatch_thread_message(
        thread_id: str, payload: coder_workspace.CoderDispatchMessageRequest
    ) -> dict[str, Any]:
        prompt = payload.content_md.strip()
        if not prompt:
            raise invalid("coder_thread", "Message cannot be empty.")
        thread = coder_workspace.get_thread(storage.conn, thread_id)
        project = projects_module.get(storage.conn, thread.project_id)
        runtime_id = _canonical_runtime_id(payload.runtime_id or thread.active_runtime_id)
        provider = payload.provider or thread.active_provider or _provider_for_runtime(runtime_id)
        model = payload.model or thread.active_model or _model_for_runtime(runtime_id)
        argv = _argv_for_runtime(runtime_id)
        with storage.transaction() as conn:
            if (
                runtime_id != _canonical_runtime_id(thread.active_runtime_id)
                or provider != (thread.active_provider or _provider_for_runtime(runtime_id))
                or model != (thread.active_model or _model_for_runtime(runtime_id))
            ):
                coder_workspace.switch_runtime(
                    conn,
                    thread_id,
                    coder_workspace.CoderRuntimeSwitchRequest(
                        runtime_id=runtime_id,
                        provider=provider,
                        model=model,
                        reason="dispatch",
                    ),
                )
            message = coder_workspace.add_message(
                conn,
                thread_id,
                coder_workspace.CoderMessageCreate(
                    role=coder_workspace.CoderMessageRole.USER,
                    content_md=prompt,
                    runtime_id=runtime_id,
                    provider=provider,
                    model=model,
                    metadata=payload.metadata,
                ),
            )
            run_record = coder_workspace.create_run(
                conn,
                coder_workspace.CoderRunCreate(
                    thread_id=thread_id,
                    message_id=message.id,
                    runtime_id=runtime_id,
                    provider=provider,
                    model=model,
                    surface_kind="coder-thread-dispatch",
                    surface_profile_version="v1",
                    project_id=project.id,
                    workspace_context_mode=payload.workspace_context_mode
                    or thread.workspace_context_mode,
                    attachments_count=len(files_storage.list_for_project(conn, project.id)),
                    workspace_overhead_bytes=len(prompt.encode("utf-8")),
                    metadata={"argv": argv, **payload.metadata},
                ),
            )
            coder_workspace.attach_run_to_message(conn, message.id, run_record.id)
        session = await pty_manager.spawn(argv=argv, cwd=project.path, project_id=project.id)
        with storage.transaction() as conn:
            run_record = coder_workspace.update_run_session(conn, run_record.id, session.session_id)
        await _write_prompt_to_session(session, prompt)
        return {
            "thread_id": thread_id,
            "message": message.model_dump(mode="json"),
            "run": run_record.model_dump(mode="json"),
            "session": session.summary().__dict__,
            "detail": _thread_detail(storage.conn, thread_id),
        }

    @router.post("/coder-threads/{thread_id}/runtime", response_model=None)
    async def switch_thread_runtime(
        thread_id: str, payload: coder_workspace.CoderRuntimeSwitchRequest
    ) -> dict[str, Any]:
        with storage.transaction() as conn:
            switch = coder_workspace.switch_runtime(conn, thread_id, payload)
            thread = coder_workspace.get_thread(conn, thread_id)
        return {"thread": thread.model_dump(mode="json"), "switch": switch.model_dump(mode="json")}

    @router.post("/coder-threads/{thread_id}/review-passes", response_model=None, status_code=201)
    async def create_review_pass(
        thread_id: str, payload: coder_workspace.CoderReviewPassCreate
    ) -> dict[str, Any]:
        with storage.transaction() as conn:
            review_pass = coder_workspace.create_review_pass(conn, thread_id, payload)
        return review_pass.model_dump(mode="json")

    @router.post("/coder-review-passes/{review_pass_id}/verdict", response_model=None)
    async def publish_review_pass_verdict(
        review_pass_id: str,
        payload: coder_workspace.CoderReviewPassVerdictRequest,
    ) -> dict[str, Any]:
        with storage.transaction() as conn:
            updated = coder_workspace.update_review_pass_verdict(conn, review_pass_id, payload)
            gate = None
            if payload.verdict.blocking:
                gate = quality_os.create_gate(
                    conn,
                    quality_os.QualityGateCreate(
                        subject_type="coder_review_pass",
                        subject_id=review_pass_id,
                        gate_kind="ui-review",
                        title=payload.summary_md or updated.title or "Blocking review findings",
                        blocking=True,
                        required_evidence=["review-verdict"],
                        linked_surface_ids=payload.verdict.surface_ids,
                        linked_contract_ids=payload.verdict.contract_ids,
                        audit_details={
                            "severity": payload.verdict.severity.value,
                            "recommended_next_step": payload.verdict.recommended_next_step,
                        },
                    ),
                )
            else:
                for existing in quality_os.list_gates(
                    conn,
                    subject_type="coder_review_pass",
                    subject_id=review_pass_id,
                    status=quality_os.QualityGateStatus.OPEN,
                ):
                    if existing.gate_kind == "ui-review":
                        quality_os.resolve_gate(
                            conn,
                            existing.id,
                            quality_os.QualityGateResolveRequest(
                                status=quality_os.QualityGateStatus.PASSED,
                                resolved_by="review-verdict",
                                note=payload.summary_md or "Structured review verdict cleared the review gate.",
                            ),
                        )
            thread_id = updated.thread_id
        return {
            "review_pass": updated.model_dump(mode="json"),
            "gate": gate.model_dump(mode="json") if gate else None,
            "detail": _thread_detail(storage.conn, thread_id),
        }

    @router.post(
        "/coder-threads/{thread_id}/review-passes/{review_pass_id}/launch",
        response_model=None,
    )
    async def launch_review_pass(
        thread_id: str,
        review_pass_id: str,
        payload: coder_workspace.CoderLaunchReviewPassRequest | None = None,
    ) -> dict[str, Any]:
        body = payload or coder_workspace.CoderLaunchReviewPassRequest()
        thread = coder_workspace.get_thread(storage.conn, thread_id)
        review_pass = coder_workspace.get_review_pass(storage.conn, review_pass_id)
        if review_pass.thread_id != thread_id:
            raise invalid("coder_review_pass", "Review pass does not belong to this thread.")
        project = projects_module.get(storage.conn, thread.project_id)
        runtime_id = _canonical_runtime_id(
            body.runtime_id or review_pass.requested_runtime_id or thread.active_runtime_id
        )
        provider = (
            body.provider
            or review_pass.requested_provider
            or thread.active_provider
            or _provider_for_runtime(runtime_id)
        )
        model = (
            body.model
            or review_pass.requested_model
            or thread.active_model
            or _model_for_runtime(runtime_id)
        )
        argv = _argv_for_runtime(runtime_id)
        prompt_md = body.prompt_md or _review_prompt(storage.conn, thread, review_pass)
        with storage.transaction() as conn:
            run_record = coder_workspace.create_run(
                conn,
                coder_workspace.CoderRunCreate(
                    thread_id=thread_id,
                    review_pass_id=review_pass_id,
                    runtime_id=runtime_id,
                    provider=provider,
                    model=model,
                    surface_kind="coder-review-pass",
                    surface_profile_version="v1",
                    project_id=project.id,
                    workspace_context_mode=thread.workspace_context_mode,
                    attachments_count=len(files_storage.list_for_project(conn, project.id)),
                    workspace_overhead_bytes=len(prompt_md.encode("utf-8")),
                    metadata={"argv": argv, **body.metadata},
                ),
            )
            coder_workspace.attach_run_to_review_pass(conn, review_pass_id, run_record.id)
        session = await pty_manager.spawn(argv=argv, cwd=project.path, project_id=project.id)
        with storage.transaction() as conn:
            run_record = coder_workspace.update_run_session(conn, run_record.id, session.session_id)
        await _write_prompt_to_session(session, prompt_md)
        return {
            "thread_id": thread_id,
            "review_pass_id": review_pass_id,
            "run": run_record.model_dump(mode="json"),
            "session": session.summary().__dict__,
            "detail": _thread_detail(storage.conn, thread_id),
        }

    @router.get("/coder-threads/{thread_id}/context", response_model=None)
    async def get_thread_context(thread_id: str) -> dict[str, Any]:
        thread = coder_workspace.get_thread(storage.conn, thread_id)
        files = files_storage.list_for_project(storage.conn, thread.project_id)
        records = project_records.get_records(storage.conn, thread.project_id)
        context = coder_workspace.CoderWorkspaceContext(
            thread=thread,
            recent_messages=coder_workspace.list_messages(storage.conn, thread_id)[-25:],
            review_passes=coder_workspace.list_review_passes(storage.conn, thread_id)[:10],
            linked_runs=coder_workspace.list_runs_for_thread(storage.conn, thread_id)[:10],
            files_count=len(files),
            recent_file_ids=[item.id for item in files[:10]],
            records_summary={
                "adrs": len(records.adrs),
                "backlog": len(records.backlog),
                "versions": len(records.versions),
            },
            available_actions=[
                "send-message",
                "dispatch-message",
                "switch-runtime",
                "start-review-pass",
                "launch-review-pass",
                "open-advanced-terminal",
            ],
            preferences=coder_workspace.get_preferences(storage.conn),
        )
        return context.model_dump(mode="json")

    return router


def subscribe_coder_workspace_events(storage: Storage, bus: EventBus) -> None:
    """Mirror PTY lifecycle into linked coder runs and benchmark attempts."""

    async def _on_input(event: Event) -> None:
        if event.name != "v1.pty.session_input":
            return
        payload = event.payload
        session_id = str(payload.get("session_id") or "")
        if not session_id:
            return
        with storage.transaction() as conn:
            run = coder_workspace.record_run_input(conn, session_id)
            if run is not None:
                benchmarks.sync_attempt_from_coder_run(conn, run)

    async def _on_output(event: Event) -> None:
        if event.name != "v1.pty.session_output":
            return
        payload = event.payload
        session_id = str(payload.get("session_id") or "")
        if not session_id:
            return
        with storage.transaction() as conn:
            run = coder_workspace.record_run_output(conn, session_id)
            if run is not None:
                benchmarks.sync_attempt_from_coder_run(conn, run)

    async def _on_exit(event: Event) -> None:
        if event.name != "v1.pty.session_exited":
            return
        payload = event.payload
        session_id = str(payload.get("session_id") or "")
        if not session_id:
            return
        exit_code = payload.get("exit_code")
        with storage.transaction() as conn:
            run = coder_workspace.finish_run(conn, session_id, exit_code=exit_code)
            if run is not None:
                benchmarks.sync_attempt_from_coder_run(conn, run)

    # build_app() is synchronous; subscribe directly before the app starts
    # serving so we do not need an async startup hop just to register these.
    bus._subscribers.add(_on_input)  # type: ignore[attr-defined]
    bus._subscribers.add(_on_output)  # type: ignore[attr-defined]
    bus._subscribers.add(_on_exit)  # type: ignore[attr-defined]
