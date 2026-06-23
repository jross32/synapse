"""Local-model marketplace (ADR-0014, Phase M).

Two pieces:

* A curated catalog of small/popular open models (``docs/models-sample.json``),
  cross-referenced against what the user already has installed.
* A ``ModelPullManager`` that runs ``ollama pull`` downloads as background tasks,
  bounded by a concurrency cap (so selecting several queues the rest), and
  streams progress over the WS bus as ``v1.model.pull_progress`` events.

Nothing here assumes Ollama is installed; the catalog renders regardless and
pulls only start when the engine is present.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from . import ollama_client
from .api_versions import event_name
from .runtime_paths import bundled_models_sample
from .time_utils import to_iso, utc_now

MAX_CONCURRENT_PULLS = 2

PullStatus = Literal["queued", "downloading", "success", "error", "canceled"]


class ModelCatalogEntry(BaseModel):
    id: str  # the ``ollama pull`` name, e.g. "llama3.2:1b"
    name: str
    publisher: str | None = None
    description: str = ""
    parameter_size: str | None = None
    size_label: str | None = None
    tags: list[str] = Field(default_factory=list)
    recommended: bool = False
    installed: bool = False  # filled at request time from /api/tags


class ModelCatalog(BaseModel):
    version: int = 1
    generated_at: str | None = None
    models: list[ModelCatalogEntry] = Field(default_factory=list)


class ModelPullState(BaseModel):
    name: str
    status: PullStatus = "queued"
    completed: int = 0
    total: int = 0
    percent: float = 0.0
    detail: str | None = None  # Ollama's current step ("pulling manifest", ...)
    error: str | None = None
    updated_at: str


class ModelPullList(BaseModel):
    pulls: list[ModelPullState] = Field(default_factory=list)


class ModelPullRequest(BaseModel):
    name: str


def _now() -> str:
    return to_iso(utc_now())


def load_catalog(installed: set[str]) -> ModelCatalog:
    """Read the bundled catalog and mark which entries are already installed.

    Degrades to an empty catalog if the file is missing/corrupt rather than
    erroring -- the marketplace should still render."""
    path: Path = bundled_models_sample()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 -- missing/corrupt feed -> empty catalog
        return ModelCatalog(models=[])
    entries: list[ModelCatalogEntry] = []
    for item in raw.get("models", []):
        if not isinstance(item, dict) or not isinstance(item.get("id"), str):
            continue
        try:
            entry = ModelCatalogEntry(**item)
        except Exception:  # noqa: BLE001 -- skip malformed entry
            continue
        entry.installed = entry.id in installed
        entries.append(entry)
    return ModelCatalog(version=raw.get("version", 1), generated_at=raw.get("generated_at"), models=entries)


class ModelPullManager:
    """Tracks model downloads as background asyncio tasks + streams progress.

    In-memory only (pulls don't survive a daemon restart -- ``ollama pull`` is
    resumable, so re-pulling continues where it left off). A semaphore caps how
    many download at once; extra requests sit in ``queued`` until a slot frees."""

    def __init__(self, bus: Any) -> None:
        self._bus = bus
        self._states: dict[str, ModelPullState] = {}
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._sem = asyncio.Semaphore(MAX_CONCURRENT_PULLS)

    def list(self) -> list[ModelPullState]:
        return list(self._states.values())

    def get(self, name: str) -> ModelPullState | None:
        return self._states.get(name)

    def start(self, name: str) -> ModelPullState:
        existing = self._states.get(name)
        if existing and existing.status in ("queued", "downloading"):
            return existing  # already in flight -- idempotent
        state = ModelPullState(name=name, status="queued", updated_at=_now())
        self._states[name] = state
        self._tasks[name] = asyncio.create_task(self._run(name))
        return state

    def cancel(self, name: str) -> bool:
        task = self._tasks.get(name)
        if task and not task.done():
            task.cancel()
            return True
        return False

    async def shutdown(self) -> None:
        for task in self._tasks.values():
            if not task.done():
                task.cancel()

    async def _emit(self, state: ModelPullState) -> None:
        try:
            await self._bus.publish(event_name("model", "pull_progress"), state.model_dump())
        except Exception:  # noqa: BLE001 -- never let a publish failure kill a pull
            pass

    async def _run(self, name: str) -> None:
        state = self._states[name]
        async with self._sem:
            state.status = "downloading"
            state.updated_at = _now()
            await self._emit(state)
            try:
                async for chunk in ollama_client.pull(name):
                    if isinstance(chunk.get("error"), str):
                        state.status = "error"
                        state.error = chunk["error"]
                        break
                    total = chunk.get("total")
                    completed = chunk.get("completed")
                    if isinstance(total, int) and total > 0:
                        state.total = total
                    if isinstance(completed, int):
                        state.completed = completed
                    if state.total > 0:
                        state.percent = round(min(state.completed / state.total * 100, 100.0), 1)
                    if isinstance(chunk.get("status"), str):
                        state.detail = chunk["status"]
                    state.updated_at = _now()
                    await self._emit(state)
                if state.status != "error":
                    state.status = "success"
                    state.percent = 100.0
            except asyncio.CancelledError:
                state.status = "canceled"
                state.updated_at = _now()
                await self._emit(state)
                raise
            except Exception as exc:  # noqa: BLE001 -- surface as an error state
                state.status = "error"
                state.error = str(exc)
            state.updated_at = _now()
            await self._emit(state)
