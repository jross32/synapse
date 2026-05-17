"""Tests for the multi-stack project detector (v0.1.8.5)."""

from __future__ import annotations

import json
from pathlib import Path

from synapse_daemon.discovery import detect_project, scan_directory


def _mk(tmp: Path, name: str, files: dict[str, str]) -> Path:
    """Create a project folder with the given files."""

    d = tmp / name
    d.mkdir(parents=True)
    for rel, content in files.items():
        fp = d / rel
        fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_text(content, encoding="utf-8")
    return d


# ── per-stack detection ──────────────────────────────────────────────────


def test_node_vite_project(tmp_path: Path) -> None:
    d = _mk(tmp_path, "my-vite-app", {
        "package.json": json.dumps({
            "name": "my-vite-app",
            "scripts": {"dev": "vite", "build": "vite build"},
            "devDependencies": {"vite": "^5.0.0"},
        }),
    })
    result = detect_project(d)
    assert result is not None
    assert result.stack == "node"
    assert result.framework == "vite"
    assert result.suggested_launch_cmd == "npm run dev"
    assert result.suggested_port == 5173
    assert result.confidence >= 0.9
    assert any(c.command == "npm run build" for c in result.candidates)


def test_node_start_script(tmp_path: Path) -> None:
    d = _mk(tmp_path, "express-api", {
        "package.json": json.dumps({
            "scripts": {"start": "node index.js"},
            "dependencies": {"express": "^4.0.0"},
        }),
    })
    result = detect_project(d)
    assert result is not None
    assert result.framework == "express"
    assert result.suggested_launch_cmd == "npm start"


def test_python_django(tmp_path: Path) -> None:
    d = _mk(tmp_path, "django-site", {"manage.py": "# django", "requirements.txt": "django"})
    result = detect_project(d)
    assert result is not None
    assert result.stack == "python-django"
    assert result.suggested_launch_cmd == "python manage.py runserver"
    assert result.suggested_port == 8000


def test_python_entry_file(tmp_path: Path) -> None:
    d = _mk(tmp_path, "py-tool", {"main.py": "print('hi')"})
    result = detect_project(d)
    assert result is not None
    assert result.stack == "python"
    assert result.suggested_launch_cmd == "python main.py"


def test_python_loose_files_not_a_project(tmp_path: Path) -> None:
    # A folder with only library .py files (no marker, no entry point) must
    # NOT be flagged -- that's the discovery-noise guard.
    d = _mk(tmp_path, "just-helpers", {"utils.py": "x = 1", "helpers.py": "y = 2"})
    assert detect_project(d) is None


def test_rust_project(tmp_path: Path) -> None:
    d = _mk(tmp_path, "rust-cli", {"Cargo.toml": "[package]\nname='x'"})
    result = detect_project(d)
    assert result is not None
    assert result.stack == "rust"
    assert result.suggested_launch_cmd == "cargo run"


def test_go_project(tmp_path: Path) -> None:
    d = _mk(tmp_path, "go-svc", {"go.mod": "module x"})
    result = detect_project(d)
    assert result is not None
    assert result.stack == "go"
    assert result.suggested_launch_cmd == "go run ."


def test_docker_compose(tmp_path: Path) -> None:
    d = _mk(tmp_path, "stack", {"docker-compose.yml": "services: {}"})
    result = detect_project(d)
    assert result is not None
    assert result.stack == "docker-compose"
    assert result.suggested_launch_cmd == "docker compose up"


def test_makefile_with_run_target(tmp_path: Path) -> None:
    d = _mk(tmp_path, "make-proj", {"Makefile": "run:\n\t./app\nbuild:\n\tcc app.c"})
    result = detect_project(d)
    assert result is not None
    assert result.stack == "make"
    assert result.suggested_launch_cmd == "make run"


def test_static_site(tmp_path: Path) -> None:
    d = _mk(tmp_path, "landing", {"index.html": "<html></html>"})
    result = detect_project(d)
    assert result is not None
    assert result.stack == "static"


def test_bare_git_repo_low_confidence(tmp_path: Path) -> None:
    d = tmp_path / "mystery"
    d.mkdir()
    (d / ".git").mkdir()
    result = detect_project(d)
    assert result is not None
    assert result.stack == "unknown"
    assert result.suggested_launch_cmd is None
    assert result.confidence < 0.5


def test_empty_folder_is_not_a_project(tmp_path: Path) -> None:
    d = tmp_path / "empty"
    d.mkdir()
    assert detect_project(d) is None


def test_id_is_kebab_case(tmp_path: Path) -> None:
    d = _mk(tmp_path, "My_Cool App", {"package.json": "{}"})
    result = detect_project(d)
    assert result is not None
    assert result.suggested_id == "my-cool-app"


# ── scanning ─────────────────────────────────────────────────────────────


def test_scan_finds_multiple_projects(tmp_path: Path) -> None:
    _mk(tmp_path, "app-one", {"package.json": json.dumps({"scripts": {"dev": "vite"}})})
    _mk(tmp_path, "app-two", {"Cargo.toml": "[package]"})
    _mk(tmp_path, "app-three", {"main.py": "pass"})
    results = scan_directory(tmp_path, max_depth=1)
    stacks = {r.stack for r in results}
    assert {"node", "rust", "python"} <= stacks
    assert len(results) == 3


def test_scan_skips_node_modules_and_hidden(tmp_path: Path) -> None:
    _mk(tmp_path, "real-app", {"package.json": json.dumps({"scripts": {"dev": "x"}})})
    _mk(tmp_path, "node_modules", {"package.json": "{}"})
    _mk(tmp_path, ".hidden", {"package.json": "{}"})
    results = scan_directory(tmp_path, max_depth=2)
    # Compare by folder basename -- pytest's tmp dir is itself named after the
    # test, so a naive substring check on r.path would false-positive.
    found = {Path(r.path).name for r in results}
    assert "real-app" in found
    assert "node_modules" not in found
    assert ".hidden" not in found


def test_scan_root_itself_not_treated_as_project(tmp_path: Path) -> None:
    # The root has a package.json AND a child project -- the root must not
    # short-circuit the walk.
    (tmp_path / "package.json").write_text(json.dumps({"scripts": {"dev": "x"}}), encoding="utf-8")
    _mk(tmp_path, "child-app", {"go.mod": "module x"})
    results = scan_directory(tmp_path, max_depth=1)
    assert any(r.stack == "go" for r in results)


def test_scan_sorts_by_confidence(tmp_path: Path) -> None:
    _mk(tmp_path, "high", {"package.json": json.dumps({"scripts": {"dev": "vite"}})})
    bare = tmp_path / "low"
    bare.mkdir()
    (bare / ".git").mkdir()
    results = scan_directory(tmp_path, max_depth=1)
    assert results[0].confidence >= results[-1].confidence
