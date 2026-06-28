"""AI-first bundle catalog + install manager for Marketplace and AI Factory.

A bundle is an installable pack of AI-facing workflow assets: specialized
roles, personalities, quick-action templates, and optional AI Factory assets.
Unlike a plain tool, the target user is often another AI system operating
through Synapse, so the manifest carries efficiency and overlap metadata that
helps the runtime pick the right bundle for a task.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from . import agent_squads
from . import ai_factory
from . import personalities as personalities_module
from .errors import conflict, invalid, not_found
from .runtime_paths import bundled_ai_bundles_sample
from .time_utils import from_iso, to_iso, utc_now


class AiBundleAssetKind(str, Enum):
    ROLE_TEMPLATE = "role_template"
    PERSONALITY = "personality"
    QUICK_ACTION = "quick_action"
    COMPONENT = "component"
    RECIPE = "recipe"
    SOURCE = "source"


class AiBundleAssetRef(BaseModel):
    kind: AiBundleAssetKind
    id: str
    label: str
    summary: str = ""


class AiBundleOverlap(BaseModel):
    bundle_id: str
    similarity_percent: int = Field(default=0, ge=0, le=100)
    summary: str = ""
    complementary: bool = False


class AiBundleEfficiency(BaseModel):
    quality_gain_summary: str = ""
    token_savings_summary: str = ""
    speed_gain_summary: str = ""
    best_for: list[str] = Field(default_factory=list)
    caveats: list[str] = Field(default_factory=list)


class AiBundleQuickAction(BaseModel):
    id: str
    name: str
    description: str
    prompt: str
    icon: str | None = None
    category: str | None = None
    tags: list[str] = Field(default_factory=list)
    default_argv: list[str] = Field(default_factory=list)

    def to_template_payload(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class AiBundleManifest(BaseModel):
    id: str
    name: str
    publisher: str
    version: str = "1.0.0"
    description: str = ""
    featured: bool = False
    verified: bool = True
    sort_rank: int = 999
    tags: list[str] = Field(default_factory=list)
    recommended_case_modes: list[str] = Field(default_factory=list)
    recommended_mission_profiles: list[str] = Field(default_factory=list)
    asset_refs: list[AiBundleAssetRef] = Field(default_factory=list)
    overlap_report: list[AiBundleOverlap] = Field(default_factory=list)
    efficiency: AiBundleEfficiency = Field(default_factory=AiBundleEfficiency)
    roles: list[agent_squads.AgentRoleTemplateCreate] = Field(default_factory=list)
    personalities: list[personalities_module.PersonalityCreate] = Field(default_factory=list)
    components: list[ai_factory.AiComponentCreate] = Field(default_factory=list)
    recipes: list[ai_factory.AiRecipeCreate] = Field(default_factory=list)
    sources: list[ai_factory.AiSourceCreate] = Field(default_factory=list)
    quick_actions: list[AiBundleQuickAction] = Field(default_factory=list)
    notes_md: str = ""


class InstalledAiBundle(BaseModel):
    bundle_id: str
    name: str
    publisher: str
    version: str
    source: str
    installed_at: datetime
    updated_at: datetime
    manifest: AiBundleManifest


def installed_quick_actions_dir(data_dir: Path) -> Path:
    return Path(data_dir) / "ai-bundles" / "quick-actions"


def load_catalog() -> list[AiBundleManifest]:
    path = bundled_ai_bundles_sample()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise invalid("ai_bundle", f"Bundled AI bundle sample missing at {path}: {exc}")
    except json.JSONDecodeError as exc:
        raise invalid("ai_bundle", f"AI bundle sample is malformed JSON: {exc}")
    if not isinstance(raw, dict):
        raise invalid("ai_bundle", "AI bundle catalog must be a JSON object.")
    bundles = raw.get("bundles")
    if not isinstance(bundles, list):
        raise invalid("ai_bundle", "AI bundle catalog 'bundles' must be a list.")
    out: list[AiBundleManifest] = []
    for entry in bundles:
        if not isinstance(entry, dict):
            continue
        out.append(AiBundleManifest.model_validate(entry))
    return sorted(out, key=lambda item: (999999 if not item.featured else 0, item.sort_rank, item.name.lower()))


def bundle_by_id(bundle_id: str) -> AiBundleManifest:
    for bundle in load_catalog():
        if bundle.id == bundle_id:
            return bundle
    raise not_found("ai_bundle", bundle_id)


def list_installed_bundle_ids(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute(
        "SELECT bundle_id FROM ai_bundle_installs ORDER BY updated_at DESC, bundle_id"
    ).fetchall()
    return [str(row["bundle_id"]) for row in rows]


def list_installed_bundles(conn: sqlite3.Connection) -> list[InstalledAiBundle]:
    rows = conn.execute(
        "SELECT * FROM ai_bundle_installs ORDER BY updated_at DESC, bundle_id"
    ).fetchall()
    return [_row_to_installed_bundle(row) for row in rows]


def get_installed_bundle(conn: sqlite3.Connection, bundle_id: str) -> InstalledAiBundle:
    row = conn.execute(
        "SELECT * FROM ai_bundle_installs WHERE bundle_id = ?",
        (bundle_id,),
    ).fetchone()
    if row is None:
        raise not_found("ai_bundle_install", bundle_id)
    return _row_to_installed_bundle(row)


def list_owned_assets(conn: sqlite3.Connection, bundle_id: str) -> list[AiBundleAssetRef]:
    rows = conn.execute(
        "SELECT asset_kind, asset_id, label FROM ai_bundle_assets WHERE bundle_id = ? ORDER BY asset_kind, asset_id",
        (bundle_id,),
    ).fetchall()
    return [
        AiBundleAssetRef(
            kind=AiBundleAssetKind(row["asset_kind"]),
            id=row["asset_id"],
            label=row["label"] or row["asset_id"],
        )
        for row in rows
    ]


def install_bundle(
    conn: sqlite3.Connection,
    data_dir: Path,
    bundle: AiBundleManifest,
    *,
    source: str = "marketplace",
    force: bool = False,
) -> InstalledAiBundle:
    current = conn.execute(
        "SELECT bundle_id FROM ai_bundle_installs WHERE bundle_id = ?",
        (bundle.id,),
    ).fetchone()
    if current is not None and not force:
        raise conflict("ai_bundle", f"Bundle '{bundle.id}' is already installed.")

    now = utc_now()
    owned_assets: list[AiBundleAssetRef] = []

    for role in bundle.roles:
        _upsert_role_template(conn, role)
        owned_assets.append(
            AiBundleAssetRef(
                kind=AiBundleAssetKind.ROLE_TEMPLATE,
                id=role.id,
                label=role.name,
            )
        )
    for personality in bundle.personalities:
        _upsert_personality(conn, personality)
        if personality.id is None:
            raise invalid("ai_bundle", f"Bundle personality '{personality.name}' must declare an id.")
        owned_assets.append(
            AiBundleAssetRef(
                kind=AiBundleAssetKind.PERSONALITY,
                id=personality.id,
                label=personality.name,
            )
        )
    for source_payload in bundle.sources:
        _upsert_source(conn, source_payload)
        owned_assets.append(
            AiBundleAssetRef(
                kind=AiBundleAssetKind.SOURCE,
                id=source_payload.id,
                label=source_payload.label,
            )
        )
    for component in bundle.components:
        _upsert_component(conn, component)
        owned_assets.append(
            AiBundleAssetRef(
                kind=AiBundleAssetKind.COMPONENT,
                id=component.id,
                label=component.name,
            )
        )
    for recipe in bundle.recipes:
        _upsert_recipe(conn, recipe)
        owned_assets.append(
            AiBundleAssetRef(
                kind=AiBundleAssetKind.RECIPE,
                id=recipe.id,
                label=recipe.name,
            )
        )
    for action in bundle.quick_actions:
        _write_quick_action(data_dir, action)
        owned_assets.append(
            AiBundleAssetRef(
                kind=AiBundleAssetKind.QUICK_ACTION,
                id=action.id,
                label=action.name,
            )
        )

    conn.execute(
        """
        INSERT INTO ai_bundle_installs (
            bundle_id, name, publisher, version, source, manifest_json, installed_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(bundle_id) DO UPDATE SET
            name = excluded.name,
            publisher = excluded.publisher,
            version = excluded.version,
            source = excluded.source,
            manifest_json = excluded.manifest_json,
            updated_at = excluded.updated_at
        """,
        (
            bundle.id,
            bundle.name,
            bundle.publisher,
            bundle.version,
            source,
            json.dumps(bundle.model_dump(mode="json")),
            to_iso(now),
            to_iso(now),
        ),
    )
    conn.execute("DELETE FROM ai_bundle_assets WHERE bundle_id = ?", (bundle.id,))
    for asset in owned_assets:
        conn.execute(
            """
            INSERT INTO ai_bundle_assets (bundle_id, asset_kind, asset_id, label, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                bundle.id,
                asset.kind.value,
                asset.id,
                asset.label,
                to_iso(now),
            ),
        )
    return get_installed_bundle(conn, bundle.id)


