from __future__ import annotations

import json
import re
import secrets
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import UTC, datetime, timedelta
from html import escape
from typing import Any, Literal

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import Depends, FastAPI, Header, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from .config import AccountsSettings, load_settings
from .db import (
    Account,
    AuthAuditEvent,
    EmailVerificationToken,
    LinkedIdentity,
    OAuthHandoff,
    OAuthState,
    PasswordResetToken,
    RefreshSession,
    SyncDocument,
    build_session_factory,
    session_scope,
    utc_now,
)

_HASHER = PasswordHasher()
_USERNAME_RE = re.compile(r"[^a-z0-9_]+")


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


class SignUpRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=32)
    email: str = Field(..., min_length=3, max_length=320)
    password: str = Field(..., min_length=8, max_length=256)
    display_name: str | None = Field(default=None, max_length=120)


class SignInRequest(BaseModel):
    login: str = Field(..., min_length=3, max_length=320)
    password: str = Field(..., min_length=8, max_length=256)


class SignOutRequest(BaseModel):
    refresh_token: str | None = None


class OAuthStartRequest(BaseModel):
    provider: str
    callback_url: str
    mode: Literal["signin", "link"] = "signin"


class OAuthStartResponse(BaseModel):
    url: str


class OAuthExchangeRequest(BaseModel):
    handoff: str


class PutSyncDocumentRequest(BaseModel):
    document: dict[str, Any]


class TokenIssue(BaseModel):
    access_token: str
    refresh_token: str
    expires_in: int


class SocialIdentity(BaseModel):
    provider: str
    subject: str
    email: str | None = None
    display_name: str | None = None
    avatar_url: str | None = None
    email_verified: bool = False


def _now() -> datetime:
    return datetime.now(UTC)


def _utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _hash_token(value: str) -> str:
    import hashlib

    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _normalize_email(value: str) -> str:
    return value.strip().lower()


def _normalize_username(value: str) -> str:
    collapsed = _USERNAME_RE.sub("_", value.strip().lower())
    collapsed = collapsed.strip("_")
    return collapsed[:32] or "synapse_user"


def _slug_base(value: str) -> str:
    if "@" in value:
        value = value.split("@", 1)[0]
    return _normalize_username(value)


def _serialize_identity(identity: LinkedIdentity) -> LinkedIdentityPayload:
    return LinkedIdentityPayload(
        provider=identity.provider,
        email=identity.email,
        identity_id=identity.provider_subject,
    )


def _serialize_account(account: Account) -> AccountPayload:
    linked = sorted(account.identities, key=lambda item: (item.provider, item.created_at))
    return AccountPayload(
        account_id=account.id,
        username=account.username,
        email=account.email,
        email_verified=account.email_verified_at is not None,
        email_verified_at=_iso(account.email_verified_at),
        display_name=account.display_name,
        avatar_url=account.avatar_url,
        account_provider=account.last_sign_in_provider or ("native" if account.password_hash else None),
        linked_identities=[_serialize_identity(identity) for identity in linked],
    )


