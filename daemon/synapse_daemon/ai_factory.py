"""SQLite-backed AI Factory catalog for recipes, components, and sources.

The AI Factory is Synapse's native authoring/operating surface for reusable
generation intelligence: recipe blueprints, nav/layout/interaction packs,
profiles, policies, and provenance-aware source intake.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from .errors import invalid, not_found
from .time_utils import from_iso, to_iso, utc_now


class AiComponentFamily(str, Enum):
    NAV_PACK = "nav_pack"
    LAYOUT_PACK = "layout_pack"
    INTERACTION_PACK = "interaction_pack"
    VISUAL_SYSTEM = "visual_system"
    DENSITY_RULE = "density_rule"
    ASSET_PACK = "asset_pack"
    WORKFLOW_PRESET = "workflow_preset"
    TEST_PACK = "test_pack"
    BRAND_PROFILE = "brand_profile"
    TECH_PROFILE = "tech_profile"
    DATA_PROFILE = "data_profile"
    DEPLOYMENT_PROFILE = "deployment_profile"
    QUALITY_PROFILE = "quality_profile"
    SIMILARITY_POLICY = "similarity_policy"
    EVIDENCE_POLICY = "evidence_policy"
    PROVENANCE_POLICY = "provenance_policy"


class AiSourceType(str, Enum):
    WEB = "web"
    REPO = "repo"
    MANUAL = "manual"
    SCREENSHOT = "screenshot"
    API_SURFACE = "api_surface"


class AiReusePosture(str, Enum):
    REFERENCE_ONLY = "reference_only"
    USER_AUTHORIZED = "user_authorized"
    LICENSED_REUSABLE = "licensed_reusable"
    UNKNOWN_RESTRICTED = "unknown_restricted"


class AiComponent(BaseModel):
    id: str
    family: AiComponentFamily
    name: str
    description: str = ""
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    content_md: str = ""
    builtin: bool = False
    source_id: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class AiComponentCreate(BaseModel):
    id: str
    family: AiComponentFamily
    name: str
    description: str = ""
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    content_md: str = ""
    builtin: bool = False
    source_id: str | None = None


class AiComponentUpdate(BaseModel):
    family: AiComponentFamily | None = None
    name: str | None = None
    description: str | None = None
    tags: list[str] | None = None
    metadata: dict[str, Any] | None = None
    content_md: str | None = None
    source_id: str | None = None


class AiRecipe(BaseModel):
    id: str
    name: str
    description: str = ""
    archetype: str
    nav_model: str
    interaction_model: str
    visual_language: str
    data_behavior: str
    density_rule: str
    component_ids: list[str] = Field(default_factory=list)
    default_directives: dict[str, Any] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)
    builtin: bool = False
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class AiRecipeCreate(BaseModel):
    id: str
    name: str
    description: str = ""
    archetype: str
    nav_model: str
    interaction_model: str
    visual_language: str
    data_behavior: str
    density_rule: str
    component_ids: list[str] = Field(default_factory=list)
    default_directives: dict[str, Any] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)
    builtin: bool = False


class AiRecipeUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    archetype: str | None = None
    nav_model: str | None = None
    interaction_model: str | None = None
    visual_language: str | None = None
    data_behavior: str | None = None
    density_rule: str | None = None
    component_ids: list[str] | None = None
    default_directives: dict[str, Any] | None = None
    tags: list[str] | None = None


class AiSource(BaseModel):
    id: str
    label: str
    source_type: AiSourceType
    url: str | None = None
    reuse_posture: AiReusePosture = AiReusePosture.REFERENCE_ONLY
    provenance_summary: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)
    notes_md: str = ""
    builtin: bool = False
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class AiSourceCreate(BaseModel):
    id: str
    label: str
    source_type: AiSourceType
    url: str | None = None
    reuse_posture: AiReusePosture = AiReusePosture.REFERENCE_ONLY
    provenance_summary: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)
    notes_md: str = ""
    builtin: bool = False


class AiSourceUpdate(BaseModel):
    label: str | None = None
    source_type: AiSourceType | None = None
    url: str | None = None
    reuse_posture: AiReusePosture | None = None
    provenance_summary: str | None = None
    metadata: dict[str, Any] | None = None
    notes_md: str | None = None


class AiSourcePromoteRequest(BaseModel):
    target_type: str
    new_id: str
    name: str
    family: AiComponentFamily | None = None
    description: str = ""
    notes_md: str = ""


class AiFactoryCatalog(BaseModel):
    components: list[AiComponent] = Field(default_factory=list)
    recipes: list[AiRecipe] = Field(default_factory=list)
    sources: list[AiSource] = Field(default_factory=list)


def _loads_list(payload: str | None) -> list[str]:
    if not payload:
        return []
    data = json.loads(payload)
    return [str(item) for item in data] if isinstance(data, list) else []


def _loads_dict(payload: str | None) -> dict[str, Any]:
    if not payload:
        return {}
    data = json.loads(payload)
    return data if isinstance(data, dict) else {}


def _row_to_component(row: sqlite3.Row) -> AiComponent:
    return AiComponent(
        id=row["id"],
        family=AiComponentFamily(row["family"]),
        name=row["name"],
        description=row["description"] or "",
        tags=_loads_list(row["tags_json"]),
        metadata=_loads_dict(row["metadata_json"]),
        content_md=row["content_md"] or "",
        builtin=bool(row["builtin"]),
        source_id=row["source_id"],
        created_at=from_iso(row["created_at"]),
        updated_at=from_iso(row["updated_at"]),
    )


def _row_to_recipe(row: sqlite3.Row) -> AiRecipe:
    return AiRecipe(
        id=row["id"],
        name=row["name"],
        description=row["description"] or "",
        archetype=row["archetype"],
        nav_model=row["nav_model"],
        interaction_model=row["interaction_model"],
        visual_language=row["visual_language"],
        data_behavior=row["data_behavior"],
        density_rule=row["density_rule"],
        component_ids=_loads_list(row["component_ids_json"]),
        default_directives=_loads_dict(row["default_directives_json"]),
        tags=_loads_list(row["tags_json"]),
        builtin=bool(row["builtin"]),
        created_at=from_iso(row["created_at"]),
        updated_at=from_iso(row["updated_at"]),
    )


def _row_to_source(row: sqlite3.Row) -> AiSource:
    return AiSource(
        id=row["id"],
        label=row["label"],
        source_type=AiSourceType(row["source_type"]),
        url=row["url"],
        reuse_posture=AiReusePosture(row["reuse_posture"]),
        provenance_summary=row["provenance_summary"] or "",
        metadata=_loads_dict(row["metadata_json"]),
        notes_md=row["notes_md"] or "",
        builtin=bool(row["builtin"]),
        created_at=from_iso(row["created_at"]),
        updated_at=from_iso(row["updated_at"]),
    )


def list_components(conn: sqlite3.Connection) -> list[AiComponent]:
    rows = conn.execute(
        "SELECT * FROM ai_factory_components ORDER BY family, builtin DESC, name COLLATE NOCASE"
    ).fetchall()
    return [_row_to_component(row) for row in rows]


def get_component(conn: sqlite3.Connection, component_id: str) -> AiComponent:
    row = conn.execute(
        "SELECT * FROM ai_factory_components WHERE id = ?",
        (component_id,),
    ).fetchone()
    if row is None:
        raise not_found("ai_component", component_id)
    return _row_to_component(row)


def create_component(conn: sqlite3.Connection, payload: AiComponentCreate) -> AiComponent:
    now = utc_now()
    if conn.execute(
        "SELECT 1 FROM ai_factory_components WHERE id = ?",
        (payload.id,),
    ).fetchone():
        raise invalid("ai_component", f"Component id '{payload.id}' already exists.")
    conn.execute(
        """
        INSERT INTO ai_factory_components (
            id, family, name, description, tags_json, metadata_json, content_md,
            builtin, source_id, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            payload.id,
            payload.family.value,
            payload.name,
            payload.description,
            json.dumps(payload.tags),
            json.dumps(payload.metadata),
            payload.content_md,
            1 if payload.builtin else 0,
            payload.source_id,
            to_iso(now),
            to_iso(now),
        ),
    )
    return get_component(conn, payload.id)