def uninstall_bundle(
    conn: sqlite3.Connection,
    data_dir: Path,
    bundle_id: str,
) -> dict[str, Any]:
    install = get_installed_bundle(conn, bundle_id)
    owned_assets = sorted(
        list_owned_assets(conn, bundle_id),
        key=lambda asset: _delete_priority(asset.kind),
    )
    removed: list[str] = []
    retained: list[str] = []
    for asset in owned_assets:
        if _other_bundle_owns_asset(conn, bundle_id=bundle_id, asset=asset):
            retained.append(f"{asset.kind.value}:{asset.id}")
            continue
        try:
            _delete_owned_asset(conn, data_dir, asset)
            removed.append(f"{asset.kind.value}:{asset.id}")
        except Exception:
            retained.append(f"{asset.kind.value}:{asset.id}")
    conn.execute("DELETE FROM ai_bundle_assets WHERE bundle_id = ?", (bundle_id,))
    conn.execute("DELETE FROM ai_bundle_installs WHERE bundle_id = ?", (bundle_id,))
    return {
        "bundle_id": install.bundle_id,
        "removed_assets": removed,
        "retained_assets": retained,
    }


def count_installed(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT COUNT(*) AS count FROM ai_bundle_installs").fetchone()
    return int(row["count"] if row is not None else 0)


def _row_to_installed_bundle(row: sqlite3.Row) -> InstalledAiBundle:
    return InstalledAiBundle(
        bundle_id=row["bundle_id"],
        name=row["name"],
        publisher=row["publisher"],
        version=row["version"],
        source=row["source"],
        installed_at=from_iso(row["installed_at"]),
        updated_at=from_iso(row["updated_at"]),
        manifest=AiBundleManifest.model_validate(json.loads(row["manifest_json"])),
    )


def _other_bundle_owns_asset(
    conn: sqlite3.Connection,
    *,
    bundle_id: str,
    asset: AiBundleAssetRef,
) -> bool:
    row = conn.execute(
        """
        SELECT 1
        FROM ai_bundle_assets
        WHERE bundle_id <> ? AND asset_kind = ? AND asset_id = ?
        LIMIT 1
        """,
        (bundle_id, asset.kind.value, asset.id),
    ).fetchone()
    return row is not None


def _delete_priority(kind: AiBundleAssetKind) -> int:
    order = {
        AiBundleAssetKind.QUICK_ACTION: 10,
        AiBundleAssetKind.RECIPE: 20,
        AiBundleAssetKind.COMPONENT: 30,
        AiBundleAssetKind.ROLE_TEMPLATE: 40,
        AiBundleAssetKind.PERSONALITY: 50,
        AiBundleAssetKind.SOURCE: 60,
    }
    return order.get(kind, 999)


def _upsert_role_template(
    conn: sqlite3.Connection,
    payload: agent_squads.AgentRoleTemplateCreate,
) -> None:
    existing = conn.execute(
        "SELECT id FROM agent_role_templates WHERE id = ?",
        (payload.id,),
    ).fetchone()
    if existing is None:
        agent_squads.create_role_template(conn, payload)
        return
    agent_squads.update_role_template(
        conn,
        payload.id,
        agent_squads.AgentRoleTemplateUpdate(**payload.model_dump()),
    )


def _upsert_personality(
    conn: sqlite3.Connection,
    payload: personalities_module.PersonalityCreate,
) -> None:
    if payload.id is None:
        raise invalid("ai_bundle", f"Bundle personality '{payload.name}' must declare an id.")
    existing = conn.execute(
        "SELECT id FROM personalities WHERE id = ?",
        (payload.id,),
    ).fetchone()
    if existing is None:
        personalities_module.create_personality(conn, payload)
        return
    personalities_module.update_personality(
        conn,
        payload.id,
        personalities_module.PersonalityUpdate(**payload.model_dump(exclude={"id"})),
    )


def _upsert_source(conn: sqlite3.Connection, payload: ai_factory.AiSourceCreate) -> None:
    existing = conn.execute(
        "SELECT id FROM ai_factory_sources WHERE id = ?",
        (payload.id,),
    ).fetchone()
    if existing is None:
        ai_factory.create_source(conn, payload)
        return
    ai_factory.update_source(
        conn,
        payload.id,
        ai_factory.AiSourceUpdate(**payload.model_dump(exclude={"id", "builtin"})),
    )


def _upsert_component(
    conn: sqlite3.Connection,
    payload: ai_factory.AiComponentCreate,
) -> None:
    existing = conn.execute(
        "SELECT id FROM ai_factory_components WHERE id = ?",
        (payload.id,),
    ).fetchone()
    if existing is None:
        ai_factory.create_component(conn, payload)
        return
    ai_factory.update_component(
        conn,
        payload.id,
        ai_factory.AiComponentUpdate(**payload.model_dump(exclude={"id", "builtin"})),
    )


def _upsert_recipe(conn: sqlite3.Connection, payload: ai_factory.AiRecipeCreate) -> None:
    existing = conn.execute(
        "SELECT id FROM ai_factory_recipes WHERE id = ?",
        (payload.id,),
    ).fetchone()
    if existing is None:
        ai_factory.create_recipe(conn, payload)
        return
    ai_factory.update_recipe(
        conn,
        payload.id,
        ai_factory.AiRecipeUpdate(**payload.model_dump(exclude={"id", "builtin"})),
    )


def _write_quick_action(data_dir: Path, action: AiBundleQuickAction) -> None:
    target_dir = installed_quick_actions_dir(data_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / f"{action.id}.json"
    target_path.write_text(
        json.dumps(action.to_template_payload(), indent=2) + "\n",
        encoding="utf-8",
    )


def _delete_owned_asset(
    conn: sqlite3.Connection,
    data_dir: Path,
    asset: AiBundleAssetRef,
) -> None:
    if asset.kind == AiBundleAssetKind.ROLE_TEMPLATE:
        agent_squads.delete_role_template(conn, asset.id)
        return
    if asset.kind == AiBundleAssetKind.PERSONALITY:
        personalities_module.delete_personality(conn, asset.id)
        return
    if asset.kind == AiBundleAssetKind.COMPONENT:
        ai_factory.delete_component(conn, asset.id)
        return
    if asset.kind == AiBundleAssetKind.RECIPE:
        ai_factory.delete_recipe(conn, asset.id)
        return
    if asset.kind == AiBundleAssetKind.SOURCE:
        ai_factory.delete_source(conn, asset.id)
        return
    if asset.kind == AiBundleAssetKind.QUICK_ACTION:
        target_path = installed_quick_actions_dir(data_dir) / f"{asset.id}.json"
        if target_path.exists():
            target_path.unlink()
        return
    raise invalid("ai_bundle", f"Unknown owned asset kind '{asset.kind.value}'.")
