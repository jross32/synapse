"""Secrets management (Contract #25).

Per-project env vars marked ``secret: true`` are stored encrypted at rest:

  • Windows: DPAPI scoped to the daemon's user account (``CryptProtectData``).
  • Other platforms (dev/CI on Linux/macOS): ``cryptography.Fernet`` with a
    machine-local key file under ``data/.secrets-key``. **Not** intended for
    production on those platforms — v0.1 is Windows-first.

Public API:

  • :class:`EnvVar`         — pydantic model for a single env var (manifest input).
  • :class:`SecretStore`    — abstract; persists ciphertext somewhere durable.
  • :func:`encrypt`         — bytes → bytes (opaque ciphertext).
  • :func:`decrypt`         — bytes → bytes.

The SQLite-backed implementation of :class:`SecretStore` lives in
:mod:`synapse_daemon.storage` (Milestone B). This module owns the crypto only.
"""

from __future__ import annotations

import os
import secrets as _stdlib_secrets
import sys
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel, Field


class EnvVar(BaseModel):
    """One env var on a project manifest. The user edits these in the UI."""

    key: str = Field(..., min_length=1)
    value: str | None = Field(
        default=None,
        description=(
            "Plaintext on save; '(set)' placeholder on read for secrets. "
            "Daemon never round-trips real secret values back to clients."
        ),
    )
    secret: bool = False
    description: str | None = None


SECRET_PLACEHOLDER = "(set)"


class SecretStore(Protocol):
    """Persistence interface for encrypted secret payloads."""

    def put(self, project_id: str, key: str, plaintext: str) -> None: ...
    def get(self, project_id: str, key: str) -> str | None: ...
    def delete(self, project_id: str, key: str) -> None: ...
    def list_keys(self, project_id: str) -> list[str]: ...


# ── crypto layer ──────────────────────────────────────────────────────────


def encrypt(plaintext: str | bytes, *, data_dir: Path | None = None) -> bytes:
    """Encrypt ``plaintext`` to opaque bytes safe to store in SQLite.

    Caller is responsible for persisting the returned bytes verbatim.
    """

    raw = plaintext.encode("utf-8") if isinstance(plaintext, str) else plaintext
    if sys.platform == "win32":
        return _dpapi_encrypt(raw)
    return _fernet_encrypt(raw, data_dir=data_dir)


def decrypt(ciphertext: bytes, *, data_dir: Path | None = None) -> str:
    """Reverse of :func:`encrypt`. Returns plaintext as ``str``."""

    if sys.platform == "win32":
        return _dpapi_decrypt(ciphertext).decode("utf-8")
    return _fernet_decrypt(ciphertext, data_dir=data_dir).decode("utf-8")


# ── DPAPI (Windows) ───────────────────────────────────────────────────────


def _dpapi_encrypt(raw: bytes) -> bytes:
    import ctypes
    import ctypes.wintypes

    blob_in = _DataBlob.from_bytes(raw)
    blob_out = _DataBlob()
    ok = ctypes.windll.crypt32.CryptProtectData(  # type: ignore[attr-defined]
        ctypes.byref(blob_in),
        None, None, None, None,
        0,
        ctypes.byref(blob_out),
    )
    if not ok:
        raise OSError("CryptProtectData failed (error code: %d)" % ctypes.GetLastError())
    try:
        return ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(blob_out.pbData)  # type: ignore[attr-defined]


def _dpapi_decrypt(raw: bytes) -> bytes:
    import ctypes
    import ctypes.wintypes

    blob_in = _DataBlob.from_bytes(raw)
    blob_out = _DataBlob()
    ok = ctypes.windll.crypt32.CryptUnprotectData(  # type: ignore[attr-defined]
        ctypes.byref(blob_in),
        None, None, None, None,
        0,
        ctypes.byref(blob_out),
    )
    if not ok:
        raise OSError("CryptUnprotectData failed (error code: %d)" % ctypes.GetLastError())
    try:
        return ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(blob_out.pbData)  # type: ignore[attr-defined]


if sys.platform == "win32":
    import ctypes

    class _DataBlob(ctypes.Structure):
        _fields_ = [
            ("cbData", ctypes.c_ulong),
            ("pbData", ctypes.POINTER(ctypes.c_char)),
        ]

        @classmethod
        def from_bytes(cls, raw: bytes) -> "_DataBlob":  # pragma: no cover (Windows)
            buf = ctypes.create_string_buffer(raw, len(raw))
            return cls(len(raw), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))
else:  # placeholder so the symbol exists for type checkers on dev machines
    class _DataBlob:  # type: ignore[no-redef]
        @classmethod
        def from_bytes(cls, raw: bytes) -> "_DataBlob":
            raise NotImplementedError("DPAPI is Windows-only.")


# ── Fernet (non-Windows fallback) ─────────────────────────────────────────


_DEFAULT_KEY_FILENAME = ".secrets-key"


def _fernet_key_path(data_dir: Path | None) -> Path:
    base = data_dir or Path("data")
    base.mkdir(parents=True, exist_ok=True)
    return base / _DEFAULT_KEY_FILENAME


def _load_or_create_fernet_key(data_dir: Path | None) -> bytes:
    from cryptography.fernet import Fernet

    path = _fernet_key_path(data_dir)
    if path.exists():
        return path.read_bytes()
    key = Fernet.generate_key()
    path.write_bytes(key)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return key


def _fernet_encrypt(raw: bytes, *, data_dir: Path | None) -> bytes:
    from cryptography.fernet import Fernet

    key = _load_or_create_fernet_key(data_dir)
    return Fernet(key).encrypt(raw)


def _fernet_decrypt(raw: bytes, *, data_dir: Path | None) -> bytes:
    from cryptography.fernet import Fernet

    key = _load_or_create_fernet_key(data_dir)
    return Fernet(key).decrypt(raw)


# ── helper ────────────────────────────────────────────────────────────────


def redact(env_vars: list[EnvVar]) -> list[EnvVar]:
    """Return a copy of ``env_vars`` with secret values replaced by the placeholder.

    Used by every read path that returns project data to a client.
    """

    return [
        ev.model_copy(update={"value": SECRET_PLACEHOLDER if ev.secret and ev.value else ev.value})
        for ev in env_vars
    ]


def generate_token(byte_length: int = 32) -> str:
    """Convenience for daemon-internal use (e.g. pairing PINs in v0.2)."""

    return _stdlib_secrets.token_urlsafe(byte_length)
