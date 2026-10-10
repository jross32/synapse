"""Conservative HTTPS attachment downloader for Synapse imports.

Only explicitly configured hostnames are trusted; no redirects or private IPs.
"""
from __future__ import annotations
import hashlib
import ipaddress
import os
import socket
import tempfile
import urllib.parse
import http.client
from pathlib import Path

MAX_BYTES = 50 * 1024 * 1024
SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}

def fetch_attachment(url: str, *, allowed_hosts: set[str], expected_sha256: str | None = None) -> Path:
    parsed = urllib.parse.urlsplit(url)
    host = (parsed.hostname or "").lower().rstrip(".")
    if parsed.scheme != "https" or host not in allowed_hosts or parsed.username or parsed.password or parsed.port not in (None, 443):
        raise ValueError("attachment URL must use an explicitly trusted HTTPS host")
    if not parsed.path or parsed.fragment:
        raise ValueError("invalid attachment URL")
    suffix = Path(urllib.parse.unquote(parsed.path)).suffix.lower()
    if suffix not in SUFFIXES:
        raise ValueError("attachment URL must name a supported image")
    addresses = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    if not addresses or any(not ipaddress.ip_address(item[4][0]).is_global for item in addresses):
        raise ValueError("attachment host resolves to a non-public address")
    # Pin the resolved address at connection time to avoid DNS rebinding.
    address = addresses[0][4][0]
    class PinnedConnection(http.client.HTTPSConnection):
        def connect(self):
            import ssl
            raw = socket.create_connection((address, 443), timeout=15)
            self.sock = ssl.create_default_context().wrap_socket(raw, server_hostname=host)
    conn = PinnedConnection(host, timeout=20)
    tmp = None
    try:
        target = parsed.path + ("?" + parsed.query if parsed.query else "")
        conn.request("GET", target, headers={"Accept": "image/jpeg,image/png,image/webp", "Host": host})
        response = conn.getresponse()
        if response.status != 200:
            raise ValueError("attachment fetch failed (HTTP %d)" % response.status)
        with tempfile.NamedTemporaryFile(prefix="synapse-chat-", suffix=suffix, delete=False) as handle:
            tmp = Path(handle.name)
            digest = hashlib.sha256()
            total = 0
            while True:
                chunk = response.read(65536)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_BYTES:
                    raise ValueError("attachment exceeds 50MB limit")
                digest.update(chunk)
                handle.write(chunk)
        if not total:
            raise ValueError("empty attachment")
        if expected_sha256 and digest.hexdigest().lower() != expected_sha256.lower():
            raise ValueError("attachment SHA256 mismatch")
        return tmp
    except Exception:
        if tmp:
            tmp.unlink(missing_ok=True)
        raise
    finally:
        conn.close()
