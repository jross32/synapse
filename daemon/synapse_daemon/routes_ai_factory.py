"""REST routes for the Synapse AI Factory catalog."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from . import ai_bundles
from . import ai_cases
from . import ai_factory
from .storage import Storage


def build_ai_factory_router(storage: Storage) -> APIRouter:
    router = APIRouter(tags=["ai-factory"])

    @router.get("/ai-factory/catalog", response_model=None)
    async def get_catalog() -> dict[str, Any]:
        installed_bundle_ids = set(ai_bundles.list_installed_bundle_ids(storage.conn))
        return {
            "catalog": ai_factory.catalog(storage.conn).model_dump(mode="json"),
            "counts": {
                **ai_factory.counts(storage.conn),
                "installed_bundles": ai_bundles.count_installed(storage.conn),
            },
            "mission_profiles": [profile.model_dump(mode="json") for profile in ai_cases.mission_profiles()],
            "bundles": [
                {
                    **bundle.model_dump(mode="json"),
                    "installed": bundle.id in installed_bundle_ids,
                }
                for bundle in ai_bundles.load_catalog()
            ],
            "recent_cases": [
                case.model_dump(mode="json")
                for case in ai_cases.list_cases(storage.conn)[:8]
            ],
        }

    @router.get("/ai-components", response_model=None)
    async def list_components() -> dict[str, Any]:
        return {"components": [item.model_dump(mode="json") for item in ai_factory.list_components(storage.conn)]}

    @router.post("/ai-components", response_model=None, status_code=201)
    async def create_component(payload: ai_factory.AiComponentCreate) -> dict[str, Any]:
        with storage.transaction() as conn:
            created = ai_factory.create_component(conn, payload)
        return created.model_dump(mode="json")

    @router.patch("/ai-components/{component_id}", response_model=None)
    async def patch_component(component_id: str, payload: ai_factory.AiComponentUpdate) -> dict[str, Any]:
        with storage.transaction() as conn:
            updated = ai_factory.update_component(conn, component_id, payload)
        return updated.model_dump(mode="json")

    @router.delete("/ai-components/{component_id}", response_model=None, status_code=204)
    async def delete_component(component_id: str) -> None:
        with storage.transaction() as conn:
            ai_factory.delete_component(conn, component_id)

    @router.get("/ai-recipes", response_model=None)
    async def list_recipes() -> dict[str, Any]:
        return {"recipes": [item.model_dump(mode="json") for item in ai_factory.list_recipes(storage.conn)]}

    @router.post("/ai-recipes", response_model=None, status_code=201)
    async def create_recipe(payload: ai_factory.AiRecipeCreate) -> dict[str, Any]:
        with storage.transaction() as conn:
            created = ai_factory.create_recipe(conn, payload)
        return created.model_dump(mode="json")

    @router.patch("/ai-recipes/{recipe_id}", response_model=None)
    async def patch_recipe(recipe_id: str, payload: ai_factory.AiRecipeUpdate) -> dict[str, Any]:
        with storage.transaction() as conn:
            updated = ai_factory.update_recipe(conn, recipe_id, payload)
        return updated.model_dump(mode="json")

    @router.delete("/ai-recipes/{recipe_id}", response_model=None, status_code=204)
    async def delete_recipe(recipe_id: str) -> None:
        with storage.transaction() as conn:
            ai_factory.delete_recipe(conn, recipe_id)

    @router.get("/ai-sources", response_model=None)
    async def list_sources() -> dict[str, Any]:
        return {"sources": [item.model_dump(mode="json") for item in ai_factory.list_sources(storage.conn)]}

    @router.post("/ai-sources", response_model=None, status_code=201)
    async def create_source(payload: ai_factory.AiSourceCreate) -> dict[str, Any]:
        with storage.transaction() as conn:
            created = ai_factory.create_source(conn, payload)
        return created.model_dump(mode="json")

    @router.patch("/ai-sources/{source_id}", response_model=None)
    async def patch_source(source_id: str, payload: ai_factory.AiSourceUpdate) -> dict[str, Any]:
        with storage.transaction() as conn:
            updated = ai_factory.update_source(conn, source_id, payload)
        return updated.model_dump(mode="json")

    @router.delete("/ai-sources/{source_id}", response_model=None, status_code=204)
    async def delete_source(source_id: str) -> None:
        with storage.transaction() as conn:
            ai_factory.delete_source(conn, source_id)

    @router.post("/ai-sources/{source_id}/promote", response_model=None, status_code=201)
    async def promote_source(source_id: str, payload: ai_factory.AiSourcePromoteRequest) -> dict[str, Any]:
        with storage.transaction() as conn:
            promoted = ai_factory.promote_source(conn, source_id, payload)
        return promoted.model_dump(mode="json")

    return router
