"""REST routes for Sessions-centric AI squads."""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any, Callable

from fastapi import APIRouter, Request

from . import activity as activity_module
from . import agent_squads as squads
from . import coder_runtimes
from . import ai_executions
from . import coordination
from . import mcp_servers as mcp_servers_module
from . import personalities as personalities_module
from . import projects as projects_module
from . import quality_os
from .agent_squads import (
    AgentRoleTemplateCreate,
    AgentRoleTemplateUpdate,
    AgentSquadCreate,
    AgentSquadUpdate,
    AgentWorkItemCreate,
    AgentWorkItemDelegateRequest,
    AgentWorkItemHandoffRequest,
    AgentWorkItemLaunchRequest,
    AgentWorkItemStatusRequest,
)
from .ai_context_memory import (
    AI_CONTEXT_DIRECTION_PROMPT,
    ai_context_path,
    append_work_item_handoff,
    ensure_ai_context_file,
    write_role_prompt,
)
from .api_versions import event_name
from .auth import AuthManager
from .audit import AuditRecord, audit
from . import token_ledger
from .errors import SynapseError, conflict, invalid
from .pty_sessions import PtySessionManager
from .storage import Storage
from .ws import Event, EventBus

log = logging.getLogger(__name__)


def _write_mcp_config(storage: Storage, role=None) -> Path | None:
    """Generate a Claude ``--mcp-config`` file from the user's enabled MCP
    servers (ADR-0017 MW2), scoped to the role's binding (ADR-0025): a role's
    ``mcp_server_ids`` of None -> all enabled; [] -> none; [ids] -> only those.
    Returns the path, or None if there's nothing to wire in. Lives in the data
    dir (project's own ``.mcp.json`` untouched); the filename is keyed by role
    so different roles don't clobber each other's config."""
    servers = [s for s in mcp_servers_module.list_servers(storage.conn) if s.enabled]
    allow_ids = role.mcp_server_ids if role is not None else None
    config = mcp_servers_module.build_mcp_config(servers, allow_ids)
    if not config.get("mcpServers"):
        return None
    slug = role.id if role is not None else "all"
    path = (storage.data_dir / "mcp" / f"claude-mcp-{slug}.json").resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config, indent=2), encoding="utf-8")
    return path


def _write_copilot_mcp_config(storage: Storage, role=None) -> tuple[Path | None, dict[str, str]]:
    """Generate a session-only Copilot CLI MCP file with env references only."""
    servers = mcp_servers_module.list_servers(storage.conn)
    allow_ids = role.mcp_server_ids if role is not None else None
    config, worker_env = mcp_servers_module.build_copilot_mcp_config(servers, allow_ids)
    if not config.get("mcpServers"):
        return None, worker_env
    slug = role.id if role is not None else "all"
    path = (storage.data_dir / "mcp" / f"copilot-mcp-{slug}.json").resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config, indent=2), encoding="utf-8")
    return path, worker_env


# File-mutating tools withheld from a Claude OBSERVE worker. Space-separated in a
# single argument because `--disallowedTools` is variadic -- passing them as separate
# argv entries risks the parser swallowing the flag that follows.
_CLAUDE_OBSERVE_DENIED_TOOLS = "Write Edit NotebookEdit"


def _automatic_worker_argv(
    argv: list[str],
    *,
    runtime: str,
    authority: squads.AgentExecutionAuthority,
    prompt_file: Path,
) -> list[str]:
    """Translate one task-scoped automatic launch into each supported CLI.

    Interactive remains the default. Callers must opt into this path and name the authority
    boundary; the resulting process immediately executes the daemon-authored role prompt
    instead of opening an idle TUI.

    The per-CLI flags now live in ``coder_runtimes`` because the blueprint builder needs the
    same translation to drive a runtime headlessly. Each of those flags was learned from a
    real failure - a worker that sat forever on an interactive prompt, or one that refused
    to file its own findings - and two copies of that knowledge is one too many.
    """
    prompt = (
        f"Read the complete instructions in {prompt_file}, perform that work now, "
        "and finish by POSTing an explicit handoff to the Synapse work-item handoff endpoint. "
        "Do not wait for more user input."
    )
    try:
        return coder_runtimes.headless_argv(
            argv, runtime=runtime, authority=authority, prompt=prompt
        )
    except ValueError:
        raise invalid(
            "agent_work_item",
            "Automatic execution is supported only for Claude, Codex, GitHub Copilot, "
            "and Gemini workers.",
        )


class WorkerTimeoutRegistry:
    """Own automatic-worker deadline tasks until exit, stop, or shutdown."""

    def __init__(self) -> None:
        self._tasks: dict[str, asyncio.Task[None]] = {}

    def track(self, work_item_id: str, task: asyncio.Task[None]) -> None:
        self.cancel(work_item_id)
        self._tasks[work_item_id] = task

        def _discard(completed: asyncio.Task[None]) -> None:
            if self._tasks.get(work_item_id) is completed:
                self._tasks.pop(work_item_id, None)
            if completed.cancelled():
                return
            error = completed.exception()
            if error is not None:
                log.error(
                    "Automatic worker timeout task failed for %s: %s",
                    work_item_id,
                    error,
                    exc_info=(type(error), error, error.__traceback__),
                )

        task.add_done_callback(_discard)

    def cancel(self, work_item_id: str) -> None:
        task = self._tasks.pop(work_item_id, None)
        if task is not None and task is not asyncio.current_task():
            task.cancel()

    def cancel_all(self) -> None:
        for work_item_id in list(self._tasks):
            self.cancel(work_item_id)

    @property
    def active_count(self) -> int:
        return len(self._tasks)


