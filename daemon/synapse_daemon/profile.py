"""Daemon-owned profile/account/catalog state for the Synapse Profile hub.

Local-first rules:

* Synapse continues to work without any account.
* Remote sync only happens after the user configures a Supabase project and
  signs in deliberately.
* Portable data is stored locally first, then mirrored into the signed-in
  Supabase user's ``user_metadata.synapse_profile`` blob so v1 can ship
  cross-host favorites/history without requiring a custom hosted schema.
"""

from __future__ import annotations

import base64
import hashlib
import json
import platform as platform_mod
import secrets
import shutil
import socket
import subprocess
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from .errors import SynapseError, invalid
from .secrets import decrypt, encrypt
from .storage import Storage
from .time_utils import to_iso, utc_now

_PROFILE_SINGLETON_ID = 1
_SYNC_METADATA_KEY = "synapse_profile"
_TOKEN_REFRESH_MARGIN_SECONDS = 45
_SUPABASE_TIMEOUT_SECONDS = 12
_OAUTH_STATE_TTL_SECONDS = 900


class ProfileSyncStatus(str):
    LOCAL_ONLY = "local-only"
    CONNECTED = "connected"
    ERROR = "error"
    CONFIG_REQUIRED = "config-required"


class ServiceConnectionMode(str):
    PORTABLE_OFFICIAL = "portable-official"
    LOCAL_DETECTED = "local-detected"


class ServiceConnectionStatus(str):
    READY = "ready"
    NEEDS_ATTENTION = "needs-attention"
    DISCONNECTED = "disconnected"
    LOCAL_ONLY = "local-only"


class ProviderIdentity(BaseModel):
    provider: str
    email: str | None = None
    identity_id: str | None = None


class HostPresence(BaseModel):
    id: str
    name: str
    platform: str
    current_host: bool
    last_seen_at: str
    created_at: str
    updated_at: str


class ServiceConnection(BaseModel):
    id: str
    provider: str
    display_name: str
    mode: str
    portability: str
    status: str
    details: dict[str, Any] = Field(default_factory=dict)
    last_verified_at: str | None = None
    last_host_id: str | None = None
    created_at: str
    updated_at: str


class CatalogPreferenceItem(BaseModel):
    item_key: str
    kind: str
    item_id: str
    favorite: bool
    last_used_at: str | None = None
    use_count: int = 0
    last_installed_at: str | None = None
    installed_host_ids: list[str] = Field(default_factory=list)
    installed_here: bool = False
    previously_installed: bool = False
    used_before: bool = False
    updated_at: str


class CatalogPreferenceState(BaseModel):
    current_host_id: str
    items: list[CatalogPreferenceItem] = Field(default_factory=list)
    favorite_keys: list[str] = Field(default_factory=list)
    sync_enabled: bool = False
    signed_in: bool = False
    last_sync_at: str | None = None
    last_sync_error: str | None = None


class ProfileSummary(BaseModel):
    signed_in: bool
    config_ready: bool
    supabase_url: str | None = None
    has_anon_key: bool = False
    sync_enabled: bool = False
    sync_status: str
    user_id: str | None = None
    email: str | None = None
    display_name: str | None = None
    avatar_url: str | None = None
    provider: str | None = None
    provider_identities: list[ProviderIdentity] = Field(default_factory=list)
    current_host: HostPresence
    portable_connection_count: int = 0
    local_connection_count: int = 0
    last_sync_at: str | None = None
    last_sync_error: str | None = None


class ProfileConfigUpdate(BaseModel):
    supabase_url: str | None = None
    supabase_anon_key: str | None = None
    sync_enabled: bool | None = None


class _SupabaseResponse(BaseModel):
    status: int
    payload: Any


def _now_iso() -> str:
    return to_iso(utc_now())


def _json_loads(raw: str | None, default: Any) -> Any:
    if not raw:
        return default
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return default


