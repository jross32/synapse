"""Local per-account/per-device MCP enrollment preferences (no bearer secrets stored here)."""
from __future__ import annotations

import hashlib
import json
import secrets
from pathlib import Path

def _file(data_dir: Path, user_id: str, device_id: str) -> Path:
    key = hashlib.sha256((user_id + ":" + device_id).encode("utf-8")).hexdigest()
    return Path(data_dir) / "mcp-device-enrollment" / (key + ".json")

def get_device_preference(data_dir: Path, user_id: str | None, device_id: str) -> bool:
    if not user_id:
        return False
    try:
        return bool(json.loads(_file(data_dir, user_id, device_id).read_text(encoding="utf-8"))["enabled"])
    except (OSError, ValueError, KeyError, TypeError):
        return True

def device_token(data_dir: Path, user_id: str, device_id: str) -> str:
    """Issue a distinct credential for this account/device, never the primary token."""
    path = _file(data_dir, user_id, device_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        existing = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        existing = {}
    token = existing.get("token")
    if not isinstance(token, str) or len(token) < 32:
        token = secrets.token_urlsafe(32)
        existing["token"] = token
        existing.setdefault("enabled", True)
        _write(path, existing)
    return token

def _write(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(state), encoding="utf-8")
    temporary.replace(path)

def set_device_preference(data_dir: Path, user_id: str, device_id: str, enabled: bool) -> None:
    path = _file(data_dir, user_id, device_id)
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        state = {}
    state["enabled"] = bool(enabled)
    if enabled and not state.get("token"):
        state["token"] = secrets.token_urlsafe(32)
    _write(path, state)