def update_component(
    conn: sqlite3.Connection,
    component_id: str,
    payload: AiComponentUpdate,
) -> AiComponent:
    current = get_component(conn, component_id)
    data = current.model_dump()
    for key, value in payload.model_dump(exclude_none=True).items():
        data[key] = value
    updated = AiComponent.model_validate({**data, "updated_at": utc_now()})
    conn.execute(
        """
        UPDATE ai_factory_components
        SET family = ?, name = ?, description = ?, tags_json = ?, metadata_json = ?,
            content_md = ?, source_id = ?, updated_at = ?
        WHERE id = ?
        """,
        (
            updated.family.value,
            updated.name,
            updated.description,
            json.dumps(updated.tags),
            json.dumps(updated.metadata),
            updated.content_md,
            updated.source_id,
            to_iso(updated.updated_at),
            component_id,
        ),
    )
    return get_component(conn, component_id)


def delete_component(conn: sqlite3.Connection, component_id: str) -> None:
    current = get_component(conn, component_id)
    if current.builtin:
        raise invalid("ai_component", "Built-in components cannot be deleted.")
    conn.execute("DELETE FROM ai_factory_components WHERE id = ?", (component_id,))


def list_recipes(conn: sqlite3.Connection) -> list[AiRecipe]:
    rows = conn.execute(
        "SELECT * FROM ai_factory_recipes ORDER BY builtin DESC, name COLLATE NOCASE"
    ).fetchall()
    return [_row_to_recipe(row) for row in rows]


