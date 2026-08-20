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
from . import coder_runtimes
from . import ollama_client
from .blueprints import Blueprint
from .errors import invalid
from .scaffold import runner as runner_mod


class BuildRequest(BaseModel):
    workspace: str | None = None
    model: str = ""
    max_repairs: int = 4
    runtimes: list[str] = Field(default_factory=list)
    """Which coding runtimes to use, best first. Empty means the default ladder.

    e.g. `["claude", "codex", "local"]`, or `["local"]` to force the free tier.
    """
    max_attempts: int = 1
    """Retry a failing piece from a clean slate this many times.

    Leave at 1 for interactive builds. Overnight, raise it: the local tier passes a large
    stateful module about one run in five, and a fresh attempt costs only time nobody is
    waiting on.
    """
    deadline_seconds: float | None = None
    """Also bound retries by wall clock, for a fixed overnight window rather than a fixed
    attempt count. Never cancels an attempt already running - only refuses to START another
    retry once the deadline has passed. Leave unset for no deadline (attempt count only)."""


class RegisterRequest(BaseModel):
    blueprint: dict[str, Any]


class FromBuildRequest(BaseModel):
    directory: str
    blueprint_id: str = ""
    name: str = ""
    summary: str = ""
    save: bool = False
    """Off by default: a draft is a starting point, not a catalog entry."""


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

    @router.post("/from-build", response_model=Blueprint)
    async def from_build(payload: FromBuildRequest) -> Blueprint:
        """Draft a blueprint from an app that already works.

        Returns a **draft**: pieces, contracts and dependencies are read off the source, but
        every scenario is empty. A scenario says what a caller needs, and that is not
        recoverable from code that happens to work - inferring one from the implementation
        would assert whatever the code already does, which is a check that cannot fail.

        Saved only when `save` is set, so a bad draft does not silently join the catalog.
        """
        directory = Path(payload.directory).expanduser()
        if not directory.is_dir():
            raise invalid("blueprint", f"No such directory: {directory}")
        bp = bp_mod.distil_from_build(
            directory,
            blueprint_id=payload.blueprint_id or bp_mod.slugify(directory.name),
            name=payload.name or directory.name,
            summary=payload.summary,
        )
        if not bp.pieces:
            raise invalid("blueprint", f"No app modules found in {directory}")
        if payload.save:
            bp_mod.save_blueprint(bp)
        return bp

    @router.post("/{blueprint_id}/build", response_model=runner_mod.BuildResult)
    async def build(blueprint_id: str, payload: BuildRequest) -> runner_mod.BuildResult:
        """Build it with the best available runtime, verifying each piece as it goes.

        Each piece is written by the highest rung of the ladder that still has room -
        `claude -> codex -> copilot -> local` by default - and every piece records which one
        wrote it. Long-running by nature, especially once it reaches the local tier, where a
        single repair is a local inference: free, and slow.

        Pieces nothing can finish come back with a self-contained `escalation_packet` rather
        than a half-built file and a claim of success.
        """
        bp = bp_mod.get_blueprint(blueprint_id)
        if bp is None:
            raise invalid("blueprint_id", f"No blueprint called {blueprint_id!r}.")

        try:
            ladder = (tuple(coder_runtimes.CoderRuntime(name) for name in payload.runtimes)
                      if payload.runtimes else coder_runtimes.DEFAULT_LADDER)
        except ValueError as exc:
            raise invalid("runtimes", f"Unknown runtime: {exc}")

        # Ollama is only required when the build could actually reach the local tier. A
        # build routed to Claude has no use for it, and refusing to start without it would
        # make a paid runtime depend on a free one being installed.
        if coder_runtimes.CoderRuntime.LOCAL in ladder:
            reachable = [r for r in ladder if r is not coder_runtimes.CoderRuntime.LOCAL
                         and coder_runtimes.available(r)]
            if not reachable:
                if not ollama_client.is_installed():
                    raise invalid("model", "No coding runtime is available: nothing above "
                                           "the local tier is installed, and neither is "
                                           "Ollama.")
                if not await ollama_client.server_up():
                    raise invalid("model", "The build would fall to the local tier, but the "
                                           "Ollama server isn't running. Start it first.")

        ws = Path(payload.workspace).resolve() if payload.workspace else (
            default_root / blueprint_id)
        return await runner_mod.build_blueprint(
            bp, workspace=ws, coder_model=payload.model,
            max_repairs=max(0, min(payload.max_repairs, 20)),
            ladder=ladder,
            max_attempts=max(1, min(payload.max_attempts, 20)),
            deadline_seconds=payload.deadline_seconds)

    return router
