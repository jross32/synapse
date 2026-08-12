"""REST for blueprints: what can be built, what it guarantees, and how to build it.

Deliberately discoverable. An AI that reads ``/ai/context`` learns blueprints exist; these
routes let it list them, see what each one *guarantees* (not merely describes), work out which
ones compose, and run one — without any file paths in its prompt.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from . import blueprints as bp_mod
from . import ollama_client
from .blueprints import Blueprint
from .errors import invalid
from .scaffold import runner as runner_mod


class BuildRequest(BaseModel):
    workspace: str | None = None
    model: str = ""
    max_repairs: int = 4


class RegisterRequest(BaseModel):
    blueprint: dict[str, Any]


class StackRequest(BaseModel):
    want: list[str] = Field(default_factory=list)


def build_blueprints_router(storage: Any, data_dir: Path) -> APIRouter:
    router = APIRouter(prefix="/blueprints", tags=["blueprints"])
    default_root = data_dir / "blueprint-builds"

    @router.get("", response_model=list[Blueprint])
    async def list_blueprints(kind: str = "", tag: str = "") -> list[Blueprint]:
        items = bp_mod.load_catalog()
        if kind:
            items = [b for b in items if b.kind.value == kind]
        if tag:
            items = [b for b in items if tag in b.tags]
        return items

    @router.get("/summary")
    async def summary() -> dict[str, Any]:
        """The catalog shaped for an AI: guarantees, capabilities, measured scores."""
        return bp_mod.summarize_for_ai()

    @router.get("/{blueprint_id}", response_model=Blueprint)
    async def get_one(blueprint_id: str) -> Blueprint:
        bp = bp_mod.get_blueprint(blueprint_id)
        if bp is None:
            raise invalid("blueprint_id", f"No blueprint called {blueprint_id!r}.")
        return bp

    @router.get("/{blueprint_id}/compatible")
    async def compatible(blueprint_id: str) -> dict[str, list[str]]:
        """Which blueprints fit with this one, derived from declared capabilities."""
        if bp_mod.get_blueprint(blueprint_id) is None:
            raise invalid("blueprint_id", f"No blueprint called {blueprint_id!r}.")
        return bp_mod.compatible_with(blueprint_id)

    @router.post("/stack")
    async def stack(payload: StackRequest) -> dict[str, Any]:
        """Assemble a set whose requirements are all met, and say what is still missing."""
        if not payload.want:
            raise invalid("want", "Name at least one blueprint.")
        return bp_mod.resolve_stack(payload.want)

    @router.post("", response_model=Blueprint)
    async def register(payload: RegisterRequest) -> Blueprint:
        """Add a blueprint. They are data, so growing the library needs no code change."""
        try:
            bp = Blueprint.model_validate(payload.blueprint)
        except Exception as exc:  # noqa: BLE001
            raise invalid("blueprint", f"That is not a valid blueprint: {exc}")
        if not bp.id:
            raise invalid("blueprint", "A blueprint needs an id.")
        bp_mod.save_blueprint(bp)
        return bp

    @router.post("/{blueprint_id}/build", response_model=runner_mod.BuildResult)
    async def build(blueprint_id: str, payload: BuildRequest) -> runner_mod.BuildResult:
        """Build it with local models, verifying each piece as it goes.

        Long-running by nature: every repair is a local inference, which is free but slow.
        Pieces that cannot be finished locally come back with a self-contained
        `escalation_packet` rather than a half-built file and a claim of success.
        """
        bp = bp_mod.get_blueprint(blueprint_id)
        if bp is None:
            raise invalid("blueprint_id", f"No blueprint called {blueprint_id!r}.")
        if not ollama_client.is_installed():
            raise invalid("model", "Ollama isn't installed, so local models can't run.")
        if not await ollama_client.server_up():
            raise invalid("model", "The Ollama server isn't running. Start it first.")

        ws = Path(payload.workspace).resolve() if payload.workspace else (
            default_root / blueprint_id)
        return await runner_mod.build_blueprint(
            bp, workspace=ws, coder_model=payload.model,
            max_repairs=max(0, min(payload.max_repairs, 20)))

    return router
