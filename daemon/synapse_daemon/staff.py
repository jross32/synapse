"""Persistent owner-facing AI staff built on Synapse role + personality workers."""

from __future__ import annotations

import json
import secrets
import sqlite3
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from . import agent_squads, personalities
from .errors import conflict, invalid, not_found
from .time_utils import to_iso, utc_now


class StaffStatus(str, Enum):
    AVAILABLE = "available"
    WORKING = "working"
    WAITING_FOR_OWNER = "waiting_for_owner"
    BLOCKED = "blocked"
    OFFLINE = "offline"


class StaffAuthority(str, Enum):
    ADVISE_ONLY = "advise_only"
    PREPARE_FOR_APPROVAL = "prepare_for_approval"
    ACT_WITHIN_LIMITS = "act_within_limits"


class StaffAvatarAsset(BaseModel):
    id: str
    name: str
    description: str = ""
    glyph: str
    background: str
    accent: str
    builtin: bool = True
    sort_order: int = 0
    created_at: str
    updated_at: str


class StaffMember(BaseModel):
    id: str
    handle: str
    display_name: str
    title: str
    role_template_id: str
    personality_id: str | None = None
    avatar_asset_id: str | None = None
    bio: str = ""
    about_md: str = ""
    status: StaffStatus = StaffStatus.AVAILABLE
    status_line: str = ""
    specialties: list[str] = Field(default_factory=list)
    goals: list[str] = Field(default_factory=list)
    assigned_project_ids: list[str] = Field(default_factory=list)
    authority_policy: StaffAuthority = StaffAuthority.PREPARE_FOR_APPROVAL
    notification_policy: dict[str, Any] = Field(default_factory=dict)
    contact_channels: list[str] = Field(default_factory=list)
    builtin: bool = False
    sort_order: int = 0
    created_at: str
    updated_at: str


class StaffMemberCreate(BaseModel):
    id: str | None = None
    handle: str
    display_name: str
    title: str
    role_template_id: str
    personality_id: str | None = None
    avatar_asset_id: str | None = None
    bio: str = ""
    about_md: str = ""
    status: StaffStatus = StaffStatus.AVAILABLE
    status_line: str = ""
    specialties: list[str] = Field(default_factory=list)
    goals: list[str] = Field(default_factory=list)
    assigned_project_ids: list[str] = Field(default_factory=list)
    authority_policy: StaffAuthority = StaffAuthority.PREPARE_FOR_APPROVAL
    notification_policy: dict[str, Any] = Field(default_factory=dict)
    contact_channels: list[str] = Field(default_factory=list)
    sort_order: int = 0


class StaffMemberUpdate(BaseModel):
    handle: str | None = None
    display_name: str | None = None
    title: str | None = None
    role_template_id: str | None = None
    personality_id: str | None = None
    avatar_asset_id: str | None = None
    bio: str | None = None
    about_md: str | None = None
    status: StaffStatus | None = None
    status_line: str | None = None
    specialties: list[str] | None = None
    goals: list[str] | None = None
    assigned_project_ids: list[str] | None = None
    authority_policy: StaffAuthority | None = None
    notification_policy: dict[str, Any] | None = None
    contact_channels: list[str] | None = None
    sort_order: int | None = None


def _loads_list(raw: str | None) -> list[str]:
    if not raw:
        return []
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return []
    return [str(item) for item in value] if isinstance(value, list) else []