def get_recipe(conn: sqlite3.Connection, recipe_id: str) -> AiRecipe:
    row = conn.execute(
        "SELECT * FROM ai_factory_recipes WHERE id = ?",
        (recipe_id,),
    ).fetchone()
    if row is None:
        raise not_found("ai_recipe", recipe_id)
    return _row_to_recipe(row)


def create_recipe(conn: sqlite3.Connection, payload: AiRecipeCreate) -> AiRecipe:
    now = utc_now()
    if conn.execute(
        "SELECT 1 FROM ai_factory_recipes WHERE id = ?",
        (payload.id,),
    ).fetchone():
        raise invalid("ai_recipe", f"Recipe id '{payload.id}' already exists.")
    conn.execute(
        """
        INSERT INTO ai_factory_recipes (
            id, name, description, archetype, nav_model, interaction_model,
            visual_language, data_behavior, density_rule, component_ids_json,
            default_directives_json, tags_json, builtin, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            payload.id,
            payload.name,
            payload.description,
            payload.archetype,
            payload.nav_model,
            payload.interaction_model,
            payload.visual_language,
            payload.data_behavior,
            payload.density_rule,
            json.dumps(payload.component_ids),
            json.dumps(payload.default_directives),
            json.dumps(payload.tags),
            1 if payload.builtin else 0,
            to_iso(now),
            to_iso(now),
        ),
    )
    return get_recipe(conn, payload.id)


def update_recipe(
    conn: sqlite3.Connection,
    recipe_id: str,
    payload: AiRecipeUpdate,
) -> AiRecipe:
    current = get_recipe(conn, recipe_id)
    data = current.model_dump()
    for key, value in payload.model_dump(exclude_none=True).items():
        data[key] = value
    updated = AiRecipe.model_validate({**data, "updated_at": utc_now()})
    conn.execute(
        """
        UPDATE ai_factory_recipes
        SET name = ?, description = ?, archetype = ?, nav_model = ?, interaction_model = ?,
            visual_language = ?, data_behavior = ?, density_rule = ?, component_ids_json = ?,
            default_directives_json = ?, tags_json = ?, updated_at = ?
        WHERE id = ?
        """,
        (
            updated.name,
            updated.description,
            updated.archetype,
            updated.nav_model,
            updated.interaction_model,
            updated.visual_language,
            updated.data_behavior,
            updated.density_rule,
            json.dumps(updated.component_ids),
            json.dumps(updated.default_directives),
            json.dumps(updated.tags),
            to_iso(updated.updated_at),
            recipe_id,
        ),
    )
    return get_recipe(conn, recipe_id)


def delete_recipe(conn: sqlite3.Connection, recipe_id: str) -> None:
    current = get_recipe(conn, recipe_id)
    if current.builtin:
        raise invalid("ai_recipe", "Built-in recipes cannot be deleted.")
    conn.execute("DELETE FROM ai_factory_recipes WHERE id = ?", (recipe_id,))


def list_sources(conn: sqlite3.Connection) -> list[AiSource]:
    rows = conn.execute(
        "SELECT * FROM ai_factory_sources ORDER BY builtin DESC, updated_at DESC, label COLLATE NOCASE"
    ).fetchall()
    return [_row_to_source(row) for row in rows]


def get_source(conn: sqlite3.Connection, source_id: str) -> AiSource:
    row = conn.execute(
        "SELECT * FROM ai_factory_sources WHERE id = ?",
        (source_id,),
    ).fetchone()
    if row is None:
        raise not_found("ai_source", source_id)
    return _row_to_source(row)


def create_source(conn: sqlite3.Connection, payload: AiSourceCreate) -> AiSource:
    now = utc_now()
    if conn.execute(
        "SELECT 1 FROM ai_factory_sources WHERE id = ?",
        (payload.id,),
    ).fetchone():
        raise invalid("ai_source", f"Source id '{payload.id}' already exists.")
    conn.execute(
        """
        INSERT INTO ai_factory_sources (
            id, label, source_type, url, reuse_posture, provenance_summary,
            metadata_json, notes_md, builtin, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            payload.id,
            payload.label,
            payload.source_type.value,
            payload.url,
            payload.reuse_posture.value,
            payload.provenance_summary,
            json.dumps(payload.metadata),
            payload.notes_md,
            1 if payload.builtin else 0,
            to_iso(now),
            to_iso(now),
        ),
    )
    return get_source(conn, payload.id)


