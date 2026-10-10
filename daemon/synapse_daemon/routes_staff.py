"""REST surface for persistent owner-facing AI staff."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from . import (
    agent_squads,
    projects as projects_module,
    staff as staff_module,
    staff_chat as staff_chat_module,
    staff_operations as staff_ops,
)
from .audit import AuditRecord, audit
from .errors import invalid
from .models import AuditSource
from .storage import Storage
from .staff import StaffMemberCreate, StaffMemberUpdate
from .staff_hq_proactivity import set_staff_trigger_enabled
from .staff_operations import (
    StaffKpiCreate,
    StaffKpiUpdate,
    StaffMemoryCreate,
    StaffPermissionCreate,
    StaffTriggerCreate,
)


class SummonStaffRequest(BaseModel):
    project_id: str
    task: str = Field(min_length=1)
    instructions_md: str = ""
    max_concurrent: int = Field(default=1, ge=1, le=8)
    token_budget: int = Field(default=0, ge=0)


class RouteStaffRequest(BaseModel):
    task: str = Field(min_length=1)
    project_id: str | None = None
    create_assignment: bool = False
    instructions_md: str = ""


class StaffTriggerEnabledRequest(BaseModel):
    enabled: bool


class StaffChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=8000)


class StaffCouncilRequest(BaseModel):
    project_id: str
    objective: str = Field(min_length=1)
    staff_handles: list[str] = Field(default_factory=list)
    max_members: int = Field(default=4, ge=2, le=6)


def _recommended_execution_authority(member: staff_module.StaffMember) -> str:
    if member.authority_policy == staff_module.StaffAuthority.ADVISE_ONLY:
        return agent_squads.AgentExecutionAuthority.OBSERVE.value
    return agent_squads.AgentExecutionAuthority.WORKSPACE.value


def _summon_in_tx(
    conn,
    member: staff_module.StaffMember,
    payload: SummonStaffRequest,
) -> tuple[agent_squads.AgentSquad, agent_squads.AgentWorkItem]:
    projects_module.get(conn, payload.project_id)
    staff_ops.assert_project_work_allowed(conn, member, payload.project_id)

    squad = agent_squads.create_squad(
        conn,
        agent_squads.AgentSquadCreate(
            project_id=payload.project_id,
            name=f"{member.display_name} · {payload.task[:72]}",
            goal_md=(
                f"Persistent Synapse staff owner: @{member.handle} "
                f"({member.display_name}, {member.title}).\n\n"
                f"Task: {payload.task}\n\n"
                f"Authority policy: {member.authority_policy.value}.\n"
                f"Staff goals: {'; '.join(member.goals)}"
            ),
            lead_role_id=member.role_template_id,
            max_concurrent=payload.max_concurrent,
            token_budget=payload.token_budget,
            source=AuditSource.DESKTOP,
        ),
    )
    item = agent_squads.create_work_item(
        conn,
        squad.id,
        agent_squads.AgentWorkItemCreate(
            title=payload.task,
            instructions_md=(
                f"You are {member.display_name}, the owner's {member.title}. "
                "This is your persistent staff identity, not a generic one-off worker.\n\n"
                f"{payload.instructions_md}\n\n"
                f"Authority policy: {member.authority_policy.value}. "
                "Stay within this authority, preserve an evidence trail, and request owner "
                "approval for anything outside the stored permission boundary."
            ).strip(),
            assigned_role_id=member.role_template_id,
            personality_id=member.personality_id,
            source=AuditSource.DESKTOP,
        ),
    )
    staff_module.link_work_item(conn, member.id, item.id)
    staff_module.update_staff(
        conn,
        member.id,
        staff_module.StaffMemberUpdate(
            status=staff_module.StaffStatus.WORKING,
            status_line=f"Assigned: {payload.task[:140]}",
        ),
    )
    staff_ops.record_event(
        conn,
        member.id,
        event_type="assignment_created",
        title=f"Assigned: {payload.task[:100]}",
        body_md=f"Project: {payload.project_id}. Work item: {item.id}.",
        severity="info",
        source="staff-api",
        metadata={
            "project_id": payload.project_id,
            "squad_id": squad.id,
            "work_item_id": item.id,
        },
    )
    audit(
        conn,
        AuditRecord(
            entity_type="staff_member",
            entity_id=member.id,
            action="summon",
            source=AuditSource.DESKTOP,
            result="success",
            details={
                "project_id": payload.project_id,
                "squad_id": squad.id,
                "work_item_id": item.id,
                "recommended_execution_authority": _recommended_execution_authority(member),
            },
        ),
    )
    return squad, item


def build_staff_router(storage: Storage) -> APIRouter:
    router = APIRouter(prefix="/staff", tags=["staff"])

    @router.get("", response_model=None)
    async def list_staff() -> dict[str, Any]:
        return {
            "staff": [
                member.model_dump(mode="json")
                for member in staff_module.list_staff(storage.conn)
            ],
            "avatar_assets": [
                asset.model_dump(mode="json")
                for asset in staff_module.list_avatar_assets(storage.conn)
            ],
        }

    @router.get("/avatar-assets", response_model=None)
    async def list_avatar_assets() -> dict[str, Any]:
        return {
            "assets": [
                asset.model_dump(mode="json")
                for asset in staff_module.list_avatar_assets(storage.conn)
            ]
        }

    @router.get("/briefing", response_model=None)
    async def get_team_briefing() -> dict[str, Any]:
        return staff_ops.team_briefing(storage.conn)

    @router.post("/route", response_model=None)
    async def route_staff(payload: RouteStaffRequest, request: Request) -> dict[str, Any]:
        routed = staff_ops.route_task(storage.conn, payload.task)
        response: dict[str, Any] = routed.model_dump(mode="json")
        if payload.project_id:
            projects_module.get(storage.conn, payload.project_id)
        if payload.create_assignment:
            if not payload.project_id:
                raise invalid(
                    "staff_route",
                    "project_id is required when create_assignment is true.",
                )
            member = staff_module.get_staff(storage.conn, routed.selected.staff_id)
            with storage.transaction() as conn:
                squad, item = _summon_in_tx(
                    conn,
                    member,
                    SummonStaffRequest(
                        project_id=payload.project_id,
                        task=payload.task,
                        instructions_md=payload.instructions_md,
                    ),
                )
            response["assignment"] = {
                "staff_id": member.id,
                "squad": squad.model_dump(mode="json"),
                "work_item": item.model_dump(mode="json"),
                "recommended_execution_authority": _recommended_execution_authority(member),
                "session_id": request.headers.get("X-Synapse-Session"),
            }
        return response

    @router.post("/council", response_model=None, status_code=201)
    async def create_staff_council(payload: StaffCouncilRequest) -> dict[str, Any]:
        projects_module.get(storage.conn, payload.project_id)
        if payload.staff_handles:
            chosen: list[staff_module.StaffMember] = []
            seen: set[str] = set()
            for handle in payload.staff_handles:
                member = staff_module.get_staff(storage.conn, handle)
                if member.id not in seen:
                    chosen.append(member)
                    seen.add(member.id)
            chosen = chosen[: payload.max_members]
        else:
            routed = staff_ops.route_task(storage.conn, payload.objective)
            chosen = [
                staff_module.get_staff(storage.conn, candidate.staff_id)
                for candidate in routed.candidates[: payload.max_members]
            ]
        if len(chosen) < 2:
            raise invalid("staff_council", "A staff council requires at least two people.")

        with storage.transaction() as conn:
            for member in chosen:
                staff_ops.assert_project_work_allowed(conn, member, payload.project_id)
            lead = chosen[0]
            squad = agent_squads.create_squad(
                conn,
                agent_squads.AgentSquadCreate(
                    project_id=payload.project_id,
                    name=f"Staff Council · {payload.objective[:62]}",
                    goal_md=(
                        "Multi-person AI Staff Council. Each member owns only their domain, "
                        "must cite evidence, avoid duplicating another member, and hand back a "
                        "clear recommendation for synthesis.\n\n"
                        f"Objective: {payload.objective}"
                    ),
                    lead_role_id=lead.role_template_id,
                    max_concurrent=len(chosen),
                    source=AuditSource.DESKTOP,
                ),
            )
            work_items: list[dict[str, Any]] = []
            for member in chosen:
                item = agent_squads.create_work_item(
                    conn,
                    squad.id,
                    agent_squads.AgentWorkItemCreate(
                        title=f"{member.display_name}: {payload.objective[:86]}",
                        instructions_md=(
                            f"You are {member.display_name}, {member.title}. Analyze this objective "
                            "strictly from your staff domain and stored authority. Do not duplicate "
                            "other council members. Return evidence, risks, recommendation, and the "
                            "next concrete action.\n\n"
                            f"Council objective: {payload.objective}"
                        ),
                        assigned_role_id=member.role_template_id,
                        personality_id=member.personality_id,
                        source=AuditSource.DESKTOP,
                    ),
                )
                staff_module.link_work_item(conn, member.id, item.id)
                staff_ops.record_event(
                    conn,
                    member.id,
                    event_type="council_assignment",
                    title=f"Council: {payload.objective[:100]}",
                    body_md=f"Project: {payload.project_id}. Council squad: {squad.id}.",
                    source="staff-api",
                    metadata={"squad_id": squad.id, "work_item_id": item.id},
                )
                work_items.append(
                    {
                        "staff_id": member.id,
                        "handle": member.handle,
                        "display_name": member.display_name,
                        "recommended_execution_authority": _recommended_execution_authority(member),
                        "work_item": item.model_dump(mode="json"),
                    }
                )
            audit(
                conn,
                AuditRecord(
                    entity_type="staff_council",
                    entity_id=squad.id,
                    action="create",
                    source=AuditSource.DESKTOP,
                    result="success",
                    details={
                        "project_id": payload.project_id,
                        "staff_ids": [member.id for member in chosen],
                    },
                ),
            )
        return {
            "squad": squad.model_dump(mode="json"),
            "members": work_items,
            "objective": payload.objective,
        }

    @router.get("/{staff_id}/chat", response_model=None)
    async def get_staff_chat(staff_id: str) -> dict[str, Any]:
        member = staff_module.get_staff(storage.conn, staff_id)
        return {
            "staff": member.model_dump(mode="json"),
            "messages": [
                message.model_dump(mode="json")
                for message in staff_chat_module.list_messages(storage.conn, member.id, limit=100)
            ],
        }

    @router.post("/{staff_id}/chat", response_model=None)
    async def send_staff_chat(staff_id: str, payload: StaffChatRequest) -> dict[str, Any]:
        member, reply = await staff_chat_module.converse(
            conn=storage.conn,
            data_dir=storage.data_dir,
            staff_id=staff_id,
            user_message=payload.message.strip(),
            timeout_seconds=180.0,
        )
        with storage.transaction() as conn:
            user_message = staff_chat_module.append_message(
                conn, member.id, "user", payload.message.strip()
            )
            assistant_message = staff_chat_module.append_message(
                conn, member.id, "assistant", reply
            )
            staff_ops.record_event(
                conn,
                member.id,
                event_type="conversation",
                title="Conversation updated",
                body_md=payload.message.strip()[:180],
                source="staff-chat",
                metadata={"assistant_message_id": assistant_message.id},
            )
        return {
            "staff_id": member.id,
            "user_message": user_message.model_dump(mode="json"),
            "assistant_message": assistant_message.model_dump(mode="json"),
        }

    @router.get("/maya/growth-review", response_model=None)
    async def get_maya_growth_review() -> dict[str, Any]:
        # Read-only evidence preflight. No model call or external actions.
        from . import maya_growth

        return maya_growth.build_growth_review(storage.conn)

    @router.post("/maya/growth-review", response_model=None)
    async def record_maya_growth_review() -> dict[str, Any]:
        # Idempotent receipt; does not activate scheduled workers.
        from . import maya_growth

        with storage.transaction() as conn:
            return maya_growth.record_growth_review(conn)
    @router.get("/maya/experiment-plan", response_model=None)
    async def get_maya_experiment_plan() -> dict[str, Any]:
        # Read-only preview: never infer that an experiment ran.
        from . import maya_experiments
        return maya_experiments.build_experiment_plan(storage.conn)

    @router.post("/maya/experiment-plan", response_model=None)
    async def record_maya_experiment_plan() -> dict[str, Any]:
        # Explicit owner gesture saves a plan; does not dispatch a worker.
        from . import maya_experiments
        with storage.transaction() as conn:
            return maya_experiments.record_experiment_plan(conn)

    @router.get("/{staff_id}/dashboard", response_model=None)
    async def get_staff_dashboard(staff_id: str) -> dict[str, Any]:
        return staff_ops.staff_dashboard(storage.conn, staff_id)

    @router.get("/{staff_id}/execution", response_model=None)
    async def get_staff_execution_truth(staff_id: str) -> dict[str, Any]:
        # Read-only: never infer liveness from a stored "working" label.
        from . import staff_execution

        return staff_execution.staff_execution_snapshot(storage.conn, staff_id)

    @router.post("/{staff_id}/kpis", response_model=None, status_code=201)
    async def create_staff_kpi(staff_id: str, payload: StaffKpiCreate) -> dict[str, Any]:
        with storage.transaction() as conn:
            created = staff_ops.create_kpi(conn, staff_id, payload)
            staff_ops.record_event(
                conn,
                staff_id,
                event_type="kpi_created",
                title=f"KPI created: {created.name}",
                source="staff-api",
                metadata={"kpi_id": created.id},
            )
        return created.model_dump(mode="json")

    @router.patch("/{staff_id}/kpis/{kpi_id}", response_model=None)
    async def patch_staff_kpi(
        staff_id: str, kpi_id: str, payload: StaffKpiUpdate
    ) -> dict[str, Any]:
        with storage.transaction() as conn:
            updated = staff_ops.update_kpi(conn, staff_id, kpi_id, payload)
            staff_ops.record_event(
                conn,
                staff_id,
                event_type="kpi_updated",
                title=f"KPI updated: {updated.name}",
                body_md=f"Status: {updated.status}.",
                severity="warning" if updated.status in {"watch", "off_track"} else "info",
                action_required=updated.status == "off_track",
                source="staff-api",
                metadata={"kpi_id": updated.id, "status": updated.status},
            )
        return updated.model_dump(mode="json")

    @router.post("/{staff_id}/memories", response_model=None, status_code=201)
    async def create_staff_memory(
        staff_id: str, payload: StaffMemoryCreate
    ) -> dict[str, Any]:
        with storage.transaction() as conn:
            memory = staff_ops.create_memory(conn, staff_id, payload)
        return memory.model_dump(mode="json")

    @router.post("/{staff_id}/permissions", response_model=None)
    async def upsert_staff_permission(
        staff_id: str, payload: StaffPermissionCreate
    ) -> dict[str, Any]:
        with storage.transaction() as conn:
            permission = staff_ops.upsert_permission(conn, staff_id, payload)
            staff_ops.record_event(
                conn,
                staff_id,
                event_type="permission_changed",
                title=(
                    f"Permission {permission.decision}: "
                    f"{permission.scope_type}/{permission.scope_id}/{permission.capability}"
                ),
                severity="warning" if permission.decision == "deny" else "info",
                source="staff-api",
                metadata={"permission_id": permission.id},
            )
        return permission.model_dump(mode="json")

    @router.post("/{staff_id}/triggers", response_model=None, status_code=201)
    async def create_staff_trigger(
        staff_id: str, payload: StaffTriggerCreate
    ) -> dict[str, Any]:
        with storage.transaction() as conn:
            trigger = staff_ops.create_trigger(conn, staff_id, payload)
            staff_ops.record_event(
                conn,
                staff_id,
                event_type="trigger_created",
                title=f"Trigger created: {trigger.name}",
                body_md=(
                    "Enabled." if trigger.enabled
                    else "Stored but disabled until an execution scheduler owns it."
                ),
                severity="info",
                source="staff-api",
                metadata={"trigger_id": trigger.id},
            )
        return trigger.model_dump(mode="json")

    @router.patch("/{staff_id}/triggers/{trigger_id}", response_model=None)
    async def patch_staff_trigger(
        staff_id: str, trigger_id: str, payload: StaffTriggerEnabledRequest
    ) -> dict[str, Any]:
        with storage.transaction() as conn:
            result = set_staff_trigger_enabled(
                conn, staff_id, trigger_id, payload.enabled
            )
            staff_ops.record_event(
                conn, staff_id, event_type="trigger_toggled",
                title=("Enabled" if payload.enabled else "Paused") + " review reminder: " + result["name"],
                body_md="Reminder-only; no AI runtime or external action launched.",
                source="staff-api",
                metadata={"trigger_id": trigger_id, "enabled": payload.enabled},
            )
        return result

    @router.get("/{staff_id}", response_model=None)
    async def get_staff(staff_id: str) -> dict[str, Any]:
        member = staff_module.get_staff(storage.conn, staff_id)
        role = agent_squads.get_role_template(storage.conn, member.role_template_id)
        personality = None
        if member.personality_id:
            from . import personalities

            personality = personalities.get_personality(
                storage.conn, member.personality_id
            )
        avatar = (
            staff_module.get_avatar_asset(storage.conn, member.avatar_asset_id)
            if member.avatar_asset_id
            else None
        )
        return {
            "staff": member.model_dump(mode="json"),
            "role": role.model_dump(mode="json"),
            "personality": (
                personality.model_dump(mode="json") if personality else None
            ),
            "avatar": avatar.model_dump(mode="json") if avatar else None,
            "recent_work": staff_module.list_recent_work_items(
                storage.conn, member.id, limit=20
            ),
            "operations_summary": {
                "responsibilities": len(
                    staff_ops.list_responsibilities(storage.conn, member.id)
                ),
                "kpis": len(staff_ops.list_kpis(storage.conn, member.id)),
                "memories": len(staff_ops.list_memories(storage.conn, member.id, 200)),
                "permissions": len(
                    staff_ops.list_permissions(storage.conn, member.id)
                ),
                "triggers": len(staff_ops.list_triggers(storage.conn, member.id)),
                "channels": len(staff_ops.list_channels(storage.conn, member.id)),
            },
        }

    @router.post("", response_model=None, status_code=201)
    async def create_staff(payload: StaffMemberCreate) -> dict[str, Any]:
        with storage.transaction() as conn:
            member = staff_module.create_staff(conn, payload)
            # New people get truthful base channel states and no invented KPIs.
            staff_ops.upsert_permission(
                conn,
                member.id,
                StaffPermissionCreate(
                    scope_type="external_action",
                    scope_id="*",
                    capability="send",
                    decision="ask",
                    reason="External sends require owner approval by default.",
                ),
            )
            audit(
                conn,
                AuditRecord(
                    entity_type="staff_member",
                    entity_id=member.id,
                    action="create",
                    source=AuditSource.DESKTOP,
                    result="success",
                    details={"handle": member.handle, "title": member.title},
                ),
            )
        return member.model_dump(mode="json")

    @router.patch("/{staff_id}", response_model=None)
    async def patch_staff(
        staff_id: str, payload: StaffMemberUpdate
    ) -> dict[str, Any]:
        with storage.transaction() as conn:
            member = staff_module.update_staff(conn, staff_id, payload)
            audit(
                conn,
                AuditRecord(
                    entity_type="staff_member",
                    entity_id=member.id,
                    action="update",
                    source=AuditSource.DESKTOP,
                    result="success",
                ),
            )
        return member.model_dump(mode="json")

    @router.post("/{staff_id}/summon", response_model=None, status_code=201)
    async def summon_staff(
        staff_id: str, payload: SummonStaffRequest, request: Request
    ) -> dict[str, Any]:
        member = staff_module.get_staff(storage.conn, staff_id)
        with storage.transaction() as conn:
            squad, item = _summon_in_tx(conn, member, payload)
        return {
            "staff_id": member.id,
            "squad": squad.model_dump(mode="json"),
            "work_item": item.model_dump(mode="json"),
            "recommended_execution_authority": _recommended_execution_authority(member),
            "session_id": request.headers.get("X-Synapse-Session"),
        }

    return router
