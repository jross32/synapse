"""Railway native OAuth with PKCE. Credentials remain local and account-bound."""
from __future__ import annotations
import base64
import hashlib
import json
import os
import secrets
import ctypes
import sys
import threading
import time
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

BASE = "https://backboard.railway.com/oauth"
SCOPES = "openid email profile offline_access project:viewer"
_LOCK = threading.RLock()
_PENDING: dict[str, dict] = {}


def owner(profile) -> str | None:
    a = profile.summary(refresh_remote=False)
    pinned = os.getenv("SYNAPSE_DEVELOPER_USER_ID", "").strip()
    if not (a.signed_in and a.email_verified and a.user_id and
            (a.email or "").strip().casefold() == "justinwross32@gmail.com" and
            (not pinned or pinned == a.user_id)):
        return None
    return str(a.user_id)


def _path(data_dir: Path, account: str) -> Path:
    identifier = hashlib.sha256(account.encode()).hexdigest()[:32]
    return data_dir / "railway-costs" / ("oauth-" + identifier + ".dpapi")


def save(data_dir: Path, account: str, value: dict) -> None:
    if sys.platform != "win32":
        raise RuntimeError("Windows credential protection is required")
    from ctypes import wintypes
    class DATA_BLOB(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]
    raw = json.dumps(value, separators=(",", ":")).encode("utf-8")
    source = ctypes.create_string_buffer(raw)
    incoming = DATA_BLOB(len(raw), ctypes.cast(source, ctypes.POINTER(ctypes.c_byte)))
    outgoing = DATA_BLOB()
    if not ctypes.windll.crypt32.CryptProtectData(ctypes.byref(incoming), None, None, None, None, 0x01, ctypes.byref(outgoing)):
        raise RuntimeError("Windows credential protection failed")
    try:
        encrypted = ctypes.string_at(outgoing.pbData, outgoing.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(outgoing.pbData)
    target = _path(data_dir, account)
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_suffix(".tmp")
    temp.write_bytes(encrypted)
    temp.replace(target)


def load(data_dir: Path, account: str) -> dict | None:
    target = _path(data_dir, account)
    if not target.is_file() or sys.platform != "win32":
        return None
    from ctypes import wintypes
    class DATA_BLOB(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]
    try:
        raw = target.read_bytes()
        source = ctypes.create_string_buffer(raw)
        incoming = DATA_BLOB(len(raw), ctypes.cast(source, ctypes.POINTER(ctypes.c_byte)))
        outgoing = DATA_BLOB()
        if not ctypes.windll.crypt32.CryptUnprotectData(ctypes.byref(incoming), None, None, None, None, 0x01, ctypes.byref(outgoing)):
            return None
        try:
            plaintext = ctypes.string_at(outgoing.pbData, outgoing.cbData)
        finally:
            ctypes.windll.kernel32.LocalFree(outgoing.pbData)
        return json.loads(plaintext)
    except (ValueError, OSError):
        return None


def remove(data_dir: Path, account: str) -> None:
    _path(data_dir, account).unlink(missing_ok=True)


def client_id() -> str:
    return os.environ.get("SYNAPSE_RAILWAY_OAUTH_CLIENT_ID", "").strip()


def make_authorization(account: str, redirect_uri: str) -> dict:
    cid = client_id()
    if not cid:
        raise RuntimeError("Railway OAuth app is not configured; register a native app and set SYNAPSE_RAILWAY_OAUTH_CLIENT_ID")
    from urllib.parse import urlparse
    parsed = urlparse(redirect_uri)
    if (parsed.scheme != "http" or parsed.hostname != "127.0.0.1" or
            parsed.path != "/api/v1/system/railway-oauth/callback" or
            parsed.username or parsed.password or parsed.query or parsed.fragment):
        raise ValueError("Native redirect must use the exact Synapse loopback callback")
    state = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    now = time.monotonic()
    with _LOCK:
        for key, pending in list(_PENDING.items()):
            if now - pending["created"] > 600:
                _PENDING.pop(key, None)
        _PENDING[state] = {"account": account, "verifier": verifier, "redirect_uri": redirect_uri, "created": now}
    url = BASE + "/auth?" + urlencode({
        "response_type": "code", "client_id": cid, "redirect_uri": redirect_uri,
        "scope": SCOPES, "prompt": "consent", "state": state,
        "code_challenge": challenge, "code_challenge_method": "S256",
    })
    return {"url": url, "state": state}


def _token_request(payload: dict) -> dict:
    data = urlencode(payload).encode()
    req = Request(BASE + "/token", data=data, headers={"Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urlopen(req, timeout=12) as response:
            result = json.load(response)
    except (HTTPError, URLError, TimeoutError, ValueError) as exc:
        raise RuntimeError("Railway authorization or token refresh failed") from exc
    if not isinstance(result, dict) or not result.get("access_token"):
        raise RuntimeError("Railway did not provide an access token")
    return result


def complete(data_dir: Path, account: str, state: str, code: str) -> dict:
    with _LOCK:
        pending = _PENDING.pop(state, None)
    if not pending or pending["account"] != account or time.monotonic() - pending["created"] > 600:
        raise ValueError("Authorization expired or mismatched; reconnect Railway")
    result = _token_request({
        "grant_type": "authorization_code", "client_id": client_id(),
        "code": code, "redirect_uri": pending["redirect_uri"], "code_verifier": pending["verifier"],
    })
    access = result["access_token"]
    identity_req = Request(BASE + "/me", headers={"Authorization": "Bearer " + access})
    try:
        with urlopen(identity_req, timeout=10) as response:
            identity = json.load(response)
    except (HTTPError, URLError, TimeoutError, ValueError) as exc:
        raise RuntimeError("Railway identity verification failed") from exc
    if not isinstance(identity, dict) or not identity.get("sub"):
        raise RuntimeError("Railway identity was not verified")
    if (identity.get("email") or "").strip().casefold() != "justinwross32@gmail.com":
        raise RuntimeError("Authorized Railway identity is not the Synapse developer account")
    save(data_dir, account, {
        "account": account, "railway_id": identity["sub"],
        "railway_email": identity.get("email"),
        "access_token": access, "refresh_token": result.get("refresh_token"),
        "expires_at": time.time() + int(result.get("expires_in", 3600)),
        "scope": result.get("scope", ""),
    })
    return {"connected": True, "railway_email": identity.get("email")}


def token(data_dir: Path, account: str) -> str:
    with _LOCK:
        credential = load(data_dir, account)
        if not credential or credential.get("account") != account:
            return ""
        if float(credential.get("expires_at", 0)) > time.time() + 90:
            return str(credential.get("access_token", ""))
        refresh = credential.get("refresh_token")
        if not refresh:
            return ""
        result = _token_request({"grant_type": "refresh_token", "client_id": client_id(),
                                  "refresh_token": refresh})
        credential.update({
            "access_token": result["access_token"],
            "refresh_token": result.get("refresh_token") or refresh,
            "expires_at": time.time() + int(result.get("expires_in", 3600)),
        })
        save(data_dir, account, credential)
        return str(credential["access_token"])


def status(data_dir: Path, account: str) -> dict:
    value = load(data_dir, account)
    return {"configured": bool(client_id()), "connected": bool(value and value.get("refresh_token")),
            "railway_email": value.get("railway_email") if value else None,
            "account_bound": True}