def update_source(
    conn: sqlite3.Connection,
    source_id: str,
    payload: AiSourceUpdate,
) -> AiSource:
    current = get_source(conn, source_id)
    data = current.model_dump()
    for key, value in payload.model_dump(exclude_none=True).items():
        data[key] = value
    updated = AiSource.model_validate({**data, "updated_at": utc_now()})
    conn.execute(
        """
        UPDATE ai_factory_sources
        SET label = ?, source_type = ?, url = ?, reuse_posture = ?, provenance_summary = ?,
            metadata_json = ?, notes_md = ?, updated_at = ?
        WHERE id = ?
        """,
        (
            updated.label,
            updated.source_type.value,
            updated.url,
            updated.reuse_posture.value,
            updated.provenance_summary,
            json.dumps(updated.metadata),
            updated.notes_md,
            to_iso(updated.updated_at),
            source_id,
        ),
    )
    return get_source(conn, source_id)


def delete_source(conn: sqlite3.Connection, source_id: str) -> None:
    current = get_source(conn, source_id)
    if current.builtin:
        raise invalid("ai_source", "Built-in sources cannot be deleted.")
    conn.execute("DELETE FROM ai_factory_sources WHERE id = ?", (source_id,))


def promote_source(
    conn: sqlite3.Connection,
    source_id: str,
    payload: AiSourcePromoteRequest,
) -> AiComponent | AiRecipe:
    source = get_source(conn, source_id)
    description = payload.description or source.provenance_summary or source.label
    notes = "\n".join(
        line for line in [
            source.notes_md.strip(),
            payload.notes_md.strip(),
            f"Promoted from source `{source.id}` ({source.source_type.value}).",
        ] if line
    )
    if payload.target_type == "component":
        if payload.family is None:
            raise invalid("ai_source", "Promoting to a component requires a family.")
        return create_component(
            conn,
            AiComponentCreate(
                id=payload.new_id,
                family=payload.family,
                name=payload.name,
                description=description,
                content_md=notes,
                tags=["promoted", source.source_type.value],
                metadata={"promoted_from": source.id, "source_url": source.url},
                source_id=source.id,
            ),
        )
    if payload.target_type == "recipe":
        return create_recipe(
            conn,
            AiRecipeCreate(
                id=payload.new_id,
                name=payload.name,
                description=description,
                archetype="harvested",
                nav_model="reference-derived",
                interaction_model="reference-derived",
                visual_language="reference-derived",
                data_behavior="reference-derived",
                density_rule="no_full_page_scroll",
                tags=["promoted", source.source_type.value],
                default_directives={
                    "promotion_notes_md": notes,
                    "source_id": source.id,
                    "source_url": source.url,
                },
            ),
        )
    raise invalid("ai_source", "target_type must be 'component' or 'recipe'.")