class WorkerPresenceRegistry:
    """Own daemon heartbeats for every automatically launched worker PTY."""

    def __init__(self) -> None:
        self._tasks: dict[str, asyncio.Task[None]] = {}

    def track(self, work_item_id: str, task: asyncio.Task[None]) -> None:
        self.cancel(work_item_id)
        self._tasks[work_item_id] = task

        def _discard(completed: asyncio.Task[None]) -> None:
            if self._tasks.get(work_item_id) is completed:
                self._tasks.pop(work_item_id, None)
            if completed.cancelled():
                return
            error = completed.exception()
            if error is not None:
                log.error(
                    "Automatic worker presence task failed for %s: %s",
                    work_item_id,
                    error,
                    exc_info=(type(error), error, error.__traceback__),
                )

        task.add_done_callback(_discard)

    def cancel(self, work_item_id: str) -> None:
        task = self._tasks.pop(work_item_id, None)
        if task is not None and task is not asyncio.current_task():
            task.cancel()

    def cancel_all(self) -> None:
        for work_item_id in list(self._tasks):
            self.cancel(work_item_id)

    @property
    def active_count(self) -> int:
        return len(self._tasks)


async def _maintain_worker_presence(
    storage: Storage,
    manager: PtySessionManager,
    bus: EventBus,
    *,
    coordination_session_id: str,
    pty_session_id: str,
    interval_seconds: float = 30.0,
) -> None:
    """Keep a worker green while its daemon-owned PTY is still running.

    Worker CLIs can spend minutes inside one tool call and cannot be trusted to
    call the coordination heartbeat endpoint on Synapse's schedule. Because
    the daemon owns the process, it also owns this liveness signal. A finalized
    or missing PTY ends the loop; the normal finalizer then marks the presence
    row gone and revokes its scoped credential.
    """

    while True:
        session = manager.get(pty_session_id)
        if session is None or session.exit_code is not None:
            return
        with storage.transaction() as conn:
            updated = coordination.heartbeat_session(
                conn,
                coordination_session_id,
                coordination.AgentSessionHeartbeat(),
            )
        await bus.publish(
            event_name("coordination", "session_heartbeat"),
            {"session": updated.model_dump(mode="json")},
        )
        await asyncio.sleep(interval_seconds)


async def _close_worker_at_timeout(
    storage: Storage,
    manager: PtySessionManager,
    bus: EventBus,
    *,
    work_item_id: str,
    session_id: str,
    timeout_seconds: int,
) -> squads.AgentWorkItem | None:
    """Close a still-live worker at its deadline, preserving truthful work state."""

    session = manager.get(session_id)
    if session is None or session.exit_code is not None:
        return None
    status_changed = False
    with storage.transaction() as conn:
        current = squads.get_work_item(conn, work_item_id)
        if current.status == squads.AgentWorkItemStatus.RUNNING:
            updated = squads.block_running_work_item(
                conn,
                work_item_id,
                f"Automatic worker timed out after {timeout_seconds} seconds and was stopped.",
            )
            status_changed = True
        else:
            # A handoff describes work state, not process state. A worker that
            # handed off but failed to exit still loses its process at the same
            # deadline; its evidence-backed status remains intact.
            updated = current
        ai_executions.finalize_pty_execution(
            conn,
            pty_session_id=session_id,
            output=(session.scrollback_bytes() if hasattr(session, "scrollback_bytes") else b""),
            exit_code=None,
            work_outcome=updated.status.value,
            process_outcome_override="timed_out",
        )
        audit(
            conn,
            AuditRecord(
                entity_type="agent_work_item",
                entity_id=work_item_id,
                action="timeout",
                source=squads.AuditSource.AUTO,
                result="error",
                error_code="agent_work_item.timeout",
                details={
                    "session_id": session_id,
                    "timeout_seconds": timeout_seconds,
                    "work_status_preserved": not status_changed,
                    "work_status": updated.status.value,
                },
            ),
        )
    if status_changed:
        await bus.publish(
            event_name("agent_work_item", "updated"),
            {"work_item": updated.model_dump(mode="json")},
        )
    await manager.close(session_id)
    return updated


