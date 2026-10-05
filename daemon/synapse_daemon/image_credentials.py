"""Encrypted image-provider credentials for Synapse.

Environment variables remain a supported deployment override. For normal desktop use,
Synapse can store the OpenAI image API key encrypted at rest using the existing secrets
crypto layer and the settings KV table. Plaintext is never returned by status/read APIs.
"""

from __future__ import annotations

import base64
import json
import os
from typing import Any

from .secrets import decrypt, encrypt
from .time_utils import to_iso, utc_now

_OPENAI_SETTING_KEY = "image.openai_api_key"
_MAX_KEY_CHARS = 4096


class ImageCredentialError(ValueError):
    """Safe credential-configuration error."""


def _stored_ciphertext(storage: Any) -> bytes | None:
    row = storage.conn.execute(
        "SELECT value_json FROM settings WHERE key = ?",
        (_OPENAI_SETTING_KEY,),
    ).fetchone()
    if row is None:
        return None
    try:
        payload = json.loads(row["value_json"])
        encoded = str(payload.get("ciphertext_b64") or "")
        if not encoded:
            return None
        return base64.b64decode(encoded, validate=True)
    except (json.JSONDecodeError, ValueError, TypeError, KeyError):
        return None


def stored_openai_api_key(storage: Any) -> str | None:
    """Decrypt the locally stored key for provider calls only."""
    ciphertext = _stored_ciphertext(storage)
    if not ciphertext:
        return None
    try:
        value = decrypt(ciphertext, data_dir=storage.data_dir).strip()
    except Exception as exc:  # noqa: BLE001 - corrupt local credential becomes safe absence
        raise ImageCredentialError(
            f"stored OpenAI image credential could not be decrypted: {type(exc).__name__}"
        ) from exc
    return value or None


def resolve_openai_api_key(storage: Any | None = None) -> tuple[str | None, str | None]:
    """Resolve the provider key without exposing it to callers.

    Environment wins so headless/server deployments can override local desktop state.
    """
    env_value = os.getenv("OPENAI_API_KEY", "").strip()
    if env_value:
        return env_value, "environment"
    if storage is not None:
        stored = stored_openai_api_key(storage)
        if stored:
            return stored, "synapse_secret"
    return None, None


def credential_status(storage: Any | None = None) -> dict[str, Any]:
    key, source = resolve_openai_api_key(storage)
    return {
        "provider": "openai",
        "configured": bool(key),
        "source": source,
        "environment_override": bool(os.getenv("OPENAI_API_KEY", "").strip()),
        "stored_secret": bool(_stored_ciphertext(storage)) if storage is not None else False,
    }


def set_openai_api_key(storage: Any, api_key: str) -> dict[str, Any]:
    clean = str(api_key or "").strip()
    if not clean:
        raise ImageCredentialError("api_key is required")
    if len(clean) > _MAX_KEY_CHARS:
        raise ImageCredentialError(f"api_key must be {_MAX_KEY_CHARS} characters or fewer")

    ciphertext = encrypt(clean, data_dir=storage.data_dir)
    value_json = json.dumps(
        {"ciphertext_b64": base64.b64encode(ciphertext).decode("ascii")},
        separators=(",", ":"),
    )
    now = to_iso(utc_now())
    with storage.transaction() as conn:
        conn.execute(
            """
            INSERT INTO settings (key, value_json, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET
                value_json = excluded.value_json,
                updated_at = excluded.updated_at
            """,
            (_OPENAI_SETTING_KEY, value_json, now),
        )
    return credential_status(storage)


def clear_openai_api_key(storage: Any) -> dict[str, Any]:
    with storage.transaction() as conn:
        conn.execute("DELETE FROM settings WHERE key = ?", (_OPENAI_SETTING_KEY,))
    return credential_status(storage)
