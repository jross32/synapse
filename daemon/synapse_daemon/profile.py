"""Daemon-owned profile/account/catalog state for the Synapse Profile hub.

Local-first rules:

* Synapse continues to work without any account.
* Local SQLite remains the per-machine source of truth and cache.
* Remote sync is an overlay backed by the first-party Synapse Accounts service.
* Mobile pairing remains separate from account identity.
"""

from __future__ import annotations

import json
import platform as platform_mod
import socket
import subprocess
import time
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from .errors import invalid
from .runtime_resolution import resolve_command
from .secrets import decrypt, encrypt
from .storage import Storage
from .synapse_accounts_client import (
    AccountPayload,
    SessionPayload,
    SynapseAccountsClient,
)
from .time_utils import to_iso, utc_now

_PROFILE_SINGLETON_ID = 1
_TOKEN_REFRESH_MARGIN_SECONDS = 45
_PUBLIC_CONFIG_CACHE_TTL_SECONDS = 300
# When the remote Synapse Accounts server is unreachable, back off this long before
# trying it again. Without this, a down accounts server makes every /profile read
# block the async event loop on a synchronous urllib call, wedging the whole app.
_REMOTE_FAILURE_COOLDOWN_SECONDS = 60
# Local CLI/service detection shells out (`where claude`, `gh auth status`, …) and
# costs ~1-1.5s per profile read. Cache the per-provider result briefly; an explicit
# connect/verify bypasses the cache for a fresh probe.
_LOCAL_DETECT_CACHE_TTL_SECONDS = 45


class ProfileSyncStatus(str):
    LOCAL_ONLY = "local-only"
    CONNECTED = "connected"
    SYNC_DISABLED = "sync-disabled"
    ERROR = "error"


class ServiceConnectionMode(str):
    PORTABLE_OFFICIAL = "portable-official"
    LOCAL_DETECTED = "local-detected"


class ServiceConnectionStatus(str):
    READY = "ready"
    NEEDS_ATTENTION = "needs-attention"
    DISCONNECTED = "disconnected"
    LOCAL_ONLY = "local-only"


class LinkedIdentity(BaseModel):
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


class ProfilePreferences(BaseModel):
    theme: str | None = None
    sidebar_layout: dict[str, Any] | None = None
    sessions_quick_actions_collapsed: bool | None = None
    discover_recent_keys: list[str] = Field(default_factory=list)
    updated_at: str | None = None


class ProfileSummary(BaseModel):
    signed_in: bool
    sync_enabled: bool = False
    sync_status: str
    sync_backend: str
    user_id: str | None = None
    username: str | None = None
    email: str | None = None
    display_name: str | None = None
    avatar_url: str | None = None
    email_verified: bool = False
    account_provider: str | None = None
    linked_identities: list[LinkedIdentity] = Field(default_factory=list)
    current_host: HostPresence
    portable_connection_count: int = 0
    local_connection_count: int = 0
    last_sync_at: str | None = None
    last_sync_error: str | None = None
    available_auth_providers: list[str] = Field(default_factory=lambda: ["native"])
    account_backend_reachable: bool = False
    preferences: ProfilePreferences = Field(default_factory=ProfilePreferences)


class ProfileConfigUpdate(BaseModel):
    sync_enabled: bool | None = None


class ProfilePreferencesUpdate(BaseModel):
    theme: str | None = None
    sidebar_layout: dict[str, Any] | None = None
    sessions_quick_actions_collapsed: bool | None = None
    discover_recent_keys: list[str] | None = None


def _now_iso() -> str:
    return to_iso(utc_now())


def _json_loads(raw: str | None, default: Any) -> Any:
    if not raw:
        return default
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return default


def _token_cipher(value: str | None, *, storage: Storage) -> bytes | None:
    if not value:
        return None
    return encrypt(value, data_dir=storage.data_dir)