def build_agent_squads_router(
    storage: Storage,
    manager: PtySessionManager,
    bus: EventBus,
    auth: AuthManager,
    api_base: Callable[[], str],
    timeout_registry: WorkerTimeoutRegistry,
    presence_registry: WorkerPresenceRegistry,
) -> APIRouter:
    router = APIRouter(tags=["agent-squads"])
    # Storage currently owns one SQLite connection. Serializing the short
    # launch reservation/spawn/finalization flow preserves the squad cap while
    # still releasing the DB transaction before the awaited PTY spawn. Other
    # endpoints (including heartbeats) remain free to transact during spawn.
    launch_lock = asyncio.Lock()

    async def _enforce_worker_timeout(
        *,
        work_item_id: str,
        session_id: str,
        timeout_seconds: int,
    ) -> None:
        await asyncio.sleep(timeout_seconds)
        await _close_worker_at_timeout(
            storage,
            manager,
            bus,
            work_item_id=work_item_id,
            session_id=session_id,
            timeout_seconds=timeout_seconds,
        )

    @router.get("/agent-role-templates", response_model=None)
    async def list_role_templates() -> dict[str, Any]:
        return {
            "templates": [
                role.model_dump(mode="json")
                for role in squads.list_role_templates(storage.conn)
            ]
        }

    @router.post("/agent-role-templates", response_model=None, status_code=201)
    async def create_role_template(payload: AgentRoleTemplateCreate) -> dict[str, Any]:
        with storage.transaction() as conn:
            role = squads.create_role_template(conn, payload)
            audit(
                conn,
                AuditRecord(
                    entity_type="agent_role_template",
                    entity_id=role.id,
                    action="create",
                    source=AuditSourceFromPayload(payload),
                    result="success",
                    details={"name": role.name},
                ),
            )
        return role.model_dump(mode="json")

    @router.patch("/agent-role-templates/{role_id}", response_model=None)
    async def patch_role_template(
        role_id: str, payload: AgentRoleTemplateUpdate
    ) -> dict[str, Any]:
        with storage.transaction() as conn:
            role = squads.update_role_template(conn, role_id, payload)
            audit(
                conn,
                AuditRecord(
                    entity_type="agent_role_template",
                    entity_id=role_id,
                    action="update",
                    source=squads.AuditSource.DESKTOP,
                    result="success",
                    details={"name": role.name},
                ),
            )
        await _publish_role_templates_updated(bus, storage)
        return role.model_dump(mode="json")

    @router.delete("/agent-role-templates/{role_id}", status_code=204, response_model=None)
    async def delete_role_template(role_id: str) -> None:
        with storage.transaction() as conn:
            squads.delete_role_template(conn, role_id)
            audit(
                conn,
                AuditRecord(
                    entity_type="agent_role_template",
                    entity_id=role_id,
                    action="delete",
                    source=squads.AuditSource.DESKTOP,
                    result="success",
                ),
            )
        await _publish_role_templates_updated(bus, storage)

    @router.get("/agent-squads", response_model=None)
    async def list_squads() -> dict[str, Any]:
        return {
            "squads": [
                squad.model_dump(mode="json")
                for squad in squads.list_squads(storage.conn)
            ]
        }

    @router.post("/agent-squads", response_model=None, status_code=201)
    async def create_squad(payload: AgentSquadCreate, request: Request) -> dict[str, Any]:
        projects_module.get(storage.conn, payload.project_id)
        if payload.lead_role_id is not None:
            squads.get_role_template(storage.conn, payload.lead_role_id)
        with storage.transaction() as conn:
            squad = squads.create_squad(conn, payload)
            ensure_ai_context_file(storage.data_dir, squad.project_id, projects_module.get(conn, squad.project_id).name)
            audit(
                conn,
                AuditRecord(
                    entity_type="agent_squad",
                    entity_id=squad.id,
                    action="create",
                    source=payload.source,
                    result="success",
                    details={"project_id": squad.project_id, "name": squad.name},
                ),
            )
        await bus.publish(
            event_name("agent_squad", "created"),
            {
                "squad": squad.model_dump(mode="json"),
                "session_id": request.headers.get("X-Synapse-Session"),
            },
        )
        return squad.model_dump(mode="json")

    @router.get("/agent-squads/{squad_id}", response_model=None)
    async def get_squad_detail(squad_id: str) -> dict[str, Any]:
        detail = squads.squad_detail(storage.conn, squad_id)
        return detail.model_dump(mode="json")

    @router.get("/agent-squads/{squad_id}/capacity", response_model=None)
    async def get_squad_capacity(squad_id: str) -> dict[str, Any]:
        # "Can I launch another worker?" -- the same concurrency-cap + token-budget gates the launch
        # path enforces, surfaced so an AI/UI can check headroom before delegating (0 = unlimited).
        squad = squads.get_squad(storage.conn, squad_id)
        running = squads.count_running_work_items(storage.conn, squad_id)
        spent = token_ledger.sum_squad_tokens(storage.conn, squad_id).total_tokens
        concurrency_ok = not squad.max_concurrent or running < squad.max_concurrent
        budget_ok = not squad.token_budget or spent < squad.token_budget
        return {
            "squad_id": squad.id,
            "running": running,
            "max_concurrent": squad.max_concurrent,
            "concurrency_available": max(0, squad.max_concurrent - running) if squad.max_concurrent else None,
            "tokens_spent": spent,
            "token_budget": squad.token_budget,
            "tokens_remaining": max(0, squad.token_budget - spent) if squad.token_budget else None,
            "can_launch": concurrency_ok and budget_ok,
        }

    @router.patch("/agent-squads/{squad_id}", response_model=None)
    async def patch_squad(squad_id: str, payload: AgentSquadUpdate) -> dict[str, Any]:
        with storage.transaction() as conn:
            squad = squads.update_squad(conn, squad_id, payload)
            audit(
                conn,
                AuditRecord(
                    entity_type="agent_squad",
                    entity_id=squad_id,
                    action="update",
                    source=payload.source,
                    result="success",
                    details={"status": squad.status.value, "lead_role_id": squad.lead_role_id},
                ),
            )
        await bus.publish(event_name("agent_squad", "updated"), {"squad": squad.model_dump(mode="json")})
        return squad.model_dump(mode="json")

    @router.delete("/agent-squads/{squad_id}", status_code=204, response_model=None)
    async def delete_squad(squad_id: str) -> None:
        with storage.transaction() as conn:
            squads.delete_squad(conn, squad_id)
            audit(
                conn,
                AuditRecord(
                    entity_type="agent_squad",
                    entity_id=squad_id,
                    action="delete",
                    source=squads.AuditSource.DESKTOP,
                    result="success",
                ),
            )

    @router.post("/agent-squads/{squad_id}/stop", response_model=None)
    async def stop_squad(squad_id: str) -> dict[str, Any]:
        # Kill switch: close every live PTY session owned by this squad's work
        # items, then deterministically finalize those work items. We do NOT
        # rely solely on the async pty.session_finalized event -- a forced close
        # must leave the queue in a clean, non-running state the instant this
        # returns, even if event delivery is delayed. Re-running the finalize is
        # idempotent (it only transitions items still in RUNNING).
        squad = squads.get_squad(storage.conn, squad_id)
        items = squads.list_work_items(storage.conn, squad_id)
        live_items = [
            item
            for item in items
            if item.pty_session_id and manager.get(item.pty_session_id) is not None
        ]
        # Block before termination. PTY finalization is asynchronous and may
        # otherwise win the race and convert a killed process into "completed".
        with storage.transaction() as conn:
            for item in live_items:
                squads.block_running_work_item(
                    conn,
                    item.id,
                    "Stopped by the operator through the squad kill switch.",
                )
        closed: list[tuple[str, str]] = []  # (work_item_id, session_id)
        for item in items:
            if not item.pty_session_id:
                continue
            timeout_registry.cancel(item.id)
            presence_registry.cancel(item.id)
            if await manager.close(item.pty_session_id):
                closed.append((item.id, item.pty_session_id))
        with storage.transaction() as conn:
            for _wid, session_id in closed:
                squads.complete_work_item_from_session_exit(
                    conn, session_id=session_id, exit_code=-1
                )
            squad = squads.update_squad(
                conn,
                squad_id,
                squads.AgentSquadUpdate(
                    status=squads.AgentSquadStatus.PAUSED,
                    source=squads.AuditSource.AUTO,
                ),
            )
            audit(
                conn,
                AuditRecord(
                    entity_type="agent_squad",
                    entity_id=squad_id,
                    action="stop",
                    source=squads.AuditSource.DESKTOP,
                    result="success",
                    details={"stopped_sessions": len(closed)},
                ),
            )
        for work_item_id, _session_id in closed:
            updated = squads.get_work_item(storage.conn, work_item_id)
            await bus.publish(
                event_name("agent_work_item", "updated"),
                {"work_item": updated.model_dump(mode="json")},
            )
        await bus.publish(
            event_name("agent_squad", "updated"),
            {"squad": squad.model_dump(mode="json"), "stopped_sessions": len(closed)},
        )
        return {
            "squad_id": squad_id,
            "status": squad.status.value,
            "stopped_sessions": len(closed),
            "work_item_ids": [wid for wid, _ in closed],
        }

    @router.get("/agent-squads/{squad_id}/work-items", response_model=None)
    async def list_squad_work_items(squad_id: str) -> dict[str, Any]:
        # Keep this focused list route alongside the richer squad-detail route.
        # Workers commonly know their squad id and need a small, discoverable way
        # to inspect siblings without fetching role-template metadata too.
        squads.get_squad(storage.conn, squad_id)
        return {
            "work_items": [
                item.model_dump(mode="json")
                for item in squads.list_work_items(storage.conn, squad_id)
            ]
        }

    @router.post("/agent-squads/{squad_id}/work-items", response_model=None, status_code=201)
    async def create_work_item(
        squad_id: str, payload: AgentWorkItemCreate, request: Request
    ) -> dict[str, Any]:
        if payload.assigned_role_id:
            squads.get_role_template(storage.conn, payload.assigned_role_id)
        if payload.parent_id:
            squads.get_work_item(storage.conn, payload.parent_id)
        with storage.transaction() as conn:
            item = squads.create_work_item(conn, squad_id, payload)
            audit(
                conn,
                AuditRecord(
                    entity_type="agent_work_item",
                    entity_id=item.id,
                    action="create",
                    source=payload.source,
                    result="success",
                    details={"squad_id": squad_id, "assigned_role_id": item.assigned_role_id},
                ),
            )
        await bus.publish(
            event_name("agent_work_item", "created"),
            {
                "work_item": item.model_dump(mode="json"),
                "session_id": request.headers.get("X-Synapse-Session"),
            },
        )
        return item.model_dump(mode="json")

    async def _do_launch_serialized(
        work_item_id: str, body: AgentWorkItemLaunchRequest
    ) -> dict[str, Any]:
        with storage.transaction() as conn:
            work_item = squads.get_work_item(conn, work_item_id)
            squad = squads.get_squad(conn, work_item.squad_id)
            # Concurrency cap (safety, ADR-0025): don't let a squad exceed its
            # running-worker limit -- an autonomous boss could otherwise thrash the
            # machine. 0 = no cap; relaunching an already-running item is exempt.
            if squad.max_concurrent and work_item.status != squads.AgentWorkItemStatus.RUNNING:
                running = squads.count_running_work_items(conn, squad.id)
                if running >= squad.max_concurrent:
                    raise conflict(
                        "agent_squad",
                        f"Squad concurrency cap reached ({running}/{squad.max_concurrent} workers running).",
                        squad_id=squad.id,
                        running=running,
                        max_concurrent=squad.max_concurrent,
                    )
            # Token budget (safety, ADR-0025): refuse new workers once the squad's
            # recorded token spend reaches its budget. 0 = no budget.
            if squad.token_budget and work_item.status != squads.AgentWorkItemStatus.RUNNING:
                spent = token_ledger.sum_squad_tokens(conn, squad.id).total_tokens
                if spent >= squad.token_budget:
                    raise conflict(
                        "agent_squad",
                        f"Squad token budget exhausted ({spent}/{squad.token_budget} tokens).",
                        squad_id=squad.id,
                        spent=spent,
                        token_budget=squad.token_budget,
                    )
            project = projects_module.get(conn, squad.project_id)
            role = squads.get_role_template(conn, work_item.assigned_role_id or squad.lead_role_id or "planner")
            # An explicit request always wins; absent that, a role can opt its workers into
            # automatic by default (ADR-0025 follow-up) -- interactive if neither says
            # otherwise, exactly today's behavior.
            execution_mode = (
                body.execution_mode or role.default_execution_mode
                or squads.AgentExecutionMode.INTERACTIVE
            )
            # Layer in the worker's personality (ADR-0018 MW3) so two same-role
            # workers differ. A deleted/missing personality must not block launch.
            personality = None
            if work_item.personality_id:
                try:
                    personality = personalities_module.get_personality(conn, work_item.personality_id)
                except Exception:
                    personality = None
            explicitly_requested = body.preferred_runtime or work_item.preferred_runtime
            chosen_runtime = squads.pick_runtime(role, explicitly_requested)
            capacity = {
                item.runtime_id: item
                for item in ai_executions.list_capacity(conn)
            }
            if explicitly_requested is None:
                candidates = role.preferred_runtimes or [chosen_runtime]
                chosen_runtime = next(
                    (
                        candidate
                        for candidate in candidates
                        if candidate in {runtime.value for runtime in coder_runtimes.CoderRuntime}
                        and capacity.get(candidate) is not None
                        and capacity[candidate].eligible_for_attempt
                    ),
                    chosen_runtime,
                )
            selected_capacity = capacity.get(chosen_runtime)
            if selected_capacity is not None and not selected_capacity.eligible_for_attempt:
                raise conflict(
                    "agent_runtime",
                    f"{chosen_runtime.title()} is not currently usable: {selected_capacity.state.value}.",
                    runtime_id=chosen_runtime,
                    capacity_state=selected_capacity.state.value,
                    reason_code=selected_capacity.reason_code,
                    detail=selected_capacity.detail,
                    evidence_at=(
                        selected_capacity.evidence_at.isoformat()
                        if selected_capacity.evidence_at else None
                    ),
                )
            argv = squads.argv_for_runtime(chosen_runtime)
            runtime_mcp_env: dict[str, str] = {}
            installed_mcp_servers = mcp_servers_module.list_servers(storage.conn)
            allowed_mcp_ids = None if role.mcp_server_ids is None else set(role.mcp_server_ids)
            attached_mcp_server_ids = [
                server.id
                for server in installed_mcp_servers
                if server.enabled and (allowed_mcp_ids is None or server.id in allowed_mcp_ids)
            ]
            # Wire the role's enabled MCP servers into either supported runtime.
            # Claude receives an additive file; Codex receives one-launch config
            # overrides plus inherited env names, so secrets never enter argv.
            if chosen_runtime == "claude":
                mcp_config_path = _write_mcp_config(storage, role)
                if mcp_config_path is not None:
                    argv = [*argv, "--mcp-config", str(mcp_config_path)]
            elif chosen_runtime == "codex":
                mcp_argv, runtime_mcp_env = mcp_servers_module.build_codex_mcp_overrides(
                    installed_mcp_servers,
                    role.mcp_server_ids,
                )
                argv = [*argv, *mcp_argv]
            elif chosen_runtime == "copilot":
                mcp_config_path, runtime_mcp_env = _write_copilot_mcp_config(storage, role)
                if mcp_config_path is not None:
                    argv = [*argv, f"--additional-mcp-config=@{mcp_config_path}"]
            session_id = squads._new_id()
            prompt_file = write_role_prompt(
                data_dir=storage.data_dir,
                project_id=project.id,
                project_name=project.name,
                squad_name=squad.name,
                squad_goal_md=squad.goal_md,
                work_item_title=work_item.title,
                instructions_md=work_item.instructions_md,
                role_name=role.name,
                role_description=role.description,
                prompt_preamble_md=role.prompt_preamble_md,
                personality_name=personality.name if personality else None,
                personality_preamble_md=personality.prompt_preamble_md if personality else "",
                context_mode=role.context_mode.value,
                handoff_summary_md=work_item.summary_md,
                handoff_blockers_md=work_item.blockers_md,
                files_touched=work_item.files_touched,
            ).resolve()
            lead_session_id = squads.lead_session_id_for_squad(conn, squad.id)
            # Nest this worker under the main AI that created the squad, so it shows up
            # inside that session instead of as another top-level row. The owner link is
            # already durable: the squad-created receipt carries the caller's
            # X-Synapse-Session (activity._owner_session_id_for_squad).
            parent_session_id = activity_module._owner_session_id_for_squad(conn, squad.id)
            coordination_session = coordination.register_session(
                conn,
                coordination.AgentSessionRegister(
                    project_id=project.id,
                    runtime_id=chosen_runtime,
                    agent_label=f"{chosen_runtime.title()} · {role.name}",
                    coder_thread_id=session_id,
                    task=work_item.title,
                    last_intent=f"Starting {work_item.title}",
                    parent_session_id=parent_session_id,
                ),
            )
            worker_credential = coordination.issue_session_credential(
                conn,
                coordination_session.id,
                authority=body.authority.value,
                ttl_seconds=(
                    body.timeout_seconds + 300
                    if execution_mode == squads.AgentExecutionMode.AUTOMATIC
                    else 86_400
                ),
                work_item_id=work_item.id,
                squad_id=squad.id,
            )
            env = {str(key): str(value) for key, value in (body.env or {}).items()}
            env.update(runtime_mcp_env)
            # Daemon-owned coordination and identity values are a trust
            # boundary. Caller and MCP env are accepted for task-specific
            # settings but cannot redirect the prompt, project, API, or auth.
            env.update({
                "SYNAPSE_API": api_base(),
                "SYNAPSE_TOKEN": worker_credential,
                "SYNAPSE_PROJECT_ID": project.id,
                "SYNAPSE_SQUAD_ID": squad.id,
                "SYNAPSE_WORK_ITEM_ID": work_item.id,
                "SYNAPSE_ROLE_ID": role.id,
                "SYNAPSE_RUNTIME_ID": chosen_runtime,
                "SYNAPSE_PTY_SESSION_ID": session_id,
                "SYNAPSE_SESSION_ID": coordination_session.id,
                "SYNAPSE_SESSION_KEY": worker_credential,
                # The parent Live session this worker reports under. Prefer the real
                # parent coordination session; `lead_session_id_for_squad` returns a PTY
                # session id, which is a different namespace and was never usable as a
                # session reference by anything consuming this variable.
                "SYNAPSE_LEAD_SESSION_ID": (
                    parent_session_id or lead_session_id or coordination_session.id
                ),
                "SYNAPSE_ROLE_PROMPT_FILE": str(prompt_file),
                "SYNAPSE_AI_CONTEXT": str(ai_context_path(storage.data_dir, project.id).resolve()),
                "SYNAPSE_AI_CONTEXT_DIRECTION_PROMPT": AI_CONTEXT_DIRECTION_PROMPT,
            })
            if execution_mode == squads.AgentExecutionMode.AUTOMATIC:
                argv = _automatic_worker_argv(
                    argv,
                    runtime=chosen_runtime,
                    authority=body.authority,
                    prompt_file=prompt_file,
                )
            # Correlate the work item and execution before PTY startup. An
            # instant-exiting CLI may publish its final event from inside
            # manager.spawn(); the subscriber must already be able to find both.
            work_item = squads.set_work_item_session(
                conn,
                work_item.id,
                status=squads.AgentWorkItemStatus.RUNNING,
                pty_session_id=session_id,
                chosen_runtime=chosen_runtime,
                opened_in_tab=body.open_in_tab,
            )
            try:
                runtime_profile = coder_runtimes.profile_for(
                    coder_runtimes.CoderRuntime(chosen_runtime)
                )
            except ValueError:
                # Direct/custom executable sessions are an existing supported
                # escape hatch. They still receive an execution receipt, but no
                # provider-specific model/effort defaults or quota classification.
                runtime_profile = coder_runtimes.RuntimeProfile()
            execution = ai_executions.reserve_execution(
                conn,
                kind="agent_work_item",
                project_id=project.id,
                runtime_id=chosen_runtime,
                model=runtime_profile.model or None,
                effort=runtime_profile.effort or None,
                authority=body.authority.value,
                source_type="agent_work_item",
                source_id=work_item.id,
                pty_session_id=session_id,
                metadata={
                    "squad_id": squad.id,
                    "role_id": role.id,
                    "execution_mode": execution_mode.value,
                    "mcp_server_ids_configured": attached_mcp_server_ids,
                },
            )
        # PTY startup can await platform work. Never hold the daemon's shared
        # SQLite transaction across that await: simultaneous squad launches or
        # a routine heartbeat would otherwise attempt BEGIN on the same live
        # transaction and fail with an internal 500.
        try:
            session = await manager.spawn(
                argv=argv,
                cwd=body.cwd_override or project.path,
                env=env,
                rows=body.rows,
                cols=body.cols,
                project_id=project.id,
                session_id=session_id,
            )
        except Exception as exc:
            with storage.transaction() as conn:
                coordination.end_session(conn, coordination_session.id)
                ai_executions.finalize_spawn_failure(conn, execution.id, str(exc))
                # No process ever owned the work. Keep the item retryable while
                # the failed launch attempt remains a durable blocked receipt.
                squads.update_work_item_status(
                    conn, work_item.id, squads.AgentWorkItemStatus.QUEUED
                )
                audit(
                    conn,
                    AuditRecord(
                        entity_type="agent_work_item",
                        entity_id=work_item.id,
                        action="launch",
                        source=body.source,
                        result="error",
                        error_code="agent_work_item.invalid",
                        details={
                            "squad_id": squad.id,
                            "runtime": chosen_runtime,
                            "role_id": role.id,
                        },
                    ),
                )
            await bus.publish(
                event_name("coordination", "session_ended"),
                {"session_id": coordination_session.id},
            )
            if isinstance(exc, FileNotFoundError):
                raise invalid("agent_work_item", str(exc))
            # A PTY spawn can fail many ways beyond a missing binary -- a bad
            # project cwd, winpty errors, or permission issues. Surface them
            # as a clean ErrorEnvelope (Contract #4) instead of letting the
            # exception escape and take the daemon down.
            raise invalid(
                "agent_work_item",
                f"Could not start a session for this work item: {exc}",
            )

        with storage.transaction() as conn:
            work_item = squads.get_work_item(conn, work_item.id)
            audit(
                conn,
                AuditRecord(
                    entity_type="agent_work_item",
                    entity_id=work_item.id,
                    action="launch",
                    source=body.source,
                    result="success",
                    details={
                        "squad_id": squad.id,
                        "session_id": session.session_id,
                        "runtime": chosen_runtime,
                        "role_id": role.id,
                    },
                ),
            )
        await bus.publish(
            event_name("coordination", "session_registered"),
            {
                "session_id": coordination_session.id,
                "project_id": coordination_session.project_id,
                "seq": coordination_session.seq,
                "runtime_id": coordination_session.runtime_id,
                "agent_label": coordination_session.agent_label,
                "coder_thread_id": coordination_session.coder_thread_id,
                "task": coordination_session.task,
                "connection_level": coordination_session.connection_level,
                "connection_code": coordination_session.connection_code,
            },
        )
        await bus.publish(event_name("agent_work_item", "updated"), {"work_item": work_item.model_dump(mode="json")})
        await bus.publish(
            event_name("agent_run", "started"),
            {
                "squad_id": squad.id,
                "work_item_id": work_item.id,
                "role_id": role.id,
                "session_id": work_item.pty_session_id,
                "runtime": chosen_runtime,
                "execution_mode": execution_mode.value,
                "authority": body.authority.value,
                "timeout_seconds": body.timeout_seconds,
                "mcp_server_ids": attached_mcp_server_ids,
            },
        )
        if attached_mcp_server_ids:
            await bus.publish(
                event_name("agent_mcp", "attached"),
                {
                    "squad_id": squad.id,
                    "work_item_id": work_item.id,
                    "role_id": role.id,
                    "session_id": work_item.pty_session_id,
                    "runtime": chosen_runtime,
                    "mcp_server_ids": attached_mcp_server_ids,
                },
            )
        if execution_mode == squads.AgentExecutionMode.AUTOMATIC:
            presence_task = asyncio.create_task(
                _maintain_worker_presence(
                    storage,
                    manager,
                    bus,
                    coordination_session_id=coordination_session.id,
                    pty_session_id=session.session_id,
                )
            )
            presence_registry.track(work_item.id, presence_task)
            timeout_task = asyncio.create_task(
                _enforce_worker_timeout(
                    work_item_id=work_item.id,
                    session_id=session.session_id,
                    timeout_seconds=body.timeout_seconds,
                )
            )
            timeout_registry.track(work_item.id, timeout_task)
        return {
            **session.summary().__dict__,
            "squad_id": squad.id,
            "work_item_id": work_item.id,
            "role_id": role.id,
            "runtime": chosen_runtime,
            "role_prompt_file": str(prompt_file),
            "project_id": project.id,
            "project_name": project.name,
            "execution_mode": execution_mode.value,
            "authority": body.authority.value,
            "timeout_seconds": body.timeout_seconds,
            "coordination_session_id": coordination_session.id,
            "execution_id": execution.id,
        }

    async def _do_launch(
        work_item_id: str, body: AgentWorkItemLaunchRequest
    ) -> dict[str, Any]:
        async with launch_lock:
            return await _do_launch_serialized(work_item_id, body)

    @router.post("/agent-work-items/{work_item_id}/launch", response_model=None)
    async def launch_work_item(
        work_item_id: str,
        payload: AgentWorkItemLaunchRequest | None = None,
    ) -> dict[str, Any]:
        return await _do_launch(work_item_id, payload or AgentWorkItemLaunchRequest())

    @router.post("/agent-work-items/{work_item_id}/delegate", response_model=None, status_code=201)
    async def delegate_work_item(
        work_item_id: str,
        payload: AgentWorkItemDelegateRequest,
    ) -> dict[str, Any]:
        with storage.transaction() as conn:
            parent = squads.get_work_item(conn, work_item_id)
            if parent.assigned_role_id:
                squads.validate_role_can_delegate(conn, parent.assigned_role_id)
            if payload.assigned_role_id:
                squads.get_role_template(conn, payload.assigned_role_id)
            child = squads.create_work_item(
                conn,
                parent.squad_id,
                AgentWorkItemCreate(
                    title=payload.title,
                    instructions_md=payload.instructions_md,
                    assigned_role_id=payload.assigned_role_id,
                    preferred_runtime=payload.preferred_runtime,
                    parent_id=parent.id,
                    source=payload.source,
                ),
            )
            audit(
                conn,
                AuditRecord(
                    entity_type="agent_work_item",
                    entity_id=child.id,
                    action="delegate",
                    source=payload.source,
                    result="success",
                    details={"parent_id": parent.id, "squad_id": parent.squad_id, "auto_launch": payload.auto_launch},
                ),
            )
        await bus.publish(event_name("agent_work_item", "created"), {"work_item": child.model_dump(mode="json")})

        # Auto-launch (Plan 3 Phase 3): optionally spawn the delegated child right away, bounded by
        # the squad's concurrency cap + token budget. If a gate trips, the child is left QUEUED for a
        # later launch instead of erroring the whole delegation.
        if not payload.auto_launch:
            return child.model_dump(mode="json")
        try:
            launched = await _do_launch(
                child.id,
                AgentWorkItemLaunchRequest(preferred_runtime=payload.preferred_runtime, source=payload.source),
            )
        except SynapseError as exc:
            # A concurrency-cap / token-budget gate (409) leaves the child QUEUED for a later launch.
            # Any other failure (bad cwd, spawn error) is a real problem -- surface it; the child
            # was still created and can be launched manually once the cause is fixed.
            if exc.status == 409:
                return {**child.model_dump(mode="json"), "launched": None, "queued_reason": exc.envelope.message}
            raise
        # `launched` is the authoritative "it started" signal. `fresh` reflects the child's *current*
        # status, which for an instant-exiting runtime may already read completed rather than running
        # -- that's accurate, not a race bug. Both auto-launch branches return launched+queued_reason.
        fresh = squads.get_work_item(storage.conn, child.id)
        return {**fresh.model_dump(mode="json"), "launched": launched, "queued_reason": None}

    @router.post("/agent-work-items/{work_item_id}/handoff", response_model=None)
    async def handoff_work_item(
        work_item_id: str,
        payload: AgentWorkItemHandoffRequest,
    ) -> dict[str, Any]:
        with storage.transaction() as conn:
            item = squads.get_work_item(conn, work_item_id)
            squad = squads.get_squad(conn, item.squad_id)
            project = projects_module.get(conn, squad.project_id)
            role_name = None
            if item.assigned_role_id:
                role_name = squads.get_role_template(conn, item.assigned_role_id).name
            adjusted_payload = payload
            if payload.verdict.blocking and payload.status == squads.AgentWorkItemStatus.COMPLETED:
                adjusted_payload = payload.model_copy(
                    update={"status": squads.AgentWorkItemStatus.HANDOFF}
                )
            if adjusted_payload.status == squads.AgentWorkItemStatus.COMPLETED:
                quality_os.assert_subject_can_complete(conn, "agent_work_item", work_item_id)
            item = squads.handoff_work_item(conn, work_item_id, adjusted_payload)
            gate = None
            if payload.verdict.blocking:
                gate = quality_os.create_gate(
                    conn,
                    quality_os.QualityGateCreate(
                        subject_type="agent_work_item",
                        subject_id=work_item_id,
                        gate_kind="ui-review",
                        title=payload.summary_md or item.title,
                        blocking=True,
                        required_evidence=["review-verdict"],
                        linked_surface_ids=payload.verdict.surface_ids,
                        linked_contract_ids=payload.verdict.contract_ids,
                        audit_details={
                            "severity": payload.verdict.severity.value,
                            "recommended_next_step": payload.verdict.recommended_next_step,
                            "squad_id": squad.id,
                        },
                    ),
                )
            else:
                for existing in quality_os.list_gates(
                    conn,
                    subject_type="agent_work_item",
                    subject_id=work_item_id,
                    status=quality_os.QualityGateStatus.OPEN,
                ):
                    if existing.gate_kind == "ui-review":
                        quality_os.resolve_gate(
                            conn,
                            existing.id,
                            quality_os.QualityGateResolveRequest(
                                status=quality_os.QualityGateStatus.PASSED,
                                resolved_by="squad-handoff",
                                note=payload.summary_md or "Non-blocking handoff cleared the review gate.",
                            ),
                        )
            append_work_item_handoff(
                data_dir=storage.data_dir,
                project_id=project.id,
                project_name=project.name,
                squad_name=squad.name,
                work_item_title=item.title,
                role_name=role_name,
                summary_md=adjusted_payload.summary_md,
                blockers_md=adjusted_payload.blockers_md,
                files_touched=adjusted_payload.files_touched,
                suggested_next_role=adjusted_payload.suggested_next_role,
            )
            # If the worker self-reported token usage in its handoff, record it to
            # the ledger (ADR-0025) so reporting is frictionless -- part of the
            # handoff the worker already does, not a separate call it forgets.
            if any(
                t is not None
                for t in (payload.input_tokens, payload.output_tokens, payload.total_tokens)
            ):
                token_ledger.record_tokens(
                    conn,
                    work_item_id,
                    token_ledger.WorkItemTokenUsageCreate(
                        input_tokens=payload.input_tokens or 0,
                        output_tokens=payload.output_tokens or 0,
                        total_tokens=payload.total_tokens,
                        metadata={"via": "handoff"},
                    ),
                )
            audit(
                conn,
                AuditRecord(
                    entity_type="agent_work_item",
                    entity_id=work_item_id,
                    action="handoff",
                    source=adjusted_payload.source,
                    result="success",
                    details={"status": item.status.value, "suggested_next_role": item.suggested_next_role},
                ),
            )
        await bus.publish(event_name("agent_work_item", "handoff"), {"work_item": item.model_dump(mode="json")})
        return {
            **item.model_dump(mode="json"),
            "gate": gate.model_dump(mode="json") if gate else None,
        }

    @router.post("/agent-work-items/{work_item_id}/status", response_model=None)
    async def update_work_item_status(
        work_item_id: str,
        payload: AgentWorkItemStatusRequest,
    ) -> dict[str, Any]:
        with storage.transaction() as conn:
            if payload.status == squads.AgentWorkItemStatus.COMPLETED:
                quality_os.assert_subject_can_complete(conn, "agent_work_item", work_item_id)
            item = squads.update_work_item_status(conn, work_item_id, payload.status)
            audit(
                conn,
                AuditRecord(
                    entity_type="agent_work_item",
                    entity_id=work_item_id,
                    action="status",
                    source=payload.source,
                    result="success",
                    details={"status": item.status.value},
                ),
            )
        await bus.publish(event_name("agent_work_item", "updated"), {"work_item": item.model_dump(mode="json")})
        return item.model_dump(mode="json")

    return router