def catalog(conn: sqlite3.Connection) -> AiFactoryCatalog:
    return AiFactoryCatalog(
        components=list_components(conn),
        recipes=list_recipes(conn),
        sources=list_sources(conn),
    )


def counts(conn: sqlite3.Connection) -> dict[str, int]:
    return {
        "components": conn.execute("SELECT COUNT(*) FROM ai_factory_components").fetchone()[0],
        "recipes": conn.execute("SELECT COUNT(*) FROM ai_factory_recipes").fetchone()[0],
        "sources": conn.execute("SELECT COUNT(*) FROM ai_factory_sources").fetchone()[0],
    }


def seed_default_catalog(conn: sqlite3.Connection) -> None:
    for component in _seed_components():
        if conn.execute(
            "SELECT 1 FROM ai_factory_components WHERE id = ?",
            (component.id,),
        ).fetchone():
            continue
        create_component(conn, component)
    for recipe in _seed_recipes():
        if conn.execute(
            "SELECT 1 FROM ai_factory_recipes WHERE id = ?",
            (recipe.id,),
        ).fetchone():
            continue
        create_recipe(conn, recipe)
    if not conn.execute(
        "SELECT 1 FROM ai_factory_sources WHERE id = ?",
        ("synapse-internal-patterns",),
    ).fetchone():
        create_source(
            conn,
            AiSourceCreate(
                id="synapse-internal-patterns",
                label="Synapse internal patterns",
                source_type=AiSourceType.MANUAL,
                reuse_posture=AiReusePosture.USER_AUTHORIZED,
                provenance_summary="Built-in internal notes that describe the current Synapse product and workflow patterns.",
                notes_md=(
                    "Use this as the default reference source when harvesting from Synapse's own product "
                    "patterns, workflows, and generated-app bakeoff results."
                ),
                builtin=True,
            ),
        )


