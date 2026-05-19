"""Device authentication + pairing (Milestone H · v0.1.11).

Every ``/api/v1`` data route requires a bearer token in the
``X-Synapse-Token`` header. Two kinds of token are accepted:

  • the **local token** — a secret the daemon writes to ``data/auth-token`` on
    boot. The desktop app (and the dev browser) read it via the trusted-local
    bootstrap endpoint and send it on every request.
  • a **device token** — minted when a phone redeems a pairing code. Stored
    only as a SHA-256 hash; the raw token is shown to the device once.

Why not "trust localhost": a Cloudflare tunnel runs ``cloudflared`` on this
machine, so tunnelled requests reach the daemon from ``127.0.0.1`` — they
look local. :func:`is_trusted_local` therefore also rejects anything that
carries proxy headers (``X-Forwarded-For`` / ``CF-*``). Only that one
bootstrap endpoint relies on it; everything else checks a real token.
"""

from __future__ import annotations

import hashlib
import logging
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from fastapi import Request
from starlette.requests import HTTPConnection

from .errors import SynapseError, invalid
from .storage import Storage
from .time_utils import to_iso, utc_now

log = logging.getLogger(__name__)

LOCAL_TOKEN_FILENAME = "auth-token"
PAIRING_CODE_TTL_SECONDS = 600  # 10 minutes
PAIRING_CODE_DIGITS = 6

# Headers a reverse proxy / tunnel adds. Their presence means the request did
# NOT come straight from a process on this machine.
_PROXY_HEADERS = (
    "x-forwarded-for",
    "forwarded",
    "x-real-ip",
    "cf-connecting-ip",
    "cf-ray",
)
_LOOPBACK = {"127.0.0.1", "::1", "localhost"}


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def is_trusted_local(conn: HTTPConnection) -> bool:
    """True only for a connection straight from a process on this machine.

    Loopback client address AND no proxy/tunnel headers. Works for both an
    HTTP :class:`Request` and a :class:`WebSocket` (both are HTTPConnections).
    A Cloudflare-tunnelled request is loopback but always carries ``CF-*``
    headers, so it fails here.
    """

    client = conn.client.host if conn.client else ""
    if client not in _LOOPBACK:
        return False
    return not any(h in conn.headers for h in _PROXY_HEADERS)


def ensure_local_token(data_dir) -> str:
    """Read the daemon's local auth token, creating it on first boot."""

    path = data_dir / LOCAL_TOKEN_FILENAME
    try:
        existing = path.read_text(encoding="utf-8").strip()
        if existing:
            return existing
    except OSError:
        pass
    token = secrets.token_urlsafe(32)
    path.write_text(token, encoding="utf-8")
    log.info("Generated a new local auth token at %s", path)
    return token


@dataclass
class _PendingCode:
    code: str
    expires_at: datetime


class AuthManager:
    """Verifies tokens and runs the pairing-code lifecycle."""

    def __init__(self, storage: Storage, local_token: str) -> None:
        self._storage = storage
        self._local_token = local_token
        self._local_hash = _sha256(local_token)
        self._pending: _PendingCode | None = None  # one live code at a time

    @property
    def local_token(self) -> str:
        return self._local_token

    # ── verification ─────────────────────────────────────────────────────

    def verify(self, token: str | None) -> bool:
        """True if ``token`` is the local token or a live paired-device token."""

        if not token:
            return False
        token_hash = _sha256(token)
        if secrets.compare_digest(token_hash, self._local_hash):
            return True
        row = self._storage.conn.execute(
            "SELECT id FROM paired_devices WHERE token_sha256 = ? AND revoked = 0",
            (token_hash,),
        ).fetchone()
        if row is None:
            return False
        self._touch(row["id"])
        return True

    def _touch(self, device_id: str) -> None:
        try:
            with self._storage.transaction() as conn:
                conn.execute(
                    "UPDATE paired_devices SET last_seen_at = ? WHERE id = ?",
                    (to_iso(utc_now()), device_id),
                )
        except Exception:  # pragma: no cover — last_seen is best-effort
            log.debug("Could not update last_seen for device %s", device_id)

    # ── pairing-code lifecycle ───────────────────────────────────────────

    def issue_code(self) -> dict:
        """Mint a fresh pairing code, replacing any previous one."""

        code = "".join(secrets.choice("0123456789") for _ in range(PAIRING_CODE_DIGITS))
        expires_at = utc_now() + timedelta(seconds=PAIRING_CODE_TTL_SECONDS)
        self._pending = _PendingCode(code=code, expires_at=expires_at)
        log.info("Issued a pairing code (expires %s).", to_iso(expires_at))
        return {"code": code, "expires_at": to_iso(expires_at)}

    def has_live_code(self) -> bool:
        return self._pending is not None and utc_now() <= self._pending.expires_at

    def redeem(self, code: str, device_name: str) -> dict:
        """Redeem a pairing code -> create a paired device, return its token.

        The raw token is returned exactly once; only its hash is stored.
        """

        pending = self._pending
        if pending is None or utc_now() > pending.expires_at:
            self._pending = None
            raise invalid("pairing", "No live pairing code. Generate a new one on the desktop.")
        if not secrets.compare_digest((code or "").strip(), pending.code):
            raise invalid("pairing", "That pairing code is incorrect.")

        self._pending = None  # codes are single-use
        token = secrets.token_urlsafe(32)
        device_id = str(uuid.uuid4())
        name = (device_name or "").strip() or "Paired device"
        now = to_iso(utc_now())
        with self._storage.transaction() as conn:
            conn.execute(
                "INSERT INTO paired_devices (id, name, token_sha256, created_at) "
                "VALUES (?, ?, ?, ?)",
                (device_id, name, _sha256(token), now),
            )
        log.info("Paired a new device '%s' (%s).", name, device_id)
        return {
            "token": token,
            "device": {"id": device_id, "name": name, "created_at": now},
        }

    # ── device management ────────────────────────────────────────────────

    def list_devices(self) -> list[dict]:
        rows = self._storage.conn.execute(
            "SELECT id, name, created_at, last_seen_at FROM paired_devices "
            "WHERE revoked = 0 ORDER BY created_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]

    def revoke(self, device_id: str) -> None:
        with self._storage.transaction() as conn:
            cursor = conn.execute(
                "UPDATE paired_devices SET revoked = 1 WHERE id = ? AND revoked = 0",
                (device_id,),
            )
            if cursor.rowcount == 0:
                raise SynapseError(
                    code="device.not_found",
                    message=f"No paired device '{device_id}'.",
                    status=404,
                )
        log.info("Revoked paired device %s", device_id)


def require_token(auth: AuthManager):
    """Build a FastAPI dependency that 401s any request without a valid token.

    Applied to every protected ``/api/v1`` router. The token rides in the
    ``X-Synapse-Token`` header (REST) — see :mod:`synapse_daemon.app`.
    """

    async def _dependency(request: Request) -> None:
        token = request.headers.get("x-synapse-token")
        if not auth.verify(token):
            raise SynapseError(
                code="auth.unauthorized",
                message="A valid X-Synapse-Token is required.",
                status=401,
            )

    return _dependency
