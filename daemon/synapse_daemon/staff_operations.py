"""Advanced operating layer for persistent AI staff.

Keeps staff identity (staff.py) separate from the operational data that grows over
time: responsibilities, KPIs, memories, permissions, triggers, channels,
relationships, events, routing, and team briefings.
"""

from __future__ import annotations

import json
import secrets
import sqlite3
from typing import Any

from pydantic import BaseModel, Field

from . import agent_squads
from .errors import conflict, invalid, not_found
from .staff import StaffAuthority, StaffMember, get_staff, list_staff
from .time_utils import to_iso, utc_now


def _id(prefix: str) -> str:
    return f"{prefix}-{secrets.token_hex(5)}"


def _now() -> str:
    return to_iso(utc_now())


def _loads(raw: str | None, default: Any) -> Any:
    if not raw:
        return default
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return default


class StaffResponsibility(BaseModel):
    id: str
    staff_member_id: str
    title: str
    description: str = ""
    priority: str = "medium"
    cadence: str = ""
    enabled: bool = True
    sort_order: int = 0
    created_at: str
    updated_at: str


class StaffKpi(BaseModel):
    id: str
    staff_member_id: str
    name: str
    description: str = ""
    unit: str = ""
    direction: str = "increase"
    target_value: float | None = None
    target_min: float | None = None
    target_max: float | None = None
    current_value: float | None = None
    status: str = "unknown"
    source: str = "manual"
    period: str = ""
    sort_order: int = 0
    created_at: str
    updated_at: str


class StaffKpiCreate(BaseModel):
    name: str
    description: str = ""
    unit: str = ""
    direction: str = "increase"
    target_value: float | None = None
    target_min: float | None = None
    target_max: float | None = None
    current_value: float | None = None
    status: str = "unknown"
    source: str = "manual"
    period: str = ""
    sort_order: int = 0


class StaffKpiUpdate(BaseModel):
    current_value: float | None = None
    status: str | None = None
    target_value: float | None = None
    target_min: float | None = None
    target_max: float | None = None
    source: str | None = None
    description: str | None = None
    period: str | None = None


class StaffMemory(BaseModel):
    id: str
    staff_member_id: str
    kind: str
    title: str
    body_md: str = ""
    tags: list[str] = Field(default_factory=list)
    importance: int = 3
    pinned: bool = False
    source: str = "owner"
    created_at: str
    updated_at: str


class StaffMemoryCreate(BaseModel):
    kind: str = "observation"
    title: str
    body_md: str = ""
    tags: list[str] = Field(default_factory=list)
    importance: int = Field(default=3, ge=1, le=5)
    pinned: bool = False
    source: str = "owner"


class StaffPermission(BaseModel):
    id: str
    staff_member_id: str
    scope_type: str
    scope_id: str
    capability: str
    decision: str
    limits: dict[str, Any] = Field(default_factory=dict)
    reason: str = ""
    created_at: str
    updated_at: str


class StaffPermissionCreate(BaseModel):
    scope_type: str
    scope_id: str
    capability: str
    decision: str
    limits: dict[str, Any] = Field(default_factory=dict)
    reason: str = ""


class StaffTrigger(BaseModel):
    id: str
    staff_member_id: str
    name: str
    trigger_type: str
    config: dict[str, Any] = Field(default_factory=dict)
    prompt_md: str = ""
    enabled: bool = False
    last_run_at: str | None = None
    next_run_at: str | None = None
    created_at: str
    updated_at: str


class StaffTriggerCreate(BaseModel):
    name: str
    trigger_type: str
    config: dict[str, Any] = Field(default_factory=dict)
    prompt_md: str = ""
    enabled: bool = False
    next_run_at: str | None = None


class StaffChannelConnection(BaseModel):
    id: str
    staff_member_id: str
    channel: str
    status: str
    account_label: str | None = None
    external_id: str | None = None
    capabilities: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: str
    updated_at: str


class StaffRelationship(BaseModel):
    from_staff_id: str
    to_staff_id: str
    relationship: str
    notes: str = ""
    created_at: str
    updated_at: str


class StaffEvent(BaseModel):
    id: str
    staff_member_id: str
    event_type: str
    title: str
    body_md: str = ""
    severity: str = "info"
    action_required: bool = False
    source: str = "system"
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: str


class StaffRouteCandidate(BaseModel):
    staff_id: str
    handle: str
    display_name: str
    title: str
    score: int
    reasons: list[str] = Field(default_factory=list)


class StaffRouteResult(BaseModel):
    selected: StaffRouteCandidate
    candidates: list[StaffRouteCandidate]
    explicit: bool = False