def _normalize_supabase_url(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip().rstrip("/")
    if not cleaned:
        return None
    if not cleaned.startswith("http://") and not cleaned.startswith("https://"):
        cleaned = f"https://{cleaned}"
    return cleaned


def _token_cipher(value: str | None, *, storage: Storage) -> bytes | None:
    if not value:
        return None
    return encrypt(value, data_dir=storage.data_dir)


def _token_plaintext(value: bytes | None, *, storage: Storage) -> str | None:
    if not value:
        return None
    return decrypt(value, data_dir=storage.data_dir)


def _s256_pkce_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def _timestamp_or_empty(value: str | None) -> str:
    return value or ""


class ProfileManager:
    """Owns local profile state, optional Supabase auth, and sync."""

    def __init__(self, storage: Storage) -> None:
        self._storage = storage

    # ── public summary / config ──────────────────────────────────────────

    def summary(self, *, refresh_remote: bool = True) -> ProfileSummary:
        current_host = self.ensure_current_host()
        row = self._state_row()
        if refresh_remote and row["user_id"] and row["sync_enabled"]:
            self._refresh_from_remote(best_effort=True)
            row = self._state_row()
        connections = self.list_service_connections(refresh_remote=False)
        portable_count = len(
            [c for c in connections if c.mode == ServiceConnectionMode.PORTABLE_OFFICIAL]
        )
        local_count = len(
            [c for c in connections if c.mode == ServiceConnectionMode.LOCAL_DETECTED]
        )
        signed_in = bool(row["user_id"])
        config_ready = bool(row["supabase_url"] and row["supabase_anon_key"])
        if row["last_sync_error"]:
            sync_status = ProfileSyncStatus.ERROR
        elif signed_in:
            sync_status = ProfileSyncStatus.CONNECTED
        elif config_ready:
            sync_status = ProfileSyncStatus.LOCAL_ONLY
        else:
            sync_status = ProfileSyncStatus.CONFIG_REQUIRED
        return ProfileSummary(
            signed_in=signed_in,
            config_ready=config_ready,
            supabase_url=row["supabase_url"],
            has_anon_key=bool(row["supabase_anon_key"]),
            sync_enabled=bool(row["sync_enabled"]),
            sync_status=sync_status,
            user_id=row["user_id"],
            email=row["email"],
            display_name=row["display_name"],
            avatar_url=row["avatar_url"],
            provider=row["provider"],
            provider_identities=[
                ProviderIdentity.model_validate(item)
                for item in _json_loads(row["provider_identities_json"], [])
            ],
            current_host=current_host,
            portable_connection_count=portable_count,
            local_connection_count=local_count,
            last_sync_at=row["last_sync_at"],
            last_sync_error=row["last_sync_error"],
        )

    def configure(self, payload: ProfileConfigUpdate) -> ProfileSummary:
        row = self._state_row()
        now = _now_iso()
        next_url = row["supabase_url"] if payload.supabase_url is None else _normalize_supabase_url(payload.supabase_url)
        next_key = row["supabase_anon_key"] if payload.supabase_anon_key is None else (payload.supabase_anon_key or None)
        next_sync = row["sync_enabled"] if payload.sync_enabled is None else int(payload.sync_enabled)
        changed_backend = next_url != row["supabase_url"] or next_key != row["supabase_anon_key"]
        with self._storage.transaction() as conn:
            conn.execute(
                """
                UPDATE profile_state
                SET supabase_url = ?,
                    supabase_anon_key = ?,
                    sync_enabled = ?,
                    updated_at = ?,
                    user_id = CASE WHEN ? THEN NULL ELSE user_id END,
                    email = CASE WHEN ? THEN NULL ELSE email END,
                    display_name = CASE WHEN ? THEN NULL ELSE display_name END,
                    avatar_url = CASE WHEN ? THEN NULL ELSE avatar_url END,
                    provider = CASE WHEN ? THEN NULL ELSE provider END,
                    provider_identities_json = CASE WHEN ? THEN '[]' ELSE provider_identities_json END,
                    access_token_cipher = CASE WHEN ? THEN NULL ELSE access_token_cipher END,
                    refresh_token_cipher = CASE WHEN ? THEN NULL ELSE refresh_token_cipher END,
                    access_token_expires_at = CASE WHEN ? THEN NULL ELSE access_token_expires_at END,
                    last_sync_error = CASE WHEN ? THEN NULL ELSE last_sync_error END
                WHERE id = 1
                """,
                (
                    next_url,
                    next_key,
                    next_sync,
                    now,
                    int(changed_backend),
                    int(changed_backend),
                    int(changed_backend),
                    int(changed_backend),
                    int(changed_backend),
                    int(changed_backend),
                    int(changed_backend),
                    int(changed_backend),
                    int(changed_backend),
                    int(changed_backend),
                ),
            )
        return self.summary(refresh_remote=False)

    # ── auth lifecycle ───────────────────────────────────────────────────

    def sign_up_password(
        self,
        *,
        email: str,
        password: str,
        display_name: str | None = None,
    ) -> tuple[ProfileSummary, str | None]:
        config = self._require_supabase_config()
        body: dict[str, Any] = {"email": email, "password": password}
        if display_name:
            body["data"] = {"display_name": display_name}
        res = self._supabase_request(
            path="/auth/v1/signup",
            anon_key=config["supabase_anon_key"],
            method="POST",
            payload=body,
        )
        session = res.payload.get("session") if isinstance(res.payload, dict) else None
        user = res.payload.get("user") if isinstance(res.payload, dict) else None
        notice = None
        if session:
            self._store_session_payload(session, user=user)
            self._refresh_from_remote(best_effort=True)
        else:
            notice = "Check your email to finish confirming this Synapse account."
        return self.summary(refresh_remote=False), notice

    def sign_in_password(self, *, email: str, password: str) -> ProfileSummary:
        config = self._require_supabase_config()
        res = self._supabase_request(
            path="/auth/v1/token?grant_type=password",
            anon_key=config["supabase_anon_key"],
            method="POST",
            payload={"email": email, "password": password},
        )
        self._store_session_payload(res.payload)
        self._refresh_from_remote(best_effort=True)
        return self.summary(refresh_remote=False)

    def start_oauth(self, *, provider: str, redirect_to: str) -> str:
        if provider not in {"google", "github"}:
            raise invalid("profile", f"Unsupported provider '{provider}'.")
        config = self._require_supabase_config()
        state = secrets.token_urlsafe(24)
        verifier = secrets.token_urlsafe(48)
        challenge = _s256_pkce_challenge(verifier)
        now = utc_now()
        expires_at = now + timedelta(seconds=_OAUTH_STATE_TTL_SECONDS)
        with self._storage.transaction() as conn:
            conn.execute(
                """
                INSERT INTO profile_oauth_states (
                    state, provider, code_verifier, redirect_to, created_at, expires_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    state,
                    provider,
                    verifier,
                    redirect_to,
                    to_iso(now),
                    to_iso(expires_at),
                ),
            )
        query = urllib.parse.urlencode(
            {
                "provider": provider,
                "redirect_to": redirect_to,
                "code_challenge": challenge,
                "code_challenge_method": "s256",
                "state": state,
                "flow_type": "pkce",
            }
        )
        return f"{config['supabase_url']}/auth/v1/authorize?{query}"

    def complete_oauth(self, *, code: str, state: str) -> ProfileSummary:
        row = self._storage.conn.execute(
            """
            SELECT state, provider, code_verifier, expires_at, used_at
            FROM profile_oauth_states
            WHERE state = ?
            """,
            (state,),
        ).fetchone()
        if row is None:
            raise invalid("profile", "That sign-in handoff is no longer valid.")
        if row["used_at"] is not None:
            raise invalid("profile", "That sign-in handoff was already used.")
        if utc_now() > datetime.fromisoformat(row["expires_at"]):
            raise invalid("profile", "That sign-in handoff expired. Start again from Synapse.")
        config = self._require_supabase_config()
        res = self._supabase_request(
            path="/auth/v1/token?grant_type=pkce",
            anon_key=config["supabase_anon_key"],
            method="POST",
            payload={"auth_code": code, "code_verifier": row["code_verifier"]},
        )
        with self._storage.transaction() as conn:
            conn.execute(
                "UPDATE profile_oauth_states SET used_at = ? WHERE state = ?",
                (_now_iso(), state),
            )
        self._store_session_payload(res.payload)
        self._refresh_from_remote(best_effort=True)
        return self.summary(refresh_remote=False)

    def sign_out(self) -> ProfileSummary:
        row = self._state_row()
        config_ready = bool(row["supabase_url"] and row["supabase_anon_key"])
        access_token = _token_plaintext(row["access_token_cipher"], storage=self._storage)
        if config_ready and access_token:
            try:
                self._supabase_request(
                    path="/auth/v1/logout",
                    anon_key=row["supabase_anon_key"],
                    method="POST",
                    access_token=access_token,
                )
            except Exception:
                pass
        with self._storage.transaction() as conn:
            conn.execute(
                """
                UPDATE profile_state
                SET user_id = NULL,
                    email = NULL,
                    display_name = NULL,
                    avatar_url = NULL,
                    provider = NULL,
                    provider_identities_json = '[]',
                    access_token_cipher = NULL,
                    refresh_token_cipher = NULL,
                    access_token_expires_at = NULL,
                    last_sync_error = NULL,
                    updated_at = ?
                WHERE id = 1
                """,
                (_now_iso(),),
            )
        return self.summary(refresh_remote=False)

    # ── catalog state ────────────────────────────────────────────────────

    def catalog_state(self) -> CatalogPreferenceState:
        current_host = self.ensure_current_host()
        rows = self._storage.conn.execute(
            """
            SELECT item_key, kind, item_id, favorite, last_used_at, use_count,
                   last_installed_at, installed_host_ids_json, updated_at
            FROM catalog_preferences
            ORDER BY favorite DESC, COALESCE(last_used_at, '') DESC, updated_at DESC, item_key ASC
            """
        ).fetchall()
        items: list[CatalogPreferenceItem] = []
        for row in rows:
            installed_host_ids = list(_json_loads(row["installed_host_ids_json"], []))
            installed_here = row["kind"] == "tool" and current_host.id in installed_host_ids
            items.append(
                CatalogPreferenceItem(
                    item_key=row["item_key"],
                    kind=row["kind"],
                    item_id=row["item_id"],
                    favorite=bool(row["favorite"]),
                    last_used_at=row["last_used_at"],
                    use_count=int(row["use_count"] or 0),
                    last_installed_at=row["last_installed_at"],
                    installed_host_ids=installed_host_ids,
                    installed_here=installed_here,
                    previously_installed=not installed_here and bool(row["last_installed_at"]),
                    used_before=bool(row["last_used_at"]) or int(row["use_count"] or 0) > 0,
                    updated_at=row["updated_at"],
                )
            )
        summary = self.summary(refresh_remote=False)
        return CatalogPreferenceState(
            current_host_id=current_host.id,
            items=items,
            favorite_keys=[item.item_key for item in items if item.favorite],
            sync_enabled=summary.sync_enabled,
            signed_in=summary.signed_in,
            last_sync_at=summary.last_sync_at,
            last_sync_error=summary.last_sync_error,
        )

    def set_favorite(self, *, kind: str, item_id: str, favorite: bool | None = None) -> CatalogPreferenceItem:
        self.ensure_current_host()
        item_key = f"{kind}:{item_id}"
        row = self._storage.conn.execute(
            """
            SELECT favorite, last_used_at, use_count, last_installed_at, installed_host_ids_json, updated_at
            FROM catalog_preferences
            WHERE item_key = ?
            """,
            (item_key,),
        ).fetchone()
        current = bool(row["favorite"]) if row is not None else False
        next_value = (not current) if favorite is None else bool(favorite)
        now = _now_iso()
        with self._storage.transaction() as conn:
            if row is None:
                conn.execute(
                    """
                    INSERT INTO catalog_preferences (
                        item_key, kind, item_id, favorite, use_count, installed_host_ids_json, updated_at
                    ) VALUES (?, ?, ?, ?, 0, '[]', ?)
                    """,
                    (item_key, kind, item_id, int(next_value), now),
                )
            else:
                conn.execute(
                    "UPDATE catalog_preferences SET favorite = ?, updated_at = ? WHERE item_key = ?",
                    (int(next_value), now, item_key),
                )
        self._sync_to_remote(best_effort=True)
        return self._catalog_item(item_key)

    def record_catalog_use(self, *, kind: str, item_id: str) -> None:
        self.ensure_current_host()
        item_key = f"{kind}:{item_id}"
        now = _now_iso()
        row = self._storage.conn.execute(
            "SELECT use_count FROM catalog_preferences WHERE item_key = ?",
            (item_key,),
        ).fetchone()
        with self._storage.transaction() as conn:
            if row is None:
                conn.execute(
                    """
                    INSERT INTO catalog_preferences (
                        item_key, kind, item_id, favorite, last_used_at, use_count,
                        installed_host_ids_json, updated_at
                    ) VALUES (?, ?, ?, 0, ?, 1, '[]', ?)
                    """,
                    (item_key, kind, item_id, now, now),
                )
            else:
                conn.execute(
                    """
                    UPDATE catalog_preferences
                    SET last_used_at = ?, use_count = ?, updated_at = ?
                    WHERE item_key = ?
                    """,
                    (now, int(row["use_count"] or 0) + 1, now, item_key),
                )
        self._sync_to_remote(best_effort=True)

    def record_tool_install(self, *, tool_id: str) -> None:
        host = self.ensure_current_host()
        item_key = f"tool:{tool_id}"
        now = _now_iso()
        row = self._storage.conn.execute(
            """
            SELECT favorite, last_used_at, use_count, installed_host_ids_json
            FROM catalog_preferences
            WHERE item_key = ?
            """,
            (item_key,),
        ).fetchone()
        host_ids = set(_json_loads(row["installed_host_ids_json"], [])) if row is not None else set()
        host_ids.add(host.id)
        with self._storage.transaction() as conn:
            if row is None:
                conn.execute(
                    """
                    INSERT INTO catalog_preferences (
                        item_key, kind, item_id, favorite, use_count,
                        last_installed_at, installed_host_ids_json, updated_at
                    ) VALUES (?, 'tool', ?, 0, 0, ?, ?, ?)
                    """,
                    (item_key, tool_id, now, json.dumps(sorted(host_ids)), now),
                )
            else:
                conn.execute(
                    """
                    UPDATE catalog_preferences
                    SET last_installed_at = ?, installed_host_ids_json = ?, updated_at = ?
                    WHERE item_key = ?
                    """,
                    (now, json.dumps(sorted(host_ids)), now, item_key),
                )
        self._sync_to_remote(best_effort=True)

    def record_tool_uninstall(self, *, tool_id: str) -> None:
        host = self.ensure_current_host()
        item_key = f"tool:{tool_id}"
        row = self._storage.conn.execute(
            "SELECT installed_host_ids_json FROM catalog_preferences WHERE item_key = ?",
            (item_key,),
        ).fetchone()
        if row is None:
            return
        host_ids = set(_json_loads(row["installed_host_ids_json"], []))
        if host.id in host_ids:
            host_ids.remove(host.id)
        with self._storage.transaction() as conn:
            conn.execute(
                """
                UPDATE catalog_preferences
                SET installed_host_ids_json = ?, updated_at = ?
                WHERE item_key = ?
                """,
                (json.dumps(sorted(host_ids)), _now_iso(), item_key),
            )
        self._sync_to_remote(best_effort=True)

    # ── services / hosts ────────────────────────────────────────────────

    def list_hosts(self) -> list[HostPresence]:
        self.ensure_current_host()
        rows = self._storage.conn.execute(
            """
            SELECT id, name, platform, current_host, last_seen_at, created_at, updated_at
            FROM profile_hosts
            ORDER BY current_host DESC, last_seen_at DESC
            """
        ).fetchall()
        return [
            HostPresence(
                id=row["id"],
                name=row["name"],
                platform=row["platform"],
                current_host=bool(row["current_host"]),
                last_seen_at=row["last_seen_at"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )
            for row in rows
        ]

    def list_service_connections(self, *, refresh_remote: bool = True) -> list[ServiceConnection]:
        if refresh_remote:
            self._refresh_from_remote(best_effort=True)
        host = self.ensure_current_host()
        persisted_rows = self._storage.conn.execute(
            """
            SELECT id, provider, display_name, mode, portability, status, details_json,
                   last_verified_at, last_host_id, created_at, updated_at
            FROM service_connections
            ORDER BY updated_at DESC, display_name ASC
            """
        ).fetchall()
        persisted = {
            row["provider"]: ServiceConnection(
                id=row["id"],
                provider=row["provider"],
                display_name=row["display_name"],
                mode=row["mode"],
                portability=row["portability"],
                status=row["status"],
                details=_json_loads(row["details_json"], {}),
                last_verified_at=row["last_verified_at"],
                last_host_id=row["last_host_id"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )
            for row in persisted_rows
        }

        out: dict[str, ServiceConnection] = dict(persisted)
        for provider in ("claude-code", "openai-codex", "chatgpt-openai", "github-copilot"):
            detected = self._detect_local_service(provider, host)
            if provider in out:
                out[provider] = out[provider].model_copy(
                    update={
                        "status": detected.status,
                        "details": {**out[provider].details, **detected.details},
                        "last_verified_at": detected.last_verified_at,
                        "last_host_id": detected.last_host_id,
                        "updated_at": max(out[provider].updated_at, detected.updated_at),
                    }
                )
            else:
                out[provider] = detected

        identities = [
            ProviderIdentity.model_validate(item)
            for item in _json_loads(self._state_row()["provider_identities_json"], [])
        ]
        for identity in identities:
            if identity.provider not in {"github", "google"}:
                continue
            existing = out.get(identity.provider)
            now = _now_iso()
            portable = ServiceConnection(
                id=existing.id if existing else f"account-{identity.provider}",
                provider=identity.provider,
                display_name="GitHub" if identity.provider == "github" else "Google",
                mode=ServiceConnectionMode.PORTABLE_OFFICIAL,
                portability="portable",
                status=ServiceConnectionStatus.READY,
                details={
                    "source": "synapse-account",
                    "email": identity.email,
                    "message": "Linked through your Synapse account sign-in.",
                },
                last_verified_at=now,
                last_host_id=host.id,
                created_at=existing.created_at if existing else now,
                updated_at=now,
            )
            out[identity.provider] = portable

        return sorted(out.values(), key=lambda item: (item.mode != ServiceConnectionMode.PORTABLE_OFFICIAL, item.display_name.lower()))

    def connect_service(self, *, provider: str) -> ServiceConnection:
        host = self.ensure_current_host()
        if provider in {"github", "google"}:
            identities = [
                ProviderIdentity.model_validate(item)
                for item in _json_loads(self._state_row()["provider_identities_json"], [])
            ]
            identity = next((item for item in identities if item.provider == provider), None)
            if identity is None:
                raise invalid(
                    "profile",
                    f"Sign into Synapse with {provider.title()} first to mark that service portable.",
                )
            connection = ServiceConnection(
                id=f"account-{provider}",
                provider=provider,
                display_name="GitHub" if provider == "github" else "Google",
                mode=ServiceConnectionMode.PORTABLE_OFFICIAL,
                portability="portable",
                status=ServiceConnectionStatus.READY,
                details={
                    "source": "synapse-account",
                    "email": identity.email,
                    "message": "Linked through your Synapse account sign-in.",
                },
                last_verified_at=_now_iso(),
                last_host_id=host.id,
                created_at=_now_iso(),
                updated_at=_now_iso(),
            )
        else:
            connection = self._detect_local_service(provider, host)
        self._upsert_service_connection(connection)
        self._sync_to_remote(best_effort=True)
        return connection

    def verify_service(self, *, provider: str) -> ServiceConnection:
        return self.connect_service(provider=provider)

    def delete_service_connection(self, connection_id: str) -> None:
        with self._storage.transaction() as conn:
            conn.execute("DELETE FROM service_connections WHERE id = ?", (connection_id,))
        self._sync_to_remote(best_effort=True)

    def ensure_current_host(self) -> HostPresence:
        row = self._state_row()
        current_host_id = row["current_host_id"] or str(uuid.uuid4())
        current_host_name = row["current_host_name"] or (socket.gethostname() or "This computer")
        current_host_platform = row["current_host_platform"] or platform_mod.system()
        now = _now_iso()
        with self._storage.transaction() as conn:
            conn.execute("UPDATE profile_hosts SET current_host = 0")
            conn.execute(
                """
                INSERT INTO profile_hosts (id, name, platform, current_host, last_seen_at, created_at, updated_at)
                VALUES (?, ?, ?, 1, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name = excluded.name,
                    platform = excluded.platform,
                    current_host = 1,
                    last_seen_at = excluded.last_seen_at,
                    updated_at = excluded.updated_at
                """,
                (
                    current_host_id,
                    current_host_name,
                    current_host_platform,
                    now,
                    now,
                    now,
                ),
            )
            conn.execute(
                """
                UPDATE profile_state
                SET current_host_id = ?, current_host_name = ?, current_host_platform = ?, updated_at = ?
                WHERE id = 1
                """,
                (current_host_id, current_host_name, current_host_platform, now),
            )
        refreshed = self._storage.conn.execute(
            """
            SELECT id, name, platform, current_host, last_seen_at, created_at, updated_at
            FROM profile_hosts
            WHERE id = ?
            """,
            (current_host_id,),
        ).fetchone()
        return HostPresence(
            id=refreshed["id"],
            name=refreshed["name"],
            platform=refreshed["platform"],
            current_host=bool(refreshed["current_host"]),
            last_seen_at=refreshed["last_seen_at"],
            created_at=refreshed["created_at"],
            updated_at=refreshed["updated_at"],
        )

    # ── remote sync ──────────────────────────────────────────────────────

    def _refresh_from_remote(self, *, best_effort: bool) -> None:
        row = self._state_row()
        if not row["user_id"] or not row["sync_enabled"]:
            return
        try:
            user = self._fetch_current_user()
            self._merge_remote_payload(user)
            self._set_sync_status(error=None)
        except Exception as exc:
            if best_effort:
                self._set_sync_status(error=str(exc))
                return
            raise

    def _sync_to_remote(self, *, best_effort: bool) -> None:
        row = self._state_row()
        if not row["user_id"] or not row["sync_enabled"]:
            return
        try:
            access_token = self._ensure_access_token()
            payload = {
                "data": {
                    _SYNC_METADATA_KEY: self._build_remote_payload(),
                }
            }
            self._supabase_request(
                path="/auth/v1/user",
                anon_key=row["supabase_anon_key"],
                access_token=access_token,
                method="PUT",
                payload=payload,
            )
            self._set_sync_status(error=None)
        except Exception as exc:
            if best_effort:
                self._set_sync_status(error=str(exc))
                return
            raise

    def _build_remote_payload(self) -> dict[str, Any]:
        catalog_rows = self._storage.conn.execute(
            """
            SELECT item_key, kind, item_id, favorite, last_used_at, use_count,
                   last_installed_at, installed_host_ids_json, updated_at
            FROM catalog_preferences
            ORDER BY updated_at DESC
            """
        ).fetchall()
        service_rows = self._storage.conn.execute(
            """
            SELECT id, provider, display_name, mode, portability, status, details_json,
                   last_verified_at, last_host_id, created_at, updated_at
            FROM service_connections
            ORDER BY updated_at DESC
            """
        ).fetchall()
        host_rows = self._storage.conn.execute(
            """
            SELECT id, name, platform, current_host, last_seen_at, created_at, updated_at
            FROM profile_hosts
            ORDER BY updated_at DESC
            """
        ).fetchall()
        return {
            "schema": 1,
            "updated_at": _now_iso(),
            "catalog_preferences": [
                {
                    "item_key": row["item_key"],
                    "kind": row["kind"],
                    "item_id": row["item_id"],
                    "favorite": bool(row["favorite"]),
                    "last_used_at": row["last_used_at"],
                    "use_count": int(row["use_count"] or 0),
                    "last_installed_at": row["last_installed_at"],
                    "installed_host_ids": _json_loads(row["installed_host_ids_json"], []),
                    "updated_at": row["updated_at"],
                }
                for row in catalog_rows
            ],
            "service_connections": [
                {
                    "id": row["id"],
                    "provider": row["provider"],
                    "display_name": row["display_name"],
                    "mode": row["mode"],
                    "portability": row["portability"],
                    "status": row["status"],
                    "details": _json_loads(row["details_json"], {}),
                    "last_verified_at": row["last_verified_at"],
                    "last_host_id": row["last_host_id"],
                    "created_at": row["created_at"],
                    "updated_at": row["updated_at"],
                }
                for row in service_rows
            ],
            "hosts": [
                {
                    "id": row["id"],
                    "name": row["name"],
                    "platform": row["platform"],
                    "current_host": bool(row["current_host"]),
                    "last_seen_at": row["last_seen_at"],
                    "created_at": row["created_at"],
                    "updated_at": row["updated_at"],
                }
                for row in host_rows
            ],
        }

    def _merge_remote_payload(self, user_payload: dict[str, Any]) -> None:
        user = user_payload.get("user") if "user" in user_payload else user_payload
        metadata = user.get("user_metadata") if isinstance(user, dict) else {}
        profile_payload = metadata.get(_SYNC_METADATA_KEY) if isinstance(metadata, dict) else None
        if not isinstance(profile_payload, dict):
            return

        with self._storage.transaction() as conn:
            for item in profile_payload.get("catalog_preferences", []):
                if not isinstance(item, dict):
                    continue
                existing = conn.execute(
                    "SELECT updated_at FROM catalog_preferences WHERE item_key = ?",
                    (item.get("item_key"),),
                ).fetchone()
                remote_updated = str(item.get("updated_at") or "")
                if existing is not None and _timestamp_or_empty(existing["updated_at"]) > remote_updated:
                    continue
                conn.execute(
                    """
                    INSERT INTO catalog_preferences (
                        item_key, kind, item_id, favorite, last_used_at, use_count,
                        last_installed_at, installed_host_ids_json, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(item_key) DO UPDATE SET
                        kind = excluded.kind,
                        item_id = excluded.item_id,
                        favorite = excluded.favorite,
                        last_used_at = excluded.last_used_at,
                        use_count = excluded.use_count,
                        last_installed_at = excluded.last_installed_at,
                        installed_host_ids_json = excluded.installed_host_ids_json,
                        updated_at = excluded.updated_at
                    """,
                    (
                        item.get("item_key"),
                        item.get("kind"),
                        item.get("item_id"),
                        int(bool(item.get("favorite"))),
                        item.get("last_used_at"),
                        int(item.get("use_count") or 0),
                        item.get("last_installed_at"),
                        json.dumps(item.get("installed_host_ids") or []),
                        remote_updated or _now_iso(),
                    ),
                )

            for connection in profile_payload.get("service_connections", []):
                if not isinstance(connection, dict):
                    continue
                existing = conn.execute(
                    "SELECT updated_at FROM service_connections WHERE id = ?",
                    (connection.get("id"),),
                ).fetchone()
                remote_updated = str(connection.get("updated_at") or "")
                if existing is not None and _timestamp_or_empty(existing["updated_at"]) > remote_updated:
                    continue
                conn.execute(
                    """
                    INSERT INTO service_connections (
                        id, provider, display_name, mode, portability, status, details_json,
                        last_verified_at, last_host_id, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        provider = excluded.provider,
                        display_name = excluded.display_name,
                        mode = excluded.mode,
                        portability = excluded.portability,
                        status = excluded.status,
                        details_json = excluded.details_json,
                        last_verified_at = excluded.last_verified_at,
                        last_host_id = excluded.last_host_id,
                        updated_at = excluded.updated_at
                    """,
                    (
                        connection.get("id"),
                        connection.get("provider"),
                        connection.get("display_name") or connection.get("provider") or "Service",
                        connection.get("mode") or ServiceConnectionMode.LOCAL_DETECTED,
                        connection.get("portability") or "local-only",
                        connection.get("status") or ServiceConnectionStatus.DISCONNECTED,
                        json.dumps(connection.get("details") or {}),
                        connection.get("last_verified_at"),
                        connection.get("last_host_id"),
                        connection.get("created_at") or _now_iso(),
                        remote_updated or _now_iso(),
                    ),
                )

            for host in profile_payload.get("hosts", []):
                if not isinstance(host, dict):
                    continue
                conn.execute(
                    """
                    INSERT INTO profile_hosts (id, name, platform, current_host, last_seen_at, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        name = excluded.name,
                        platform = excluded.platform,
                        last_seen_at = excluded.last_seen_at,
                        updated_at = excluded.updated_at
                    """,
                    (
                        host.get("id"),
                        host.get("name") or "Host",
                        host.get("platform") or "unknown",
                        int(bool(host.get("current_host"))),
                        host.get("last_seen_at") or _now_iso(),
                        host.get("created_at") or _now_iso(),
                        host.get("updated_at") or _now_iso(),
                    ),
                )

    # ── Supabase wire helpers ────────────────────────────────────────────

    def _fetch_current_user(self) -> dict[str, Any]:
        row = self._state_row()
        access_token = self._ensure_access_token()
        res = self._supabase_request(
            path="/auth/v1/user",
            anon_key=row["supabase_anon_key"],
            access_token=access_token,
            method="GET",
        )
        return res.payload

    def _ensure_access_token(self) -> str:
        row = self._state_row()
        access_token = _token_plaintext(row["access_token_cipher"], storage=self._storage)
        refresh_token = _token_plaintext(row["refresh_token_cipher"], storage=self._storage)
        expires_at = row["access_token_expires_at"]
        if not access_token or not refresh_token or not expires_at:
            raise invalid("profile", "Sign into your Synapse account first.")
        if utc_now() + timedelta(seconds=_TOKEN_REFRESH_MARGIN_SECONDS) < datetime.fromisoformat(expires_at):
            return access_token

        res = self._supabase_request(
            path="/auth/v1/token?grant_type=refresh_token",
            anon_key=row["supabase_anon_key"],
            method="POST",
            payload={"refresh_token": refresh_token},
        )
        self._store_session_payload(res.payload)
        row = self._state_row()
        renewed = _token_plaintext(row["access_token_cipher"], storage=self._storage)
        if not renewed:
            raise invalid("profile", "Could not refresh the Synapse account session.")
        return renewed

    def _store_session_payload(self, payload: dict[str, Any], *, user: dict[str, Any] | None = None) -> None:
        if not isinstance(payload, dict):
            raise invalid("profile", "The account provider did not return a valid session.")
        access_token = payload.get("access_token")
        refresh_token = payload.get("refresh_token")
        if not isinstance(access_token, str) or not isinstance(refresh_token, str):
            raise invalid("profile", "The account provider did not return login tokens.")

        current_user = user
        if current_user is None:
            current_user = payload.get("user") if isinstance(payload.get("user"), dict) else None
        if current_user is None:
            fetched = self._supabase_request(
                path="/auth/v1/user",
                anon_key=self._state_row()["supabase_anon_key"],
                access_token=access_token,
                method="GET",
            )
            current_user = fetched.payload

        if not isinstance(current_user, dict):
            raise invalid("profile", "The account provider did not return a valid user.")

        app_metadata = current_user.get("app_metadata") if isinstance(current_user.get("app_metadata"), dict) else {}
        user_metadata = current_user.get("user_metadata") if isinstance(current_user.get("user_metadata"), dict) else {}
        identities: list[dict[str, Any]] = []
        for entry in current_user.get("identities") or []:
            if not isinstance(entry, dict):
                continue
            identity_data = entry.get("identity_data") if isinstance(entry.get("identity_data"), dict) else {}
            identities.append(
                {
                    "provider": entry.get("provider"),
                    "email": identity_data.get("email"),
                    "identity_id": entry.get("id"),
                }
            )
        expires_in = int(payload.get("expires_in") or 3600)
        expires_at = to_iso(utc_now() + timedelta(seconds=expires_in))
        display_name = user_metadata.get("display_name") or current_user.get("email") or "Synapse user"
        provider = app_metadata.get("provider")
        now = _now_iso()
        with self._storage.transaction() as conn:
            conn.execute(
                """
                UPDATE profile_state
                SET user_id = ?,
                    email = ?,
                    display_name = ?,
                    avatar_url = ?,
                    provider = ?,
                    provider_identities_json = ?,
                    access_token_cipher = ?,
                    refresh_token_cipher = ?,
                    access_token_expires_at = ?,
                    sync_enabled = 1,
                    updated_at = ?,
                    last_sync_error = NULL
                WHERE id = 1
                """,
                (
                    current_user.get("id"),
                    current_user.get("email"),
                    display_name,
                    user_metadata.get("avatar_url"),
                    provider,
                    json.dumps(identities),
                    _token_cipher(access_token, storage=self._storage),
                    _token_cipher(refresh_token, storage=self._storage),
                    expires_at,
                    now,
                ),
            )

    def _supabase_request(
        self,
        *,
        path: str,
        anon_key: str,
        method: str,
        payload: Any | None = None,
        access_token: str | None = None,
    ) -> _SupabaseResponse:
        base = self._state_row()["supabase_url"]
        if not base:
            raise invalid("profile", "Configure a Supabase project first.")
        url = f"{base}{path}"
        data: bytes | None = None
        headers = {
            "Accept": "application/json",
            "apikey": anon_key,
        }
        if access_token:
            headers["Authorization"] = f"Bearer {access_token}"
        if payload is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(url, data=data, method=method.upper(), headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=_SUPABASE_TIMEOUT_SECONDS) as response:
                raw = response.read().decode("utf-8")
                parsed = json.loads(raw) if raw else {}
                return _SupabaseResponse(status=response.status, payload=parsed)
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            try:
                parsed = json.loads(raw) if raw else {}
            except json.JSONDecodeError:
                parsed = {"message": raw or exc.reason}
            message = parsed.get("msg") or parsed.get("message") or exc.reason
            raise SynapseError(
                code="profile.remote_error",
                message=f"Supabase request failed: {message}",
                status=422,
                details={"status": exc.code, "body": parsed},
            )
        except urllib.error.URLError as exc:
            raise SynapseError(
                code="profile.remote_unreachable",
                message=f"Could not reach Supabase: {exc.reason}",
                status=422,
            )

    # ── internal helpers ────────────────────────────────────────────────

    def _require_supabase_config(self) -> dict[str, str]:
        row = self._state_row()
        if not row["supabase_url"] or not row["supabase_anon_key"]:
            raise invalid(
                "profile",
                "Configure your Supabase URL and anon key in the Profile hub first.",
            )
        return {
            "supabase_url": row["supabase_url"],
            "supabase_anon_key": row["supabase_anon_key"],
        }

    def _state_row(self):
        row = self._storage.conn.execute("SELECT * FROM profile_state WHERE id = 1").fetchone()
        if row is not None:
            return row
        now = _now_iso()
        with self._storage.transaction() as conn:
            conn.execute(
                """
                INSERT INTO profile_state (id, sync_enabled, provider_identities_json, created_at, updated_at)
                VALUES (1, 0, '[]', ?, ?)
                """,
                (now, now),
            )
        return self._storage.conn.execute("SELECT * FROM profile_state WHERE id = 1").fetchone()

    def _set_sync_status(self, *, error: str | None) -> None:
        with self._storage.transaction() as conn:
            conn.execute(
                """
                UPDATE profile_state
                SET last_sync_at = ?, last_sync_error = ?, updated_at = ?
                WHERE id = 1
                """,
                (_now_iso(), error, _now_iso()),
            )

    def _catalog_item(self, item_key: str) -> CatalogPreferenceItem:
        state = self.catalog_state()
        item = next((item for item in state.items if item.item_key == item_key), None)
        if item is None:
            raise invalid("profile", f"No catalog item '{item_key}'.")
        return item

    def _upsert_service_connection(self, connection: ServiceConnection) -> None:
        with self._storage.transaction() as conn:
            conn.execute(
                """
                INSERT INTO service_connections (
                    id, provider, display_name, mode, portability, status, details_json,
                    last_verified_at, last_host_id, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    provider = excluded.provider,
                    display_name = excluded.display_name,
                    mode = excluded.mode,
                    portability = excluded.portability,
                    status = excluded.status,
                    details_json = excluded.details_json,
                    last_verified_at = excluded.last_verified_at,
                    last_host_id = excluded.last_host_id,
                    updated_at = excluded.updated_at
                """,
                (
                    connection.id,
                    connection.provider,
                    connection.display_name,
                    connection.mode,
                    connection.portability,
                    connection.status,
                    json.dumps(connection.details),
                    connection.last_verified_at,
                    connection.last_host_id,
                    connection.created_at,
                    connection.updated_at,
                ),
            )

    def _detect_local_service(self, provider: str, host: HostPresence) -> ServiceConnection:
        now = _now_iso()
        provider_map = {
            "claude-code": {
                "display_name": "Claude Code",
                "binary": "claude",
                "config_paths": [Path.home() / ".claude"],
            },
            "openai-codex": {
                "display_name": "OpenAI Codex",
                "binary": "codex",
                "config_paths": [Path.home() / ".codex", Path.home() / ".config" / "codex"],
            },
            "chatgpt-openai": {
                "display_name": "ChatGPT / OpenAI session",
                "binary": "codex",
                "config_paths": [Path.home() / ".codex", Path.home() / ".config" / "codex"],
            },
            "github-copilot": {
                "display_name": "GitHub Copilot CLI",
                "binary": "copilot",
                "config_paths": [],
            },
        }
        if provider not in provider_map:
            raise invalid("profile", f"Unsupported service provider '{provider}'.")
        meta = provider_map[provider]
        binary_path = shutil.which(meta["binary"])
        config_detected = any(path.exists() for path in meta["config_paths"])
        details: dict[str, Any] = {
            "binary": meta["binary"],
            "binary_path": binary_path,
            "config_detected": config_detected,
            "config_paths": [str(path) for path in meta["config_paths"]],
        }
        status = ServiceConnectionStatus.DISCONNECTED
        if binary_path and config_detected:
            status = ServiceConnectionStatus.READY
            details["message"] = "CLI and local sign-in cache detected on this host."
        elif binary_path:
            status = ServiceConnectionStatus.NEEDS_ATTENTION
            details["message"] = "CLI detected, but no local sign-in cache was found yet."
        elif config_detected:
            status = ServiceConnectionStatus.LOCAL_ONLY
            details["message"] = "Local sign-in cache was found, but the CLI is not on PATH here."
        else:
            details["message"] = "No local sign-in cache or CLI was detected on this host."

        if provider == "github-copilot":
            gh_path = shutil.which("gh")
            details["gh_path"] = gh_path
            if gh_path:
                try:
                    result = subprocess.run(
                        ["gh", "auth", "status"],
                        capture_output=True,
                        text=True,
                        timeout=6,
                        check=False,
                    )
                    details["gh_auth_status"] = result.returncode == 0
                    if result.returncode == 0 and binary_path:
                        status = ServiceConnectionStatus.READY
                    elif result.returncode != 0 and binary_path:
                        status = ServiceConnectionStatus.NEEDS_ATTENTION
                except Exception:
                    details["gh_auth_status"] = False

        return ServiceConnection(
            id=f"local-{provider}",
            provider=provider,
            display_name=meta["display_name"],
            mode=ServiceConnectionMode.LOCAL_DETECTED,
            portability="local-only",
            status=status,
            details=details,
            last_verified_at=now,
            last_host_id=host.id,
            created_at=now,
            updated_at=now,
        )


__all__ = [
    "CatalogPreferenceItem",
    "CatalogPreferenceState",
    "HostPresence",
    "ProfileConfigUpdate",
    "ProfileManager",
    "ProfileSummary",
    "ProviderIdentity",
    "ServiceConnection",
]
