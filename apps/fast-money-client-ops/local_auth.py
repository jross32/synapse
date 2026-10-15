from __future__ import annotations

import secrets
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from http.cookies import SimpleCookie
from typing import Callable

SESSION_COOKIE_NAME = "fast_money_session"
SESSION_TTL_SECONDS = 8 * 60 * 60
CSRF_HEADER_NAME = "X-CSRF-Token"

ROLE_PROFILES = {
    "operator": {
        "display_name": "Local operator",
        "lead_id": None,
    },
    "customer": {
        "display_name": "Erin Stone - Northline HVAC",
        "lead_id": "lead-1001",
    },
}


@dataclass(frozen=True)
class LocalSession:
    token: str
    csrf_token: str
    role: str
    display_name: str
    created_at: float
    expires_at: float
    lead_id: str | None = None

    def public(self, *, include_csrf: bool = False) -> dict[str, object]:
        payload: dict[str, object] = {
            "role": self.role,
            "display_name": self.display_name,
            "lead_id": self.lead_id,
            "expires_at": datetime.fromtimestamp(
                self.expires_at,
                timezone.utc,
            ).isoformat().replace("+00:00", "Z"),
        }
        if include_csrf:
            payload["csrf_token"] = self.csrf_token
        return payload


class LocalSessionStore:
    """Process-local opaque sessions for the private localhost reference app."""

    def __init__(
        self,
        *,
        ttl_seconds: int = SESSION_TTL_SECONDS,
        clock: Callable[[], float] = time.time,
    ) -> None:
        if ttl_seconds <= 0:
            raise ValueError("Session TTL must be positive.")
        self._lock = threading.RLock()
        self._sessions: dict[str, LocalSession] = {}
        self._ttl_seconds = int(ttl_seconds)
        self._clock = clock

    def _purge_expired_unlocked(self, now: float) -> None:
        expired = [
            token
            for token, session in self._sessions.items()
            if session.expires_at <= now
        ]
        for token in expired:
            self._sessions.pop(token, None)

    def create(self, role: str) -> LocalSession:
        profile = ROLE_PROFILES.get(role)
        if profile is None:
            raise ValueError("Unknown local role.")
        now = float(self._clock())
        session = LocalSession(
            token=secrets.token_urlsafe(32),
            csrf_token=secrets.token_urlsafe(32),
            role=role,
            display_name=str(profile["display_name"]),
            created_at=now,
            expires_at=now + self._ttl_seconds,
            lead_id=profile.get("lead_id"),
        )
        with self._lock:
            self._purge_expired_unlocked(now)
            self._sessions[session.token] = session
        return session

    def get(self, token: str | None) -> LocalSession | None:
        if not token:
            return None
        now = float(self._clock())
        with self._lock:
            session = self._sessions.get(token)
            if session is None:
                return None
            if session.expires_at <= now:
                self._sessions.pop(token, None)
                return None
            return session

    def delete(self, token: str | None) -> None:
        if not token:
            return
        with self._lock:
            self._sessions.pop(token, None)


def csrf_matches(session: LocalSession, supplied_token: str | None) -> bool:
    if not supplied_token:
        return False
    return secrets.compare_digest(session.csrf_token, supplied_token)


def read_session_token(cookie_header: str | None) -> str | None:
    if not cookie_header:
        return None
    cookie = SimpleCookie()
    try:
        cookie.load(cookie_header)
    except Exception:
        return None
    morsel = cookie.get(SESSION_COOKIE_NAME)
    return morsel.value if morsel else None


def build_session_cookie(
    token: str,
    *,
    max_age: int = SESSION_TTL_SECONDS,
) -> str:
    return (
        f"{SESSION_COOKIE_NAME}={token}; Path=/; HttpOnly; SameSite=Strict; "
        f"Max-Age={int(max_age)}"
    )


def clear_session_cookie() -> str:
    return (
        f"{SESSION_COOKIE_NAME}=; Path=/; HttpOnly; SameSite=Strict; Max-Age=0"
    )
