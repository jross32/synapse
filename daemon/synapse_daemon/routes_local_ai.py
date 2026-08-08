"""REST for local AI: what this machine can run, what each model is good at, and running
a local model as a real agent with tools.

The point of these routes is that work which doesn't need a frontier model shouldn't cost
API tokens. Any AI connected to Synapse can read ``/local-ai/models`` to see which local
models exist and what they are measured to be good at, then hand a job to
``/local-ai/agent/run`` instead of doing it itself.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from . import local_models, ollama_client
from .errors import invalid
from .local_agent import MAX_STEPS_DEFAULT, AgentRun, PermissionMode, run_agent


class LocalAiOverview(BaseModel):
    ollama_installed: bool
    ollama_running: bool
    hardware: local_models.HardwareProfile
    models: list[local_models.ModelProfile] = Field(default_factory=list)
    recommendations: list[local_models.RoleRecommendation] = Field(default_factory=list)
    benchmark_present: bool = False
    benchmark_hint: str = ""


class AgentRunRequest(BaseModel):
    model: str
    task: str
    workspace: str | None = None
    mode: PermissionMode = PermissionMode.AUTO
    allow_web: bool = True
    max_steps: int = MAX_STEPS_DEFAULT
    num_ctx: int = 8192


def build_local_ai_router(data_dir: Path) -> APIRouter:
    router = APIRouter(prefix="/local-ai", tags=["local-ai"])

    # Agents write here unless a workspace is named, so a careless call can't scribble
    # over the repo.
    default_ws = data_dir / "local-agent-workspace"

    @router.get("/hardware", response_model=local_models.HardwareProfile)
    async def hardware() -> local_models.HardwareProfile:
        return local_models.detect_hardware()

    @router.get("/models", response_model=LocalAiOverview)
    async def models() -> LocalAiOverview:
        hw = local_models.detect_hardware()
        profiles = local_models.load_benchmarks()

        installed: set[str] = set()
        running = False
        if ollama_client.is_installed():
            running = await ollama_client.server_up()
            if running:
                try:
                    installed = {m["name"] for m in await ollama_client.list_models()}
                except Exception:  # noqa: BLE001 -- engine hiccup shouldn't 500 the route
                    installed = set()

        # Show installed models even when they have no benchmark data yet, so the list
        # reflects reality rather than only what has been measured.
        for name in sorted(installed):
            if name not in profiles:
                profiles[name] = local_models.ModelProfile(name=name, installed=True)
        for name, prof in profiles.items():
            prof.installed = name in installed if installed else prof.installed

        return LocalAiOverview(
            ollama_installed=ollama_client.is_installed(),
            ollama_running=running,
            hardware=hw,
            models=sorted(profiles.values(),
                          key=lambda p: -(p.overall_pass_rate or -1)),
            recommendations=local_models.recommend_for_roles(hw, profiles),
            benchmark_present=local_models.benchmark_path().exists(),
            benchmark_hint=(
                "Run `python benchmarks/local-models/bench.py` to measure the models on "
                "this machine. Recommendations are only as good as the measurements."
            ),
        )

    @router.post("/agent/run", response_model=AgentRun)
    async def agent_run(payload: AgentRunRequest) -> AgentRun:
        model = payload.model.strip()
        task = payload.task.strip()
        if not model:
            raise invalid("model", "A model name is required.")
        if not task:
            raise invalid("task", "A task is required.")
        if not ollama_client.is_installed():
            raise invalid("model", "Ollama isn't installed, so local models can't run.")
        if not await ollama_client.server_up():
            raise invalid("model", "The Ollama server isn't running. Start it first.")

        ws = Path(payload.workspace) if payload.workspace else default_ws
        ws.mkdir(parents=True, exist_ok=True)

        return await run_agent(
            model=model,
            task=task,
            workspace=ws,
            mode=payload.mode,
            allow_web=payload.allow_web,
            max_steps=max(1, min(payload.max_steps, 40)),
            num_ctx=payload.num_ctx,
        )

    return router
