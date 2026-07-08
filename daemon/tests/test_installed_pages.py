"""Tests for curated installed pages and the Web Scraper proxy routes."""

from __future__ import annotations

import json
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Iterator

from fastapi.testclient import TestClient

from synapse_daemon import projects as projects_module
from synapse_daemon.app import build_app
from synapse_daemon.projects import Project
from synapse_daemon.storage import Storage
from synapse_daemon.ws import EventBus


def _harness(tmp_path: Path) -> tuple[TestClient, Storage]:
    storage = Storage(tmp_path / "data")
    storage.open()
    storage.migrate()
    app = build_app(storage, EventBus())
    return TestClient(app, headers={"X-Synapse-Token": app.state.auth.local_token}), storage


@contextmanager
def _json_server(routes: dict[tuple[str, str], tuple[int, object]]) -> Iterator[str]:
    class Handler(BaseHTTPRequestHandler):
        def _reply(self, method: str) -> None:
            status, payload = routes.get((method, self.path), (404, {"detail": "missing"}))
            body = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:  # noqa: N802
            self._reply("GET")

        def do_POST(self) -> None:  # noqa: N802
            length = int(self.headers.get("Content-Length", "0"))
            if length:
                self.rfile.read(length)
            self._reply("POST")

        def log_message(self, format: str, *args) -> None:  # noqa: A003
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address
        yield f"http://{host}:{port}"
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


def test_installed_pages_lists_known_web_scraper_even_when_offline(tmp_path: Path) -> None:
    client, _ = _harness(tmp_path)
    installed = client.post(
        "/api/v1/mcp-servers/install",
        json={
            "id": "web-scraper",
            "name": "Web Scraper",
            "transport": "http",
            "url": "http://127.0.0.1:59999/mcp",
        },
    )
    assert installed.status_code == 201, installed.text

    response = client.get("/api/v1/installed-pages")
    assert response.status_code == 200, response.text
    payload = response.json()["pages"]
    assert len(payload) == 1
    assert payload[0]["id"] == "web-scraper"
    assert payload[0]["status"] == "offline"


def test_installed_pages_drops_known_id_when_fingerprint_is_wrong(tmp_path: Path) -> None:
    with _json_server(
        {
            ("GET", "/api/mcp-meta"): (200, {"server": {"name": "not-web-scraper"}}),
        }
    ) as base_url:
        client, _ = _harness(tmp_path)
        installed = client.post(
            "/api/v1/mcp-servers/install",
            json={
                "id": "web-scraper",
                "name": "Web Scraper",
                "transport": "http",
                "url": f"{base_url}/mcp",
            },
        )
        assert installed.status_code == 201, installed.text

        response = client.get("/api/v1/installed-pages")
        assert response.status_code == 200, response.text
        assert response.json()["pages"] == []


def test_web_scraper_routes_proxy_through_synapse(tmp_path: Path) -> None:
    with _json_server(
        {
            ("GET", "/api/mcp-meta"): (
                200,
                {
                    "server": {"name": "web-scraper"},
                    "tools_count": 12,
                    "prompts_count": 3,
                },
            ),
            ("GET", "/api/saves"): (
                200,
                {"items": [{"id": "save-1", "title": "First scrape"}]},
            ),
            ("GET", "/api/schedules"): (200, {"items": [{"id": "sch-1"}]}),
            ("GET", "/api/active"): (200, {"items": [{"id": "job-1", "status": "running"}]}),
            ("POST", "/api/scrape_url"): (200, {"save_id": "save-2"}),
            ("POST", "/api/generate_react"): (200, {"component": "export function Card(){ return <div />; }"}),
        }
    ) as base_url:
        client, _ = _harness(tmp_path)
        installed = client.post(
            "/api/v1/mcp-servers/install",
            json={
                "id": "web-scraper",
                "name": "Web Scraper",
                "transport": "http",
                "url": f"{base_url}/mcp",
            },
        )
        assert installed.status_code == 201, installed.text

        overview = client.get("/api/v1/installed-pages/web-scraper")
        assert overview.status_code == 200, overview.text
        assert overview.json()["status"] == "connected"
        assert overview.json()["tool_count"] == 12

        saves = client.get("/api/v1/installed-pages/web-scraper/saves")
        assert saves.status_code == 200, saves.text
        assert saves.json()["items"][0]["id"] == "save-1"

        scrape = client.post(
            "/api/v1/installed-pages/web-scraper/scrape-url",
            json={"url": "https://example.com"},
        )
        assert scrape.status_code == 200, scrape.text
        assert scrape.json()["save_id"] == "save-2"

        action = client.post(
            "/api/v1/installed-pages/web-scraper/actions/generate_react",
            json={"url": "https://example.com"},
        )
        assert action.status_code == 200, action.text
        assert "component" in action.json()


def test_web_scraper_overview_prefers_scraper_url_env_for_first_party_server(tmp_path: Path) -> None:
    with _json_server(
        {
            ("GET", "/api/mcp-meta"): (
                200,
                {
                    "server": {"name": "web-scraper"},
                    "tools_count": 12,
                    "prompts_count": 3,
                },
            ),
        }
    ) as base_url:
        client, _ = _harness(tmp_path)
        installed = client.post(
            "/api/v1/mcp-servers/install",
            json={
                "id": "web-scraper",
                "name": "Web Scraper",
                "transport": "http",
                "url": "http://127.0.0.1:12000/mcp",
                "env": {"SCRAPER_URL": base_url},
            },
        )
        assert installed.status_code == 201, installed.text

        overview = client.get("/api/v1/installed-pages/web-scraper")
        assert overview.status_code == 200, overview.text
        payload = overview.json()
        assert payload["status"] == "connected"
        assert payload["source_url"] == "http://127.0.0.1:12000/mcp"
        assert payload["base_url"] == base_url
        assert payload["docs_url"] == f"{base_url}/docs"


def test_web_scraper_harvest_save_persists_project_files(tmp_path: Path) -> None:
    client, storage = _harness(tmp_path)
    with storage.transaction() as conn:
        projects_module.create(
            conn,
            Project(
                id="design-lab",
                name="Design Lab",
                path=str(tmp_path / "design-lab"),
                launch_cmd="npm start",
            ),
        )

    response = client.post(
        "/api/v1/installed-pages/web-scraper/save-artifacts",
        json={
            "project_id": "design-lab",
            "reference_urls": ["https://example.com"],
            "provenance_mode": "regenerated-original-output",
            "originality_notes": "Adapted into the project's own tone and spacing.",
            "artifacts": [
                {
                    "name": "reference-brief.md",
                    "kind": "reference-brief",
                    "mime": "text/markdown",
                    "content": "# Reference brief\n\nCaptured from an authorized source.",
                },
                {
                    "name": "component-candidate.tsx",
                    "kind": "component",
                    "mime": "text/plain",
                    "content": "export function Hero(){ return <section />; }",
                },
            ],
        },
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["project_id"] == "design-lab"
    saved_names = [row["original_name"] for row in payload["saved"]]
    assert "design-harvest-manifest.json" in saved_names
    assert "reference-brief.md" in saved_names
    assert "component-candidate.tsx" in saved_names