def _loads_dict(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def _avatar_row(row: sqlite3.Row) -> StaffAvatarAsset:
    return StaffAvatarAsset(
        id=row["id"],
        name=row["name"],
        description=row["description"] or "",
        glyph=row["glyph"],
        background=row["background"],
        accent=row["accent"],
        builtin=bool(row["builtin"]),
        sort_order=int(row["sort_order"] or 0),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _staff_row(row: sqlite3.Row) -> StaffMember:
    return StaffMember(
        id=row["id"],
        handle=row["handle"],
        display_name=row["display_name"],
        title=row["title"],
        role_template_id=row["role_template_id"],
        personality_id=row["personality_id"],
        avatar_asset_id=row["avatar_asset_id"],
        bio=row["bio"] or "",
        about_md=row["about_md"] or "",
        status=StaffStatus(row["status"]),
        status_line=row["status_line"] or "",
        specialties=_loads_list(row["specialties_json"]),
        goals=_loads_list(row["goals_json"]),
        assigned_project_ids=_loads_list(row["assigned_project_ids_json"]),
        authority_policy=StaffAuthority(row["authority_policy"]),
        notification_policy=_loads_dict(row["notification_policy_json"]),
        contact_channels=_loads_list(row["contact_channels_json"]),
        builtin=bool(row["builtin"]),
        sort_order=int(row["sort_order"] or 0),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def list_avatar_assets(conn: sqlite3.Connection) -> list[StaffAvatarAsset]:
    rows = conn.execute("SELECT * FROM staff_avatar_assets ORDER BY sort_order, name").fetchall()
    return [_avatar_row(row) for row in rows]


def get_avatar_asset(conn: sqlite3.Connection, asset_id: str) -> StaffAvatarAsset:
    row = conn.execute("SELECT * FROM staff_avatar_assets WHERE id = ?", (asset_id,)).fetchone()
    if row is None:
        raise not_found("staff_avatar_asset", asset_id)
    return _avatar_row(row)


def list_staff(conn: sqlite3.Connection) -> list[StaffMember]:
    rows = conn.execute("SELECT * FROM staff_members ORDER BY sort_order, display_name").fetchall()
    return [_staff_row(row) for row in rows]


def get_staff(conn: sqlite3.Connection, staff_id_or_handle: str) -> StaffMember:
    row = conn.execute(
        "SELECT * FROM staff_members WHERE id = ? OR handle = ?",
        (staff_id_or_handle, staff_id_or_handle.lower().lstrip("@")),
    ).fetchone()
    if row is None:
        raise not_found("staff_member", staff_id_or_handle)
    return _staff_row(row)


def _validate_links(conn: sqlite3.Connection, payload: StaffMemberCreate | StaffMemberUpdate) -> None:
    if payload.role_template_id is not None:
        agent_squads.get_role_template(conn, payload.role_template_id)
    if payload.personality_id:
        personalities.get_personality(conn, payload.personality_id)
    if payload.avatar_asset_id:
        get_avatar_asset(conn, payload.avatar_asset_id)
    project_ids = payload.assigned_project_ids
    if project_ids is not None:
        for project_id in project_ids:
            if conn.execute("SELECT id FROM projects WHERE id = ?", (project_id,)).fetchone() is None:
                raise invalid("staff_member", f"Unknown assigned project '{project_id}'.")


def create_staff(
    conn: sqlite3.Connection,
    payload: StaffMemberCreate,
    *,
    builtin: bool = False,
) -> StaffMember:
    _validate_links(conn, payload)
    staff_id = (payload.id or secrets.token_hex(6)).strip()
    handle = payload.handle.lower().lstrip("@").strip()
    if not handle:
        raise invalid("staff_member", "A staff handle is required.")
    if conn.execute("SELECT 1 FROM staff_members WHERE id = ? OR handle = ?", (staff_id, handle)).fetchone():
        raise conflict("staff_member", f"Staff member '{handle}' already exists.")
    now = to_iso(utc_now())
    conn.execute(
        """INSERT INTO staff_members (
            id, handle, display_name, title, role_template_id, personality_id, avatar_asset_id,
            bio, about_md, status, status_line, specialties_json, goals_json,
            assigned_project_ids_json, authority_policy, notification_policy_json,
            contact_channels_json, builtin, sort_order, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            staff_id,
            handle,
            payload.display_name,
            payload.title,
            payload.role_template_id,
            payload.personality_id,
            payload.avatar_asset_id,
            payload.bio,
            payload.about_md,
            payload.status.value,
            payload.status_line,
            json.dumps(payload.specialties),
            json.dumps(payload.goals),
            json.dumps(payload.assigned_project_ids),
            payload.authority_policy.value,
            json.dumps(payload.notification_policy),
            json.dumps(payload.contact_channels),
            1 if builtin else 0,
            payload.sort_order,
            now,
            now,
        ),
    )
    return get_staff(conn, staff_id)


def update_staff(conn: sqlite3.Connection, staff_id: str, patch: StaffMemberUpdate) -> StaffMember:
    current = get_staff(conn, staff_id)
    _validate_links(conn, patch)
    data = patch.model_dump(exclude_unset=True)
    mapping = {
        "specialties": "specialties_json",
        "goals": "goals_json",
        "assigned_project_ids": "assigned_project_ids_json",
        "notification_policy": "notification_policy_json",
        "contact_channels": "contact_channels_json",
    }
    sets: list[str] = []
    args: list[Any] = []
    for key, value in data.items():
        column = mapping.get(key, key)
        if key == "handle" and value is not None:
            value = str(value).lower().lstrip("@").strip()
        if key in mapping:
            value = json.dumps(value)
        if isinstance(value, Enum):
            value = value.value
        sets.append(f"{column} = ?")
        args.append(value)
    if sets:
        sets.append("updated_at = ?")
        args.append(to_iso(utc_now()))
        args.append(current.id)
        try:
            conn.execute(f"UPDATE staff_members SET {', '.join(sets)} WHERE id = ?", args)
        except sqlite3.IntegrityError as exc:
            raise conflict("staff_member", "That staff handle is already in use.") from exc
    return get_staff(conn, current.id)


def link_work_item(conn: sqlite3.Connection, staff_id: str, work_item_id: str) -> None:
    member = get_staff(conn, staff_id)
    agent_squads.get_work_item(conn, work_item_id)
    conn.execute(
        "INSERT OR IGNORE INTO staff_work_items (staff_member_id, work_item_id, created_at) VALUES (?, ?, ?)",
        (member.id, work_item_id, to_iso(utc_now())),
    )


def list_recent_work_items(conn: sqlite3.Connection, staff_id: str, limit: int = 20) -> list[dict[str, Any]]:
    member = get_staff(conn, staff_id)
    rows = conn.execute(
        """SELECT w.id, w.squad_id, w.title, w.status, w.summary_md, w.blockers_md,
                  w.created_at, w.updated_at, w.completed_at
           FROM staff_work_items sw
           JOIN agent_work_items w ON w.id = sw.work_item_id
           WHERE sw.staff_member_id = ?
           ORDER BY sw.created_at DESC LIMIT ?""",
        (member.id, max(1, min(limit, 100))),
    ).fetchall()
    return [dict(row) for row in rows]


_AVATARS = [
    ("orbit-blue", "Blue Orbit", "Classic electric-blue gamer badge.", "◎", "linear-gradient(145deg,#08152f,#123f8f)", "#66d9ff"),
    ("violet-grid", "Violet Grid", "Purple neon grid identity.", "◇", "linear-gradient(145deg,#170b2f,#5a1ea6)", "#c89bff"),
    ("emerald-core", "Emerald Core", "Green operator core.", "⬢", "linear-gradient(145deg,#062820,#0f7155)", "#79ffd1"),
    ("solar-flare", "Solar Flare", "Warm high-energy growth badge.", "✦", "linear-gradient(145deg,#321006,#a14613)", "#ffd27c"),
    ("cyan-pulse", "Cyan Pulse", "Clean systems pulse badge.", "◉", "linear-gradient(145deg,#05242c,#08657b)", "#76efff"),
    ("rose-signal", "Rose Signal", "Bold communication badge.", "◆", "linear-gradient(145deg,#2f0a20,#8b245f)", "#ff9fd0"),
    ("amber-ledger", "Amber Ledger", "Measured finance and records badge.", "▦", "linear-gradient(145deg,#2c2106,#7a5d10)", "#ffe08a"),
    ("red-vector", "Red Vector", "Fast action and sales badge.", "➤", "linear-gradient(145deg,#300b0b,#8c2525)", "#ff9c9c"),
    ("indigo-lab", "Indigo Lab", "Research and experimentation badge.", "⌬", "linear-gradient(145deg,#11113a,#36369a)", "#aeb5ff"),
    ("teal-compass", "Teal Compass", "Direction-finding scout badge.", "✥", "linear-gradient(145deg,#072a2a,#11706f)", "#8bffff"),
]


def seed_staff_foundation(conn: sqlite3.Connection) -> None:
    now = to_iso(utc_now())
    for order, (asset_id, name, description, glyph, background, accent) in enumerate(_AVATARS, 10):
        conn.execute(
            """INSERT INTO staff_avatar_assets
               (id, name, description, glyph, background, accent, builtin, sort_order, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?, ?)
               ON CONFLICT(id) DO NOTHING""",
            (asset_id, name, description, glyph, background, accent, order, now, now),
        )

    roles = [
        agent_squads.AgentRoleTemplateCreate(
            id="growth-director",
            name="Growth Director",
            description="Finds and prioritizes the highest-leverage paths to revenue and adoption across the portfolio.",
            preferred_runtimes=["chatgpt_web", "claude", "codex", "gemini"],
            default_visibility=agent_squads.AgentVisibility.LEAD,
            context_mode=agent_squads.AgentContextMode.FULL,
            role_tier=agent_squads.AgentRoleTier.BOSS,
            can_delegate=True,
            prompt_preamble_md=(
                "You are the owner's Growth Director. Optimize for durable revenue and adoption, not vanity metrics. "
                "Inspect current evidence before recommending work, compare opportunity cost across products, define "
                "measurable experiments, and delegate implementation/research when useful. Never invent traction, "
                "customers, revenue, or completed actions. Purchases, binding commitments, public sends, and money "
                "movement require explicit owner approval unless a narrowly scoped authority policy says otherwise."
            ),
            sort_order=11,
        ),
        agent_squads.AgentRoleTemplateCreate(
            id="finance-director",
            name="Finance Director",
            description="Owns financial visibility, bookkeeping readiness, unit economics, cash awareness, and financial decision support.",
            preferred_runtimes=["chatgpt_web", "claude", "gemini"],
            default_visibility=agent_squads.AgentVisibility.LEAD,
            context_mode=agent_squads.AgentContextMode.FULL,
            role_tier=agent_squads.AgentRoleTier.SUPERVISOR,
            can_delegate=True,
            prompt_preamble_md=(
                "You are the owner's Finance Director. Separate known numbers from estimates, reconcile sources, and "
                "surface cash, cost, margin, runway, tax/receipt readiness, and app-level economics clearly. You may "
                "analyze and prepare actions, but never move money, open/close financial accounts, submit taxes, or "
                "make binding purchases without explicit owner authorization."
            ),
            sort_order=12,
        ),
        agent_squads.AgentRoleTemplateCreate(
            id="marketing-director",
            name="Marketing Director",
            description="Turns product value into positioning, launches, campaigns, content, acquisition experiments, and follow-up.",
            preferred_runtimes=["chatgpt_web", "claude", "gemini"],
            default_visibility=agent_squads.AgentVisibility.LEAD,
            context_mode=agent_squads.AgentContextMode.FULL,
            role_tier=agent_squads.AgentRoleTier.SUPERVISOR,
            can_delegate=True,
            prompt_preamble_md=(
                "You are the owner's Marketing Director. Learn the product and audience before creating campaigns. "
                "Build positioning, launch plans, content systems, distribution experiments, and measurement loops. "
                "Draft freely, but public posting, paid spend, outbound sends, and account changes require approval "
                "unless explicitly authorized."
            ),
            sort_order=13,
        ),
        agent_squads.AgentRoleTemplateCreate(
            id="product-operator",
            name="Product Operator",
            description="Turns evidence from products, users, tests, and backlogs into scoped product improvements.",
            preferred_runtimes=["codex", "claude", "chatgpt_web", "gemini"],
            default_visibility=agent_squads.AgentVisibility.LEAD,
            context_mode=agent_squads.AgentContextMode.FULL,
            role_tier=agent_squads.AgentRoleTier.SUPERVISOR,
            can_delegate=True,
            prompt_preamble_md=(
                "You are the owner's Product Operator. Inspect the exact product state before changing it, prioritize "
                "user value and business impact, make reversible scoped changes, verify them end to end, and leave "
                "evidence-backed handoffs. Protect concurrent work and never claim completion without proof."
            ),
            sort_order=14,
        ),
        agent_squads.AgentRoleTemplateCreate(
            id="sales-operator",
            name="Sales & Client Operator",
            description="Owns lead follow-up, proposals, pipeline next actions, client communication preparation, and sales process quality.",
            preferred_runtimes=["chatgpt_web", "claude", "gemini"],
            default_visibility=agent_squads.AgentVisibility.LEAD,
            context_mode=agent_squads.AgentContextMode.STANDARD,
            role_tier=agent_squads.AgentRoleTier.SUPERVISOR,
            can_delegate=True,
            prompt_preamble_md=(
                "You are the owner's Sales & Client Operator. Keep a clear pipeline, identify next actions, prepare "
                "specific outreach and proposals, and protect trust. Do not fabricate relationships or send messages, "
                "accept terms, or create binding commitments without explicit authorization."
            ),
            sort_order=15,
        ),
        agent_squads.AgentRoleTemplateCreate(
            id="research-scout",
            name="Research Scout",
            description="Finds market, competitor, user, technology, and opportunity evidence and turns it into actionable briefs.",
            preferred_runtimes=["chatgpt_web", "claude", "gemini"],
            default_visibility=agent_squads.AgentVisibility.HELPER,
            context_mode=agent_squads.AgentContextMode.STANDARD,
            role_tier=agent_squads.AgentRoleTier.WORKER,
            can_delegate=False,
            prompt_preamble_md=(
                "You are the owner's Research Scout. Search broadly, verify important claims, distinguish primary "
                "evidence from opinion, compare alternatives, and hand back concise opportunity briefs with sources, "
                "uncertainty, and the next decision."
            ),
            sort_order=16,
        ),
    ]
    existing_roles = {role.id for role in agent_squads.list_role_templates(conn)}
    for role in roles:
        if role.id not in existing_roles:
            agent_squads.create_role_template(conn, role)

    if conn.execute("SELECT 1 FROM personalities WHERE id = 'growth-operator'").fetchone() is None:
        personalities.create_personality(
            conn,
            personalities.PersonalityCreate(
                id="growth-operator",
                name="The Growth Operator",
                blurb="Commercially curious, energetic, evidence-first, and relentlessly prioritizes leverage.",
                traits=["commercial", "curious", "decisive", "experimental", "evidence-first"],
                prompt_preamble_md=(
                    "You are commercially curious and energetic without becoming reckless. Ask what creates real "
                    "value, prefer measurable experiments, compare opportunity cost, and keep the owner focused on "
                    "the few moves most likely to matter."
                ),
                sort_order=8,
            ),
        )

    if conn.execute("SELECT 1 FROM staff_members WHERE handle = 'maya'").fetchone() is None:
        create_staff(
            conn,
            StaffMemberCreate(
                id="maya-growth",
                handle="maya",
                display_name="Maya",
                title="Growth Director",
                role_template_id="growth-director",
                personality_id="growth-operator",
                avatar_asset_id="solar-flare",
                bio="Turns your portfolio into a prioritized growth plan and keeps the highest-leverage revenue experiments moving.",
                about_md=(
                    "Maya is the portfolio-level growth lead. She compares your apps, markets, pricing, funnels, "
                    "distribution options, and active work to decide what is most worth doing next. She is allowed to "
                    "research, plan, delegate, and prepare experiments. She does not invent business traction or spend "
                    "money, publish externally, or make binding commitments without the owner's approval."
                ),
                status=StaffStatus.AVAILABLE,
                status_line="Looking for the highest-leverage move across the portfolio.",
                specialties=[
                    "Portfolio prioritization",
                    "Pricing and packaging",
                    "Acquisition experiments",
                    "Conversion funnels",
                    "Launch strategy",
                    "Revenue opportunity scoring",
                ],
                goals=[
                    "Identify the highest-value next action across active apps.",
                    "Build measurable growth loops instead of one-off marketing.",
                    "Reduce time spent on low-return projects.",
                    "Turn promising products into repeatable distribution and revenue.",
                ],
                authority_policy=StaffAuthority.PREPARE_FOR_APPROVAL,
                notification_policy={
                    "notify_on": ["owner_decision_needed", "meaningful_result", "blocked", "material_risk"],
                    "digest": "daily",
                    "quiet_unless_actionable": True,
                },
                contact_channels=["synapse"],
                sort_order=10,
            ),
            builtin=True,
        )

    additional_personalities = [
        personalities.PersonalityCreate(
            id="finance-steward",
            name="The Finance Steward",
            blurb="Calm, exact, skeptical of fuzzy numbers, and protective of cash and commitments.",
            traits=["precise", "calm", "skeptical", "risk-aware", "organized"],
            prompt_preamble_md=(
                "Be calm and numerically exact. Distinguish verified figures from estimates, reconcile contradictions, "
                "show assumptions, and protect the owner from avoidable financial risk. Prefer clear tables, thresholds, "
                "and next decisions over vague financial commentary."
            ),
            sort_order=9,
        ),
        personalities.PersonalityCreate(
            id="marketing-storyteller",
            name="The Audience Builder",
            blurb="Creative and audience-first, but insists that messaging connect to a measurable outcome.",
            traits=["creative", "audience-first", "persuasive", "analytical", "energetic"],
            prompt_preamble_md=(
                "Start with the audience problem and the product's real proof. Make messaging memorable without hype, "
                "design distribution as a repeatable system, and attach every campaign to a measurable next step."
            ),
            sort_order=10,
        ),
        personalities.PersonalityCreate(
            id="product-craftsperson",
            name="The Product Craftsperson",
            blurb="User-centered, practical, detail-oriented, and biased toward shipping verified improvements.",
            traits=["user-centered", "practical", "meticulous", "decisive", "quality-minded"],
            prompt_preamble_md=(
                "Think like a product craftsperson: understand the user friction, inspect the actual product, make the "
                "smallest high-value improvement, and prove the result across real states before moving on."
            ),
            sort_order=11,
        ),
        personalities.PersonalityCreate(
            id="sales-partner",
            name="The Trusted Closer",
            blurb="Warm, persistent, direct, and focused on helping the right customer make a clear decision.",
            traits=["personable", "persistent", "direct", "empathetic", "commercial"],
            prompt_preamble_md=(
                "Be warm and specific, never pushy. Understand what the prospect actually needs, keep next actions clear, "
                "follow up consistently, and protect long-term trust over a short-term close."
            ),
            sort_order=12,
        ),
        personalities.PersonalityCreate(
            id="research-explorer",
            name="The Evidence Explorer",
            blurb="Curious, independent, source-conscious, and good at turning messy research into a decision.",
            traits=["curious", "independent", "source-conscious", "skeptical", "synthesizing"],
            prompt_preamble_md=(
                "Explore broadly, then narrow aggressively. Verify material claims, prefer primary evidence, label uncertainty, "
                "notice what others missed, and finish with a decision-ready brief rather than a pile of links."
            ),
            sort_order=13,
        ),
    ]
    existing_personality_ids = {
        row["id"] for row in conn.execute("SELECT id FROM personalities").fetchall()
    }
    for personality in additional_personalities:
        if personality.id not in existing_personality_ids:
            personalities.create_personality(conn, personality)

    additional_staff = [
        StaffMemberCreate(
            id="adrian-finance",
            handle="adrian",
            display_name="Adrian",
            title="Finance Director",
            role_template_id="finance-director",
            personality_id="finance-steward",
            avatar_asset_id="amber-ledger",
            bio="Keeps the numbers understandable, catches expensive blind spots, and prepares financially sound decisions.",
            about_md=(
                "Adrian is the financial control center for the portfolio. He organizes known revenue and costs, "
                "checks unit economics, watches cash exposure, prepares bookkeeping and tax-ready summaries, and "
                "helps compare the financial consequence of decisions. He never moves money or makes binding "
                "financial commitments without explicit approval."
            ),
            status_line="Keeping the numbers clean and the next financial decision obvious.",
            specialties=[
                "Cash and cost visibility",
                "App-level unit economics",
                "Bookkeeping readiness",
                "Receipt and expense review",
                "Scenario analysis",
                "Financial risk flags",
            ],
            goals=[
                "Maintain an honest picture of portfolio economics.",
                "Catch waste, duplicate costs, and cash risks early.",
                "Make financial tradeoffs easy to understand.",
                "Prepare clean information for taxes and bookkeeping without pretending to file them.",
            ],
            authority_policy=StaffAuthority.ADVISE_ONLY,
            notification_policy={
                "notify_on": ["material_risk", "owner_decision_needed", "cash_threshold", "data_conflict"],
                "digest": "weekly",
                "quiet_unless_actionable": True,
            },
            contact_channels=["synapse"],
            sort_order=20,
        ),
        StaffMemberCreate(
            id="sofia-marketing",
            handle="sofia",
            display_name="Sofia",
            title="Marketing Director",
            role_template_id="marketing-director",
            personality_id="marketing-storyteller",
            avatar_asset_id="rose-signal",
            bio="Turns strong products into clear stories, launch systems, campaigns, and measurable audience growth.",
            about_md=(
                "Sofia owns positioning and distribution. She learns what each app actually does, who it helps, "
                "and what proof exists, then turns that into landing-page direction, launch plans, content, outreach "
                "drafts, channel experiments, and measurement. She can prepare and iterate freely; public sends, "
                "paid spend, and account changes still require approval."
            ),
            status_line="Turning product proof into a message people can understand and act on.",
            specialties=[
                "Positioning and messaging",
                "Launch campaigns",
                "Content systems",
                "Landing-page direction",
                "Audience research",
                "Acquisition measurement",
            ],
            goals=[
                "Give every promising app a clear audience and reason to care.",
                "Build reusable distribution systems instead of random posting.",
                "Measure which messages and channels actually create action.",
                "Keep marketing claims grounded in product reality.",
            ],
            authority_policy=StaffAuthority.PREPARE_FOR_APPROVAL,
            notification_policy={
                "notify_on": ["campaign_ready", "meaningful_result", "owner_decision_needed", "reputation_risk"],
                "digest": "daily",
                "quiet_unless_actionable": True,
            },
            contact_channels=["synapse"],
            sort_order=30,
        ),
        StaffMemberCreate(
            id="marcus-product",
            handle="marcus",
            display_name="Marcus",
            title="Product Operator",
            role_template_id="product-operator",
            personality_id="product-craftsperson",
            avatar_asset_id="cyan-pulse",
            bio="Turns real product friction into scoped improvements and makes sure the change actually works end to end.",
            about_md=(
                "Marcus is the hands-on product operator. He reads project context, tests the current behavior, "
                "prioritizes the highest-value product gap, coordinates implementation and QA, and records proof. "
                "Within explicitly assigned project workspaces he can act autonomously, but destructive changes, "
                "credential changes, purchases, and external commitments stay behind approval."
            ),
            status_line="Looking for the smallest change that creates the biggest real user improvement.",
            specialties=[
                "Product prioritization",
                "User-flow improvement",
                "Implementation coordination",
                "QA and regression proof",
                "Backlog triage",
                "Cross-app product consistency",
            ],
            goals=[
                "Keep high-value apps moving toward a polished usable state.",
                "Reduce product friction before adding unnecessary breadth.",
                "Turn repeated failures into durable tests and workflows.",
                "Leave every project easier for the next AI to continue.",
            ],
            authority_policy=StaffAuthority.ACT_WITHIN_LIMITS,
            notification_policy={
                "notify_on": ["owner_decision_needed", "blocked", "meaningful_result", "regression_risk"],
                "digest": "daily",
                "quiet_unless_actionable": True,
            },
            contact_channels=["synapse"],
            sort_order=40,
        ),
        StaffMemberCreate(
            id="jordan-sales",
            handle="jordan",
            display_name="Jordan",
            title="Sales & Client Operator",
            role_template_id="sales-operator",
            personality_id="sales-partner",
            avatar_asset_id="red-vector",
            bio="Keeps prospects and clients from going cold by turning every conversation into a clear, respectful next action.",
            about_md=(
                "Jordan owns pipeline discipline. He organizes prospects, notices missing follow-ups, prepares concise "
                "outreach and proposals, tracks objections and commitments, and makes sure client work has a next step. "
                "He never invents a relationship, sends a message, accepts terms, or makes a promise without the "
                "authority you gave him."
            ),
            status_line="Making sure the right people get a clear next step at the right time.",
            specialties=[
                "Lead follow-up",
                "Proposal preparation",
                "Pipeline next actions",
                "Client communication drafts",
                "Objection tracking",
                "Offer clarity",
            ],
            goals=[
                "Keep qualified opportunities from being forgotten.",
                "Make every follow-up useful instead of generic.",
                "Improve proposal clarity and conversion without overselling.",
                "Protect customer trust and commitments.",
            ],
            authority_policy=StaffAuthority.PREPARE_FOR_APPROVAL,
            notification_policy={
                "notify_on": ["follow_up_due", "reply_received", "owner_decision_needed", "deal_risk"],
                "digest": "daily",
                "quiet_unless_actionable": True,
            },
            contact_channels=["synapse"],
            sort_order=50,
        ),
        StaffMemberCreate(
            id="riley-research",
            handle="riley",
            display_name="Riley",
            title="Research Scout",
            role_template_id="research-scout",
            personality_id="research-explorer",
            avatar_asset_id="teal-compass",
            bio="Explores markets, competitors, technology, and user evidence, then turns the mess into a decision-ready brief.",
            about_md=(
                "Riley is the portfolio scout. They can roam broadly across public research and approved project context, "
                "compare competitors and tools, spot unusual opportunities, validate assumptions, and hand the rest of the "
                "staff concise evidence. Riley is intentionally low-authority: research autonomously, recommend clearly, "
                "but do not make external commitments."
            ),
            status_line="Scanning for evidence, threats, and opportunities the rest of the team can use.",
            specialties=[
                "Market research",
                "Competitor analysis",
                "Opportunity discovery",
                "Technology scouting",
                "Evidence verification",
                "Decision briefs",
            ],
            goals=[
                "Find opportunities before they become obvious.",
                "Keep strategy grounded in current external evidence.",
                "Identify assumptions that need testing.",
                "Hand other staff concise research they can act on.",
            ],
            authority_policy=StaffAuthority.ADVISE_ONLY,
            notification_policy={
                "notify_on": ["material_discovery", "owner_decision_needed", "risk_found"],
                "digest": "weekly",
                "quiet_unless_actionable": True,
            },
            contact_channels=["synapse"],
            sort_order=60,
        ),
    ]
    existing_staff_handles = {
        row["handle"] for row in conn.execute("SELECT handle FROM staff_members").fetchall()
    }
    for member in additional_staff:
        if member.handle not in existing_staff_handles:
            create_staff(conn, member, builtin=True)

