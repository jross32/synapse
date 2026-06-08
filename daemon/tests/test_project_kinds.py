"""Tests for project classification (v0.1.19)."""

from __future__ import annotations

import json
from pathlib import Path

from synapse_daemon.discovery import detect_project
from synapse_daemon.projects import Project, ProjectKind, create, get
from synapse_daemon.storage import Storage


# ── helpers ────────────────────────────────────────────────────────────────


def _mk(root: Path, name: str, files: dict[str, str]) -> Path:
    d = root / name
    d.mkdir(parents=True)
    for rel, content in files.items():
        target = d / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    return d


# ── discovery classification ──────────────────────────────────────────────


def test_node_vite_app_is_classified_as_ui(tmp_path: Path) -> None:
    d = _mk(
        tmp_path, "ui-app",
        {"package.json": json.dumps({
            "name": "ui-app",
            "scripts": {"dev": "vite"},
            "devDependencies": {"vite": "^5.0.0"},
        })},
    )
    detected = detect_project(d)
    assert detected is not None
    assert detected.kind == "ui"


def test_node_express_backend_is_classified_as_service(tmp_path: Path) -> None:
    d = _mk(
        tmp_path, "api",
        {"package.json": json.dumps({
            "name": "api",
            "scripts": {"start": "node server.js"},
            "dependencies": {"express": "^4.0.0"},
        })},
    )
    assert detect_project(d).kind == "service"


def test_node_mcp_server_detected_by_dep(tmp_path: Path) -> None:
    d = _mk(
        tmp_path, "tool-mcp",
        {"package.json": json.dumps({
            "name": "my-tool-mcp",
            "scripts": {"start": "node mcp.js"},
            "dependencies": {"@modelcontextprotocol/sdk": "^1.0.0"},
        })},
    )
    assert detect_project(d).kind == "mcp-server"


def test_node_mcp_server_detected_by_filename(tmp_path: Path) -> None:
    d = _mk(
        tmp_path, "wbscrper",
        {
            "package.json": json.dumps({"name": "wbscrper", "scripts": {"start": "node server.js"}}),
            "mcp-server.js": "module.exports = {}",
        },
    )
    assert detect_project(d).kind == "mcp-server"


def test_node_mcp_server_detected_by_script_name(tmp_path: Path) -> None:
    d = _mk(
        tmp_path, "scraper-mcp",
        {"package.json": json.dumps({
            "name": "scraper",
            "scripts": {"start": "node x.js", "mcp": "node mcp.js"},
        })},
    )
    assert detect_project(d).kind == "mcp-server"


def test_python_fastapi_is_service(tmp_path: Path) -> None:
    d = _mk(
        tmp_path, "api",
        {"pyproject.toml": '[project]\nname="api"\ndependencies = ["fastapi>=0.100"]\n'},
    )
    assert detect_project(d).kind == "service"


def test_python_mcp_server_detected_by_dep(tmp_path: Path) -> None:
    d = _mk(
        tmp_path, "mcp-thing",
        {"pyproject.toml": '[project]\nname="thing"\ndependencies = ["mcp>=1.0", "httpx"]\n'},
    )
    assert detect_project(d).kind == "mcp-server"


def test_python_single_file_is_script(tmp_path: Path) -> None:
    d = _mk(tmp_path, "oneshot", {"main.py": "print('hi')\n"})
    assert detect_project(d).kind == "script"


def test_static_index_is_ui(tmp_path: Path) -> None:
    d = _mk(tmp_path, "site", {"index.html": "<h1>hi</h1>"})
    assert detect_project(d).kind == "ui"


def test_docker_compose_is_service(tmp_path: Path) -> None:
    d = _mk(tmp_path, "stack", {"docker-compose.yml": "services:\n  app: {}\n"})
    assert detect_project(d).kind == "service"


def test_rust_project_is_app(tmp_path: Path) -> None:
    d = _mk(tmp_path, "rs", {"Cargo.toml": '[package]\nname = "rs"\nversion = "0.1.0"\n'})
    assert detect_project(d).kind == "app"


# ── persistence round-trip ────────────────────────────────────────────────


def test_kind_round_trips_through_sqlite(tmp_path: Path) -> None:
    s = Storage(tmp_path / "data")
    s.open()
    s.migrate()
    try:
        with s.transaction() as conn:
            create(conn, Project(
                id="wbscrper",
                name="Web Scraper",
                path="C:/x",
                launch_cmd="npm start",
                kind=ProjectKind.MCP_SERVER,
            ))
        loaded = get(s.conn, "wbscrper")
        assert loaded.kind == ProjectKind.MCP_SERVER
    finally:
        s.close()


def test_kind_defaults_to_app_when_omitted(tmp_path: Path) -> None:
    s = Storage(tmp_path / "data")
    s.open()
    s.migrate()
    try:
        with s.transaction() as conn:
            create(conn, Project(
                id="plain", name="Plain", path="C:/x", launch_cmd="x",
            ))
        assert get(s.conn, "plain").kind == ProjectKind.APP
    finally:
        s.close()
