"""REST routes for Sessions-centric AI squads."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter

from . import agent_squads as squads
from . import mcp_servers as mcp_servers_module
from . import personalities as personalities_module
from . import projects as projects_module
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
from .audit import AuditRecord, audit
from .errors import invalid
from .pty_sessions import PtySessionManager
from .storage import Storage
from .ws import Event, EventBus


def _write_mcp_config(storage: Storage) -> Path | None:
    """Generate a Claude ``--mcp-config`` file from the user's enabled MCP
    servers (ADR-0017 MW2). Returns the path, or None if there's nothing to wire
    in. Lives in the data dir, so a project's own ``.mcp.json`` is untouched."""
    servers = [s for s in mcp_servers_module.list_servers(storage.conn) if s.enabled]
    config = mcp_servers_module.build_mcp_config(servers)
    if not config.get("mcpServers"):
        return None
    path = storage.data_dir / "mcp" / "claude-mcp.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config, indent=2), encoding="utf-8")
    return path


def build_agent_squads_router(
    storage: Storage,
    manager: PtySessionManager,
    bus: EventBus,
) -> APIRouter:
    router = APIRouter(tags=["agent-squads"])

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
    async def create_squad(payload: AgentSquadCreate) -> dict[str, Any]:
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
        await bus.publish(event_name("agent_squad", "created"), {"squad": squad.model_dump(mode="json")})
        return squad.model_dump(mode="json")

    @router.get("/agent-squads/{squad_id}", response_model=None)
    async def get_squad_detail(squad_id: str) -> dict[str, Any]:
        detail = squads.squad_detail(storage.conn, squad_id)
        return detail.model_dump(mode="json")

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
        closed: list[tuple[str, str]] = []  # (work_item_id, session_id)
        for item in items:
            if not item.pty_session_id:
                continue
            if await manager.close(item.pty_session_id):
                closed.append((item.id, item.pty_session_id))
        with storage.transaction() as conn:
            for _wid, session_id in closed:
                squads.complete_work_item_from_session_exit(
                    conn, session_id=session_id, exit_code=-1
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
            "stopped_sessions": len(closed),
            "work_item_ids": [wid for wid, _ in closed],
        }

    @router.post("/agent-squads/{squad_id}/work-items", response_model=None, status_code=201)
    async def create_work_item(
        squad_id: str, payload: AgentWorkItemCreate
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
        await bus.publish(event_name("agent_work_item", "created"), {"work_item": item.model_dump(mode="json")})
        return item.model_dump(mode="json")

    @router.post("/agent-work-items/{work_item_id}/launch", response_model=None)
    async def launch_work_item(
        work_item_id: str,
        payload: AgentWorkItemLaunchRequest | None = None,
    ) -> dict[str, Any]:
        body = payload or AgentWorkItemLaunchRequest()
        with storage.transaction() as conn:
            work_item = squads.get_work_item(conn, work_item_id)
            squad = squads.get_squad(conn, work_item.squad_id)
            project = projects_module.get(conn, squad.project_id)
            role = squads.get_role_template(conn, work_item.assigned_role_id or squad.lead_role_id or "planner")
            # Layer in the worker's personality (ADR-0018 MW3) so two same-role
            # workers differ. A deleted/missing personality must not block launch.
            personality = None
            if work_item.personality_id:
                try:
                    personality = personalities_module.get_personality(conn, work_item.personality_id)
                except Exception:
                    personality = None
            chosen_runtime = squads.pick_runtime(role, body.preferred_runtime or work_item.preferred_runtime)
            argv = squads.argv_for_runtime(chosen_runtime)
            # Wire the user's enabled MCP servers into a Claude worker (ADR-0017
            # MW2). `--mcp-config` merges additively, so the project's own
            # `.mcp.json` (if any) is left untouched.
            if chosen_runtime == "claude":
                mcp_config_path = _write_mcp_config(storage)
                if mcp_config_path is not None:
                    argv = [*argv, "--mcp-config", str(mcp_config_path)]
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
            )
            lead_session_id = squads.lead_session_id_for_squad(conn, squad.id)
            env = {
                "SYNAPSE_SQUAD_ID": squad.id,
                "SYNAPSE_WORK_ITEM_ID": work_item.id,
                "SYNAPSE_ROLE_ID": role.id,
                "SYNAPSE_LEAD_SESSION_ID": lead_session_id or session_id,
                "SYNAPSE_ROLE_PROMPT_FILE": str(prompt_file),
                "SYNAPSE_AI_CONTEXT": str(ai_context_path(storage.data_dir, project.id)),
                "SYNAPSE_AI_CONTEXT_DIRECTION_PROMPT": AI_CONTEXT_DIRECTION_PROMPT,
            }
            try:
                session = await manager.spawn(
                    argv=argv,
                    cwd=project.path,
                    env=env,
                    rows=body.rows,
                    cols=body.cols,
                    project_id=project.id,
                    session_id=session_id,
                )
            except FileNotFoundError as exc:
                raise invalid("agent_work_item", str(exc))
            except Exception as exc:
                # A PTY spawn can fail many ways beyond a missing binary -- a bad
                # project cwd, winpty errors, or permission issues. Surface them
                # as a clean ErrorEnvelope (Contract #4) instead of letting the
                # exception escape and take the daemon down.
                raise invalid(
                    "agent_work_item",
                    f"Could not start a session for this work item: {exc}",
                )
            work_item = squads.set_work_item_session(
                conn,
                work_item.id,
                status=squads.AgentWorkItemStatus.RUNNING,
                pty_session_id=session.session_id,
                chosen_runtime=chosen_runtime,
                opened_in_tab=body.open_in_tab,
            )
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
        await bus.publish(event_name("agent_work_item", "updated"), {"work_item": work_item.model_dump(mode="json")})
        await bus.publish(
            event_name("agent_run", "started"),
            {
                "squad_id": squad.id,
                "work_item_id": work_item.id,
                "role_id": role.id,
                "session_id": work_item.pty_session_id,
                "runtime": chosen_runtime,
            },
        )
        return {
            **session.summary().__dict__,
            "squad_id": squad.id,
            "work_item_id": work_item.id,
            "role_id": role.id,
            "runtime": chosen_runtime,
            "role_prompt_file": str(prompt_file),
            "project_id": project.id,
            "project_name": project.name,
        }

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
                    details={"parent_id": parent.id, "squad_id": parent.squad_id},
                ),
            )
        await bus.publish(event_name("agent_work_item", "created"), {"work_item": child.model_dump(mode="json")})
        return child.model_dump(mode="json")

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
            item = squads.handoff_work_item(conn, work_item_id, payload)
            append_work_item_handoff(
                data_dir=storage.data_dir,
                project_id=project.id,
                project_name=project.name,
                squad_name=squad.name,
                work_item_title=item.title,
                role_name=role_name,
                summary_md=payload.summary_md,
                blockers_md=payload.blockers_md,
                files_touched=payload.files_touched,
                suggested_next_role=payload.suggested_next_role,
            )
            audit(
                conn,
                AuditRecord(
                    entity_type="agent_work_item",
                    entity_id=work_item_id,
                    action="handoff",
                    source=payload.source,
                    result="success",
                    details={"status": item.status.value, "suggested_next_role": item.suggested_next_role},
                ),
            )
        await bus.publish(event_name("agent_work_item", "handoff"), {"work_item": item.model_dump(mode="json")})
        return item.model_dump(mode="json")

    @router.post("/agent-work-items/{work_item_id}/status", response_model=None)
    async def update_work_item_status(
        work_item_id: str,
        payload: AgentWorkItemStatusRequest,
    ) -> dict[str, Any]:
        with storage.transaction() as conn:
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


async def subscribe_agent_squad_events(storage: Storage, bus: EventBus) -> None:
    async def _on_event(event: Event) -> None:
        if event.name != event_name("pty", "session_finalized"):
            return
        session_id = str(event.payload.get("session_id") or "")
        if not session_id:
            return
        exit_code = event.payload.get("exit_code")
        with storage.transaction() as conn:
            updated = squads.complete_work_item_from_session_exit(
                conn,
                session_id=session_id,
                exit_code=exit_code if isinstance(exit_code, int) or exit_code is None else None,
            )
        if updated is None:
            return
        await bus.publish(event_name("agent_work_item", "updated"), {"work_item": updated.model_dump(mode="json")})
        await bus.publish(
            event_name("agent_run", "ended"),
            {
                "work_item_id": updated.id,
                "squad_id": updated.squad_id,
                "session_id": session_id,
                "status": updated.status.value,
                "transcript_file_id": updated.transcript_file_id,
            },
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