def _token_plaintext(value: bytes | None, *, storage: Storage) -> str | None:
    if not value:
        return None
    return decrypt(value, data_dir=storage.data_dir)


def _timestamp_or_empty(value: str | None) -> str:
    return value or ""


class ProfileManager:
    """Owns local profile state, optional Synapse Accounts auth, and sync."""

    def __init__(
        self,
        storage: Storage,
        accounts_client: SynapseAccountsClient | None = None,
    ) -> None:
        self._storage = storage
        self._accounts = accounts_client or SynapseAccountsClient()
        self._cached_auth_providers: list[str] = ["native"]
        self._cached_auth_providers_at: datetime | None = None
        self._account_backend_reachable = False
        # Circuit breaker for the remote accounts server (see
        # _REMOTE_FAILURE_COOLDOWN_SECONDS). monotonic() deadline; 0 = closed.
        self._remote_cooldown_until: float = 0.0
        # Short-TTL cache of local CLI/service detection, keyed "provider:host_id"
        # -> (monotonic_stamp, ServiceConnection). See _LOCAL_DETECT_CACHE_TTL_SECONDS.
        self._local_detect_cache: dict[str, tuple[float, ServiceConnection]] = {}

    # ── public summary / preferences ───────────────────────────────────

    def summary(self, *, refresh_remote: bool = True) -> ProfileSummary:
        current_host = self.ensure_current_host()
        row = self._state_row()
        if refresh_remote and row["user_id"]:
            self._refresh_from_remote(best_effort=True)
            row = self._state_row()
        connections = self.list_service_connections(refresh_remote=False, detect_local=False)
        portable_count = len(
            [c for c in connections if c.mode == ServiceConnectionMode.PORTABLE_OFFICIAL]
        )
        local_count = len(
            [c for c in connections if c.mode == ServiceConnectionMode.LOCAL_DETECTED]
        )
        signed_in = bool(row["user_id"])
        if row["last_sync_error"]:
            sync_status = ProfileSyncStatus.ERROR
        elif signed_in and row["sync_enabled"]:
            sync_status = ProfileSyncStatus.CONNECTED
        elif signed_in and not row["sync_enabled"]:
            sync_status = ProfileSyncStatus.SYNC_DISABLED
        else:
            sync_status = ProfileSyncStatus.LOCAL_ONLY
        return ProfileSummary(
            signed_in=signed_in,
            sync_enabled=bool(row["sync_enabled"]),
            sync_status=sync_status,
            sync_backend="synapse-account" if signed_in else "local-only",
            user_id=row["user_id"],
            username=row["username"],
            email=row["email"],
            display_name=row["display_name"],
            avatar_url=row["avatar_url"],
            email_verified=bool(row["email_verified_at"]),
            account_provider=row["provider"],
            linked_identities=[
                LinkedIdentity.model_validate(item)
                for item in _json_loads(row["provider_identities_json"], [])
            ],
            current_host=current_host,
            portable_connection_count=portable_count,
            local_connection_count=local_count,
            last_sync_at=row["last_sync_at"],
            last_sync_error=row["last_sync_error"],
            available_auth_providers=self._available_auth_providers(best_effort=True),
            account_backend_reachable=self._account_backend_reachable,
            preferences=self.preferences(),
        )

    def configure(self, payload: ProfileConfigUpdate) -> ProfileSummary:
        row = self._state_row()
        next_sync = row["sync_enabled"] if payload.sync_enabled is None else int(payload.sync_enabled)
        with self._storage.transaction() as conn:
            conn.execute(
                """
                UPDATE profile_state
                SET sync_enabled = ?, updated_at = ?, last_sync_error = NULL
                WHERE id = 1
                """,
                (next_sync, _now_iso()),
            )
        if next_sync and row["user_id"]:
            self._sync_to_remote(best_effort=True)
        return self.summary(refresh_remote=False)

    def preferences(self) -> ProfilePreferences:
        row = self._state_row()
        payload = _json_loads(row["preferences_json"], {})
        if not isinstance(payload, dict):
            payload = {}
        payload.setdefault("updated_at", row["preferences_updated_at"])
        return ProfilePreferences.model_validate(payload)

    def update_preferences(self, payload: ProfilePreferencesUpdate) -> ProfilePreferences:
        current = self.preferences().model_dump()
        if payload.theme is not None:
            current["theme"] = payload.theme
        if payload.sidebar_layout is not None:
            current["sidebar_layout"] = payload.sidebar_layout
        if payload.sessions_quick_actions_collapsed is not None:
            current["sessions_quick_actions_collapsed"] = payload.sessions_quick_actions_collapsed
        if payload.discover_recent_keys is not None:
            current["discover_recent_keys"] = payload.discover_recent_keys
        current["updated_at"] = _now_iso()
        with self._storage.transaction() as conn:
            conn.execute(
                """
                UPDATE profile_state
                SET preferences_json = ?, preferences_updated_at = ?, updated_at = ?
                WHERE id = 1
                """,
                (
                    json.dumps(current),
                    current["updated_at"],
                    current["updated_at"],
                ),
            )
        self._sync_to_remote(best_effort=True)
        return self.preferences()

    # ── auth lifecycle ─────────────────────────────────────────────────

    def sign_up_password(
        self,
        *,
        username: str,
        email: str,
        password: str,
        display_name: str | None = None,
    ) -> tuple[ProfileSummary, str | None]:
        session = self._accounts.sign_up(
            username=username,
            email=email,
            password=password,
            display_name=display_name,
        )
        self._store_session_payload(session)
        self._sync_to_remote(best_effort=True)
        return self.summary(refresh_remote=False), None

    def sign_in_password(self, *, login: str, password: str) -> ProfileSummary:
        session = self._accounts.sign_in(login=login, password=password)
        self._store_session_payload(session)
        self._refresh_from_remote(best_effort=True)
        return self.summary(refresh_remote=False)

    def start_oauth(self, *, provider: str, redirect_to: str, mode: str = "signin") -> str:
        access_token = self._ensure_access_token() if mode == "link" else None
        response = self._accounts.start_oauth(
            provider=provider,
            callback_url=redirect_to,
            mode="link" if mode == "link" else "signin",
            access_token=access_token,
        )
        return response.url

    def complete_oauth(self, *, handoff: str) -> ProfileSummary:
        session = self._accounts.exchange_oauth(handoff=handoff)
        self._store_session_payload(session)
        self._refresh_from_remote(best_effort=True)
        return self.summary(refresh_remote=False)

    def unlink_provider(self, *, provider: str) -> ProfileSummary:
        access_token = self._ensure_access_token()
        account = self._accounts.unlink_provider(provider=provider, access_token=access_token)
        self._store_account_payload(account)
        self._sync_to_remote(best_effort=True)
        return self.summary(refresh_remote=False)

    def sign_out(self) -> ProfileSummary:
        row = self._state_row()
        access_token = _token_plaintext(row["access_token_cipher"], storage=self._storage)
        refresh_token = _token_plaintext(row["refresh_token_cipher"], storage=self._storage)
        if access_token or refresh_token:
            try:
                self._accounts.sign_out(
                    access_token=access_token,
                    refresh_token=refresh_token,
                )
            except Exception:
                pass
        with self._storage.transaction() as conn:
            conn.execute(
                """
                UPDATE profile_state
                SET user_id = NULL,
                    username = NULL,
                    email = NULL,
                    email_verified_at = NULL,
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

    # ── catalog state ──────────────────────────────────────────────────

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
            installed_here = row["kind"] in {"tool", "bundle"} and current_host.id in installed_host_ids
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
            SELECT favorite FROM catalog_preferences WHERE item_key = ?
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

    def record_catalog_install(self, *, kind: str, item_id: str) -> None:
        host = self.ensure_current_host()
        item_key = f"{kind}:{item_id}"
        now = _now_iso()
        row = self._storage.conn.execute(
            """
            SELECT installed_host_ids_json FROM catalog_preferences WHERE item_key = ?
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
                    ) VALUES (?, ?, ?, 0, 0, ?, ?, ?)
                    """,
                    (item_key, kind, item_id, now, json.dumps(sorted(host_ids)), now),
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

    def record_catalog_uninstall(self, *, kind: str, item_id: str) -> None:
        host = self.ensure_current_host()
        item_key = f"{kind}:{item_id}"
        row = self._storage.conn.execute(
            "SELECT installed_host_ids_json FROM catalog_preferences WHERE item_key = ?",
            (item_key,),
        ).fetchone()
        if row is None:
            return
        host_ids = set(_json_loads(row["installed_host_ids_json"], []))
        host_ids.discard(host.id)
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

    def record_tool_install(self, *, tool_id: str) -> None:
        self.record_catalog_install(kind="tool", item_id=tool_id)

    def record_tool_uninstall(self, *, tool_id: str) -> None:
        self.record_catalog_uninstall(kind="tool", item_id=tool_id)

    # ── services / hosts ───────────────────────────────────────────────

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

    def list_service_connections(
        self,
        *,
        refresh_remote: bool = True,
        detect_local: bool = True,
    ) -> list[ServiceConnection]:
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
        if detect_local:
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
            LinkedIdentity.model_validate(item)
            for item in _json_loads(self._state_row()["provider_identities_json"], [])
        ]
        for identity in identities:
            if identity.provider not in {"google", "github"}:
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
                    "message": "Linked through your Synapse account.",
                },
                last_verified_at=now,
                last_host_id=host.id,
                created_at=existing.created_at if existing else now,
                updated_at=now,
            )
            out[identity.provider] = portable

        return sorted(
            out.values(),
            key=lambda item: (item.mode != ServiceConnectionMode.PORTABLE_OFFICIAL, item.display_name.lower()),
        )

    def connect_service(self, *, provider: str) -> ServiceConnection:
        host = self.ensure_current_host()
        if provider in {"github", "google"}:
            identities = [
                LinkedIdentity.model_validate(item)
                for item in _json_loads(self._state_row()["provider_identities_json"], [])
            ]
            identity = next((item for item in identities if item.provider == provider), None)
            if identity is None:
                raise invalid(
                    "profile",
                    f"Link {provider.title()} through your Synapse account first.",
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
                    "message": "Linked through your Synapse account.",
                },
                last_verified_at=_now_iso(),
                last_host_id=host.id,
                created_at=_now_iso(),
                updated_at=_now_iso(),
            )
        else:
            # Explicit connect/verify -> bypass the detection cache for a fresh probe.
            connection = self._detect_local_service(provider, host, use_cache=False)
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

    # ── remote sync ─────────────────────────────────────────────────────

    def _refresh_from_remote(self, *, best_effort: bool) -> None:
        row = self._state_row()
        if not row["user_id"]:
            return
        if best_effort and time.monotonic() < self._remote_cooldown_until:
            # Accounts server recently failed -- serve local state instead of
            # blocking the event loop on another doomed request.
            return
        try:
            access_token = self._ensure_access_token()
            account = self._accounts.get_me(access_token=access_token)
            self._store_account_payload(account)
            if row["sync_enabled"]:
                document = self._accounts.get_sync_document(access_token=access_token)
                self._merge_remote_payload(document.document)
            self._set_sync_status(error=None)
            self._remote_cooldown_until = 0.0
        except Exception as exc:
            if best_effort:
                self._remote_cooldown_until = time.monotonic() + _REMOTE_FAILURE_COOLDOWN_SECONDS
                self._set_sync_status(error=str(exc))
                return
            raise

    def _sync_to_remote(self, *, best_effort: bool) -> None:
        row = self._state_row()
        if not row["user_id"] or not row["sync_enabled"]:
            return
        if best_effort and time.monotonic() < self._remote_cooldown_until:
            return
        try:
            access_token = self._ensure_access_token()
            document = self._build_remote_payload()
            self._accounts.put_sync_document(access_token=access_token, document=document)
            self._set_sync_status(error=None)
            self._remote_cooldown_until = 0.0
        except Exception as exc:
            if best_effort:
                self._remote_cooldown_until = time.monotonic() + _REMOTE_FAILURE_COOLDOWN_SECONDS
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
            "schema": 2,
            "updated_at": _now_iso(),
            "preferences": self.preferences().model_dump(mode="json"),
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

    def _merge_remote_payload(self, document: dict[str, Any]) -> None:
        if not isinstance(document, dict):
            return
        preferences_payload = document.get("preferences")
        with self._storage.transaction() as conn:
            if isinstance(preferences_payload, dict):
                local_updated = _timestamp_or_empty(self._state_row()["preferences_updated_at"])
                remote_updated = str(preferences_payload.get("updated_at") or "")
                if remote_updated and local_updated <= remote_updated:
                    conn.execute(
                        """
                        UPDATE profile_state
                        SET preferences_json = ?, preferences_updated_at = ?, updated_at = ?
                        WHERE id = 1
                        """,
                        (json.dumps(preferences_payload), remote_updated, _now_iso()),
                    )

            for item in document.get("catalog_preferences", []):
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

            for connection in document.get("service_connections", []):
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

            for host in document.get("hosts", []):
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

    # ── account transport helpers ──────────────────────────────────────

    def _ensure_access_token(self) -> str:
        row = self._state_row()
        access_token = _token_plaintext(row["access_token_cipher"], storage=self._storage)
        refresh_token = _token_plaintext(row["refresh_token_cipher"], storage=self._storage)
        expires_at = row["access_token_expires_at"]
        if not access_token or not refresh_token or not expires_at:
            raise invalid("profile", "Sign into your Synapse account first.")
        if utc_now() + timedelta(seconds=_TOKEN_REFRESH_MARGIN_SECONDS) < datetime.fromisoformat(expires_at):
            return access_token

        session = self._accounts.refresh(refresh_token=refresh_token)
        self._store_session_payload(session)
        row = self._state_row()
        renewed = _token_plaintext(row["access_token_cipher"], storage=self._storage)
        if not renewed:
            raise invalid("profile", "Could not refresh the Synapse account session.")
        return renewed

    def _store_session_payload(self, payload: SessionPayload) -> None:
        expires_at = to_iso(utc_now() + timedelta(seconds=int(payload.expires_in or 900)))
        self._store_account_payload(
            payload.account,
            access_token=payload.access_token,
            refresh_token=payload.refresh_token,
            expires_at=expires_at,
        )

    def _store_account_payload(
        self,
        account: AccountPayload,
        *,
        access_token: str | None = None,
        refresh_token: str | None = None,
        expires_at: str | None = None,
    ) -> None:
        now = _now_iso()
        existing = self._state_row()
        with self._storage.transaction() as conn:
            conn.execute(
                """
                UPDATE profile_state
                SET user_id = ?,
                    username = ?,
                    email = ?,
                    email_verified_at = ?,
                    display_name = ?,
                    avatar_url = ?,
                    provider = ?,
                    provider_identities_json = ?,
                    access_token_cipher = COALESCE(?, access_token_cipher),
                    refresh_token_cipher = COALESCE(?, refresh_token_cipher),
                    access_token_expires_at = COALESCE(?, access_token_expires_at),
                    sync_enabled = CASE WHEN user_id IS NULL THEN 1 ELSE sync_enabled END,
                    updated_at = ?,
                    last_sync_error = NULL
                WHERE id = 1
                """,
                (
                    account.account_id,
                    account.username,
                    account.email,
                    account.email_verified_at if account.email_verified else None,
                    account.display_name,
                    account.avatar_url,
                    account.account_provider,
                    json.dumps([identity.model_dump(mode="json") for identity in account.linked_identities]),
                    _token_cipher(access_token, storage=self._storage) if access_token else None,
                    _token_cipher(refresh_token, storage=self._storage) if refresh_token else None,
                    expires_at,
                    now,
                ),
            )
            if existing["user_id"] is None:
                conn.execute(
                    "UPDATE profile_state SET sync_enabled = 1 WHERE id = 1"
                )

    def _available_auth_providers(self, *, best_effort: bool) -> list[str]:
        now = utc_now()
        if (
            self._cached_auth_providers_at is not None
            and now - self._cached_auth_providers_at < timedelta(seconds=_PUBLIC_CONFIG_CACHE_TTL_SECONDS)
        ):
            return self._cached_auth_providers
        if best_effort and time.monotonic() < self._remote_cooldown_until:
            # Same circuit breaker as _refresh_from_remote: the accounts server
            # recently failed, so skip the (slow, blocking) probe on routine polls
            # and serve the last-known providers. This keeps /profile fast when the
            # accounts server is offline. An explicit refresh (best_effort=False)
            # still re-probes immediately so a just-started server is picked up.
            self._account_backend_reachable = False
            return self._cached_auth_providers
        try:
            config = self._accounts.public_config()
            self._cached_auth_providers = config.available_providers or ["native"]
            self._cached_auth_providers_at = now
            self._account_backend_reachable = True
            self._remote_cooldown_until = 0.0
            return self._cached_auth_providers
        except Exception:
            # No accounts backend reachable -> sign-in is unavailable. Keep the
            # "native" default in the providers list (back-compat) but flag the
            # backend unreachable so the UI shows an honest "sync is optional"
            # state instead of a sign-in form that always errors. Deliberately
            # do NOT stamp _cached_auth_providers_at here: a Refresh (best_effort=
            # False) right after the user starts the accounts service should
            # re-probe and pick it up immediately rather than wait out the TTL.
            self._account_backend_reachable = False
            self._remote_cooldown_until = time.monotonic() + _REMOTE_FAILURE_COOLDOWN_SECONDS
            if best_effort:
                return self._cached_auth_providers
            raise

    # ── internal helpers ───────────────────────────────────────────────

    def _state_row(self):
        row = self._storage.conn.execute("SELECT * FROM profile_state WHERE id = 1").fetchone()
        if row is not None:
            return row
        now = _now_iso()
        with self._storage.transaction() as conn:
            conn.execute(
                """
                INSERT INTO profile_state (
                    id,
                    sync_enabled,
                    provider_identities_json,
                    preferences_json,
                    created_at,
                    updated_at
                ) VALUES (1, 0, '[]', '{}', ?, ?)
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

    def _detect_local_service(
        self, provider: str, host: HostPresence, *, use_cache: bool = True
    ) -> ServiceConnection:
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
        cache_key = f"{provider}:{host.id}"
        if use_cache:
            cached = self._local_detect_cache.get(cache_key)
            if cached is not None and time.monotonic() - cached[0] < _LOCAL_DETECT_CACHE_TTL_SECONDS:
                return cached[1]
        binary_path = resolve_command(meta["binary"])
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
            gh_path = resolve_command("gh")
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

        connection = ServiceConnection(
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
        self._local_detect_cache[cache_key] = (time.monotonic(), connection)
        return connection


__all__ = [
    "CatalogPreferenceItem",
    "CatalogPreferenceState",
    "HostPresence",
    "LinkedIdentity",
    "ProfileConfigUpdate",
    "ProfileManager",
    "ProfilePreferences",
    "ProfilePreferencesUpdate",
    "ProfileSummary",
    "ServiceConnection",
]
