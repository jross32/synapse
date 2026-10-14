"""Run ONLY the public Synapse download-site directory on loopback.

Designed for Windows scheduled on-logon startup and Cloudflare tunnel origin.
Never serves the repository root, local Synapse daemon data, or signing keys.
"""
from __future__ import annotations
import functools
import os
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SITE = (REPO / "download-site").resolve(strict=True)
HOST, PORT = "127.0.0.1", 8879

class PublicDownloads(SimpleHTTPRequestHandler):
    def log_message(self, fmt: str, *args: object) -> None:
        # pythonw.exe has no stderr; avoid failing requests during logging.
        return

def serve() -> None:
    handler = functools.partial(PublicDownloads, directory=str(SITE))
    class Server(ThreadingHTTPServer):
        allow_reuse_address = True
    try:
        server = Server((HOST, PORT), handler)
    except OSError as exc:
        # Another healthy site process might already be bound.
        raise SystemExit(f"Download site could not bind loopback port {PORT}: {exc}") from exc
    with server:
        server.serve_forever(poll_interval=0.5)

if __name__ == "__main__":
    serve()
