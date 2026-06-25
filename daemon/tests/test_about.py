"""Tests for the What's New + Roadmap surface (ADR-0019)."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from synapse_daemon.about import parse_changelog
from synapse_daemon.app import build_app
from synapse_daemon.storage import Storage
from synapse_daemon.ws import EventBus

SAMPLE = """# Changelog

## [Unreleased]

## [0.2.0] -- 2026-07-01

A short summary line for the release.

### Added
- A shiny new thing
- A second thing that wraps
  onto another line

### Fixed
- A nasty bug

## [0.1.0] -- 2026-06-01
### Added
- The first release
"""


def _harness(tmp_path: Path) -> TestClient:
    storage = Storage(tmp_path / "data")
    storage.open()
    storage.migrate()
    app = build_app(storage, EventBus())
    return TestClient(app, headers={"X-Synapse-Token": app.state.auth.local_token})


def test_parse_changelog_structure() -> None:
    versions = parse_changelog(SAMPLE)
    # The empty [Unreleased] is dropped.
    assert [v.version for v in versions] == ["0.2.0", "0.1.0"]
    v = versions[0]
    assert v.date == "2026-07-01"
    assert "short summary" in v.summary
    added = next(s for s in v.sections if s.title == "Added")
    assert added.items[0] == "A shiny new thing"
    # continuation line folds into the previous bullet
    assert "wraps onto another line" in added.items[1]
    assert any(s.title == "Fixed" for s in v.sections)


def test_changelog_endpoint_serves_real_file(tmp_path: Path) -> None:
    client = _harness(tmp_path)
    res = client.get("/api/v1/about/changelog")
    assert res.status_code == 200, res.text
    versions = res.json()["versions"]
    assert len(versions) > 0
    # every version has a version string + at least some content
    assert all(v["version"] for v in versions)
    assert any(v["sections"] for v in versions)


def test_roadmap_endpoint_has_statuses(tmp_path: Path) -> None:
    client = _harness(tmp_path)
    res = client.get("/api/v1/about/roadmap")
    assert res.status_code == 200, res.text
    items = res.json()["items"]
    assert len(items) > 0
    statuses = {i["status"] for i in items}
    # the curated roadmap spans shipped -> in_progress -> coming
    assert {"shipped", "in_progress", "coming"} <= statuses
    # shipped items reference their feature/ADR
    shipped = [i for i in items if i["status"] == "shipped"]
    assert shipped and all(i["title"] for i in shipped)
