"""Encrypted video-provider credentials for Synapse Video Studio.

Environment variables remain deployment overrides. Desktop users can store provider keys
inside Synapse's existing encrypted settings store. Plaintext credentials are only resolved
inside provider calls and are never returned by status/MCP APIs.
"""

from __future__ import annotations

import base64
import json
import os
from typing import Any

from .secrets import decrypt, encrypt
from .time_utils import to_iso, utc_now

_SETTING_KEYS = {
    "google": "video.google_api_key",
    "runway": "video.runway_api_key",
}
_MAX_KEY_CHARS = 4096


class VideoCredentialError(ValueError):
    """Safe credential-configuration error."""


def _stored_ciphertext(storage: Any, provider: str) -> bytes | None:
    key = _SETTING_KEYS.get(provider)
    if not key:
        return None
    row = storage.conn.execute(
        "SELECT value_json FROM settings WHERE key = ?",
        (key,),
    ).fetchone()
    if row is None:
        return None
    try:
        payload = json.loads(row["value_json"])
        encoded = str(payload.get("ciphertext_b64") or "")
        return base64.b64decode(encoded, validate=True) if encoded else None
    except (json.JSONDecodeError, ValueError, TypeError, KeyError):
        return None


def _stored_api_key(storage: Any, provider: str) -> str | None:
    ciphertext = _stored_ciphertext(storage, provider)
    if not ciphertext:
        return None
    try:
        value = decrypt(ciphertext, data_dir=storage.data_dir).strip()
    except Exception as exc:  # noqa: BLE001 - corrupt local secret becomes safe absence
        raise VideoCredentialError(
            f"stored {provider} video credential could not be decrypted: {type(exc).__name__}"
        ) from exc
    return value or None


def resolve_google_api_key(storage: Any | None = None) -> tuple[str | None, str | None]:
    for name in ("GEMINI_API_KEY", "GOOGLE_API_KEY"):
        value = os.getenv(name, "").strip()
        if value:
            return value, f"environment:{name}"
    if storage is not None:
        value = _stored_api_key(storage, "google")
        if value:
            return value, "synapse_secret"
    return None, None


def resolve_runway_api_key(storage: Any | None = None) -> tuple[str | None, str | None]:
    for name in ("RUNWAYML_API_SECRET", "RUNWAY_API_KEY"):
        value = os.getenv(name, "").strip()
        if value:
            return value, f"environment:{name}"
    if storage is not None:
        value = _stored_api_key(storage, "runway")
        if value:
            return value, "synapse_secret"
    return None, None


def credential_status(storage: Any | None = None) -> dict[str, Any]:
    google_key, google_source = resolve_google_api_key(storage)
    runway_key, runway_source = resolve_runway_api_key(storage)
    return {
        "google": {
            "configured": bool(google_key),
            "source": google_source,
            "environment_override": bool(
                os.getenv("GEMINI_API_KEY", "").strip() or os.getenv("GOOGLE_API_KEY", "").strip()
            ),
            "stored_secret": bool(_stored_ciphertext(storage, "google")) if storage is not None else False,
        },
        "runway": {
            "configured": bool(runway_key),
            "source": runway_source,
            "environment_override": bool(
                os.getenv("RUNWAYML_API_SECRET", "").strip() or os.getenv("RUNWAY_API_KEY", "").strip()
            ),
            "stored_secret": bool(_stored_ciphertext(storage, "runway")) if storage is not None else False,
        },
    }


def set_api_key(storage: Any, provider: str, api_key: str) -> dict[str, Any]:
    provider = str(provider or "").strip().lower()
    if provider not in _SETTING_KEYS:
        raise VideoCredentialError("provider must be 'google' or 'runway'")
    clean = str(api_key or "").strip()
    if not clean:
        raise VideoCredentialError("api_key is required")
    if len(clean) > _MAX_KEY_CHARS:
        raise VideoCredentialError(f"api_key must be {_MAX_KEY_CHARS} characters or fewer")

    ciphertext = encrypt(clean, data_dir=storage.data_dir)
    value_json = json.dumps(
        {"ciphertext_b64": base64.b64encode(ciphertext).decode("ascii")},
        separators=(",", ":"),
    )
    now = to_iso(utc_now())
    setting_key = _SETTING_KEYS[provider]
    with storage.transaction() as conn:
        conn.execute(
            """
            INSERT INTO settings (key, value_json, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET
                value_json = excluded.value_json,
                updated_at = excluded.updated_at
            """,
            (setting_key, value_json, now),
        )
    return credential_status(storage)[provider]


def clear_api_key(storage: Any, provider: str) -> dict[str, Any]:
    provider = str(provider or "").strip().lower()
    if provider not in _SETTING_KEYS:
        raise VideoCredentialError("provider must be 'google' or 'runway'")
    with storage.transaction() as conn:
        conn.execute("DELETE FROM settings WHERE key = ?", (_SETTING_KEYS[provider],))
    return credential_status(storage)[provider]