def _seed_components() -> list[AiComponentCreate]:
    return [
        AiComponentCreate(id="nav-left-rail", family=AiComponentFamily.NAV_PACK, name="Left rail workspace", description="A persistent left rail for multi-surface productivity apps.", tags=["nav", "workspace"], metadata={"model": "left_rail"}, builtin=True),
        AiComponentCreate(id="nav-top-tabs", family=AiComponentFamily.NAV_PACK, name="Top tabs workspace", description="Top-tab navigation for compact toolbars and quick context switching.", tags=["nav", "tabs"], metadata={"model": "top_tabs"}, builtin=True),
        AiComponentCreate(id="nav-split-pane", family=AiComponentFamily.NAV_PACK, name="Split pane inspector", description="Master-detail navigation with a stable inspector rail.", tags=["nav", "split_pane"], metadata={"model": "split_pane"}, builtin=True),
        AiComponentCreate(id="nav-bottom-mobile", family=AiComponentFamily.NAV_PACK, name="Bottom nav mobile shell", description="Mobile-friendly bottom navigation for touch-heavy flows.", tags=["nav", "mobile"], metadata={"model": "bottom_nav"}, builtin=True),
        AiComponentCreate(id="nav-command-palette", family=AiComponentFamily.NAV_PACK, name="Command palette first", description="Keyboard-first launch surface where actions outrank page chrome.", tags=["nav", "keyboard"], metadata={"model": "command_palette"}, builtin=True),
        AiComponentCreate(id="nav-wizard", family=AiComponentFamily.NAV_PACK, name="Wizard track", description="Step-based flow for guided setup and staged completion.", tags=["nav", "wizard"], metadata={"model": "wizard"}, builtin=True),
        AiComponentCreate(id="layout-cockpit", family=AiComponentFamily.LAYOUT_PACK, name="Cockpit triad", description="Three-zone cockpit with setup, live center board, and right-side evidence.", tags=["layout", "cockpit"], metadata={"zones": 3}, builtin=True),
        AiComponentCreate(id="layout-stacked-workspace", family=AiComponentFamily.LAYOUT_PACK, name="Stacked workspace", description="Top command bar with stacked work surfaces underneath.", tags=["layout", "workspace"], metadata={"zones": 2}, builtin=True),
        AiComponentCreate(id="layout-notebook-canvas", family=AiComponentFamily.LAYOUT_PACK, name="Notebook canvas", description="Notebook navigation with canvas-style detail views.", tags=["layout", "canvas"], metadata={"zones": 2}, builtin=True),
        AiComponentCreate(id="layout-dense-ops", family=AiComponentFamily.LAYOUT_PACK, name="Dense operations grid", description="High-density ops view for monitoring, triage, and many small controls.", tags=["layout", "dense"], metadata={"density": "high"}, builtin=True),
        AiComponentCreate(id="interaction-quick-add", family=AiComponentFamily.INTERACTION_PACK, name="Quick add everywhere", description="Fast inline creation from many surfaces.", tags=["interaction", "quick_add"], metadata={"model": "quick_add"}, builtin=True),
        AiComponentCreate(id="interaction-bulk-edit", family=AiComponentFamily.INTERACTION_PACK, name="Bulk edit flow", description="Selection, batch actions, and command trays for high-volume editing.", tags=["interaction", "bulk_edit"], metadata={"model": "bulk_edit"}, builtin=True),
        AiComponentCreate(id="interaction-inline-edit", family=AiComponentFamily.INTERACTION_PACK, name="Inline edit", description="Direct manipulation with small, local edits instead of full forms.", tags=["interaction", "inline_edit"], metadata={"model": "inline_edit"}, builtin=True),
        AiComponentCreate(id="interaction-drawers", family=AiComponentFamily.INTERACTION_PACK, name="Drawers and side panels", description="Secondary tasks open in drawers instead of page hops.", tags=["interaction", "drawers"], metadata={"model": "drawers"}, builtin=True),
        AiComponentCreate(id="interaction-keyboard-first", family=AiComponentFamily.INTERACTION_PACK, name="Keyboard-first operations", description="Shortcuts, palette actions, and focus rails for power users.", tags=["interaction", "keyboard"], metadata={"model": "keyboard_first"}, builtin=True),
        AiComponentCreate(id="visual-editorial", family=AiComponentFamily.VISUAL_SYSTEM, name="Editorial", description="Type-led, airy, confident layout language.", tags=["visual", "editorial"], metadata={"mood": "editorial"}, builtin=True),
        AiComponentCreate(id="visual-industrial", family=AiComponentFamily.VISUAL_SYSTEM, name="Industrial", description="Functional panels, hard edges, and utilitarian emphasis.", tags=["visual", "industrial"], metadata={"mood": "industrial"}, builtin=True),
        AiComponentCreate(id="visual-playful", family=AiComponentFamily.VISUAL_SYSTEM, name="Playful", description="Friendly cards, brighter accents, and approachable guidance.", tags=["visual", "playful"], metadata={"mood": "playful"}, builtin=True),
        AiComponentCreate(id="visual-dense-ops", family=AiComponentFamily.VISUAL_SYSTEM, name="Dense ops", description="Operational, information-rich, and highly scannable.", tags=["visual", "ops"], metadata={"mood": "dense_ops"}, builtin=True),
        AiComponentCreate(id="visual-notebook", family=AiComponentFamily.VISUAL_SYSTEM, name="Notebook", description="Thoughtful, layered, research-oriented interface language.", tags=["visual", "notebook"], metadata={"mood": "notebook"}, builtin=True),
        AiComponentCreate(id="visual-premium-saas", family=AiComponentFamily.VISUAL_SYSTEM, name="Premium SaaS", description="Clean, polished, commercial software aesthetic.", tags=["visual", "saas"], metadata={"mood": "premium_saas"}, builtin=True),
        AiComponentCreate(id="density-no-scroll", family=AiComponentFamily.DENSITY_RULE, name="No long-scroll by default", description="Prefer tabs, panels, and workspaces before a long page stack.", tags=["density", "rule"], metadata={"default": True}, builtin=True),
        AiComponentCreate(id="density-justified-scroll", family=AiComponentFamily.DENSITY_RULE, name="Justified long-scroll", description="Allow long pages only when the content is naturally narrative or reference-heavy.", tags=["density", "rule"], metadata={"default": False}, builtin=True),
        AiComponentCreate(id="quality-default", family=AiComponentFamily.QUALITY_PROFILE, name="Default quality gate", description="Requires nav clarity, empty states, mobile fit, and reviewer/tester completion.", tags=["quality"], metadata={"requires_reviewer": True, "requires_tester": True}, builtin=True),
        AiComponentCreate(id="similarity-advisory", family=AiComponentFamily.SIMILARITY_POLICY, name="Advisory similarity", description="Report similarity across dimensions without blocking generation.", tags=["similarity"], metadata={"blocking": False}, builtin=True),
        AiComponentCreate(id="evidence-repo-first", family=AiComponentFamily.EVIDENCE_POLICY, name="Repo-first evidence", description="Repo-backed and tool-observed evidence outrank generic web opinion.", tags=["evidence"], metadata={"priority": ["repo-backed", "tool-observed", "official-doc", "web"]}, builtin=True),
        AiComponentCreate(id="provenance-aware", family=AiComponentFamily.PROVENANCE_POLICY, name="Provenance aware", description="Capture whether a source is reference-only, licensed, user-authorized, or restricted.", tags=["provenance"], metadata={"requires_posture": True}, builtin=True),
        AiComponentCreate(id="tech-react-fastapi", family=AiComponentFamily.TECH_PROFILE, name="React + FastAPI fullstack", description="Local fullstack path using React/Vite frontend and FastAPI backend patterns.", tags=["tech", "fullstack"], metadata={"frontend": "react", "backend": "fastapi"}, builtin=True),
        AiComponentCreate(id="data-local-first", family=AiComponentFamily.DATA_PROFILE, name="Local-first data", description="Prefer local persistence and optimistic workflows before remote sync.", tags=["data", "local_first"], metadata={"mode": "local_first"}, builtin=True),
        AiComponentCreate(id="deploy-local-runner", family=AiComponentFamily.DEPLOYMENT_PROFILE, name="Local runnable deployment", description="Generated apps should be runnable locally with explicit start/test commands.", tags=["deployment", "local"], metadata={"target": "local"}, builtin=True),
        AiComponentCreate(id="test-playwright-review", family=AiComponentFamily.TEST_PACK, name="Playwright + reviewer pass", description="Requires browser smoke coverage plus reviewer/tester signoff.", tags=["test", "playwright"], metadata={"browser_required": True}, builtin=True),
        AiComponentCreate(id="workflow-bakeoff", family=AiComponentFamily.WORKFLOW_PRESET, name="Parallel bakeoff", description="Compare several generated candidates side by side before picking a winner.", tags=["workflow", "benchmark"], metadata={"case_mode": "benchmark"}, builtin=True),
    ]


