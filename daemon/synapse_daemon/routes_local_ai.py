"""REST for local AI: what this machine can run, what each model is good at, and running
a local model as a real agent with tools.

The point of these routes is that work which doesn't need a frontier model shouldn't cost
API tokens. Any AI connected to Synapse can read ``/local-ai/models`` to see which local
models exist and what they are measured to be good at, then hand a job to
``/local-ai/agent/run`` instead of doing it itself.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, AsyncIterator

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from . import (local_bench, local_chat, local_improve, local_models, local_pipeline,
               local_router, ollama_client)
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
    playbook: dict[str, Any] = Field(default_factory=dict)
    """The measured how-to, served to the UI from the same constant the AI reads in
    /ai/context - so the human guidance and the machine guidance cannot drift apart."""


class AgentRunRequest(BaseModel):
    model: str
    task: str
    workspace: str | None = None
    mode: PermissionMode = PermissionMode.AUTO
    allow_web: bool = True
    max_steps: int = MAX_STEPS_DEFAULT
    num_ctx: int = 8192


class PipelineRequest(BaseModel):
    spec: str
    path: str = "solution.py"
    workspace: str | None = None
    model: str = ""
    max_repairs: int = 4
    write_test: bool = True


class DoRequest(BaseModel):
    task: str
    workspace: str | None = None
    path: str = "solution.py"
    max_repairs: int = 4
    allow_shell: bool = False


class BenchRequest(BaseModel):
    models: list[str] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)


class ImproveRequest(BaseModel):
    skills: list[str] = Field(default_factory=list)
    variables: list[str] = Field(default_factory=list)
    repeats: int = 3


class CreateChatRequest(BaseModel):
    model: str
    title: str | None = None
    mode: PermissionMode = PermissionMode.AUTO
    workspace: str | None = None
    project_id: str | None = None


class SendRequest(BaseModel):
    prompt: str
    allow_web: bool = True


class PatchChatRequest(BaseModel):
    title: str | None = None
    model: str | None = None
    mode: PermissionMode | None = None
    workspace: str | None = None


def build_local_ai_router(storage: Any, data_dir: Path) -> APIRouter:
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
            playbook=local_models.PLAYBOOK,
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

    @router.post("/pipeline", response_model=local_pipeline.PipelineResult)
    async def pipeline(payload: PipelineRequest) -> local_pipeline.PipelineResult:
        """Generate code locally, prove it runs, repair it from real errors.

        This is the cheapest way to get correct code out of this machine: measured at 100%
        on the benchmark suite versus 33% for an agent-driven loop, because Python does the
        orchestrating and the model only writes code. Every attempt is local, so repairs
        cost nothing but wall-clock. If it cannot finish, the response carries an
        `escalation_packet` sized for a stronger model to pick up in one shot.
        """
        spec = payload.spec.strip()
        if not spec:
            raise invalid("spec", "Describe what the code should do.")
        if not ollama_client.is_installed():
            raise invalid("model", "Ollama isn't installed, so local models can't run.")
        if not await ollama_client.server_up():
            raise invalid("model", "The Ollama server isn't running. Start it first.")

        ws = Path(payload.workspace).resolve() if payload.workspace else default_ws
        return await local_pipeline.run_pipeline(
            spec,
            workspace=ws,
            path=payload.path,
            coder_model=payload.model or local_pipeline.DEFAULT_CODER_MODEL,
            max_repairs=max(0, min(payload.max_repairs, 20)),
            write_test=payload.write_test,
        )

    @router.post("/do", response_model=local_router.RoutedResult)
    async def do_task(payload: DoRequest) -> local_router.RoutedResult:
        """One call: work out how to do this locally, then do it.

        Saves the caller from having to know that code belongs in the pipeline, that file
        work needs an agent, or which of the installed models is strongest at each - all of
        which is decided here from the measured scorecard. Returns a finished result, or
        `needs_escalation` with a self-contained packet when the honest answer is that a
        local model should not be trusted with it.
        """
        task = payload.task.strip()
        if not task:
            raise invalid("task", "Describe what you want done.")
        if not ollama_client.is_installed():
            raise invalid("model", "Ollama isn't installed, so local models can't run.")
        if not await ollama_client.server_up():
            raise invalid("model", "The Ollama server isn't running. Start it first.")

        ws = Path(payload.workspace).resolve() if payload.workspace else default_ws
        return await local_router.run_task(
            task, workspace=ws, path=payload.path,
            max_repairs=max(0, min(payload.max_repairs, 20)),
            allow_shell=payload.allow_shell)

    # ── benchmark ────────────────────────────────────────────────────────────────

    @router.get("/bench")
    async def bench_scorecard() -> dict[str, Any]:
        """The latest measured scorecard for the models on this machine."""
        return local_bench.latest_scorecard()

    @router.get("/bench/history")
    async def bench_history(skill: str = "", model: str = "", limit: int = 20) -> dict[str, Any]:
        """Score over time. A regression after a model swap should be visible, not inferred."""
        if skill:
            return {"skill": skill, "points": local_bench.trend(skill, model, limit)}
        return {"runs": local_bench.load_runs(limit)}

    @router.get("/bench/skills")
    async def bench_skills() -> dict[str, Any]:
        """What is measured. Skill packs are JSON, so this list grows without code."""
        packs = local_bench.load_skill_packs()
        return {"skills": [{"skill": p.skill, "description": p.description,
                            "checks": len(p.checks)} for p in packs.values()]}

    @router.post("/bench/run")
    async def bench_run(payload: BenchRequest) -> local_bench.BenchRun:
        """Measure. Long-running by nature - every check is a real inference."""
        models = payload.models or local_bench.installed_models()
        if not models:
            raise invalid("models", "No local models found. Is Ollama running?")
        return await asyncio.to_thread(local_bench.run_bench, models, payload.skills or None)

    # ── improver ─────────────────────────────────────────────────────────────────

    @router.get("/improve")
    async def improve_status() -> dict[str, Any]:
        """What the improver has tried, and whether it has earned the right to act."""
        return local_improve.status()

    @router.post("/improve/run")
    async def improve_run(payload: ImproveRequest) -> dict[str, Any]:
        """One improvement pass over the harness. Free: every inference is local.

        In shadow mode it records what it *would* change and changes nothing. Auto-promotion
        unlocks only after its predictions hold up on held-out checks repeatedly.
        """
        decisions = await asyncio.to_thread(
            local_improve.run_experiment, payload.skills or None,
            payload.variables or None, payload.repeats)
        return {"decisions": [d.model_dump() for d in decisions],
                "status": local_improve.status()}

    @router.post("/improve/rollback")
    async def improve_rollback() -> dict[str, Any]:
        """Undo the last promotion. Deliberately one call."""
        previous = local_improve.rollback()
        if previous is None:
            raise invalid("history", "There is no earlier configuration to roll back to.")
        return {"active_config": previous.model_dump()}

    # ── conversations ────────────────────────────────────────────────────────────

    @router.get("/chats", response_model=list[local_chat.Chat])
    async def list_chats(include_archived: bool = False) -> list[local_chat.Chat]:
        return local_chat.list_chats(storage.conn, include_archived=include_archived)

    @router.post("/chats", response_model=local_chat.Chat)
    async def create_chat(payload: CreateChatRequest) -> local_chat.Chat:
        if not payload.model.strip():
            raise invalid("model", "Pick a model for this chat.")
        return local_chat.create_chat(
            storage.conn, model=payload.model.strip(), title=payload.title,
            mode=payload.mode.value,
            workspace=str(Path(payload.workspace).resolve()) if payload.workspace
            else str(default_ws.resolve()),
            project_id=payload.project_id)

    @router.get("/chats/{chat_id}", response_model=local_chat.Chat)
    async def get_chat(chat_id: str) -> local_chat.Chat:
        chat = local_chat.get_chat(storage.conn, chat_id)
        if not chat:
            raise invalid("chat_id", "No such chat.")
        return chat

    @router.get("/chats/{chat_id}/messages", response_model=list[local_chat.ChatMessage])
    async def chat_messages(chat_id: str) -> list[local_chat.ChatMessage]:
        if not local_chat.get_chat(storage.conn, chat_id):
            raise invalid("chat_id", "No such chat.")
        return local_chat.get_messages(storage.conn, chat_id)

    @router.patch("/chats/{chat_id}", response_model=local_chat.Chat)
    async def patch_chat(chat_id: str, payload: PatchChatRequest) -> local_chat.Chat:
        chat = local_chat.get_chat(storage.conn, chat_id)
        if not chat:
            raise invalid("chat_id", "No such chat.")
        if payload.title is not None:
            local_chat.rename_chat(storage.conn, chat_id, payload.title)
        sets, vals = [], []
        if payload.model:
            sets.append("model=?"); vals.append(payload.model.strip())
        if payload.mode:
            sets.append("mode=?"); vals.append(payload.mode.value)
        if payload.workspace is not None:
            sets.append("workspace=?"); vals.append(payload.workspace)
        if sets:
            vals.append(chat_id)
            storage.conn.execute(f"UPDATE local_chats SET {', '.join(sets)} WHERE id=?", vals)
            storage.conn.commit()
        return local_chat.get_chat(storage.conn, chat_id)

    @router.delete("/chats/{chat_id}")
    async def remove_chat(chat_id: str) -> dict[str, bool]:
        if not local_chat.get_chat(storage.conn, chat_id):
            raise invalid("chat_id", "No such chat.")
        local_chat.delete_chat(storage.conn, chat_id)
        return {"deleted": True}

    @router.post("/chats/{chat_id}/send")
    async def send(chat_id: str, payload: SendRequest) -> StreamingResponse:
        """Stream one turn as server-sent events.

        SSE rather than a websocket: this is strictly one-way, it survives proxies, and it
        reconnects on its own. The client reads phases (engine starting, model loading,
        connected), then tokens, then tool activity, then a final done event.
        """
        chat = local_chat.get_chat(storage.conn, chat_id)
        if not chat:
            raise invalid("chat_id", "No such chat.")
        prompt = payload.prompt.strip()
        if not prompt:
            raise invalid("prompt", "Type something to send.")

        # Name the conversation after its opening line, once.
        if chat.message_count == 0 and chat.title in ("New chat", ""):
            local_chat.rename_chat(storage.conn, chat_id,
                                   local_chat.title_from_prompt(prompt))
            chat = local_chat.get_chat(storage.conn, chat_id)

        async def event_stream() -> AsyncIterator[bytes]:
            try:
                async for ev in local_chat.stream_reply(
                        storage.conn, chat, prompt, allow_web=payload.allow_web):
                    yield f"data: {json.dumps(ev)}\n\n".encode("utf-8")
            except Exception as exc:  # noqa: BLE001 -- a crash must still close the stream
                err = {"type": "error", "phase": "server",
                       "message": f"{type(exc).__name__}: {exc}"}
                yield f"data: {json.dumps(err)}\n\n".encode("utf-8")

        return StreamingResponse(event_stream(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache",
                                          "X-Accel-Buffering": "no"})

    return router
