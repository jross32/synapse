"""Marketplace-style routes for AI-first bundles."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from . import ai_bundles
from .profile import ProfileManager
from .storage import Storage


def build_ai_bundles_router(
    storage: Storage,
    profile_manager: ProfileManager | None = None,
) -> APIRouter:
    router = APIRouter(prefix="/ai-bundles", tags=["ai-bundles"])

    @router.get("", response_model=None)
    async def list_ai_bundles() -> dict[str, Any]:
        installed_ids = set(ai_bundles.list_installed_bundle_ids(storage.conn))
        installed = {
            item.bundle_id: item.model_dump(mode="json")
            for item in ai_bundles.list_installed_bundles(storage.conn)
        }
        return {
            "catalog": [
                {
                    **bundle.model_dump(mode="json"),
                    "installed": bundle.id in installed_ids,
                }
                for bundle in ai_bundles.load_catalog()
            ],
            "installed_ids": sorted(installed_ids),
            "installed": installed,
        }

    @router.post("/install/{bundle_id}", response_model=None)
    async def install_ai_bundle(bundle_id: str, force: bool = False) -> dict[str, Any]:
        bundle = ai_bundles.bundle_by_id(bundle_id)
        with storage.transaction() as conn:
            installed = ai_bundles.install_bundle(
                conn,
                storage.data_dir,
                bundle,
                force=force,
            )
        if profile_manager is not None:
            profile_manager.record_catalog_install(kind="bundle", item_id=bundle_id)
        return {
            "installed": installed.bundle_id,
            "bundle": installed.model_dump(mode="json"),
            "owned_assets": [
                asset.model_dump(mode="json")
                for asset in ai_bundles.list_owned_assets(storage.conn, bundle_id)
            ],
        }

    @router.delete("/install/{bundle_id}", response_model=None)
    async def uninstall_ai_bundle(bundle_id: str) -> dict[str, Any]:
        with storage.transaction() as conn:
            result = ai_bundles.uninstall_bundle(conn, storage.data_dir, bundle_id)
        if profile_manager is not None:
            profile_manager.record_catalog_uninstall(kind="bundle", item_id=bundle_id)
        return result

    return router
