"""Mocked native ChatGPT UI fleet tests: no browser, no live daemon, no real git writes."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from synapse_daemon.fleet_controller import (
    FleetController, _safe_lanes, _safe_url, archive_code, dispatch_code,
)


SHA = "a" * 40
PROJECT = "https://chatgpt.com/g/g-p-test-12345/demo"


class FakeGit:
    def __init__(self) -> None:
        self.calls: list[tuple[list[str], Path | None]] = []

    def __call__(self, args: list[str], cwd: Path | None) -> str:
        self.calls.append((args, cwd))
        if args[:2] == ["worktree", "add"]:
            Path(args[4]).mkdir(parents=True)
            return ""
        return SHA


class FakeBrowser:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.archives: int = 0
        self.count: int = 0

    def __call__(self, code: str) -> dict:
        self.calls.append(code)
        if "getByText('Archive'" in code:
            self.archives += 1
            return {"archived": True}
        self.count += 1
        return {"url": f"https://chatgpt.com/c/test-{self.count}",
                "synapse2Mention": True, "ownedTabConfirmed": True, "connectors": ["Connect To Synapse"]}


@pytest.fixture
def scenario(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".git").mkdir()
    clock = [datetime(2026, 10, 17, 10, 0, tzinfo=timezone.utc)]
    browser = FakeBrowser()
    git = FakeGit()
    ctl = FleetController(tmp_path, browser=browser, runner=git, clock=lambda: clock[0])
    return ctl, repo, browser, git, clock


def start(ctl, repo, **kwargs):
    return ctl.start(project_url=PROJECT, repo=str(repo), base_ref="HEAD",
                     lanes=[{"name": "alpha", "task": "Write alpha", "files": ["alpha.txt"]},
                            {"name": "beta", "task": "Write beta", "files": ["beta.txt"]}],
                     **kwargs)


def test_validates_urls_lanes_and_file_collisions():
    assert _safe_url(PROJECT) == PROJECT
    for url in ["http://chatgpt.com/g/abc", "https://evil.example/g/abc",
                "https://chatgpt.com/?key=hi"]:
        with pytest.raises(ValueError):
            _safe_url(url)
    with pytest.raises(ValueError, match="overlaps"):
        _safe_lanes(workers=None, lanes=[
            {"name": "a", "task": "work", "files": ["src/a.py"]},
            {"name": "b", "task": "work", "files": ["src/a.py"]}])
    with pytest.raises(ValueError, match="traversal"):
        _safe_lanes(workers=None, lanes=[{"name": "a", "task": "work", "files": ["../private"]}])
    with pytest.raises(ValueError):
        _safe_lanes(workers=13, lanes=None)


def test_creates_all_worktrees_before_dispatch_and_persists(scenario):
    ctl, repo, browser, git, _ = scenario
    result = start(ctl, repo)
    assert len(result["lanes"]) == 2
    assert [r["state"] for r in result["lanes"]] == ["busy", "busy"]
    assert len([c for c, _ in git.calls if c[:2] == ["worktree", "add"]]) == 2
    assert len(browser.calls) == 2
    assert "Connect To Synapse" in browser.calls[0]
    assert "Synapse2" in browser.calls[0]
    assert "Select ChatGPT model" in browser.calls[0]
    assert ctl.status(result["id"])[0]["lanes"][0]["branch"].startswith("fleet/")
    assert len(list((ctl.root).glob("*.json"))) == 1


def test_idle_sha_reconciliation_and_fresh_chat_archive(scenario):
    ctl, repo, browser, _, _ = scenario
    result = start(ctl, repo)
    fleet_id = result["id"]
    record = ctl._load(fleet_id)
    alpha = record["lanes"][0]
    Path(alpha["status_path"]).write_text(f"idle {SHA} more work")
    beta = record["lanes"][1]
    Path(beta["status_path"]).write_text(f"idle {'b' * 40} DONE")
    current = ctl.report(fleet_id)
    assert current["lanes"][0]["state"] == "idle"
    assert current["lanes"][1]["state"] == "blocked"
    errors = ctl.nudge(fleet_id)
    assert not errors
    assert browser.archives == 1
    assert len(browser.calls) == 4  # 2 initial dispatch + archive + fresh dispatch
    assert ctl.report(fleet_id)["lanes"][0]["round"] == 2


def test_done_archived_once_without_redispatch(scenario):
    ctl, repo, browser, _, _ = scenario
    id_ = start(ctl, repo)["id"]
    record = ctl._load(id_)
    for lane in record["lanes"]:
        Path(lane["status_path"]).write_text(f"idle {SHA} DONE")
    assert [x["state"] for x in ctl.report(id_)["lanes"]] == ["done", "done"]
    ctl.nudge(id_)
    assert browser.archives == 2
    ctl.nudge(id_)
    assert browser.archives == 2
    assert ctl.report(id_)["lanes"][0]["round"] == 1


def test_stale_after_two_hours_and_timer_opt_in(scenario):
    ctl, repo, browser, _, clock = scenario
    id_ = start(ctl, repo, interval_minutes=15)["id"]
    lane = ctl._load(id_)["lanes"][0]
    Path(lane["status_path"]).write_text("working 2026-10-17T10:00:00+00:00")
    clock[0] += timedelta(minutes=119)
    assert ctl.report(id_)["lanes"][0]["state"] == "busy"
    clock[0] += timedelta(minutes=2)
    assert ctl.report(id_)["lanes"][0]["state"] == "stale"
    ctl.tick()
    assert ctl.report(id_)["lanes"][0]["round"] == 2
    ctl.stop(id_)
    clock[0] += timedelta(hours=3)
    before = len(browser.calls)
    ctl.tick()
    assert len(browser.calls) == before


def test_subfleets_limit_and_stop_propagation(scenario):
    ctl, repo, _, _, _ = scenario
    parent = ctl.start(project_url=PROJECT, repo=str(repo), base_ref="HEAD",
                       workers=1)["id"]
    child = ctl.start(project_url=PROJECT, repo=str(repo), base_ref="HEAD",
                      workers=1, parent=parent)["id"]
    with pytest.raises(ValueError, match="depth"):
        ctl.start(project_url=PROJECT, repo=str(repo), base_ref="HEAD",
                  workers=1, parent=child)
    ctl.stop(parent)
    assert ctl.report(parent)["enabled"] is False
    assert ctl.report(child)["enabled"] is False


def test_source_only_archives_and_requires_mention():
    code = archive_code("https://chatgpt.com/c/test")
    assert "Archive" in code and "Delete" not in code
    script = dispatch_code(PROJECT, "hello", ["Connect To Synapse", "Another Connector"], "High")
    assert "app-mention-name" in script
    assert "GPT-6" in script
    assert "cfg.plugins" in script
    assert "p.context().newPage()" not in script
