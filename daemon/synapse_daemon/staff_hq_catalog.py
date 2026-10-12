"""Idempotent revenue and creator staff catalog for the existing Synapse Staff DB.

No independent account store or background service: standalone and embedded UIs
must use Synapse's authenticated /api/v1/staff routes.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from . import agent_squads, personalities, staff, staff_operations as ops


@dataclass(frozen=True)
class EmployeeBlueprint:
    handle: str
    name: str
    title: str
    team: str
    purpose: str
    responsibilities: tuple[str, ...]
    goals: tuple[str, ...]
    avatar: str
    authority: staff.StaffAuthority
    personality: tuple[str, ...]
    kpis: tuple[str, ...]
    triggers: tuple[str, ...]


CREW: tuple[EmployeeBlueprint, ...] = (
    EmployeeBlueprint("lena", "Lena", "Personal Money Adviser", "Money",
        "Helps with personal budgets, savings plans, bills and financial tradeoffs; separates personal finances from Adrian's business finance.",
        ("Review personal cash flow", "Prepare a realistic earning and savings plan", "Surface unnecessary spending and upcoming bills"),
        ("Help the owner create a positive cash buffer", "Keep personal money decisions evidence based"),
        "amber-ledger", staff.StaffAuthority.ADVISE_ONLY,
        ("calm", "precise", "supportive", "practical"),
        ("Monthly available cash verified", "Savings goals with tracked progress"),
        ("Personal money review",)),
    EmployeeBlueprint("eli", "Eli", "Live Streaming Director", "Creator",
        "A conversational creator coach for OBS scenes, audio, camera composition, screen capture and live production; all live feeds must be explicitly granted for each session.",
        ("Prepare streaming checklist", "Coach during user-authorized recording", "Mark worthwhile clip moments"),
        ("Get a reliable livestream setup", "Help capture useful real development stories"),
        "orbit-blue", staff.StaffAuthority.PREPARE_FOR_APPROVAL,
        ("energetic", "observant", "technical", "concise"),
        ("Verified recordings", "Clip opportunities marked"),
        ("Creator session prep",)),
    EmployeeBlueprint("nova", "Nova", "Video Editor & Producer", "Creator",
        "Plans and prepares full-length videos, clips, captions and Shorts from media the owner explicitly provides.",
        ("Build edit plans", "Draft short-form cuts", "Prepare captions and titles"),
        ("Turn real recordings into reusable content", "Improve output quality without false footage"),
        "violet-grid", staff.StaffAuthority.PREPARE_FOR_APPROVAL,
        ("creative", "structured", "fast", "detail-oriented"),
        ("Edited videos approved", "Clips exported"),
        ("Recorded media ready",)),
    EmployeeBlueprint("zoe", "Zoe", "Social Media Manager", "Creator",
        "Maintains content calendars, platform-specific post drafts and comment-response drafts; never posts or replies publicly without narrowly scoped permission.",
        ("Plan cross-platform posts", "Prepare account-specific captions", "Review audience feedback"),
        ("Build repeatable distribution", "Track actual leads rather than vanity metrics"),
        "rose-signal", staff.StaffAuthority.PREPARE_FOR_APPROVAL,
        ("engaging", "organized", "empathetic", "analytical"),
        ("Approved posts published", "Qualified audience responses"),
        ("Content calendar review",)),
    EmployeeBlueprint("iris", "Iris", "Creative Designer", "Creator",
        "Prepares stream overlays, thumbnails, backgrounds, brand guides and visual assets using approved generation/editing tools.",
        ("Design creator assets", "Maintain recognizable brand style", "QA thumbnail readability"),
        ("Make content immediately recognizable", "Save reusable branded layouts"),
        "indigo-lab", staff.StaffAuthority.PREPARE_FOR_APPROVAL,
        ("inventive", "tasteful", "precise", "consistent"),
        ("Approved visuals delivered", "Brand assets reusable"),
        ("Weekly design needs",)),
    EmployeeBlueprint("felix", "Felix", "Partnerships Manager", "Revenue",
        "Discovers sponsorships, creator partnerships and affiliate opportunities and prepares verifiable proposals without claiming a deal exists.",
        ("Research legitimate partnership opportunities", "Draft outreach and media kits", "Assess sponsorship fit"),
        ("Build trustworthy monetization partnerships", "Avoid reputational and financial risks"),
        "red-vector", staff.StaffAuthority.PREPARE_FOR_APPROVAL,
        ("resourceful", "professional", "honest", "commercial"),
        ("Qualified opportunities verified", "Approved partnership conversations"),
        ("Partnership opportunity scan",)),
    EmployeeBlueprint("tess", "Tess", "Chief of Staff", "Operations",
        "Coordinates personal priorities and inter-employee handoffs; not a replacement for the technical AI Supervisor.",
        ("Triage requests across employees", "Prepare an actionable daily briefing", "Surface stalled approvals"),
        ("Minimize interruptions", "Keep high-value work moving"),
        "emerald-core", staff.StaffAuthority.PREPARE_FOR_APPROVAL,
        ("organized", "decisive", "considerate", "clear"),
        ("Owner decisions resolved", "Priority tasks with verified progress"),
        ("Daily staff briefing",)),
    EmployeeBlueprint("sam", "Sam", "Customer Success Manager", "Revenue",
        "Builds support workflows and onboarding improvements, drafts customer communication and watches verified customer pain points.",
        ("Prepare support replies", "Review onboarding friction", "Summarize customer feedback"),
        ("Retain genuinely satisfied customers", "Close real support loops"),
        "teal-compass", staff.StaffAuthority.PREPARE_FOR_APPROVAL,
        ("patient", "helpful", "systematic", "honest"),
        ("Support responses approved", "Onboarding blockers resolved"),
        ("Customer support review",)),
)

# Camera, screen, microphone, financial accounts and public actions are NEVER
# implied by a staff profile or the act_within_limits label.
SENSITIVE_CAPABILITIES = (
    "camera", "microphone", "screen_capture", "obs_control",
    "account_access", "publish", "send", "spend", "transfer", "trade",
    "credential_change", "public_broadcast",
)


def seed_creator_revenue_staff(conn: sqlite3.Connection) -> None:
    """Create missing staff profiles; preserve all user-customized existing rows.

    Triggers are metadata and default disabled until a real scheduler with
    authorization, throttling and audit receipts has been connected.
    """
    existing_roles = {row["id"] for row in conn.execute("SELECT id FROM agent_role_templates")}
    existing_personalities = {row["id"] for row in conn.execute("SELECT id FROM personalities")}
    existing_handles = {row["handle"] for row in conn.execute("SELECT handle FROM staff_members")}

    for index, blueprint in enumerate(CREW, start=70):
        role_id = f"staff-hq-{blueprint.handle}"
        personality_id = f"staff-hq-persona-{blueprint.handle}"
        if role_id not in existing_roles:
            agent_squads.create_role_template(
                conn, agent_squads.AgentRoleTemplateCreate(
                    id=role_id, name=blueprint.title,
                    description=blueprint.purpose,
                    preferred_runtimes=["chatgpt_web", "claude", "gemini"],
                    default_visibility=agent_squads.AgentVisibility.HELPER,
                    context_mode=agent_squads.AgentContextMode.FULL,
                    role_tier=agent_squads.AgentRoleTier.SUPERVISOR,
                    can_delegate=blueprint.handle in {"tess", "eli", "nova", "zoe"},
                    prompt_preamble_md=(
                        f"You are {blueprint.name}, the owner's {blueprint.title}. "
                        f"Your job: {blueprint.purpose} "
                        "Use verified evidence. Speak proactively only when relevant; avoid repeated interruptions. "
                        "Never pretend that a tool, camera, screen, bank or social account is connected. "
                        "Never infer permission to stream, upload, publish, send, buy, trade, or access private media. "
                        "Request precise consent for each sensitive external action and keep truthful receipts."
                    ), sort_order=index,
                )
            )
        if personality_id not in existing_personalities:
            personalities.create_personality(conn, personalities.PersonalityCreate(
                id=personality_id, name=f"{blueprint.name}'s voice",
                blurb=blueprint.purpose, traits=list(blueprint.personality),
                prompt_preamble_md=(
                    "Converse like a capable person: warm, specific, independent in judgment, "
                    "brief when busy, and willing to challenge bad assumptions. "
                    "Your personality is a consistent communication style, not a claim to be human."
                ), sort_order=index,
            ))
        if blueprint.handle not in existing_handles:
            staff.create_staff(conn, staff.StaffMemberCreate(
                id=f"staff-hq-{blueprint.handle}",
                handle=blueprint.handle, display_name=blueprint.name,
                title=blueprint.title, role_template_id=role_id,
                personality_id=personality_id, avatar_asset_id=blueprint.avatar,
                bio=blueprint.purpose,
                about_md=f"Team: {blueprint.team}. Responsibilities: {'; '.join(blueprint.responsibilities)}.",
                status_line="Ready for an approved assignment · integrations not verified",
                specialties=list(blueprint.responsibilities),
                goals=list(blueprint.goals),
                authority_policy=blueprint.authority,
                notification_policy={"notify_on": ["meaningful_result", "decision_needed", "blocked"],
                                     "digest": "daily", "quiet_unless_actionable": True},
                contact_channels=["synapse"],
                sort_order=index,
            ), builtin=True)

        # Never overwrite a user's saved permissions. Explicit denies are
        # enforced independently of the broad role authority setting.
        for capability in SENSITIVE_CAPABILITIES:
            if conn.execute(
                "SELECT 1 FROM staff_permissions WHERE staff_member_id=? "
                "AND scope_type='external_action' AND scope_id='*' AND capability=?",
                (f"staff-hq-{blueprint.handle}", capability)
            ).fetchone() is None:
                ops._seed_permission(conn, blueprint.handle, "external_action", "*",
                                     capability, "ask",
                                     "Requires explicit per-action owner approval and a connected source.")
        ops._seed_channel(conn, blueprint.handle, "synapse", "connected")
        for i, responsibility in enumerate(blueprint.responsibilities):
            ops._insert_responsibility(conn, blueprint.handle, responsibility,
                                       blueprint.purpose, "high" if i == 0 else "medium",
                                       "ongoing", i + 10)
        for i, kpi in enumerate(blueprint.kpis):
            ops._insert_seed_kpi(conn, blueprint.handle, kpi,
                                 "Not connected; never fabricate progress.",
                                 "count", "increase", "monthly", i + 10)
        for trigger in blueprint.triggers:
            ops._seed_trigger(conn, blueprint.handle, trigger, "schedule",
                              {"cadence": "daily", "timezone": "America/Chicago"},
                              f"Review {trigger.lower()}; propose useful actions with evidence. "
                              "Do not execute external actions without explicit authorization.")
