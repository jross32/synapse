"""REST for the local-model marketplace (ADR-0014, Phase M).

Browse a curated catalog, kick off ``ollama pull`` downloads (streamed as
``v1.model.pull_progress`` WS events via the ModelPullManager), watch/cancel
in-flight pulls, and remove installed models. All routes degrade gracefully when
Ollama isn't installed.
"""

from __future__ import annotations

from fastapi import APIRouter

from . import ollama_client
from .errors import invalid
from .model_market import (
    ModelCatalog,
    ModelPullList,
    ModelPullManager,
    ModelPullRequest,
    ModelPullState,
    load_catalog,
)


def build_models_router(pulls: ModelPullManager) -> APIRouter:
    router = APIRouter(prefix="/models", tags=["models"])

    async def _installed_names() -> set[str]:
        if not ollama_client.is_installed():
            return set()
        try:
            return {m["name"] for m in await ollama_client.list_models()}
        except Exception:  # noqa: BLE001 -- engine down -> nothing installed
            return set()

    @router.get("/registry", response_model=ModelCatalog)
    async def registry() -> ModelCatalog:
        return load_catalog(await _installed_names())

    @router.get("/pulls", response_model=ModelPullList)
    async def list_pulls() -> ModelPullList:
        return ModelPullList(pulls=pulls.list())

    @router.post("/pull", response_model=ModelPullState)
    async def start_pull(payload: ModelPullRequest) -> ModelPullState:
        name = payload.name.strip()
        if not name:
            raise invalid("model", "A model name is required.")
        if not ollama_client.is_installed():
            raise invalid("model", "Ollama isn't installed, so models can't be downloaded.")
        return pulls.start(name)

    @router.post("/pull/cancel")
    async def cancel_pull(payload: ModelPullRequest) -> dict[str, bool]:
        return {"canceled": pulls.cancel(payload.name.strip())}

    @router.post("/remove")
    async def remove_model(payload: ModelPullRequest) -> dict[str, bool]:
        name = payload.name.strip()
        if not name:
            raise invalid("model", "A model name is required.")
        if not ollama_client.is_installed():
            raise invalid("model", "Ollama isn't installed.")
        return {"deleted": await ollama_client.delete_model(name)}

    return router