async def subscribe_agent_squad_events(
    storage: Storage,
    bus: EventBus,
    manager: PtySessionManager,
    timeout_registry: WorkerTimeoutRegistry,
    presence_registry: WorkerPresenceRegistry,
) -> None:
    async def _on_event(event: Event) -> None:
        if event.name != event_name("pty", "session_finalized"):
            return
        session_id = str(event.payload.get("session_id") or "")
        if not session_id:
            return
        exit_code = event.payload.get("exit_code")
        session = manager.get(session_id)
        failure_reason = (
            squads.classify_worker_failure(session.scrollback_bytes())
            if session is not None and exit_code not in (0, None)
            else None
        )
        with storage.transaction() as conn:
            updated = squads.complete_work_item_from_session_exit(
                conn,
                session_id=session_id,
                exit_code=exit_code if isinstance(exit_code, int) or exit_code is None else None,
                failure_reason=failure_reason,
            )
            finalized_execution = ai_executions.finalize_pty_execution(
                conn,
                pty_session_id=session_id,
                output=session.scrollback_bytes() if session is not None else b"",
                exit_code=exit_code if isinstance(exit_code, int) or exit_code is None else None,
                work_outcome=(updated.status.value if updated is not None else None),
            )
            coordination_session = coordination.get_session_by_coder_thread_id(
                conn, session_id
            )
            if (
                coordination_session is not None
                and coordination_session.status != coordination.AgentSessionStatus.GONE
            ):
                coordination.end_session(conn, coordination_session.id)
        if updated is None:
            return
        timeout_registry.cancel(updated.id)
        presence_registry.cancel(updated.id)
        await bus.publish(event_name("agent_work_item", "updated"), {"work_item": updated.model_dump(mode="json")})
        await bus.publish(
            event_name("agent_run", "ended"),
            {
                "work_item_id": updated.id,
                "squad_id": updated.squad_id,
                "session_id": session_id,
                "status": updated.status.value,
                "transcript_file_id": updated.transcript_file_id,
                "execution_id": finalized_execution.id if finalized_execution else None,
                "accounting_state": (
                    finalized_execution.accounting_state if finalized_execution else "missing_execution"
                ),
            },
        )
        if coordination_session is not None:
            await bus.publish(
                event_name("coordination", "session_ended"),
                {"session_id": coordination_session.id},
            )

    await bus.subscribe(_on_event)


async def _publish_role_templates_updated(bus: EventBus, storage: Storage) -> None:
    await bus.publish(
        event_name("agent_squad", "updated"),
        {
            "role_templates": [
                role.model_dump(mode="json")
                for role in squads.list_role_templates(storage.conn)
            ]
        },
    )


def AuditSourceFromPayload(payload: AgentRoleTemplateCreate) -> squads.AuditSource:
    return squads.AuditSource.DESKTOP
