"""Tests for ``synapse_daemon.seed`` (first-run defaults)."""

from __future__ import annotations

from pathlib import Path

from synapse_daemon import projects as projects_module
from synapse_daemon.seed import WBSCRPER_PROJECT_ID, seed_default_projects
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
        project = projects_module.get(s.conn, WBSCRPER_PROJECT_ID)
        assert project.name == "Web Scraper"
        assert project.launch_cmd == "npm start"
        assert project.health.kind == "http"
    finally:
        s.close()


def test_seed_is_idempotent(tmp_path: Path) -> None:
    s = _storage(tmp_path)
    try:
        first = seed_default_projects(s, parent_dir=tmp_path)
        second = seed_default_projects(s, parent_dir=tmp_path)
        assert WBSCRPER_PROJECT_ID in first
        assert second == []  # already present, nothing seeded
    finally:
        s.close()


def test_seed_leaves_user_edits_alone(tmp_path: Path) -> None:
    s = _storage(tmp_path)
    try:
        seed_default_projects(s, parent_dir=tmp_path)
        # Simulate user rename.
        from synapse_daemon.projects import ProjectUpdate, update

        with s.transaction() as conn:
            update(conn, WBSCRPER_PROJECT_ID, ProjectUpdate(name="My Scraper"))

        seed_default_projects(s, parent_dir=tmp_path)  # re-seed
        project = projects_module.get(s.conn, WBSCRPER_PROJECT_ID)
        assert project.name == "My Scraper"  # rename preserved
    finally:
        s.close()