def _seed_recipes() -> list[AiRecipeCreate]:
    recipes: list[AiRecipeCreate] = []
    archetypes = [
        ("planner", "left_rail", "quick_add", "editorial", "local_first", "density-no-scroll"),
        ("ledger", "top_tabs", "bulk_edit", "premium_saas", "fullstack_crud", "density-no-scroll"),
        ("studio", "split_pane", "inline_edit", "notebook", "synced_app", "density-no-scroll"),
        ("board", "left_rail", "drawers", "industrial", "collaborative", "density-no-scroll"),
        ("cockpit", "split_pane", "keyboard_first", "dense_ops", "synced_app", "density-no-scroll"),
        ("library", "top_tabs", "inline_edit", "editorial", "static_prototype", "density-justified-scroll"),
        ("console", "command_palette", "keyboard_first", "industrial", "local_first", "density-no-scroll"),
        ("canvas", "split_pane", "drawers", "playful", "local_first", "density-no-scroll"),
    ]
    recipe_names = {
        "planner": ["Focus board", "Sprint planner", "Goal grid", "Habit cockpit"],
        "ledger": ["Expense ledger", "Ops ledger", "Order tracker", "Asset register"],
        "studio": ["Content studio", "Prompt studio", "Media studio", "Snippet studio"],
        "board": ["Incident board", "Launch board", "Support board", "Research board"],
        "cockpit": ["Control room", "Fleet cockpit", "Growth cockpit", "Reliability cockpit"],
        "library": ["Reference vault", "Pattern library", "Docs shelf", "Knowledge atlas"],
        "console": ["Ops console", "Automation console", "Deploy console", "Debug console"],
        "canvas": ["Idea garden", "Journey canvas", "Mood canvas", "Concept wall"],
    }
    nav_components = {
        "left_rail": "nav-left-rail",
        "top_tabs": "nav-top-tabs",
        "split_pane": "nav-split-pane",
        "command_palette": "nav-command-palette",
    }
    interaction_components = {
        "quick_add": "interaction-quick-add",
        "bulk_edit": "interaction-bulk-edit",
        "inline_edit": "interaction-inline-edit",
        "drawers": "interaction-drawers",
        "keyboard_first": "interaction-keyboard-first",
    }
    visual_components = {
        "editorial": "visual-editorial",
        "industrial": "visual-industrial",
        "playful": "visual-playful",
        "dense_ops": "visual-dense-ops",
        "notebook": "visual-notebook",
        "premium_saas": "visual-premium-saas",
    }
    for archetype, nav_model, interaction_model, visual_language, data_behavior, density_rule in archetypes:
        for index, name in enumerate(recipe_names[archetype], start=1):
            recipe_id = f"{archetype}-{index}"
            component_ids = [
                nav_components.get(nav_model, "nav-left-rail"),
                interaction_components.get(interaction_model, "interaction-inline-edit"),
                visual_components.get(visual_language, "visual-editorial"),
                "quality-default",
                "similarity-advisory",
                "test-playwright-review",
                density_rule,
            ]
            recipes.append(
                AiRecipeCreate(
                    id=recipe_id,
                    name=f"{name}",
                    description=(
                        f"{archetype.title()} recipe using {nav_model.replace('_', ' ')}, "
                        f"{interaction_model.replace('_', ' ')}, and {visual_language.replace('_', ' ')} language."
                    ),
                    archetype=archetype,
                    nav_model=nav_model,
                    interaction_model=interaction_model,
                    visual_language=visual_language,
                    data_behavior=data_behavior,
                    density_rule=density_rule,
                    component_ids=component_ids,
                    default_directives={
                        "generation_mode": "local_fullstack" if archetype in {"ledger", "board", "cockpit"} else "prototype",
                        "recipe_selection_mode": "manual",
                    },
                    tags=[archetype, nav_model, interaction_model, visual_language],
                    builtin=True,
                )
            )
    return recipes
