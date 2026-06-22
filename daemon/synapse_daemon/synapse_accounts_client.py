from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any, Literal

from pydantic import BaseModel, Field

from .errors import SynapseError

_DEFAULT_BASE_URL = "http://127.0.0.1:8788"
_REQUEST_TIMEOUT_SECONDS = 12


class LinkedIdentityPayload(BaseModel):
    provider: str
    email: str | None = None
    identity_id: str | None = None


class AccountPayload(BaseModel):
    account_id: str
    username: str
    email: str
    email_verified: bool
    email_verified_at: str | None = None
    display_name: str | None = None
    avatar_url: str | None = None
    account_provider: str | None = None
    linked_identities: list[LinkedIdentityPayload] = Field(default_factory=list)


class SessionPayload(BaseModel):
    access_token: str
    refresh_token: str
    expires_in: int
    account: AccountPayload


class PublicConfigPayload(BaseModel):
    sync_backend: Literal["synapse-account"] = "synapse-account"
    available_providers: list[str] = Field(default_factory=list)


class SyncDocumentPayload(BaseModel):
    document: dict[str, Any]
    updated_at: str


class OAuthStartResponse(BaseModel):
    url: str


class SynapseAccountsClient:
    def __init__(self, base_url: str | None = None) -> None:
        self._base_url = (base_url or os.getenv("SYNAPSE_ACCOUNTS_BASE_URL") or _DEFAULT_BASE_URL).rstrip("/")

    @property
    def base_url(self) -> str:
        return self._base_url

    def public_config(self) -> PublicConfigPayload:
        return PublicConfigPayload.model_validate(self._request(path="/v1/public/config", method="GET"))

    def sign_up(
        self,
        *,
        username: str,
        email: str,
        password: str,
        display_name: str | None,
    ) -> SessionPayload:
        payload = {
            "username": username,
            "email": email,
            "password": password,
            "display_name": display_name,
        }
        return SessionPayload.model_validate(
            self._request(path="/v1/auth/signup", method="POST", payload=payload)
        )

    def sign_in(self, *, login: str, password: str) -> SessionPayload:
        return SessionPayload.model_validate(
            self._request(
                path="/v1/auth/signin",
                method="POST",
                payload={"login": login, "password": password},
            )
        )

    def refresh(self, *, refresh_token: str) -> SessionPayload:
        return SessionPayload.model_validate(
            self._request(
                path="/v1/auth/refresh",
                method="POST",
                payload={"refresh_token": refresh_token},
            )
        )

    def sign_out(self, *, access_token: str | None, refresh_token: str | None) -> None:
        self._request(
            path="/v1/auth/signout",
            method="POST",
            payload={"refresh_token": refresh_token},
            access_token=access_token,
        )

    def get_me(self, *, access_token: str) -> AccountPayload:
        return AccountPayload.model_validate(
            self._request(path="/v1/me", method="GET", access_token=access_token)
        )

    def get_sync_document(self, *, access_token: str) -> SyncDocumentPayload:
        return SyncDocumentPayload.model_validate(
            self._request(path="/v1/sync/document", method="GET", access_token=access_token)
        )

    def put_sync_document(self, *, access_token: str, document: dict[str, Any]) -> SyncDocumentPayload:
        return SyncDocumentPayload.model_validate(
            self._request(
                path="/v1/sync/document",
                method="PUT",
                access_token=access_token,
                payload={"document": document},
            )
        )

    def start_oauth(
        self,
        *,
        provider: str,
        callback_url: str,
        mode: Literal["signin", "link"],
        access_token: str | None = None,
    ) -> OAuthStartResponse:
        return OAuthStartResponse.model_validate(
            self._request(
                path="/v1/oauth/start",
                method="POST",
                access_token=access_token,
                payload={
                    "provider": provider,
                    "callback_url": callback_url,
                    "mode": mode,
                },
            )
        )

    def exchange_oauth(self, *, handoff: str) -> SessionPayload:
        return SessionPayload.model_validate(
            self._request(
                path="/v1/oauth/exchange",
                method="POST",
                payload={"handoff": handoff},
            )
        )

    def unlink_provider(self, *, provider: str, access_token: str) -> AccountPayload:
        return AccountPayload.model_validate(
            self._request(
                path=f"/v1/providers/{provider}",
                method="DELETE",
                access_token=access_token,
            )
        )

    def _request(
        self,
        *,
        path: str,
        method: str,
        payload: Any | None = None,
        access_token: str | None = None,
    ) -> Any:
        url = f"{self._base_url}{path}"
        headers = {"Accept": "application/json"}
        body: bytes | None = None
        if access_token:
            headers["Authorization"] = f"Bearer {access_token}"
        if payload is not None:
            headers["Content-Type"] = "application/json"
            body = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(url, data=body, method=method.upper(), headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=_REQUEST_TIMEOUT_SECONDS) as response:
                raw = response.read().decode("utf-8")
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            try:
                parsed = json.loads(raw) if raw else {}
            except json.JSONDecodeError:
                parsed = {"detail": raw or exc.reason}
            detail = parsed.get("detail") or parsed.get("message") or exc.reason
            raise SynapseError(
                code="profile.remote_error",
                message=f"Synapse Accounts request failed: {detail}",
                status=422,
                details={"status": exc.code, "body": parsed},
            ) from exc
        except urllib.error.URLError as exc:
            raise SynapseError(
                code="profile.remote_unreachable",
                message=f"Could not reach Synapse Accounts: {exc.reason}",
                status=422,
            ) from exc


__all__ = [
    "AccountPayload",
    "OAuthStartResponse",
    "PublicConfigPayload",
    "SessionPayload",
    "SyncDocumentPayload",
    "SynapseAccountsClient",
]

