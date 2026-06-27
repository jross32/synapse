"""Small local web server for the AI Operating System app."""

from __future__ import annotations

import json
import os
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

APP_DIR = Path(__file__).resolve().parent
STATIC_DIR = APP_DIR / "static"
PORT = int(os.getenv("AI_OS_PORT", "4312"))


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(STATIC_DIR), **kwargs)

    def do_GET(self) -> None:  # noqa: N802
        route = urlparse(self.path).path
        if route == "/health":
            payload = {"ok": True, "app": "ai-operating-system", "port": PORT}
            self._write_json(payload)
            return
        if route == "/config":
            payload = {
                "synapseApi": os.getenv("SYNAPSE_API", "http://127.0.0.1:7878/api/v1"),
                "synapseToken": os.getenv("SYNAPSE_TOKEN", ""),
                "port": PORT,
            }
            self._write_json(payload)
            return
        if route == "/" or not Path(route.lstrip("/")).suffix:
            self.path = "/index.html"
        return super().do_GET()

    def _write_json(self, payload: dict) -> None:
        encoded = json.dumps(payload).encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return


def main() -> None:
    STATIC_DIR.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"AI Operating System listening on http://127.0.0.1:{PORT}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
