"""Tests for runtime-resolution fallbacks."""

from __future__ import annotations

from synapse_daemon import runtime_resolution


def test_resolve_command_finds_copilot_in_global_npm(
    tmp_path, monkeypatch
) -> None:
    appdata = tmp_path / "AppData" / "Roaming"
    local_appdata = tmp_path / "AppData" / "Local"
    copilot = appdata / "npm" / "copilot.cmd"
    copilot.parent.mkdir(parents=True, exist_ok=True)
    copilot.write_text("", encoding="utf-8")

    monkeypatch.setattr(runtime_resolution.shutil, "which", lambda _cmd: None)
    monkeypatch.setattr(runtime_resolution.sys, "platform", "win32")
    monkeypatch.setenv("APPDATA", str(appdata))
    monkeypatch.setenv("LOCALAPPDATA", str(local_appdata))

    assert runtime_resolution.resolve_command("copilot") == str(copilot)


def test_resolve_command_finds_copilot_in_winget_package_dir(
    tmp_path, monkeypatch
) -> None:
    appdata = tmp_path / "AppData" / "Roaming"
    local_appdata = tmp_path / "AppData" / "Local"
    copilot = (
        local_appdata
        / "Microsoft"
        / "WinGet"
        / "Packages"
        / "GitHub.Copilot_Test"
        / "copilot.exe"
    )
    copilot.parent.mkdir(parents=True, exist_ok=True)
    copilot.write_text("", encoding="utf-8")

    monkeypatch.setattr(runtime_resolution.shutil, "which", lambda _cmd: None)
    monkeypatch.setattr(runtime_resolution.sys, "platform", "win32")
    monkeypatch.setenv("APPDATA", str(appdata))
    monkeypatch.setenv("LOCALAPPDATA", str(local_appdata))

    assert runtime_resolution.resolve_command("copilot") == str(copilot)
