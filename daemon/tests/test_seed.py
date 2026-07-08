"""Tests for ``synapse_daemon.seed`` (first-run defaults)."""

from __future__ import annotations

from pathlib import Path

from synapse_daemon import projects as projects_module
from synapse_daemon.projects import ProjectUpdate, update
from synapse_daemon.seed import (
    SYNAPSE_SELF_PROJECT_ID,
    WBSCRPER_PROJECT_ID,
    reconcile_web_scraper_project,
    seed_default_projects,
)
from synapse_daemon.storage import Storage


def _storage(tmp_path: Path) -> Storage:
    s = Storage(tmp_path / "data")
    s.open()
    s.migrate()
    return s


def test_seed_creates_wbscrper_when_missing(tmp_path: Path) -> None:
    s = _storage(tmp_path)
    try:
        created = seed_default_projects(s, parent_dir=tmp_path)
        assert WBSCRPER_PROJECT_ID in created
        assert SYNAPSE_SELF_PROJECT_ID in created
        project = projects_module.get(s.conn, WBSCRPER_PROJECT_ID)
        assert project.name == "Web Scraper"
        assert project.launch_cmd == "npm start"
        assert project.health.kind == "http"
        synapse_self = projects_module.get(s.conn, SYNAPSE_SELF_PROJECT_ID)
        assert synapse_self.name == "Synapse Self"
        assert synapse_self.launch_cmd == "synapse.cmd"
    finally:
        s.close()


def test_seed_is_idempotent(tmp_path: Path) -> None:
    s = _storage(tmp_path)
    try:
        first = seed_default_projects(s, parent_dir=tmp_path)
        second = seed_default_projects(s, parent_dir=tmp_path)
        assert WBSCRPER_PROJECT_ID in first
        assert SYNAPSE_SELF_PROJECT_ID in first
        assert second == []  # already present, nothing seeded
    finally:
        s.close()


def test_seed_leaves_user_edits_alone(tmp_path: Path) -> None:
    s = _storage(tmp_path)
    try:
        seed_default_projects(s, parent_dir=tmp_path)
        # Simulate user rename.
        with s.transaction() as conn:
            update(conn, WBSCRPER_PROJECT_ID, ProjectUpdate(name="My Scraper"))

        seed_default_projects(s, parent_dir=tmp_path)  # re-seed
        project = projects_module.get(s.conn, WBSCRPER_PROJECT_ID)
        assert project.name == "My Scraper"  # rename preserved
    finally:
        s.close()


def test_reconcile_web_scraper_project_rehomes_stale_default_path(tmp_path: Path) -> None:
    s = _storage(tmp_path)
    checkout = tmp_path / "vendor" / "web-scraper"
    checkout.mkdir(parents=True, exist_ok=True)
    (checkout / "mcp-server.js").write_text("// fake web scraper mcp\n", encoding="utf-8")
    (checkout / "package.json").write_text(
        '{"name":"web-scraper-app","scripts":{"mcp:http":"node mcp-server.js --http"}}',
        encoding="utf-8",
    )
    try:
        seed_default_projects(s, parent_dir=tmp_path)
        with s.transaction() as conn:
            update(conn, WBSCRPER_PROJECT_ID, ProjectUpdate(path=str(tmp_path / "stale-wbscrper")))
        changed = reconcile_web_scraper_project(s, source_path=checkout)
        project = projects_module.get(s.conn, WBSCRPER_PROJECT_ID)
        assert changed is True
        assert Path(project.path) == checkout.resolve()
    finally:
        s.close()
