"""Marketplace registry route (v0.1.23 · ADR-0001 step 3).

  GET /api/v1/marketplace
      Returns the registry index of tools available to install, plus the
      list of ``installed_ids`` so the UI can mark "Already installed".

Index source priority:
  1. ``SYNAPSE_TOOL_REGISTRY_URL`` env var, if set -- fetched live with httpx.
  2. The bundled sample at ``docs/marketplace-sample.json``.

The route is token-guarded like every other data route. The fetched index is
cached in-memory for ``_CACHE_TTL_SECONDS`` so the page can be browsed
without hammering the upstream every render.
"""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any

import httpx
from fastapi import APIRouter

from .errors import invalid
from .tools_registry import ToolRegistry

log = logging.getLogger(__name__)

_REGISTRY_ENV = "SYNAPSE_TOOL_REGISTRY_URL"
_CACHE_TTL_SECONDS = 60.0
_FETCH_TIMEOUT_SECONDS = 10.0
_BUNDLED_SAMPLE = Path("docs") / "marketplace-sample.json"


class _Cache:
    """Tiny single-slot TTL cache so the registry isn't fetched on every render."""

    def __init__(self) -> None:
        self.value: dict[str, Any] | None = None
        self.source: str | None = None
        self.expires_at: float = 0.0

    def get(self, source: str) -> dict[str, Any] | None:
        if self.value is None or self.source != source:
            return None
        if time.monotonic() >= self.expires_at:
            return None
        return self.value

    def set(self, source: str, value: dict[str, Any]) -> None:
        self.value = value
        self.source = source
        self.expires_at = time.monotonic() + _CACHE_TTL_SECONDS

    def clear(self) -> None:
        self.value = None
        self.source = None
        self.expires_at = 0.0


_cache = _Cache()


def _resolve_source() -> tuple[str, str]:
    """Return ``(kind, location)`` -- ``("url", "https://...")`` or
    ``("file", "/abs/path")``."""

    url = os.environ.get(_REGISTRY_ENV, "").strip()
    if url:
        return "url", url
    return "file", str(_BUNDLED_SAMPLE.resolve())


def _validate_index(raw: Any) -> dict[str, Any]:
    """Shallow validation -- enough to keep the renderer from crashing on
    a malformed feed. Each tool entry must have at least an id and a name;
    any extra fields pass through unchanged."""

    if not isinstance(raw, dict):
        raise invalid("marketplace", "Registry index must be a JSON object.")
    tools = raw.get("tools")
    if not isinstance(tools, list):
        raise invalid("marketplace", "Registry index 'tools' must be a list.")
    cleaned: list[dict[str, Any]] = []
    for entry in tools:
        if not isinstance(entry, dict):
            continue
        if not isinstance(entry.get("id"), str) or not isinstance(entry.get("name"), str):
            continue
        cleaned.append(entry)
    return {
        "version": raw.get("version", 1),
        "generated_at": raw.get("generated_at"),
        "tools": cleaned,
    }


def _load_from_file(path_str: str) -> dict[str, Any]:
    path = Path(path_str)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise invalid(
            "marketplace",
            f"Bundled registry sample missing at {path}: {exc}",
        )
    except json.JSONDecodeError as exc:
        raise invalid("marketplace", f"Registry JSON is malformed: {exc}")
    return _validate_index(raw)


async def _load_from_url(url: str) -> dict[str, Any]:
    try:
        async with httpx.AsyncClient(timeout=_FETCH_TIMEOUT_SECONDS) as client:
            response = await client.get(url)
    except httpx.HTTPError as exc:
        raise invalid("marketplace", f"Could not reach registry {url!r}: {exc}")
    if response.status_code >= 400:
        raise invalid(
            "marketplace",
            f"Registry {url!r} returned HTTP {response.status_code}.",
        )
    try:
        raw = response.json()
    except ValueError as exc:
        raise invalid("marketplace", f"Registry response was not JSON: {exc}")
    return _validate_index(raw)


def build_marketplace_router(registry: ToolRegistry) -> APIRouter:
    router = APIRouter(prefix="/marketplace", tags=["marketplace"])

    @router.get("", response_model=None)
    async def list_registry(refresh: bool = False) -> dict[str, Any]:
        kind, location = _resolve_source()

        if refresh:
            _cache.clear()

        cached = _cache.get(location)
        if cached is None:
            log.info("Marketplace registry: fetching from %s (%s)", kind, location)
            index = (
                await _load_from_url(location)
                if kind == "url"
                else _load_from_file(location)
            )
            _cache.set(location, index)
        else:
            index = cached

        installed_ids = sorted(m.id for m in registry.list_manifests())
        return {
            "source": {"kind": kind, "location": location},
            "registry": index,
            "installed_ids": installed_ids,
            "cached": cached is not None,
        }

    return router
