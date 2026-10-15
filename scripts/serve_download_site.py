"""Serve only approved public Synapse downloads over a loopback origin.

The Cloudflare route terminates TLS. This handler must not expose repository
diagnostics, builds, source/test files, or directory listings.
"""
from __future__ import annotations

import functools
import os
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

REPO = Path(__file__).resolve().parents[1]
SITE = (REPO / "download-site").resolve(strict=True)
HOST = "127.0.0.1"
PORT = int(os.environ.get("SYNAPSE_DOWNLOAD_SITE_PORT", "8879"))
PAGE_ROUTES = frozenset(
    ("features", "how-it-works", "releases", "support", "download", "start", "signup")
)
ROOT_FILES = frozenset(("index.html", "style.css", "app.js", "releases.json"))
SCRIPT_FILES = frozenset(("signup/signup.js",))
INSTALLER_FILES = frozenset(("releases/Synapse-Premium-Setup-0.2.219-preview.exe",))
ASSET_SUFFIXES = frozenset(
    (".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg", ".ico", ".woff", ".woff2", ".css")
)


class PublicDownloads(SimpleHTTPRequestHandler):
    """Reject any URL not explicitly intended for public distribution."""

    def log_message(self, fmt: str, *args: object) -> None:
        # Safe for pythonw.exe (which has no stderr).
        return

    def _public_path(self) -> bool:
        raw = urlsplit(self.path).path
        try:
            name = unquote(raw, errors="strict")
        except UnicodeError:
            return False
        if not name.startswith("/") or "\\" in name or "\x00" in name:
            return False
        parts = name.split("/")
        if any(part in (".", "..") for part in parts):
            return False

        relative = name.lstrip("/")
        if relative in ROOT_FILES or relative in SCRIPT_FILES or relative in INSTALLER_FILES:
            allowed = True
        elif not relative or relative in (route for route in PAGE_ROUTES):
            allowed = True
        elif any(relative == route + "/" or relative == route + "/index.html" for route in PAGE_ROUTES):
            allowed = True
        elif relative.startswith("assets/") and Path(relative).suffix.lower() in ASSET_SUFFIXES:
            allowed = True
        else:
            return False

        if not allowed:
            return False
        target = (SITE / relative).resolve()
        return target == SITE or target.is_relative_to(SITE)

    def do_GET(self) -> None:
        if not self._public_path():
            self.send_error(404, "Not found")
            return
        super().do_GET()

    def do_HEAD(self) -> None:
        if not self._public_path():
            self.send_error(404, "Not found")
            return
        super().do_HEAD()

    def list_directory(self, path: str):
        self.send_error(404, "Not found")
        return None

    def end_headers(self) -> None:
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "strict-origin-when-cross-origin")
        super().end_headers()


def serve() -> None:
    handler = functools.partial(PublicDownloads, directory=str(SITE))

    class Server(ThreadingHTTPServer):
        allow_reuse_address = True

    try:
        server = Server((HOST, PORT), handler)
    except OSError as exc:
        raise SystemExit(f"Download site could not bind loopback port {PORT}: {exc}") from exc
    with server:
        server.serve_forever(poll_interval=0.5)


if __name__ == "__main__":
    serve()
