"""Regression tests for bundled/source runtime path resolution."""

from __future__ import annotations

from pathlib import Path

from synapse_daemon import runtime_paths


def test_resources_root_uses_repo_root_in_source_mode() -> None:
    assert runtime_paths.is_frozen() is False
    assert runtime_paths.resources_root() == runtime_paths.repo_root()


def test_resources_root_uses_resources_parent_when_frozen(monkeypatch) -> None:
    monkeypatch.setattr(runtime_paths.sys, "frozen", True, raising=False)
    monkeypatch.setattr(
        runtime_paths.sys,
        "executable",
        str(Path(r"C:\Synapse\resources\daemon\synapse-daemon.exe")),
        raising=False,
    )

    assert runtime_paths.resources_root() == Path(r"C:\Synapse\resources")
    assert runtime_paths.bundled_tools_dir() == Path(r"C:\Synapse\resources\tools")
    assert runtime_paths.bundled_marketplace_sample() == Path(
        r"C:\Synapse\resources\docs\marketplace-sample.json"
    )
    assert runtime_paths.bundled_ai_bundles_sample() == Path(
        r"C:\Synapse\resources\docs\ai-bundles-sample.json"
    )
