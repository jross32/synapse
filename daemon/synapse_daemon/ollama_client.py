"""Async bridge to a local Ollama engine (ADR-0014).

Synapse talks to the user's local Ollama over its HTTP API at
``127.0.0.1:11434``. This module keeps that integration in one place: detect
the binary, check / start the server, list installed models, run a chat
completion, and stream a model pull (used by the model marketplace).

Nothing here assumes Ollama is installed or running -- every entry point
degrades gracefully so the Assistant surface can show an honest "not
installed / not running" state instead of erroring.
"""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import AsyncIterator
from typing import Any

import httpx

from .runtime_resolution import resolve_command

OLLAMA_BASE = os.getenv("SYNAPSE_OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")


def ollama_binary() -> str | None:
    """Resolve the ``ollama`` executable (PATH + known install dirs), or None."""
    return resolve_command("ollama")


def is_installed() -> bool:
    return ollama_binary() is not None


async def server_up(timeout: float = 1.5) -> bool:
    """True if the Ollama HTTP API answers."""
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            res = await client.get(f"{OLLAMA_BASE}/api/tags")
            return res.status_code == 200
    except Exception:  # noqa: BLE001 -- any failure means "not up"
        return False


async def list_models() -> list[dict[str, Any]]:
    """Models the user has pulled locally (GET /api/tags)."""
    async with httpx.AsyncClient(timeout=5.0) as client:
        res = await client.get(f"{OLLAMA_BASE}/api/tags")
        res.raise_for_status()
        data = res.json()
    models: list[dict[str, Any]] = []
    for entry in data.get("models", []):
        details = entry.get("details") or {}
        models.append(
            {
                "name": entry.get("name", ""),
                "size": entry.get("size"),
                "modified_at": entry.get("modified_at"),
                "family": details.get("family"),
                "parameter_size": details.get("parameter_size"),
            }
        )
    return models


def start_server() -> bool:
    """Best-effort: spawn ``ollama serve`` detached. Returns True if a process
    was started (not that it's healthy yet -- callers should poll ``server_up``)."""
    binary = ollama_binary()
    if not binary:
        return False
    creationflags = 0
    if sys.platform == "win32":
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(
            subprocess, "CREATE_NEW_PROCESS_GROUP", 0
        )
    try:
        subprocess.Popen(  # noqa: S603 -- resolved binary, fixed args
            [binary, "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            creationflags=creationflags,
            start_new_session=(sys.platform != "win32"),
        )
        return True
    except Exception:  # noqa: BLE001
        return False


def stop_server() -> int:
    """Best-effort: terminate the local ``ollama serve`` process(es). Returns
    how many were signalled. Only matches the serve process, not unrelated
    binaries. The user asked to be able to close Ollama from the app."""
    try:
        import psutil
    except Exception:  # noqa: BLE001
        return 0
    killed = 0
    for proc in psutil.process_iter(["name", "cmdline"]):
        try:
            name = (proc.info.get("name") or "").lower()
            cmdline = " ".join(proc.info.get("cmdline") or []).lower()
            if "ollama" in name and "serve" in cmdline:
                proc.terminate()
                killed += 1
        except Exception:  # noqa: BLE001 -- process vanished / no access
            continue
    return killed


async def chat(model: str, messages: list[dict[str, str]], timeout: float = 180.0) -> str:
    """Non-streaming chat completion. ``messages`` = [{role, content}, ...].
    Returns the assistant's reply text."""
    payload = {"model": model, "messages": messages, "stream": False}
    async with httpx.AsyncClient(timeout=timeout) as client:
        res = await client.post(f"{OLLAMA_BASE}/api/chat", json=payload)
        res.raise_for_status()
        data = res.json()
    return (data.get("message") or {}).get("content", "")


async def delete_model(model: str) -> bool:
    """Remove an installed model (DELETE /api/delete). Returns True on success."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        res = await client.request("DELETE", f"{OLLAMA_BASE}/api/delete", json={"model": model})
        return res.status_code == 200


async def pull(model: str) -> AsyncIterator[dict[str, Any]]:
    """Stream a model download (POST /api/pull). Yields the raw progress dicts
    Ollama emits (status, total, completed). Used by the model marketplace."""
    payload = {"model": model, "stream": True}
    async with httpx.AsyncClient(timeout=None) as client:
        async with client.stream("POST", f"{OLLAMA_BASE}/api/pull", json=payload) as res:
            res.raise_for_status()
            async for line in res.aiter_lines():
                line = line.strip()
                if not line:
                    continue
                try:
                    import json

                    yield json.loads(line)
                except Exception:  # noqa: BLE001 -- skip malformed chunk
                    continue