def _responsibility(row: sqlite3.Row) -> StaffResponsibility:
    return StaffResponsibility(
        id=row["id"], staff_member_id=row["staff_member_id"], title=row["title"],
        description=row["description"] or "", priority=row["priority"],
        cadence=row["cadence"] or "", enabled=bool(row["enabled"]),
        sort_order=int(row["sort_order"] or 0), created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _kpi(row: sqlite3.Row) -> StaffKpi:
    return StaffKpi(**dict(row))


def _memory(row: sqlite3.Row) -> StaffMemory:
    return StaffMemory(
        id=row["id"], staff_member_id=row["staff_member_id"], kind=row["kind"],
        title=row["title"], body_md=row["body_md"] or "",
        tags=list(_loads(row["tags_json"], [])), importance=int(row["importance"]),
        pinned=bool(row["pinned"]), source=row["source"],
        created_at=row["created_at"], updated_at=row["updated_at"],
    )


def _permission(row: sqlite3.Row) -> StaffPermission:
    return StaffPermission(
        id=row["id"], staff_member_id=row["staff_member_id"],
        scope_type=row["scope_type"], scope_id=row["scope_id"],
        capability=row["capability"], decision=row["decision"],
        limits=dict(_loads(row["limits_json"], {})), reason=row["reason"] or "",
        created_at=row["created_at"], updated_at=row["updated_at"],
    )


def _trigger(row: sqlite3.Row) -> StaffTrigger:
    return StaffTrigger(
        id=row["id"], staff_member_id=row["staff_member_id"], name=row["name"],
        trigger_type=row["trigger_type"], config=dict(_loads(row["config_json"], {})),
        prompt_md=row["prompt_md"] or "", enabled=bool(row["enabled"]),
        last_run_at=row["last_run_at"], next_run_at=row["next_run_at"],
        created_at=row["created_at"], updated_at=row["updated_at"],
    )


def _channel(row: sqlite3.Row) -> StaffChannelConnection:
    return StaffChannelConnection(
        id=row["id"], staff_member_id=row["staff_member_id"], channel=row["channel"],
        status=row["status"], account_label=row["account_label"],
        external_id=row["external_id"],
        capabilities=list(_loads(row["capabilities_json"], [])),
        metadata=dict(_loads(row["metadata_json"], {})),
        created_at=row["created_at"], updated_at=row["updated_at"],
    )


def _relationship(row: sqlite3.Row) -> StaffRelationship:
    return StaffRelationship(**dict(row))


def _event(row: sqlite3.Row) -> StaffEvent:
    return StaffEvent(
        id=row["id"], staff_member_id=row["staff_member_id"],
        event_type=row["event_type"], title=row["title"], body_md=row["body_md"] or "",
        severity=row["severity"], action_required=bool(row["action_required"]),
        source=row["source"], metadata=dict(_loads(row["metadata_json"], {})),
        created_at=row["created_at"],
    )


def list_responsibilities(conn: sqlite3.Connection, staff_id: str) -> list[StaffResponsibility]:
    member = get_staff(conn, staff_id)
    rows = conn.execute(
        "SELECT * FROM staff_responsibilities WHERE staff_member_id=? "
        "ORDER BY enabled DESC, sort_order, title", (member.id,)
    ).fetchall()
    return [_responsibility(row) for row in rows]


def list_kpis(conn: sqlite3.Connection, staff_id: str) -> list[StaffKpi]:
    member = get_staff(conn, staff_id)
    rows = conn.execute(
        "SELECT * FROM staff_kpis WHERE staff_member_id=? ORDER BY sort_order, name",
        (member.id,),
    ).fetchall()
    return [_kpi(row) for row in rows]


def create_kpi(conn: sqlite3.Connection, staff_id: str, payload: StaffKpiCreate) -> StaffKpi:
    member = get_staff(conn, staff_id)
    if payload.status not in {"unknown", "on_track", "watch", "off_track"}:
        raise invalid("staff_kpi", "Unknown KPI status.")
    if payload.direction not in {"increase", "decrease", "range", "maintain"}:
        raise invalid("staff_kpi", "Unknown KPI direction.")
    now = _now()
    kpi_id = _id("kpi")
    conn.execute(
        """INSERT INTO staff_kpis
        (id,staff_member_id,name,description,unit,direction,target_value,target_min,target_max,
         current_value,status,source,period,sort_order,created_at,updated_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            kpi_id, member.id, payload.name, payload.description, payload.unit,
            payload.direction, payload.target_value, payload.target_min, payload.target_max,
            payload.current_value, payload.status, payload.source, payload.period,
            payload.sort_order, now, now,
        ),
    )
    return _kpi(conn.execute("SELECT * FROM staff_kpis WHERE id=?", (kpi_id,)).fetchone())


def update_kpi(
    conn: sqlite3.Connection, staff_id: str, kpi_id: str, payload: StaffKpiUpdate
) -> StaffKpi:
    member = get_staff(conn, staff_id)
    row = conn.execute(
        "SELECT * FROM staff_kpis WHERE id=? AND staff_member_id=?", (kpi_id, member.id)
    ).fetchone()
    if row is None:
        raise not_found("staff_kpi", kpi_id)
    data = payload.model_dump(exclude_unset=True)
    if data.get("status") is not None and data["status"] not in {"unknown", "on_track", "watch", "off_track"}:
        raise invalid("staff_kpi", "Unknown KPI status.")
    if data:
        sets = [f"{key}=?" for key in data]
        args = list(data.values()) + [_now(), kpi_id, member.id]
        conn.execute(
            f"UPDATE staff_kpis SET {', '.join(sets)}, updated_at=? WHERE id=? AND staff_member_id=?",
            args,
        )
    return _kpi(conn.execute("SELECT * FROM staff_kpis WHERE id=?", (kpi_id,)).fetchone())


def list_memories(conn: sqlite3.Connection, staff_id: str, limit: int = 50) -> list[StaffMemory]:
    member = get_staff(conn, staff_id)
    rows = conn.execute(
        "SELECT * FROM staff_memories WHERE staff_member_id=? "
        "ORDER BY pinned DESC, importance DESC, updated_at DESC LIMIT ?",
        (member.id, max(1, min(limit, 200))),
    ).fetchall()
    return [_memory(row) for row in rows]


def create_memory(
    conn: sqlite3.Connection, staff_id: str, payload: StaffMemoryCreate
) -> StaffMemory:
    member = get_staff(conn, staff_id)
    if payload.kind not in {"profile", "decision", "lesson", "preference", "observation"}:
        raise invalid("staff_memory", "Unknown memory kind.")
    now = _now()
    memory_id = _id("mem")
    conn.execute(
        """INSERT INTO staff_memories
        (id,staff_member_id,kind,title,body_md,tags_json,importance,pinned,source,created_at,updated_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (
            memory_id, member.id, payload.kind, payload.title, payload.body_md,
            json.dumps(payload.tags), payload.importance, int(payload.pinned),
            payload.source, now, now,
        ),
    )
    return _memory(conn.execute("SELECT * FROM staff_memories WHERE id=?", (memory_id,)).fetchone())


def list_permissions(conn: sqlite3.Connection, staff_id: str) -> list[StaffPermission]:
    member = get_staff(conn, staff_id)
    rows = conn.execute(
        "SELECT * FROM staff_permissions WHERE staff_member_id=? "
        "ORDER BY scope_type, scope_id, capability", (member.id,)
    ).fetchall()
    return [_permission(row) for row in rows]


def upsert_permission(
    conn: sqlite3.Connection, staff_id: str, payload: StaffPermissionCreate
) -> StaffPermission:
    member = get_staff(conn, staff_id)
    if payload.decision not in {"allow", "ask", "deny"}:
        raise invalid("staff_permission", "Decision must be allow, ask, or deny.")
    now = _now()
    existing = conn.execute(
        """SELECT id FROM staff_permissions
           WHERE staff_member_id=? AND scope_type=? AND scope_id=? AND capability=?""",
        (member.id, payload.scope_type, payload.scope_id, payload.capability),
    ).fetchone()
    permission_id = existing["id"] if existing else _id("perm")
    conn.execute(
        """INSERT INTO staff_permissions
        (id,staff_member_id,scope_type,scope_id,capability,decision,limits_json,reason,created_at,updated_at)
        VALUES (?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(staff_member_id,scope_type,scope_id,capability) DO UPDATE SET
          decision=excluded.decision, limits_json=excluded.limits_json,
          reason=excluded.reason, updated_at=excluded.updated_at""",
        (
            permission_id, member.id, payload.scope_type, payload.scope_id,
            payload.capability, payload.decision, json.dumps(payload.limits),
            payload.reason, now, now,
        ),
    )
    row = conn.execute(
        """SELECT * FROM staff_permissions
           WHERE staff_member_id=? AND scope_type=? AND scope_id=? AND capability=?""",
        (member.id, payload.scope_type, payload.scope_id, payload.capability),
    ).fetchone()
    return _permission(row)


def permission_decision(
    conn: sqlite3.Connection,
    staff_id: str,
    *,
    scope_type: str,
    scope_id: str,
    capability: str,
    default: str = "ask",
) -> StaffPermission | None:
    member = get_staff(conn, staff_id)
    for candidate_scope in (scope_id, "*"):
        row = conn.execute(
            """SELECT * FROM staff_permissions
               WHERE staff_member_id=? AND scope_type=? AND scope_id=? AND capability=?""",
            (member.id, scope_type, candidate_scope, capability),
        ).fetchone()
        if row is not None:
            return _permission(row)
    return None


def assert_project_work_allowed(conn: sqlite3.Connection, member: StaffMember, project_id: str) -> None:
    explicit = permission_decision(
        conn, member.id, scope_type="project", scope_id=project_id, capability="work"
    )
    if explicit is not None and explicit.decision == "deny":
        raise conflict(
            "staff_permission",
            f"{member.display_name} is not allowed to work on project {project_id}.",
            staff_id=member.id,
            project_id=project_id,
        )
    if member.assigned_project_ids and project_id not in member.assigned_project_ids:
        if explicit is None or explicit.decision != "allow":
            raise conflict(
                "staff_permission",
                f"{member.display_name} is not assigned to project {project_id}.",
                staff_id=member.id,
                project_id=project_id,
            )


def list_triggers(conn: sqlite3.Connection, staff_id: str) -> list[StaffTrigger]:
    member = get_staff(conn, staff_id)
    rows = conn.execute(
        "SELECT * FROM staff_triggers WHERE staff_member_id=? ORDER BY enabled DESC, name",
        (member.id,),
    ).fetchall()
    return [_trigger(row) for row in rows]


def create_trigger(
    conn: sqlite3.Connection, staff_id: str, payload: StaffTriggerCreate
) -> StaffTrigger:
    member = get_staff(conn, staff_id)
    if payload.trigger_type not in {"schedule", "event", "condition"}:
        raise invalid("staff_trigger", "Unknown trigger type.")
    now = _now()
    trigger_id = _id("trigger")
    conn.execute(
        """INSERT INTO staff_triggers
        (id,staff_member_id,name,trigger_type,config_json,prompt_md,enabled,last_run_at,next_run_at,created_at,updated_at)
        VALUES (?,?,?,?,?,?,?,NULL,?,?,?)""",
        (
            trigger_id, member.id, payload.name, payload.trigger_type,
            json.dumps(payload.config), payload.prompt_md, int(payload.enabled),
            payload.next_run_at, now, now,
        ),
    )
    return _trigger(conn.execute("SELECT * FROM staff_triggers WHERE id=?", (trigger_id,)).fetchone())


def list_channels(conn: sqlite3.Connection, staff_id: str) -> list[StaffChannelConnection]:
    member = get_staff(conn, staff_id)
    rows = conn.execute(
        "SELECT * FROM staff_channel_connections WHERE staff_member_id=? ORDER BY channel",
        (member.id,),
    ).fetchall()
    return [_channel(row) for row in rows]


def list_relationships(conn: sqlite3.Connection, staff_id: str) -> list[StaffRelationship]:
    member = get_staff(conn, staff_id)
    rows = conn.execute(
        """SELECT * FROM staff_relationships
           WHERE from_staff_id=? OR to_staff_id=?
           ORDER BY relationship, from_staff_id, to_staff_id""",
        (member.id, member.id),
    ).fetchall()
    return [_relationship(row) for row in rows]


def list_events(conn: sqlite3.Connection, staff_id: str, limit: int = 40) -> list[StaffEvent]:
    member = get_staff(conn, staff_id)
    rows = conn.execute(
        "SELECT * FROM staff_events WHERE staff_member_id=? ORDER BY created_at DESC LIMIT ?",
        (member.id, max(1, min(limit, 200))),
    ).fetchall()
    return [_event(row) for row in rows]


def record_event(
    conn: sqlite3.Connection,
    staff_id: str,
    *,
    event_type: str,
    title: str,
    body_md: str = "",
    severity: str = "info",
    action_required: bool = False,
    source: str = "system",
    metadata: dict[str, Any] | None = None,
) -> StaffEvent:
    member = get_staff(conn, staff_id)
    if severity not in {"info", "success", "warning", "critical"}:
        raise invalid("staff_event", "Unknown event severity.")
    event_id = _id("event")
    conn.execute(
        """INSERT INTO staff_events
        (id,staff_member_id,event_type,title,body_md,severity,action_required,source,metadata_json,created_at)
        VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (
            event_id, member.id, event_type, title, body_md, severity,
            int(action_required), source, json.dumps(metadata or {}), _now(),
        ),
    )
    return _event(conn.execute("SELECT * FROM staff_events WHERE id=?", (event_id,)).fetchone())


def staff_for_work_item(conn: sqlite3.Connection, work_item_id: str) -> StaffMember | None:
    row = conn.execute(
        """SELECT sm.* FROM staff_work_items sw
           JOIN staff_members sm ON sm.id=sw.staff_member_id
           WHERE sw.work_item_id=? LIMIT 1""",
        (work_item_id,),
    ).fetchone()
    if row is None:
        return None
    return StaffMember(
        id=row["id"], handle=row["handle"], display_name=row["display_name"],
        title=row["title"], role_template_id=row["role_template_id"],
        personality_id=row["personality_id"], avatar_asset_id=row["avatar_asset_id"],
        bio=row["bio"] or "", about_md=row["about_md"] or "",
        status=row["status"], status_line=row["status_line"] or "",
        specialties=list(_loads(row["specialties_json"], [])),
        goals=list(_loads(row["goals_json"], [])),
        assigned_project_ids=list(_loads(row["assigned_project_ids_json"], [])),
        authority_policy=row["authority_policy"],
        notification_policy=dict(_loads(row["notification_policy_json"], {})),
        contact_channels=list(_loads(row["contact_channels_json"], [])),
        builtin=bool(row["builtin"]), sort_order=int(row["sort_order"] or 0),
        created_at=row["created_at"], updated_at=row["updated_at"],
    )


def enforce_launch_authority(
    conn: sqlite3.Connection,
    work_item_id: str,
    requested: agent_squads.AgentExecutionAuthority,
) -> StaffMember | None:
    member = staff_for_work_item(conn, work_item_id)
    if member is None:
        return None
    if requested == agent_squads.AgentExecutionAuthority.FULL:
        raise conflict(
            "staff_authority",
            f"{member.display_name} cannot receive full machine authority through a staff assignment. "
            "Use a separate explicit owner-approved workflow for full authority.",
            staff_id=member.id,
            requested_authority=requested.value,
        )
    if (
        member.authority_policy == StaffAuthority.ADVISE_ONLY
        and requested != agent_squads.AgentExecutionAuthority.OBSERVE
    ):
        raise conflict(
            "staff_authority",
            f"{member.display_name} is advice-only and may launch only with observe authority.",
            staff_id=member.id,
            requested_authority=requested.value,
            allowed_authority="observe",
        )
    return member


_ROUTE_KEYWORDS: dict[str, tuple[str, ...]] = {
    "maya": (
        "growth", "revenue", "monetize", "money", "pricing", "conversion",
        "acquisition", "funnel", "distribution", "retention", "roi",
    ),
    "adrian": (
        "finance", "financial", "cash", "cost", "expense", "budget", "margin",
        "profit", "bookkeeping", "tax", "runway", "accounting",
    ),
    "sofia": (
        "marketing", "campaign", "content", "seo", "audience", "brand",
        "positioning", "launch", "social", "message", "promotion",
    ),
    "marcus": (
        "product", "feature", "bug", "fix", "build", "ux", "ui", "onboarding",
        "performance", "app", "test", "qa", "implementation",
    ),
    "jordan": (
        "sales", "client", "customer", "lead", "proposal", "deal", "follow up",
        "follow-up", "pipeline", "prospect", "close",
    ),
    "riley": (
        "research", "competitor", "compare", "market", "trend", "investigate",
        "discover", "opportunity", "evidence", "source", "technology",
    ),
}


def route_task(conn: sqlite3.Connection, task: str) -> StaffRouteResult:
    text = task.casefold().strip()
    people = list_staff(conn)
    if not people:
        raise not_found("staff_member", "No staff are configured.")

    for member in people:
        if f"@{member.handle.casefold()}" in text:
            chosen = StaffRouteCandidate(
                staff_id=member.id, handle=member.handle,
                display_name=member.display_name, title=member.title,
                score=1000, reasons=[f"Explicit @{member.handle} mention"],
            )
            return StaffRouteResult(selected=chosen, candidates=[chosen], explicit=True)

    candidates: list[StaffRouteCandidate] = []
    for member in people:
        score = 0
        reasons: list[str] = []
        keywords = _ROUTE_KEYWORDS.get(member.handle, ())
        matches = [keyword for keyword in keywords if keyword in text]
        if matches:
            score += 8 * len(matches)
            reasons.append("Matched: " + ", ".join(matches[:6]))
        title_words = [
            word.casefold().strip("&/")
            for word in member.title.split()
            if len(word) >= 4
        ]
        title_matches = [word for word in title_words if word in text]
        if title_matches:
            score += 5 * len(title_matches)
            reasons.append("Role match: " + ", ".join(title_matches))
        specialty_matches = [
            specialty for specialty in member.specialties
            if any(token in text for token in specialty.casefold().split() if len(token) >= 5)
        ]
        if specialty_matches:
            score += 3 * min(3, len(specialty_matches))
            reasons.append("Specialty match")
        if member.status == "blocked":
            score -= 10
            reasons.append("Currently blocked")
        elif member.status == "working":
            score -= 2
            reasons.append("Already working")
        candidates.append(
            StaffRouteCandidate(
                staff_id=member.id, handle=member.handle,
                display_name=member.display_name, title=member.title,
                score=score, reasons=reasons or ["General staff fit"],
            )
        )

    candidates.sort(key=lambda item: (-item.score, item.handle))
    if candidates[0].score <= 0:
        maya = next((c for c in candidates if c.handle == "maya"), candidates[0])
        maya.score = 1
        maya.reasons = ["Portfolio triage defaults to the Growth Director when no specialist signal is strong."]
        candidates.sort(key=lambda item: (-item.score, item.handle))
    return StaffRouteResult(selected=candidates[0], candidates=candidates[:6], explicit=False)


def staff_dashboard(conn: sqlite3.Connection, staff_id: str) -> dict[str, Any]:
    member = get_staff(conn, staff_id)
    return {
        "staff": member.model_dump(mode="json"),
        "responsibilities": [x.model_dump(mode="json") for x in list_responsibilities(conn, member.id)],
        "kpis": [x.model_dump(mode="json") for x in list_kpis(conn, member.id)],
        "memories": [x.model_dump(mode="json") for x in list_memories(conn, member.id, 30)],
        "permissions": [x.model_dump(mode="json") for x in list_permissions(conn, member.id)],
        "triggers": [x.model_dump(mode="json") for x in list_triggers(conn, member.id)],
        "channels": [x.model_dump(mode="json") for x in list_channels(conn, member.id)],
        "relationships": [x.model_dump(mode="json") for x in list_relationships(conn, member.id)],
        "events": [x.model_dump(mode="json") for x in list_events(conn, member.id, 30)],
    }


def team_briefing(conn: sqlite3.Connection) -> dict[str, Any]:
    people = list_staff(conn)
    attention: list[dict[str, Any]] = []
    staff_rows: list[dict[str, Any]] = []
    for member in people:
        kpis = list_kpis(conn, member.id)
        events = list_events(conn, member.id, 12)
        alerts = [k for k in kpis if k.status in {"watch", "off_track"}]
        action_events = [event for event in events if event.action_required]
        if member.status in {"blocked", "waiting_for_owner"}:
            attention.append({
                "staff_id": member.id,
                "severity": "warning" if member.status == "waiting_for_owner" else "critical",
                "title": f"{member.display_name} is {member.status.replace('_', ' ')}",
                "detail": member.status_line,
            })
        for kpi in alerts:
            attention.append({
                "staff_id": member.id,
                "severity": "critical" if kpi.status == "off_track" else "warning",
                "title": f"{member.display_name}: {kpi.name}",
                "detail": f"KPI status is {kpi.status.replace('_', ' ')}.",
            })
        for event in action_events[:3]:
            attention.append({
                "staff_id": member.id,
                "severity": event.severity,
                "title": event.title,
                "detail": event.body_md,
            })
        staff_rows.append({
            "staff_id": member.id,
            "handle": member.handle,
            "display_name": member.display_name,
            "title": member.title,
            "status": member.status,
            "status_line": member.status_line,
            "kpis": {
                "total": len(kpis),
                "on_track": sum(1 for item in kpis if item.status == "on_track"),
                "watch": sum(1 for item in kpis if item.status == "watch"),
                "off_track": sum(1 for item in kpis if item.status == "off_track"),
                "unknown": sum(1 for item in kpis if item.status == "unknown"),
            },
        })
    suggested = (
        "Review the staff items that need your decision."
        if attention
        else "Ask Maya to prioritize the highest-leverage next action across the portfolio."
    )
    return {
        "generated_at": _now(),
        "team": staff_rows,
        "attention": attention,
        "counts": {
            "staff": len(people),
            "working": sum(1 for p in people if p.status == "working"),
            "waiting_for_owner": sum(1 for p in people if p.status == "waiting_for_owner"),
            "blocked": sum(1 for p in people if p.status == "blocked"),
            "attention_items": len(attention),
        },
        "suggested_owner_action": suggested,
    }


def _insert_responsibility(
    conn: sqlite3.Connection, staff_id: str, title: str, description: str,
    priority: str, cadence: str, sort_order: int,
) -> None:
    member = get_staff(conn, staff_id)
    existing = conn.execute(
        "SELECT 1 FROM staff_responsibilities WHERE staff_member_id=? AND title=?",
        (member.id, title),
    ).fetchone()
    if existing:
        return
    now = _now()
    conn.execute(
        """INSERT INTO staff_responsibilities
        (id,staff_member_id,title,description,priority,cadence,enabled,sort_order,created_at,updated_at)
        VALUES (?,?,?,?,?,?,1,?,?,?)""",
        (_id("resp"), member.id, title, description, priority, cadence, sort_order, now, now),
    )


def _insert_seed_kpi(
    conn: sqlite3.Connection, staff_id: str, name: str, description: str,
    unit: str, direction: str, period: str, sort_order: int,
) -> None:
    member = get_staff(conn, staff_id)
    if conn.execute(
        "SELECT 1 FROM staff_kpis WHERE staff_member_id=? AND name=?", (member.id, name)
    ).fetchone():
        return
    create_kpi(
        conn, member.id,
        StaffKpiCreate(
            name=name, description=description, unit=unit, direction=direction,
            status="unknown", source="not connected", period=period, sort_order=sort_order,
        ),
    )


def _seed_permission(
    conn: sqlite3.Connection, staff_id: str, scope_type: str, scope_id: str,
    capability: str, decision: str, reason: str,
) -> None:
    upsert_permission(
        conn, staff_id,
        StaffPermissionCreate(
            scope_type=scope_type, scope_id=scope_id, capability=capability,
            decision=decision, reason=reason,
        ),
    )


def _seed_channel(conn: sqlite3.Connection, staff_id: str, channel: str, status: str) -> None:
    member = get_staff(conn, staff_id)
    now = _now()
    connection_id = f"channel-{member.handle}-{channel}"
    capabilities = ["in_app"] if channel == "synapse" else []
    conn.execute(
        """INSERT INTO staff_channel_connections
        (id,staff_member_id,channel,status,account_label,external_id,capabilities_json,metadata_json,created_at,updated_at)
        VALUES (?,?,?,?,NULL,NULL,?,?,?,?)
        ON CONFLICT(staff_member_id,channel) DO UPDATE SET
          status=excluded.status, capabilities_json=excluded.capabilities_json,
          updated_at=excluded.updated_at""",
        (
            connection_id, member.id, channel, status, json.dumps(capabilities),
            json.dumps({"truthful_state": True}), now, now,
        ),
    )


def _seed_trigger(
    conn: sqlite3.Connection, staff_id: str, name: str, trigger_type: str,
    config: dict[str, Any], prompt: str,
) -> None:
    member = get_staff(conn, staff_id)
    if conn.execute(
        "SELECT 1 FROM staff_triggers WHERE staff_member_id=? AND name=?", (member.id, name)
    ).fetchone():
        return
    # Seeded trigger ideas stay disabled until they are wired to an actual scheduler.
    create_trigger(
        conn, member.id,
        StaffTriggerCreate(
            name=name, trigger_type=trigger_type, config=config,
            prompt_md=prompt, enabled=False,
        ),
    )


def _seed_relationship(
    conn: sqlite3.Connection, from_handle: str, to_handle: str,
    relationship: str, notes: str,
) -> None:
    source = get_staff(conn, from_handle)
    target = get_staff(conn, to_handle)
    now = _now()
    conn.execute(
        """INSERT INTO staff_relationships
        (from_staff_id,to_staff_id,relationship,notes,created_at,updated_at)
        VALUES (?,?,?,?,?,?)
        ON CONFLICT(from_staff_id,to_staff_id,relationship) DO UPDATE SET
          notes=excluded.notes, updated_at=excluded.updated_at""",
        (source.id, target.id, relationship, notes, now, now),
    )


def seed_staff_operations(conn: sqlite3.Connection) -> None:
    """Seed useful but non-fabricated operating structure for the six built-in staff."""

    responsibilities = {
        "maya": [
            ("Prioritize the portfolio", "Compare active apps and identify the highest-leverage next move.", "high", "daily"),
            ("Design growth experiments", "Turn growth assumptions into measurable, reversible experiments.", "high", "ongoing"),
            ("Coordinate specialists", "Pull in Marketing, Product, Sales, Finance, or Research when the objective crosses domains.", "medium", "as needed"),
        ],
        "adrian": [
            ("Maintain financial visibility", "Keep known costs, revenue signals, and financial assumptions clearly separated.", "high", "weekly"),
            ("Flag financial risk", "Surface material cash, margin, duplication, or commitment risks for owner review.", "high", "ongoing"),
            ("Prepare bookkeeping-ready summaries", "Organize evidence without pretending to file taxes or move money.", "medium", "monthly"),
        ],
        "sofia": [
            ("Own positioning", "Keep each priority product's audience, problem, promise, and proof clear.", "high", "ongoing"),
            ("Build distribution systems", "Create repeatable campaign/content/channel loops tied to measurable outcomes.", "high", "weekly"),
            ("Protect claim quality", "Keep marketing claims grounded in verified product capabilities.", "medium", "ongoing"),
        ],
        "marcus": [
            ("Improve priority products", "Turn verified user/product friction into scoped, tested improvements.", "high", "ongoing"),
            ("Protect product quality", "Require regression evidence and preserve concurrent work.", "high", "ongoing"),
            ("Reduce backlog noise", "Prioritize by user value, business impact, and proof rather than feature count.", "medium", "weekly"),
        ],
        "jordan": [
            ("Maintain next actions", "Keep qualified leads and clients from going stale.", "high", "daily"),
            ("Prepare outreach and proposals", "Create specific, truthful communication for owner approval.", "high", "as needed"),
            ("Track objections", "Turn repeated objections into product, offer, or messaging feedback.", "medium", "weekly"),
        ],
        "riley": [
            ("Scan the market", "Find relevant competitor, technology, user, and opportunity evidence.", "high", "weekly"),
            ("Verify important claims", "Prefer primary evidence and label uncertainty.", "high", "ongoing"),
            ("Feed the team", "Convert research into concise briefs other staff can act on.", "medium", "as needed"),
        ],
    }
    for handle, rows in responsibilities.items():
        for idx, row in enumerate(rows, 10):
            _insert_responsibility(conn, handle, *row, idx)

    kpis = {
        "maya": [
            ("Priority apps with a clear next action", "Priority apps that have an evidence-backed next move.", "apps", "increase", "weekly"),
            ("Measured growth experiments", "Growth experiments with an explicit success metric and result.", "experiments", "increase", "monthly"),
        ],
        "adrian": [
            ("Portfolio costs reconciled", "Known recurring portfolio costs with a verified source.", "percent", "increase", "monthly"),
            ("Unresolved financial risks", "Material financial risks still awaiting resolution.", "items", "decrease", "weekly"),
        ],
        "sofia": [
            ("Priority apps with clear positioning", "Priority apps with a specific audience/problem/promise/proof.", "apps", "increase", "monthly"),
            ("Measured acquisition experiments", "Campaigns or channel tests with a measurable outcome.", "experiments", "increase", "monthly"),
        ],
        "marcus": [
            ("Verified product improvements", "Product changes with end-to-end evidence.", "improvements", "increase", "monthly"),
            ("Open high-severity regressions", "Known high-severity product regressions not resolved.", "issues", "decrease", "weekly"),
        ],
        "jordan": [
            ("Qualified opportunities with a next action", "Qualified leads/clients with a concrete next step.", "percent", "increase", "weekly"),
            ("Overdue follow-ups", "Qualified opportunities whose follow-up is overdue.", "items", "decrease", "daily"),
        ],
        "riley": [
            ("Decision-ready research briefs", "Research briefs that end with a concrete decision or experiment.", "briefs", "increase", "monthly"),
            ("Unverified material assumptions", "Important assumptions still lacking sufficient evidence.", "items", "decrease", "weekly"),
        ],
    }
    for handle, rows in kpis.items():
        for idx, row in enumerate(rows, 10):
            _insert_seed_kpi(conn, handle, *row, idx)

    for member in list_staff(conn):
        _seed_permission(conn, member.id, "project", "*", "work", "allow", "May work in Synapse projects within the staff authority boundary.")
        _seed_permission(conn, member.id, "external_action", "*", "send", "ask", "External sends require owner approval.")
        _seed_permission(conn, member.id, "financial_action", "*", "spend", "deny", "Staff may not move or spend money through normal staff assignments.")
        _seed_permission(conn, member.id, "destructive_action", "*", "delete", "ask", "Destructive actions require an explicit owner-approved workflow.")
        _seed_channel(conn, member.id, "synapse", "connected")
        _seed_channel(conn, member.id, "whatsapp", "disconnected")
        _seed_channel(conn, member.id, "email", "disconnected")

    _seed_permission(conn, "adrian", "project", "*", "write", "deny", "Finance Director is advice-only by default.")
    _seed_permission(conn, "riley", "project", "*", "write", "deny", "Research Scout is advice-only by default.")
    _seed_permission(conn, "marcus", "project", "*", "write", "allow", "Product Operator may edit assigned project workspaces within limits.")

    _seed_trigger(conn, "maya", "Daily portfolio priority scan", "schedule", {"cadence": "daily", "daypart": "morning"}, "Review current portfolio evidence and surface the highest-leverage owner action.")
    _seed_trigger(conn, "adrian", "Weekly financial health review", "schedule", {"cadence": "weekly"}, "Review connected financial evidence and surface material financial changes or risks.")
    _seed_trigger(conn, "sofia", "Weekly distribution review", "schedule", {"cadence": "weekly"}, "Review priority-product marketing/distribution evidence and surface next experiments.")
    _seed_trigger(conn, "marcus", "Product blocker watch", "event", {"event": "project_blocked"}, "When a priority project is blocked, inspect the blocker and propose the smallest verified next step.")
    _seed_trigger(conn, "jordan", "Follow-up due watch", "condition", {"condition": "follow_up_due"}, "Surface qualified follow-ups that need the owner's attention.")
    _seed_trigger(conn, "riley", "Weekly opportunity scan", "schedule", {"cadence": "weekly"}, "Scan current market and competitor evidence for material opportunities or threats.")

    for target in ("sofia", "marcus", "jordan", "riley"):
        _seed_relationship(conn, "maya", target, "delegates_to", "Maya may route specialized portfolio work to this person.")
    _seed_relationship(conn, "maya", "adrian", "collaborates_with", "Maya consults Adrian on economics, cost, margin, and financial risk.")
    _seed_relationship(conn, "sofia", "jordan", "collaborates_with", "Marketing and Sales share messaging, objections, and acquisition feedback.")
    _seed_relationship(conn, "marcus", "riley", "collaborates_with", "Product uses Riley's external evidence to challenge product assumptions.")