def _callback_page(*, ok: bool, title: str, message: str) -> HTMLResponse:
    tone = "#22c55e" if ok else "#ef4444"
    body = f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>{escape(title)}</title>
    <style>
      :root {{
        color-scheme: dark;
        --bg: #07110c;
        --panel: rgba(13, 28, 20, 0.96);
        --border: rgba(57, 94, 73, 0.8);
        --text: #e6f4ec;
        --muted: #9ec6ad;
        --accent: {tone};
      }}
      body {{
        margin: 0;
        min-height: 100vh;
        display: grid;
        place-items: center;
        background:
          radial-gradient(circle at top, rgba(34, 197, 94, 0.12), transparent 44%),
          linear-gradient(180deg, #020705 0%, var(--bg) 100%);
        color: var(--text);
        font-family: "Segoe UI", system-ui, sans-serif;
      }}
      .panel {{
        width: min(92vw, 480px);
        border: 1px solid var(--border);
        border-radius: 28px;
        padding: 28px;
        background: var(--panel);
        box-shadow: 0 28px 80px rgba(0, 0, 0, 0.42);
      }}
      .badge {{
        display: inline-flex;
        align-items: center;
        gap: 10px;
        font-size: 12px;
        text-transform: uppercase;
        letter-spacing: 0.16em;
        color: var(--muted);
      }}
      .dot {{
        width: 10px;
        height: 10px;
        border-radius: 999px;
        background: var(--accent);
      }}
      h1 {{
        margin: 18px 0 8px;
        font-size: 28px;
        line-height: 1.1;
      }}
      p {{
        margin: 0;
        color: var(--muted);
        line-height: 1.55;
      }}
    </style>
  </head>
  <body>
    <section class="panel">
      <div class="badge"><span class="dot"></span>Synapse Accounts</div>
      <h1>{escape(title)}</h1>
      <p>{escape(message)}</p>
    </section>
  </body>
</html>"""
    return HTMLResponse(body)


def issue_reserved_token(
    db: Session,
    model: type[EmailVerificationToken] | type[PasswordResetToken],
    *,
    account_id: str,
    expires_at: datetime,
) -> str:
    token = secrets.token_urlsafe(32)
    record = model(
        id=str(uuid.uuid4()),
        account_id=account_id,
        token_hash=_hash_token(token),
        expires_at=expires_at,
    )
    db.add(record)
    return token


def consume_reserved_token(
    db: Session,
    model: type[EmailVerificationToken] | type[PasswordResetToken],
    *,
    token: str,
) -> str:
    record = db.scalar(select(model).where(model.token_hash == _hash_token(token)))
    if record is None:
        raise HTTPException(status_code=404, detail="Token not found.")
    if record.consumed_at is not None:
        raise HTTPException(status_code=409, detail="Token already consumed.")
    if _utc(record.expires_at) <= _now():
        raise HTTPException(status_code=410, detail="Token expired.")
    record.consumed_at = _now()
    return record.account_id


class AccountsService:
    def __init__(self, settings: AccountsSettings) -> None:
        self.settings = settings
        self.session_factory = build_session_factory(settings.database_url)

    def public_config(self) -> PublicConfigPayload:
        providers = ["native"]
        if self.settings.google_client_id and self.settings.google_client_secret:
            providers.append("google")
        return PublicConfigPayload(available_providers=providers)

    def get_account_for_access_token(self, db: Session, access_token: str) -> Account:
        session_row = db.scalar(
            select(RefreshSession).where(
                RefreshSession.access_token_hash == _hash_token(access_token)
            )
        )
        if session_row is None or session_row.revoked_at is not None or _utc(session_row.access_expires_at) <= _now():
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired.")
        account = db.scalar(select(Account).where(Account.id == session_row.account_id))
        if account is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Account missing.")
        return account

    def sign_up(self, db: Session, payload: SignUpRequest) -> SessionPayload:
        normalized_email = _normalize_email(payload.email)
        normalized_username = _normalize_username(payload.username)
        existing_email = db.scalar(select(Account).where(Account.email_normalized == normalized_email))
        if existing_email is not None:
            raise HTTPException(status_code=409, detail="That email is already in use.")
        existing_username = db.scalar(
            select(Account).where(Account.username_normalized == normalized_username)
        )
        if existing_username is not None:
            raise HTTPException(status_code=409, detail="That username is already taken.")

        now = _now()
        account = Account(
            id=str(uuid.uuid4()),
            username=payload.username.strip(),
            username_normalized=normalized_username,
            email=payload.email.strip(),
            email_normalized=normalized_email,
            password_hash=_HASHER.hash(payload.password),
            display_name=payload.display_name.strip() if payload.display_name else payload.username.strip(),
            last_sign_in_provider="native",
            created_at=now,
            updated_at=now,
        )
        db.add(account)
        self._log_event(db, account_id=account.id, event_kind="account.signup", provider="native")
        return self._issue_session(db, account, provider="native")

    def sign_in(self, db: Session, payload: SignInRequest) -> SessionPayload:
        login = payload.login.strip()
        normalized = _normalize_email(login) if "@" in login else _normalize_username(login)
        if "@" in login:
            account = db.scalar(select(Account).where(Account.email_normalized == normalized))
        else:
            account = db.scalar(select(Account).where(Account.username_normalized == normalized))
        if account is None or not account.password_hash:
            raise HTTPException(status_code=401, detail="Invalid username/email or password.")
        try:
            _HASHER.verify(account.password_hash, payload.password)
        except VerifyMismatchError as exc:
            raise HTTPException(status_code=401, detail="Invalid username/email or password.") from exc
        account.last_sign_in_provider = "native"
        account.updated_at = _now()
        self._log_event(db, account_id=account.id, event_kind="account.signin", provider="native")
        return self._issue_session(db, account, provider="native")

    def refresh(self, db: Session, refresh_token: str) -> SessionPayload:
        session_row = db.scalar(
            select(RefreshSession).where(
                RefreshSession.refresh_token_hash == _hash_token(refresh_token)
            )
        )
        if session_row is None or session_row.revoked_at is not None:
            raise HTTPException(status_code=401, detail="Refresh session is no longer valid.")
        if _utc(session_row.refresh_expires_at) <= _now():
            session_row.revoked_at = _now()
            raise HTTPException(status_code=401, detail="Refresh session expired.")
        account = db.scalar(select(Account).where(Account.id == session_row.account_id))
        if account is None:
            raise HTTPException(status_code=401, detail="Account missing.")
        session_row.revoked_at = _now()
        session_row.updated_at = _now()
        self._log_event(db, account_id=account.id, event_kind="account.refresh", provider=account.last_sign_in_provider)
        return self._issue_session(
            db,
            account,
            provider=account.last_sign_in_provider or "native",
            rotated_from=session_row.id,
        )

    def sign_out(self, db: Session, *, refresh_token: str | None, access_token: str | None) -> None:
        revoked_any = False
        if refresh_token:
            row = db.scalar(
                select(RefreshSession).where(
                    RefreshSession.refresh_token_hash == _hash_token(refresh_token)
                )
            )
            if row is not None and row.revoked_at is None:
                row.revoked_at = _now()
                row.updated_at = _now()
                revoked_any = True
                self._log_event(db, account_id=row.account_id, event_kind="account.signout", provider=None)
        elif access_token:
            row = db.scalar(
                select(RefreshSession).where(
                    RefreshSession.access_token_hash == _hash_token(access_token)
                )
            )
            if row is not None and row.revoked_at is None:
                row.revoked_at = _now()
                row.updated_at = _now()
                revoked_any = True
                self._log_event(db, account_id=row.account_id, event_kind="account.signout", provider=None)
        if not revoked_any:
            raise HTTPException(status_code=404, detail="No active session to sign out.")

    def get_sync_document(self, db: Session, account: Account) -> SyncDocumentPayload:
        document = db.scalar(select(SyncDocument).where(SyncDocument.account_id == account.id))
        if document is None:
            document = SyncDocument(account_id=account.id, document_json="{}")
            db.add(document)
            db.flush()
        return SyncDocumentPayload(
            document=json.loads(document.document_json or "{}"),
            updated_at=_iso(document.updated_at) or _iso(document.created_at) or _iso(_now()) or "",
        )

    def put_sync_document(self, db: Session, account: Account, document: dict[str, Any]) -> SyncDocumentPayload:
        row = db.scalar(select(SyncDocument).where(SyncDocument.account_id == account.id))
        now = _now()
        if row is None:
            row = SyncDocument(
                account_id=account.id,
                document_json=json.dumps(document),
                created_at=now,
                updated_at=now,
            )
            db.add(row)
        else:
            row.document_json = json.dumps(document)
            row.updated_at = now
        self._log_event(db, account_id=account.id, event_kind="sync.updated", provider=None)
        return SyncDocumentPayload(document=document, updated_at=_iso(now) or "")

    def start_oauth(
        self,
        db: Session,
        *,
        provider: str,
        callback_url: str,
        mode: Literal["signin", "link"],
        current_account: Account | None,
    ) -> OAuthStartResponse:
        if provider != "google":
            raise HTTPException(status_code=400, detail=f"Unsupported provider '{provider}'.")
        if not (self.settings.google_client_id and self.settings.google_client_secret):
            raise HTTPException(status_code=503, detail="Google sign-in is not configured on the Synapse Accounts server.")
        if mode == "link" and current_account is None:
            raise HTTPException(status_code=401, detail="Sign into Synapse before linking Google.")

        state = secrets.token_urlsafe(24)
        expires_at = _now() + timedelta(seconds=self.settings.oauth_state_ttl_seconds)
        db.add(
            OAuthState(
                state=state,
                provider=provider,
                mode=mode,
                callback_url=callback_url,
                link_account_id=current_account.id if current_account else None,
                expires_at=expires_at,
            )
        )
        query = urllib.parse.urlencode(
            {
                "client_id": self.settings.google_client_id,
                "redirect_uri": f"{self.settings.public_base_url}/v1/oauth/google/callback",
                "response_type": "code",
                "scope": "openid email profile",
                "access_type": "offline",
                "prompt": "select_account",
                "state": state,
            }
        )
        return OAuthStartResponse(url=f"https://accounts.google.com/o/oauth2/v2/auth?{query}")

    def exchange_handoff(self, db: Session, handoff: str) -> SessionPayload:
        row = db.scalar(select(OAuthHandoff).where(OAuthHandoff.handoff_code == handoff))
        if row is None:
            raise HTTPException(status_code=404, detail="That handoff is no longer valid.")
        if row.used_at is not None:
            raise HTTPException(status_code=409, detail="That handoff was already used.")
        if _utc(row.expires_at) <= _now():
            raise HTTPException(status_code=410, detail="That handoff expired.")
        row.used_at = _now()
        account = db.scalar(select(Account).where(Account.id == row.account_id))
        if account is None:
            raise HTTPException(status_code=404, detail="Account missing for this handoff.")
        self._log_event(db, account_id=account.id, event_kind="account.oauth.exchange", provider=row.provider)
        return self._issue_session(db, account, provider=row.provider)

    def finalize_google_callback(
        self,
        db: Session,
        *,
        state: str,
        code: str,
    ) -> str:
        state_row = db.scalar(select(OAuthState).where(OAuthState.state == state))
        if state_row is None:
            raise HTTPException(status_code=404, detail="That Google sign-in attempt is no longer valid.")
        if state_row.used_at is not None:
            raise HTTPException(status_code=409, detail="That Google sign-in attempt was already used.")
        if _utc(state_row.expires_at) <= _now():
            raise HTTPException(status_code=410, detail="That Google sign-in attempt expired.")
        social = self._exchange_google_code(code)
        account = self._resolve_social_account(
            db,
            provider="google",
            state_row=state_row,
            social=social,
        )
        state_row.used_at = _now()
        handoff = secrets.token_urlsafe(32)
        db.add(
            OAuthHandoff(
                handoff_code=handoff,
                account_id=account.id,
                provider="google",
                expires_at=_now() + timedelta(seconds=self.settings.oauth_handoff_ttl_seconds),
            )
        )
        self._log_event(db, account_id=account.id, event_kind="account.oauth.google", provider="google")
        return f"{state_row.callback_url}?handoff={urllib.parse.quote(handoff)}"

    def unlink_provider(self, db: Session, *, account: Account, provider: str) -> AccountPayload:
        identity = db.scalar(
            select(LinkedIdentity).where(
                LinkedIdentity.account_id == account.id,
                LinkedIdentity.provider == provider,
            )
        )
        if identity is None:
            raise HTTPException(status_code=404, detail=f"No linked {provider.title()} identity found.")
        identities = list(account.identities)
        if account.password_hash is None and len(identities) <= 1:
            raise HTTPException(
                status_code=409,
                detail="Add a native password before removing the only linked sign-in provider.",
            )
        db.delete(identity)
        account.updated_at = _now()
        self._log_event(db, account_id=account.id, event_kind="account.unlink_provider", provider=provider)
        db.flush()
        db.refresh(account)
        return _serialize_account(account)

    def _issue_session(
        self,
        db: Session,
        account: Account,
        *,
        provider: str,
        rotated_from: str | None = None,
    ) -> SessionPayload:
        access_token = secrets.token_urlsafe(32)
        refresh_token = secrets.token_urlsafe(48)
        now = _now()
        access_expires_at = now + timedelta(seconds=self.settings.access_token_ttl_seconds)
        refresh_expires_at = now + timedelta(seconds=self.settings.refresh_token_ttl_seconds)
        account.last_sign_in_provider = provider
        account.updated_at = now
        db.add(
            RefreshSession(
                id=str(uuid.uuid4()),
                account_id=account.id,
                access_token_hash=_hash_token(access_token),
                refresh_token_hash=_hash_token(refresh_token),
                access_expires_at=access_expires_at,
                refresh_expires_at=refresh_expires_at,
                rotated_from_session_id=rotated_from,
                created_at=now,
                updated_at=now,
            )
        )
        db.flush()
        db.refresh(account)
        return SessionPayload(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=self.settings.access_token_ttl_seconds,
            account=_serialize_account(account),
        )

    def _resolve_social_account(
        self,
        db: Session,
        *,
        provider: str,
        state_row: OAuthState,
        social: SocialIdentity,
    ) -> Account:
        identity = db.scalar(
            select(LinkedIdentity).where(
                LinkedIdentity.provider == provider,
                LinkedIdentity.provider_subject == social.subject,
            )
        )
        now = _now()
        if state_row.mode == "link":
            if not state_row.link_account_id:
                raise HTTPException(status_code=401, detail="Linking requires a signed-in Synapse account.")
            account = db.scalar(select(Account).where(Account.id == state_row.link_account_id))
            if account is None:
                raise HTTPException(status_code=404, detail="The current Synapse account could not be found.")
            if identity is not None and identity.account_id != account.id:
                raise HTTPException(
                    status_code=409,
                    detail="That Google account is already linked to a different Synapse account.",
                )
            if identity is None:
                db.add(
                    LinkedIdentity(
                        id=str(uuid.uuid4()),
                        account_id=account.id,
                        provider=provider,
                        provider_subject=social.subject,
                        email=social.email,
                        display_name=social.display_name,
                        avatar_url=social.avatar_url,
                        created_at=now,
                        updated_at=now,
                    )
                )
            else:
                identity.email = social.email
                identity.display_name = social.display_name
                identity.avatar_url = social.avatar_url
                identity.updated_at = now
            self._hydrate_account_from_social(account, social)
            db.flush()
            db.refresh(account)
            return account

        if identity is not None:
            account = db.scalar(select(Account).where(Account.id == identity.account_id))
            if account is None:
                raise HTTPException(status_code=404, detail="Linked Synapse account could not be found.")
            self._hydrate_account_from_social(account, social)
            db.flush()
            db.refresh(account)
            return account

        normalized_email = _normalize_email(social.email) if social.email else None
        if normalized_email:
            existing_by_email = db.scalar(
                select(Account).where(Account.email_normalized == normalized_email)
            )
            if existing_by_email is not None:
                raise HTTPException(
                    status_code=409,
                    detail="A Synapse account with that email already exists. Sign in first, then link Google from Profile.",
                )

        username = self._unique_username(db, _slug_base(social.display_name or social.email or "synapse"))
        account = Account(
            id=str(uuid.uuid4()),
            username=username,
            username_normalized=_normalize_username(username),
            email=social.email or f"{username}@synapse.invalid",
            email_normalized=_normalize_email(social.email or f"{username}@synapse.invalid"),
            password_hash=None,
            display_name=social.display_name or username,
            avatar_url=social.avatar_url,
            email_verified_at=now if social.email_verified else None,
            last_sign_in_provider=provider,
            created_at=now,
            updated_at=now,
        )
        db.add(account)
        db.flush()
        db.add(
            LinkedIdentity(
                id=str(uuid.uuid4()),
                account_id=account.id,
                provider=provider,
                provider_subject=social.subject,
                email=social.email,
                display_name=social.display_name,
                avatar_url=social.avatar_url,
                created_at=now,
                updated_at=now,
            )
        )
        db.flush()
        db.refresh(account)
        return account

    def _hydrate_account_from_social(self, account: Account, social: SocialIdentity) -> None:
        now = _now()
        if social.display_name and not account.display_name:
            account.display_name = social.display_name
        if social.avatar_url and not account.avatar_url:
            account.avatar_url = social.avatar_url
        if social.email_verified and account.email_normalized == _normalize_email(social.email or ""):
            account.email_verified_at = account.email_verified_at or now
        account.updated_at = now

    def _unique_username(self, db: Session, base: str) -> str:
        candidate = _normalize_username(base)
        for index in range(1, 1000):
            existing = db.scalar(
                select(Account).where(Account.username_normalized == candidate)
            )
            if existing is None:
                return candidate
            candidate = f"{_normalize_username(base)[:24]}_{index}"
        raise HTTPException(status_code=500, detail="Could not generate a unique username.")

    def _exchange_google_code(self, code: str) -> SocialIdentity:
        if not (self.settings.google_client_id and self.settings.google_client_secret):
            raise HTTPException(status_code=503, detail="Google sign-in is not configured.")
        token_payload = urllib.parse.urlencode(
            {
                "client_id": self.settings.google_client_id,
                "client_secret": self.settings.google_client_secret,
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": f"{self.settings.public_base_url}/v1/oauth/google/callback",
            }
        ).encode("utf-8")
        token_request = urllib.request.Request(
            "https://oauth2.googleapis.com/token",
            method="POST",
            data=token_payload,
            headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"},
        )
        try:
            with urllib.request.urlopen(token_request, timeout=self.settings.request_timeout_seconds) as response:
                token_body = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise HTTPException(status_code=502, detail=f"Google token exchange failed: {detail}") from exc
        access_token = token_body.get("access_token")
        if not isinstance(access_token, str) or not access_token:
            raise HTTPException(status_code=502, detail="Google did not return an access token.")

        profile_request = urllib.request.Request(
            "https://openidconnect.googleapis.com/v1/userinfo",
            method="GET",
            headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"},
        )
        try:
            with urllib.request.urlopen(profile_request, timeout=self.settings.request_timeout_seconds) as response:
                userinfo = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise HTTPException(status_code=502, detail=f"Google profile fetch failed: {detail}") from exc
        subject = userinfo.get("sub")
        if not isinstance(subject, str) or not subject:
            raise HTTPException(status_code=502, detail="Google did not return a valid subject id.")
        return SocialIdentity(
            provider="google",
            subject=subject,
            email=userinfo.get("email"),
            display_name=userinfo.get("name"),
            avatar_url=userinfo.get("picture"),
            email_verified=bool(userinfo.get("email_verified")),
        )

    def _log_event(
        self,
        db: Session,
        *,
        account_id: str | None,
        event_kind: str,
        provider: str | None,
        details: dict[str, Any] | None = None,
    ) -> None:
        db.add(
            AuthAuditEvent(
                account_id=account_id,
                event_kind=event_kind,
                provider=provider,
                details_json=json.dumps(details or {}),
            )
        )


def create_app(settings: AccountsSettings | None = None) -> FastAPI:
    active_settings = settings or load_settings()
    service = AccountsService(active_settings)
    app = FastAPI(title="Synapse Accounts", version="0.1.36-dev", docs_url=None, redoc_url=None)

    def get_db() -> Any:
        with session_scope(service.session_factory) as session:
            yield session

    def current_account(
        authorization: str | None = Header(default=None),
        db: Session = Depends(get_db),
    ) -> Account:
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="Authorization bearer token required.")
        return service.get_account_for_access_token(db, authorization.split(" ", 1)[1].strip())

    @app.get("/v1/health")
    def health() -> dict[str, Any]:
        return {"ok": True, "service": "synapse-accounts"}

    @app.get("/v1/public/config", response_model=PublicConfigPayload)
    def public_config() -> PublicConfigPayload:
        return service.public_config()

    @app.post("/v1/auth/signup", response_model=SessionPayload)
    def sign_up(payload: SignUpRequest, db: Session = Depends(get_db)) -> SessionPayload:
        return service.sign_up(db, payload)

    @app.post("/v1/auth/signin", response_model=SessionPayload)
    def sign_in(payload: SignInRequest, db: Session = Depends(get_db)) -> SessionPayload:
        return service.sign_in(db, payload)

    @app.post("/v1/auth/refresh", response_model=SessionPayload)
    def refresh(payload: SignOutRequest, db: Session = Depends(get_db)) -> SessionPayload:
        if not payload.refresh_token:
            raise HTTPException(status_code=422, detail="refresh_token is required.")
        return service.refresh(db, payload.refresh_token)

    @app.post("/v1/auth/signout", status_code=204)
    def sign_out(
        payload: SignOutRequest,
        authorization: str | None = Header(default=None),
        db: Session = Depends(get_db),
    ) -> None:
        access_token = None
        if authorization and authorization.startswith("Bearer "):
            access_token = authorization.split(" ", 1)[1].strip()
        service.sign_out(db, refresh_token=payload.refresh_token, access_token=access_token)

    @app.get("/v1/me", response_model=AccountPayload)
    def me(account: Account = Depends(current_account)) -> AccountPayload:
        return _serialize_account(account)

    @app.get("/v1/sync/document", response_model=SyncDocumentPayload)
    def get_sync_document(
        account: Account = Depends(current_account),
        db: Session = Depends(get_db),
    ) -> SyncDocumentPayload:
        return service.get_sync_document(db, account)

    @app.put("/v1/sync/document", response_model=SyncDocumentPayload)
    def put_sync_document(
        payload: PutSyncDocumentRequest,
        account: Account = Depends(current_account),
        db: Session = Depends(get_db),
    ) -> SyncDocumentPayload:
        return service.put_sync_document(db, account, payload.document)

    @app.post("/v1/oauth/start", response_model=OAuthStartResponse)
    def start_oauth(
        payload: OAuthStartRequest,
        authorization: str | None = Header(default=None),
        db: Session = Depends(get_db),
    ) -> OAuthStartResponse:
        account = None
        if payload.mode == "link":
            if not authorization or not authorization.startswith("Bearer "):
                raise HTTPException(status_code=401, detail="Authorization bearer token required for linking.")
            account = service.get_account_for_access_token(db, authorization.split(" ", 1)[1].strip())
        return service.start_oauth(
            db,
            provider=payload.provider,
            callback_url=payload.callback_url,
            mode=payload.mode,
            current_account=account,
        )

    @app.post("/v1/oauth/exchange", response_model=SessionPayload)
    def exchange_oauth(payload: OAuthExchangeRequest, db: Session = Depends(get_db)) -> SessionPayload:
        return service.exchange_handoff(db, payload.handoff)

    @app.delete("/v1/providers/{provider}", response_model=AccountPayload)
    def unlink_provider(
        provider: str,
        account: Account = Depends(current_account),
        db: Session = Depends(get_db),
    ) -> AccountPayload:
        return service.unlink_provider(db, account=account, provider=provider)

    @app.get("/v1/oauth/google/callback", include_in_schema=False, response_model=None)
    def google_callback(
        state: str | None = None,
        code: str | None = None,
        error: str | None = None,
        error_description: str | None = None,
        db: Session = Depends(get_db),
    ) -> Any:
        if error:
            return _callback_page(
                ok=False,
                title="Google sign-in could not continue",
                message=error_description or error,
            )
        if not state or not code:
            return _callback_page(
                ok=False,
                title="Google sign-in could not continue",
                message="The callback did not include the data Synapse expected.",
            )
        try:
            redirect_url = service.finalize_google_callback(db, state=state, code=code)
        except HTTPException as exc:
            return _callback_page(
                ok=False,
                title="Google sign-in could not continue",
                message=str(exc.detail),
            )
        return RedirectResponse(url=redirect_url, status_code=302)

    app.state.accounts_service = service
    app.state.accounts_settings = active_settings
    return app


__all__ = [
    "AccountsService",
    "consume_reserved_token",
    "create_app",
    "issue_reserved_token",
]
