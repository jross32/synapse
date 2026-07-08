"""Durable models + SQLite CRUD for Sessions-centric AI squads."""

from __future__ import annotations

import json
import secrets
import sqlite3
import sys
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from .errors import invalid, not_found
from .models import AuditSource
from .quality_os import ReviewVerdict
from .runtime_resolution import resolve_command
from .time_utils import from_iso, to_iso, utc_now


class AgentVisibility(str, Enum):
    LEAD = "lead"
    HELPER = "helper"


class AgentContextMode(str, Enum):
    FULL = "full"
    STANDARD = "standard"
    MINIMAL = "minimal"


class AgentRoleTier(str, Enum):
    """Where a role sits in the squad hierarchy (boss -> supervisor -> worker)."""

    BOSS = "boss"
    SUPERVISOR = "supervisor"
    WORKER = "worker"


class AgentSquadStatus(str, Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"


class AgentWorkItemStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    HANDOFF = "handoff"
    BLOCKED = "blocked"
    COMPLETED = "completed"


class AgentRoleTemplate(BaseModel):
    id: str
    name: str
    description: str = ""
    preferred_runtimes: list[str] = Field(default_factory=list)
    default_visibility: AgentVisibility = AgentVisibility.HELPER
    context_mode: AgentContextMode = AgentContextMode.STANDARD
    role_tier: AgentRoleTier = AgentRoleTier.WORKER
    can_delegate: bool = True
    prompt_preamble_md: str = ""
    enabled: bool = True
    sort_order: int = 0
    # MCP servers this role's workers receive (ADR-0025): None -> all enabled
    # (backward-compatible default); [] -> none; [ids] -> only those.
    mcp_server_ids: list[str] | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class AgentRoleTemplateCreate(BaseModel):
    id: str
    name: str
    description: str = ""
    preferred_runtimes: list[str] = Field(default_factory=list)
    default_visibility: AgentVisibility = AgentVisibility.HELPER
    context_mode: AgentContextMode = AgentContextMode.STANDARD
    role_tier: AgentRoleTier = AgentRoleTier.WORKER
    can_delegate: bool = True
    prompt_preamble_md: str = ""
    enabled: bool = True
    sort_order: int = 0
    mcp_server_ids: list[str] | None = None


class AgentRoleTemplateUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    preferred_runtimes: list[str] | None = None
    default_visibility: AgentVisibility | None = None
    context_mode: AgentContextMode | None = None
    role_tier: AgentRoleTier | None = None
    can_delegate: bool | None = None
    prompt_preamble_md: str | None = None
    enabled: bool | None = None
    sort_order: int | None = None
    mcp_server_ids: list[str] | None = None


class AgentSquad(BaseModel):
    id: str
    project_id: str
    name: str
    goal_md: str = ""
    status: AgentSquadStatus = AgentSquadStatus.ACTIVE
    lead_role_id: str | None = None
    # Max workers allowed to run at once; 0 = no cap (a safety bound on autonomy).
    max_concurrent: int = 0
    # Max total recorded tokens the squad may spend; 0 = no budget.
    token_budget: int = 0
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    last_activity_at: datetime = Field(default_factory=utc_now)


class AgentSquadCreate(BaseModel):
    project_id: str
    name: str
    goal_md: str = ""
    status: AgentSquadStatus = AgentSquadStatus.ACTIVE
    lead_role_id: str | None = "planner"
    max_concurrent: int = 0
    token_budget: int = 0
    source: AuditSource = AuditSource.DESKTOP


class AgentSquadUpdate(BaseModel):
    name: str | None = None
    goal_md: str | None = None
    status: AgentSquadStatus | None = None
    lead_role_id: str | None = None
    max_concurrent: int | None = None
    token_budget: int | None = None
    source: AuditSource = AuditSource.DESKTOP


class AgentWorkItem(BaseModel):
    id: str
    squad_id: str
    parent_id: str | None = None
    title: str
    instructions_md: str = ""
    status: AgentWorkItemStatus = AgentWorkItemStatus.QUEUED
    assigned_role_id: str | None = None
    personality_id: str | None = None
    preferred_runtime: str | None = None
    pty_session_id: str | None = None
    summary_md: str | None = None
    blockers_md: str | None = None
    files_touched: list[str] = Field(default_factory=list)
    suggested_next_role: str | None = None
    verdict: ReviewVerdict = Field(default_factory=ReviewVerdict)
    transcript_file_id: str | None = None
    opened_in_tab: bool = False
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    completed_at: datetime | None = None


class AgentWorkItemCreate(BaseModel):
    title: str
    instructions_md: str = ""
    assigned_role_id: str | None = None
    personality_id: str | None = None
    preferred_runtime: str | None = None
    parent_id: str | None = None
    source: AuditSource = AuditSource.DESKTOP


class AgentWorkItemDelegateRequest(BaseModel):
    title: str
    instructions_md: str = ""
    assigned_role_id: str | None = None
    preferred_runtime: str | None = None
    # Plan 3 Phase 3: launch the delegated child immediately (bounded by the squad's concurrency cap
    # + token budget). If a gate trips, the child is left QUEUED rather than erroring the delegation.
    auto_launch: bool = False
    source: AuditSource = AuditSource.DESKTOP


class AgentWorkItemLaunchRequest(BaseModel):
    preferred_runtime: str | None = None
    cwd_override: str | None = None
    env: dict[str, str] | None = None
    rows: int = Field(default=24, ge=1, le=300)
    cols: int = Field(default=80, ge=1, le=500)
    open_in_tab: bool = True
    source: AuditSource = AuditSource.DESKTOP


class AgentWorkItemHandoffRequest(BaseModel):
    status: AgentWorkItemStatus = AgentWorkItemStatus.HANDOFF
    summary_md: str
    blockers_md: str | None = None
    files_touched: list[str] = Field(default_factory=list)
    suggested_next_role: str | None = None
    verdict: ReviewVerdict = Field(default_factory=ReviewVerdict)
    # Optional self-reported token usage recorded to the ledger on handoff (ADR-0025)
    # -- so reporting is frictionless, part of the handoff a worker already does.
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    source: AuditSource = AuditSource.DESKTOP


class AgentWorkItemStatusRequest(BaseModel):
    status: AgentWorkItemStatus
    source: AuditSource = AuditSource.DESKTOP


class AgentSquadDetail(BaseModel):
    squad: AgentSquad
    role_templates: list[AgentRoleTemplate]
    work_items: list[AgentWorkItem]


def _new_id() -> str:
    return secrets.token_hex(6)


def _row_to_role(row: sqlite3.Row) -> AgentRoleTemplate:
    return AgentRoleTemplate(
        id=row["id"],
        name=row["name"],
        description=row["description"] or "",
        preferred_runtimes=_loads_list(row["preferred_runtimes_json"]),
        default_visibility=AgentVisibility(row["default_visibility"]),
        context_mode=AgentContextMode(row["context_mode"]),
        role_tier=AgentRoleTier(
            row["role_tier"] if "role_tier" in row.keys() and row["role_tier"] else "worker"
        ),
        can_delegate=bool(row["can_delegate"]),
        prompt_preamble_md=row["prompt_preamble_md"] or "",
        enabled=bool(row["enabled"]),
        sort_order=row["sort_order"],
        mcp_server_ids=(
            _loads_list_or_none(row["mcp_server_ids_json"])
            if "mcp_server_ids_json" in row.keys()
            else None
        ),
        created_at=from_iso(row["created_at"]),
        updated_at=from_iso(row["updated_at"]),
    )


def _row_to_squad(row: sqlite3.Row) -> AgentSquad:
    return AgentSquad(
        id=row["id"],
        project_id=row["project_id"],
        name=row["name"],
        goal_md=row["goal_md"] or "",
        status=AgentSquadStatus(row["status"]),
        lead_role_id=row["lead_role_id"],
        max_concurrent=(row["max_concurrent"] if "max_concurrent" in row.keys() else 0) or 0,
        token_budget=(row["token_budget"] if "token_budget" in row.keys() else 0) or 0,
        created_at=from_iso(row["created_at"]),
        updated_at=from_iso(row["updated_at"]),
        last_activity_at=from_iso(row["last_activity_at"]),
    )


def _row_to_work_item(row: sqlite3.Row) -> AgentWorkItem:
    return AgentWorkItem(
        id=row["id"],
        squad_id=row["squad_id"],
        parent_id=row["parent_id"],
        title=row["title"],
        instructions_md=row["instructions_md"] or "",
        status=AgentWorkItemStatus(row["status"]),
        assigned_role_id=row["assigned_role_id"],
        personality_id=(row["personality_id"] if "personality_id" in row.keys() else None),
        preferred_runtime=row["preferred_runtime"],
        pty_session_id=row["pty_session_id"],
        summary_md=row["summary_md"],
        blockers_md=row["blockers_md"],
        files_touched=_loads_list(row["files_touched_json"]),
        suggested_next_role=row["suggested_next_role"],
        verdict=ReviewVerdict.model_validate(_loads_dict(row["verdict_json"])),
        transcript_file_id=row["transcript_file_id"],
        opened_in_tab=bool(row["opened_in_tab"]),
        created_at=from_iso(row["created_at"]),
        updated_at=from_iso(row["updated_at"]),
        completed_at=from_iso(row["completed_at"]) if row["completed_at"] else None,
    )


def _loads_list(payload: str | None) -> list[str]:
    if not payload:
        return []
    try:
        raw = json.loads(payload)
    except json.JSONDecodeError:
        return []
    return [str(item) for item in raw] if isinstance(raw, list) else []


def _loads_list_or_none(payload: str | None) -> list[str] | None:
    """NULL column -> None (inherit-all); otherwise the parsed list (incl []-> none)."""
    if payload is None:
        return None
    return _loads_list(payload)


def _loads_dict(payload: str | None) -> dict[str, Any]:
    if not payload:
        return {}
    try:
        raw = json.loads(payload)
    except json.JSONDecodeError:
        return {}
    return raw if isinstance(raw, dict) else {}


def _seed_time() -> str:
    return to_iso(utc_now())


def seed_default_role_templates(conn: sqlite3.Connection) -> None:
    now = _seed_time()
    defaults = [
        AgentRoleTemplateCreate(
            id="boss",
            name="Boss (Orchestrator)",
            description="Top-level lead. Turns a goal into a plan and delegates to supervisors and workers.",
            preferred_runtimes=["claude", "codex", "copilot"],
            default_visibility=AgentVisibility.LEAD,
            context_mode=AgentContextMode.FULL,
            role_tier=AgentRoleTier.BOSS,
            can_delegate=True,
            prompt_preamble_md=(
                "You are the squad boss. Turn the goal into a concrete plan, decide which "
                "roles are needed, and delegate concrete tasks to supervisors and workers. "
                "Prefer existing tools and workflows over writing from scratch. Keep a "
                "crisp running summary the rest of the squad can follow."
            ),
            sort_order=5,
        ),
        AgentRoleTemplateCreate(
            id="planner",
            name="Planner",
            description="Lead agent that scopes work, breaks it down, and routes helpers.",
            preferred_runtimes=["claude", "codex", "copilot"],
            default_visibility=AgentVisibility.LEAD,
            context_mode=AgentContextMode.FULL,
            role_tier=AgentRoleTier.BOSS,
            can_delegate=True,
            prompt_preamble_md=(
                "Act as the visible lead. Clarify the goal, plan the next steps, "
                "and hand concrete tasks to helpers when it will increase throughput."
            ),
            sort_order=10,
        ),
        AgentRoleTemplateCreate(
            id="supervisor",
            name="Supervisor",
            description="Mid-level lead that owns one workstream and coordinates its workers.",
            preferred_runtimes=["claude", "codex", "copilot"],
            default_visibility=AgentVisibility.LEAD,
            context_mode=AgentContextMode.STANDARD,
            role_tier=AgentRoleTier.SUPERVISOR,
            can_delegate=True,
            prompt_preamble_md=(
                "You own one workstream for the boss. Break it into concrete worker tasks, "
                "keep them unblocked, and report a tight status back up the chain."
            ),
            sort_order=15,
        ),
        AgentRoleTemplateCreate(
            id="implementer",
            name="Implementer",
            description="Builds the code, runs checks, and reports concrete changes.",
            preferred_runtimes=["codex", "claude", "copilot"],
            default_visibility=AgentVisibility.HELPER,
            context_mode=AgentContextMode.STANDARD,
            role_tier=AgentRoleTier.WORKER,
            can_delegate=False,
            prompt_preamble_md=(
                "Bias toward implementation momentum. Make the change, run the relevant "
                "verification, and report exactly what changed."
            ),
            sort_order=20,
        ),
        AgentRoleTemplateCreate(
            id="reviewer",
            name="Reviewer",
            description="Reviews diffs, risk, regressions, and missing tests.",
            preferred_runtimes=["claude", "copilot", "codex"],
            default_visibility=AgentVisibility.HELPER,
            context_mode=AgentContextMode.MINIMAL,
            role_tier=AgentRoleTier.WORKER,
            can_delegate=False,
            prompt_preamble_md=(
                "Review with a bug-finding mindset. Prioritize concrete risks, "
                "behavioral regressions, and missing coverage."
            ),
            sort_order=30,
        ),
        AgentRoleTemplateCreate(
            id="researcher",
            name="Researcher",
            description="Explores the codebase, docs, and current constraints before changes.",
            preferred_runtimes=["claude", "copilot", "codex"],
            default_visibility=AgentVisibility.HELPER,
            context_mode=AgentContextMode.STANDARD,
            role_tier=AgentRoleTier.WORKER,
            can_delegate=False,
            prompt_preamble_md=(
                "Collect the minimal context needed to unblock the squad, then hand back "
                "a crisp summary with links, files, and next-step recommendations."
            ),
            sort_order=40,
        ),
        AgentRoleTemplateCreate(
            id="tester",
            name="Tester / QA",
            description="Writes and runs tests; reports pass/fail with the exact failing cases.",
            preferred_runtimes=["codex", "claude", "copilot"],
            default_visibility=AgentVisibility.HELPER,
            context_mode=AgentContextMode.STANDARD,
            role_tier=AgentRoleTier.WORKER,
            can_delegate=False,
            prompt_preamble_md=(
                "Own quality. Add or run tests for the change, surface concrete failures "
                "with repro steps, and confirm the fix before calling it done."
            ),
            sort_order=50,
        ),
        AgentRoleTemplateCreate(
            id="designer",
            name="Designer (UX/UI)",
            description="Owns layout, component states, accessibility, and visual polish.",
            preferred_runtimes=["claude", "copilot", "codex"],
            default_visibility=AgentVisibility.HELPER,
            context_mode=AgentContextMode.STANDARD,
            role_tier=AgentRoleTier.WORKER,
            can_delegate=False,
            prompt_preamble_md=(
                "Own the experience. Improve layout, empty/loading/error states, "
                "accessibility, and visual consistency using the existing design tokens."
            ),
            sort_order=60,
        ),
        AgentRoleTemplateCreate(
            id="docs-writer",
            name="Docs Writer",
            description="Writes and updates docs, READMEs, and changelogs to match the code.",
            preferred_runtimes=["claude", "copilot", "codex"],
            default_visibility=AgentVisibility.HELPER,
            context_mode=AgentContextMode.STANDARD,
            role_tier=AgentRoleTier.WORKER,
            can_delegate=False,
            prompt_preamble_md=(
                "Keep the written record honest. Update docs, READMEs, and changelogs so "
                "they match what the code actually does after this change."
            ),
            sort_order=70,
        ),
        AgentRoleTemplateCreate(
            id="devops",
            name="DevOps",
            description="Owns build, packaging, CI, and run/deploy scripts.",
            preferred_runtimes=["codex", "claude", "copilot"],
            default_visibility=AgentVisibility.HELPER,
            context_mode=AgentContextMode.STANDARD,
            role_tier=AgentRoleTier.WORKER,
            can_delegate=False,
            prompt_preamble_md=(
                "Own the pipeline. Make builds, packaging, and run scripts reliable and "
                "reproducible; verify they pass before handing back."
            ),
            sort_order=80,
        ),
        AgentRoleTemplateCreate(
            id="security",
            name="Security",
            description="Audits for vulnerabilities, secret leaks, and unsafe defaults.",
            preferred_runtimes=["claude", "copilot", "codex"],
            default_visibility=AgentVisibility.HELPER,
            context_mode=AgentContextMode.MINIMAL,
            role_tier=AgentRoleTier.WORKER,
            can_delegate=False,
            prompt_preamble_md=(
                "Audit with an attacker mindset. Flag vulnerabilities, leaked secrets, and "
                "unsafe defaults, with concrete severity and a recommended fix."
            ),
            sort_order=90,
        ),
        AgentRoleTemplateCreate(
            id="interaction-contract-steward",
            name="Interaction Contract Steward",
            description="Promotes real interaction bugs into durable UI contracts and blocking gates.",
            preferred_runtimes=["claude", "codex", "copilot"],
            default_visibility=AgentVisibility.HELPER,
            context_mode=AgentContextMode.STANDARD,
            role_tier=AgentRoleTier.WORKER,
            can_delegate=False,
            prompt_preamble_md=(
                "When you find a real UI interaction bug, describe the failing contract, the exact "
                "surface and action it belongs to, and what browser proof should prevent it from returning."
            ),
            sort_order=95,
        ),
        AgentRoleTemplateCreate(
            id="surface-cartographer",
            name="Surface Cartographer",
            description="Maps changed files to affected routes, dialogs, cards, and dependent views.",
            preferred_runtimes=["codex", "claude", "copilot"],
            default_visibility=AgentVisibility.HELPER,
            context_mode=AgentContextMode.MINIMAL,
            role_tier=AgentRoleTier.WORKER,
            can_delegate=False,
            prompt_preamble_md=(
                "Think in blast radius. Identify what surfaces changed directly, what linked surfaces "
                "should be rechecked, and which UI contracts ought to rerun."
            ),
            sort_order=100,
        ),
        AgentRoleTemplateCreate(
            id="launch-verifier",
            name="Launch Verifier",
            description="Checks launch, stop, save, and dismiss flows with a skepticism-first mindset.",
            preferred_runtimes=["claude", "codex", "copilot"],
            default_visibility=AgentVisibility.HELPER,
            context_mode=AgentContextMode.STANDARD,
            role_tier=AgentRoleTier.WORKER,
            can_delegate=False,
            prompt_preamble_md=(
                "Prioritize critical controls. A launch, stop, close, or save button that looks right "
                "but does nothing is a release blocker until browser proof says otherwise."
            ),
            sort_order=105,
        ),
        AgentRoleTemplateCreate(
            id="responsive-accessibility-critic",
            name="Responsive Accessibility Critic",
            description="Hunts for small UI fit-and-finish failures across viewport, focus, spacing, and dismissal behavior.",
            preferred_runtimes=["claude", "codex", "copilot"],
            default_visibility=AgentVisibility.HELPER,
            context_mode=AgentContextMode.STANDARD,
            role_tier=AgentRoleTier.WORKER,
            can_delegate=False,
            prompt_preamble_md=(
                "Look for visual strain, focus problems, double-scroll layouts, modal escape failures, "
                "misalignment, and density issues that make the product feel unfinished."
            ),
            sort_order=110,
        ),
        AgentRoleTemplateCreate(
            id="ui-judge",
            name="UI Judge",
            description="Compares candidate UI outcomes and explains why the winner should actually be trusted.",
            preferred_runtimes=["claude", "codex", "copilot"],
            default_visibility=AgentVisibility.HELPER,
            context_mode=AgentContextMode.STANDARD,
            role_tier=AgentRoleTier.SUPERVISOR,
            can_delegate=True,
            prompt_preamble_md=(
                "Judge with evidence, not vibes. Compare quality, regressions, token cost, and proof artifacts "
                "before declaring a winner."
            ),
            sort_order=115,
        ),
        AgentRoleTemplateCreate(
            id="project-flow-steward",
            name="Project Flow Steward",
            description="Protects one-window project targeting, inline creation, and return-to-caller continuation paths.",
            preferred_runtimes=["codex", "claude", "copilot"],
            default_visibility=AgentVisibility.HELPER,
            context_mode=AgentContextMode.STANDARD,
            role_tier=AgentRoleTier.WORKER,
            can_delegate=False,
            prompt_preamble_md=(
                "Watch for workflow dead ends. Users should be able to choose or create the right project "
                "without being bounced away from the task they are already doing."
            ),
            sort_order=120,
        ),
    ]
    for item in defaults:
        conn.execute(
            """
            INSERT OR IGNORE INTO agent_role_templates (
                id, name, description, preferred_runtimes_json, default_visibility,
                context_mode, role_tier, can_delegate, prompt_preamble_md, enabled, sort_order,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                item.id,
                item.name,
                item.description,
                json.dumps(item.preferred_runtimes),
                item.default_visibility.value,
                item.context_mode.value,
                item.role_tier.value,
                1 if item.can_delegate else 0,
                item.prompt_preamble_md,
                1 if item.enabled else 0,
                item.sort_order,
                now,
                now,
            ),
        )


def list_role_templates(conn: sqlite3.Connection) -> list[AgentRoleTemplate]:
    rows = conn.execute(
        "SELECT * FROM agent_role_templates ORDER BY sort_order, name"
    ).fetchall()
    return [_row_to_role(row) for row in rows]


def get_role_template(conn: sqlite3.Connection, role_id: str) -> AgentRoleTemplate:
    row = conn.execute(
        "SELECT * FROM agent_role_templates WHERE id = ?", (role_id,)
    ).fetchone()
    if row is None:
        raise not_found("agent_role_template", role_id)
    return _row_to_role(row)


def create_role_template(
    conn: sqlite3.Connection, payload: AgentRoleTemplateCreate
) -> AgentRoleTemplate:
    now = utc_now()
    conn.execute(
        """
        INSERT INTO agent_role_templates (
            id, name, description, preferred_runtimes_json, default_visibility,
            context_mode, role_tier, can_delegate, prompt_preamble_md, enabled, sort_order,
            mcp_server_ids_json, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            payload.id,
            payload.name,
            payload.description,
            json.dumps(payload.preferred_runtimes),
            payload.default_visibility.value,
            payload.context_mode.value,
            payload.role_tier.value,
            1 if payload.can_delegate else 0,
            payload.prompt_preamble_md,
            1 if payload.enabled else 0,
            payload.sort_order,
            json.dumps(payload.mcp_server_ids) if payload.mcp_server_ids is not None else None,
            to_iso(now),
            to_iso(now),
        ),
    )
    return get_role_template(conn, payload.id)


def update_role_template(
    conn: sqlite3.Connection, role_id: str, patch: AgentRoleTemplateUpdate
) -> AgentRoleTemplate:
    current = get_role_template(conn, role_id)
    updated = current.model_copy(
        update={
            key: value
            for key, value in patch.model_dump(exclude_none=True).items()
        }
    )
    now = utc_now()
    conn.execute(
        """
        UPDATE agent_role_templates
        SET name = ?, description = ?, preferred_runtimes_json = ?, default_visibility = ?,
            context_mode = ?, role_tier = ?, can_delegate = ?, prompt_preamble_md = ?, enabled = ?,
            sort_order = ?, mcp_server_ids_json = ?, updated_at = ?
        WHERE id = ?
        """,
        (
            updated.name,
            updated.description,
            json.dumps(updated.preferred_runtimes),
            updated.default_visibility.value,
            updated.context_mode.value,
            updated.role_tier.value,
            1 if updated.can_delegate else 0,
            updated.prompt_preamble_md,
            1 if updated.enabled else 0,
            updated.sort_order,
            json.dumps(updated.mcp_server_ids) if updated.mcp_server_ids is not None else None,
            to_iso(now),
            role_id,
        ),
    )
    return get_role_template(conn, role_id)


def delete_role_template(conn: sqlite3.Connection, role_id: str) -> None:
    get_role_template(conn, role_id)
    conn.execute("DELETE FROM agent_role_templates WHERE id = ?", (role_id,))


def list_squads(conn: sqlite3.Connection) -> list[AgentSquad]:
    rows = conn.execute(
        "SELECT * FROM agent_squads ORDER BY last_activity_at DESC, created_at DESC"
    ).fetchall()
    return [_row_to_squad(row) for row in rows]


def get_squad(conn: sqlite3.Connection, squad_id: str) -> AgentSquad:
    row = conn.execute("SELECT * FROM agent_squads WHERE id = ?", (squad_id,)).fetchone()
    if row is None:
        raise not_found("agent_squad", squad_id)
    return _row_to_squad(row)


def create_squad(conn: sqlite3.Connection, payload: AgentSquadCreate) -> AgentSquad:
    now = utc_now()
    squad_id = _new_id()
    conn.execute(
        """
        INSERT INTO agent_squads (
            id, project_id, name, goal_md, status, lead_role_id, max_concurrent, token_budget,
            created_at, updated_at, last_activity_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            squad_id,
            payload.project_id,
            payload.name,
            payload.goal_md,
            payload.status.value,
            payload.lead_role_id,
            payload.max_concurrent,
            payload.token_budget,
            to_iso(now),
            to_iso(now),
            to_iso(now),
        ),
    )
    return get_squad(conn, squad_id)


def update_squad(
    conn: sqlite3.Connection, squad_id: str, patch: AgentSquadUpdate
) -> AgentSquad:
    current = get_squad(conn, squad_id)
    data = patch.model_dump(exclude_none=True)
    updated = current.model_copy(update={k: v for k, v in data.items() if k != "source"})
    now = utc_now()
    conn.execute(
        """
        UPDATE agent_squads
        SET name = ?, goal_md = ?, status = ?, lead_role_id = ?, max_concurrent = ?, token_budget = ?,
            updated_at = ?, last_activity_at = ?
        WHERE id = ?
        """,
        (
            updated.name,
            updated.goal_md,
            updated.status.value,
            updated.lead_role_id,
            updated.max_concurrent,
            updated.token_budget,
            to_iso(now),
            to_iso(now),
            squad_id,
        ),
    )
    return get_squad(conn, squad_id)


def delete_squad(conn: sqlite3.Connection, squad_id: str) -> None:
    get_squad(conn, squad_id)
    conn.execute("DELETE FROM agent_squads WHERE id = ?", (squad_id,))


def list_work_items(conn: sqlite3.Connection, squad_id: str) -> list[AgentWorkItem]:
    rows = conn.execute(
        "SELECT * FROM agent_work_items WHERE squad_id = ? ORDER BY created_at",
        (squad_id,),
    ).fetchall()
    return [_row_to_work_item(row) for row in rows]


def count_running_work_items(conn: sqlite3.Connection, squad_id: str) -> int:
    """How many of a squad's workers are currently RUNNING (for the concurrency cap)."""
    row = conn.execute(
        "SELECT COUNT(*) AS n FROM agent_work_items WHERE squad_id = ? AND status = ?",
        (squad_id, AgentWorkItemStatus.RUNNING.value),
    ).fetchone()
    return int(row["n"]) if row else 0


def get_work_item(conn: sqlite3.Connection, work_item_id: str) -> AgentWorkItem:
    row = conn.execute(
        "SELECT * FROM agent_work_items WHERE id = ?", (work_item_id,)
    ).fetchone()
    if row is None:
        raise not_found("agent_work_item", work_item_id)
    return _row_to_work_item(row)


def create_work_item(
    conn: sqlite3.Connection, squad_id: str, payload: AgentWorkItemCreate
) -> AgentWorkItem:
    get_squad(conn, squad_id)
    now = utc_now()
    work_item_id = _new_id()
    conn.execute(
        """
        INSERT INTO agent_work_items (
            id, squad_id, parent_id, title, instructions_md, status, assigned_role_id, personality_id,
            preferred_runtime, pty_session_id, summary_md, blockers_md, files_touched_json,
            suggested_next_role, verdict_json, transcript_file_id, opened_in_tab, created_at, updated_at, completed_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, NULL, ?, NULL, ?, NULL, 0, ?, ?, NULL)
        """,
        (
            work_item_id,
            squad_id,
            payload.parent_id,
            payload.title,
            payload.instructions_md,
            AgentWorkItemStatus.QUEUED.value,
            payload.assigned_role_id,
            payload.personality_id,
            payload.preferred_runtime,
            json.dumps([]),
            json.dumps(ReviewVerdict().model_dump(mode="json")),
            to_iso(now),
            to_iso(now),
        ),
    )
    touch_squad_activity(conn, squad_id, when=now)
    return get_work_item(conn, work_item_id)


def set_work_item_session(
    conn: sqlite3.Connection,
    work_item_id: str,
    *,
    status: AgentWorkItemStatus,
    pty_session_id: str,
    chosen_runtime: str,
    opened_in_tab: bool,
) -> AgentWorkItem:
    current = get_work_item(conn, work_item_id)
    now = utc_now()
    conn.execute(
        """
        UPDATE agent_work_items
        SET status = ?, pty_session_id = ?, preferred_runtime = ?, opened_in_tab = ?,
            updated_at = ?, completed_at = NULL
        WHERE id = ?
        """,
        (
            status.value,
            pty_session_id,
            chosen_runtime,
            1 if opened_in_tab else 0,
            to_iso(now),
            work_item_id,
        ),
    )
    touch_squad_activity(conn, current.squad_id, when=now)
    return get_work_item(conn, work_item_id)


def handoff_work_item(
    conn: sqlite3.Connection,
    work_item_id: str,
    payload: AgentWorkItemHandoffRequest,
) -> AgentWorkItem:
    current = get_work_item(conn, work_item_id)
    now = utc_now()
    completed_at = to_iso(now) if payload.status == AgentWorkItemStatus.COMPLETED else None
    conn.execute(
        """
        UPDATE agent_work_items
        SET status = ?, summary_md = ?, blockers_md = ?, files_touched_json = ?,
            suggested_next_role = ?, verdict_json = ?, updated_at = ?, completed_at = COALESCE(?, completed_at)
        WHERE id = ?
        """,
        (
            payload.status.value,
            payload.summary_md,
            payload.blockers_md,
            json.dumps(payload.files_touched),
            payload.suggested_next_role,
            json.dumps(payload.verdict.model_dump(mode="json")),
            to_iso(now),
            completed_at,
            work_item_id,
        ),
    )
    touch_squad_activity(conn, current.squad_id, when=now)
    return get_work_item(conn, work_item_id)


def update_work_item_status(
    conn: sqlite3.Connection,
    work_item_id: str,
    status: AgentWorkItemStatus,
) -> AgentWorkItem:
    current = get_work_item(conn, work_item_id)
    now = utc_now()
    completed_at = to_iso(now) if status == AgentWorkItemStatus.COMPLETED else None
    conn.execute(
        """
        UPDATE agent_work_items
        SET status = ?, updated_at = ?, completed_at = COALESCE(?, completed_at)
        WHERE id = ?
        """,
        (
            status.value,
            to_iso(now),
            completed_at,
            work_item_id,
        ),
    )
    touch_squad_activity(conn, current.squad_id, when=now)
    return get_work_item(conn, work_item_id)


def touch_squad_activity(
    conn: sqlite3.Connection, squad_id: str, *, when: datetime | None = None
) -> None:
    now = when or utc_now()
    conn.execute(
        "UPDATE agent_squads SET updated_at = ?, last_activity_at = ? WHERE id = ?",
        (to_iso(now), to_iso(now), squad_id),
    )


def squad_detail(conn: sqlite3.Connection, squad_id: str) -> AgentSquadDetail:
    squad = get_squad(conn, squad_id)
    roles = list_role_templates(conn)
    work_items = list_work_items(conn, squad_id)
    return AgentSquadDetail(squad=squad, role_templates=roles, work_items=work_items)


def pick_runtime(
    role: AgentRoleTemplate | None,
    override: str | None = None,
) -> str:
    if override:
        return override
    if role is None:
        return "powershell.exe" if sys.platform == "win32" else "bash"
    for candidate in role.preferred_runtimes:
        if resolve_command(candidate):
            return candidate
    if role.preferred_runtimes:
        return role.preferred_runtimes[0]
    return "powershell.exe" if sys.platform == "win32" else "bash"


def argv_for_runtime(runtime: str) -> list[str]:
    if runtime == "shell":
        if sys.platform == "win32":
            return ["powershell.exe", "-NoLogo"]
        if sys.platform == "darwin":
            return ["zsh", "-i"]
        return ["bash", "-i"]
    return [runtime]


def lead_session_id_for_squad(conn: sqlite3.Connection, squad_id: str) -> str | None:
    squad = get_squad(conn, squad_id)
    if squad.lead_role_id:
        row = conn.execute(
            """
            SELECT pty_session_id
            FROM agent_work_items
            WHERE squad_id = ? AND assigned_role_id = ? AND pty_session_id IS NOT NULL
            ORDER BY updated_at DESC LIMIT 1
            """,
            (squad_id, squad.lead_role_id),
        ).fetchone()
        if row and row["pty_session_id"]:
            return str(row["pty_session_id"])
    fallback = conn.execute(
        """
        SELECT pty_session_id
        FROM agent_work_items
        WHERE squad_id = ? AND parent_id IS NULL AND pty_session_id IS NOT NULL
        ORDER BY updated_at DESC LIMIT 1
        """,
        (squad_id,),
    ).fetchone()
    return str(fallback["pty_session_id"]) if fallback and fallback["pty_session_id"] else None


def work_item_by_session(
    conn: sqlite3.Connection, session_id: str
) -> AgentWorkItem | None:
    row = conn.execute(
        "SELECT * FROM agent_work_items WHERE pty_session_id = ?",
        (session_id,),
    ).fetchone()
    return _row_to_work_item(row) if row else None


def complete_work_item_from_session_exit(
    conn: sqlite3.Connection,
    *,
    session_id: str,
    exit_code: int | None,
) -> AgentWorkItem | None:
    item = work_item_by_session(conn, session_id)
    if item is None:
        return None
    row = conn.execute(
        """
        SELECT id
        FROM project_files
        WHERE source = 'transcript' AND source_session = ?
        ORDER BY uploaded_at DESC LIMIT 1
        """,
        (session_id,),
    ).fetchone()
    transcript_file_id = row["id"] if row else None
    now = utc_now()
    next_status = item.status
    if item.status == AgentWorkItemStatus.RUNNING:
        next_status = AgentWorkItemStatus.COMPLETED if exit_code in (0, None) else AgentWorkItemStatus.BLOCKED
    conn.execute(
        """
        UPDATE agent_work_items
        SET status = ?, transcript_file_id = COALESCE(?, transcript_file_id),
            updated_at = ?, completed_at = COALESCE(completed_at, ?)
        WHERE id = ?
        """,
        (
            next_status.value,
            transcript_file_id,
            to_iso(now),
            to_iso(now) if next_status == AgentWorkItemStatus.COMPLETED else None,
            item.id,
        ),
    )
    touch_squad_activity(conn, item.squad_id, when=now)
    return get_work_item(conn, item.id)


def validate_role_can_delegate(conn: sqlite3.Connection, role_id: str | None) -> None:
    if not role_id:
        return
    role = get_role_template(conn, role_id)
    if not role.can_delegate:
        raise invalid("agent_work_item", f"Role '{role_id}' cannot delegate child work items.")
