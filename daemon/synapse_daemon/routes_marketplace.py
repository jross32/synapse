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

from .errors import conflict, invalid, not_found
from .models import ToolManifest
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


async def _fetch_manifest_payload(entry: dict[str, Any]) -> dict[str, Any]:
    """Pull the manifest body for a registry entry: inline first, else URL."""

    inline = entry.get("manifest_inline")
    if isinstance(inline, dict):
        return inline

    url = entry.get("manifest_url")
    if not isinstance(url, str) or not url.strip():
        raise invalid(
            "marketplace",
            f"Tool '{entry.get('id')}' has no installable manifest source "
            "(neither manifest_inline nor manifest_url).",
        )
    try:
        async with httpx.AsyncClient(timeout=_FETCH_TIMEOUT_SECONDS) as client:
            response = await client.get(url)
    except httpx.HTTPError as exc:
        raise invalid("marketplace", f"Could not fetch manifest {url!r}: {exc}")
    if response.status_code >= 400:
        raise invalid(
            "marketplace",
            f"Manifest URL {url!r} returned HTTP {response.status_code}.",
        )
    try:
        return response.json()
    except ValueError as exc:
        raise invalid("marketplace", f"Manifest response was not JSON: {exc}")


def build_marketplace_router(registry: ToolRegistry) -> APIRouter:
    router = APIRouter(prefix="/marketplace", tags=["marketplace"])
    tools_dir = registry._tools_dir  # the registry already validated this folder

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

    @router.post("/install/{tool_id}", response_model=None)
    async def install(tool_id: str, force: bool = False) -> dict[str, Any]:
        """Install a registry entry by writing its manifest into ``tools/``.

        Hot reload (v0.1.21) picks the manifest up; primitives (v0.1.22)
        make it runnable. Refuses to clobber an existing folder unless
        ``?force=true``.
        """

        # Find the entry in the (possibly cached) registry.
        kind, location = _resolve_source()
        cached = _cache.get(location)
        if cached is None:
            cached = (
                await _load_from_url(location)
                if kind == "url"
                else _load_from_file(location)
            )
            _cache.set(location, cached)

        entry = next(
            (e for e in cached.get("tools", []) if e.get("id") == tool_id),
            None,
        )
        if entry is None:
            raise not_found("tool", tool_id)

        target_dir = tools_dir / tool_id
        target_file = target_dir / "manifest.json"
        if target_file.exists() and not force:
            raise conflict(
                "marketplace",
                f"Tool '{tool_id}' is already installed at {target_file}. "
                "Pass ?force=true to overwrite.",
            )

        payload = await _fetch_manifest_payload(entry)

        # Validate against ToolManifest before writing -- a bad payload should
        # never land on disk and trip the registry's "skip invalid" path.
        try:
            manifest = ToolManifest.model_validate(payload)
        except Exception as exc:
            raise invalid(
                "marketplace",
                f"Manifest for '{tool_id}' failed validation: {exc}",
            )
        # Prevent a malicious or misconfigured manifest from pretending to be
        # another tool. The registry id is the trust anchor.
        if manifest.id != tool_id:
            raise invalid(
                "marketplace",
                f"Manifest declared id '{manifest.id}' does not match "
                f"registry id '{tool_id}'.",
            )

        target_dir.mkdir(parents=True, exist_ok=True)
        target_file.write_text(
            json.dumps(payload, indent=2) + "\n", encoding="utf-8"
        )

        # Hot reload will fire on its own (~250 ms), but a synchronous reload
        # here means the response we return reflects the new state.
        report = await registry.reload()

        return {
            "installed": tool_id,
            "tier": entry.get("tier"),
            "version": entry.get("version"),
            "path": str(target_file),
            "reload": report,
        }

    @router.delete("/install/{tool_id}", response_model=None)
    async def uninstall(tool_id: str) -> dict[str, Any]:
        """Uninstall a tool by removing its manifest.json.

        Handler-tier handlers compiled into the daemon are unaffected -- the
        manifest is what makes them *visible*. Reinstall by clicking Install.
        """

        target_dir = tools_dir / tool_id
        target_file = target_dir / "manifest.json"
        if not target_file.exists():
            raise not_found("tool", tool_id)

        target_file.unlink()
        # Best-effort: drop the folder if it has no other files (it usually
        # only contains the manifest, but a tool might bundle assets later).
        try:
            if not any(target_dir.iterdir()):
                target_dir.rmdir()
        except OSError:  # pragma: no cover -- non-empty / locked
            pass

        report = await registry.reload()
        return {"uninstalled": tool_id, "reload": report}

    return router
