"""Tests for runtime-resolution fallbacks."""

from __future__ import annotations

from pathlib import Path

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


def test_resolve_command_empty_returns_none() -> None:
    assert runtime_resolution.resolve_command("") is None
    assert runtime_resolution.resolve_command("   ") is None


def test_resolve_command_returns_path_when_on_path(monkeypatch) -> None:
    # The common case: a bare PATH hit short-circuits before any OS-specific fallback.
    monkeypatch.setattr(runtime_resolution.shutil, "which", lambda _cmd: "/usr/bin/claude")
    assert runtime_resolution.resolve_command("claude") == "/usr/bin/claude"


def test_resolve_command_non_windows_without_path_hit_returns_none(monkeypatch) -> None:
    monkeypatch.setattr(runtime_resolution.shutil, "which", lambda _cmd: None)
    monkeypatch.setattr(runtime_resolution.sys, "platform", "linux")
    assert runtime_resolution.resolve_command("claude") is None


def test_resolve_command_python_falls_back_to_sys_executable(monkeypatch) -> None:
    # On Windows with no PATH hit, "python" resolves to the running interpreter,
    # which always exists -- so this is deterministic on any test host.
    monkeypatch.setattr(runtime_resolution.shutil, "which", lambda _cmd: None)
    monkeypatch.setattr(runtime_resolution.sys, "platform", "win32")
    assert runtime_resolution.resolve_command("python") == str(Path(runtime_resolution.sys.executable))


def test_resolve_command_finds_claude_in_global_npm(tmp_path, monkeypatch) -> None:
    appdata = tmp_path / "AppData" / "Roaming"
    claude = appdata / "npm" / "claude.cmd"
    claude.parent.mkdir(parents=True, exist_ok=True)
    claude.write_text("", encoding="utf-8")

    monkeypatch.setattr(runtime_resolution.shutil, "which", lambda _cmd: None)
    monkeypatch.setattr(runtime_resolution.sys, "platform", "win32")
    monkeypatch.setenv("APPDATA", str(appdata))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "AppData" / "Local"))

    assert runtime_resolution.resolve_command("claude") == str(claude)


def test_resolve_command_unknown_on_windows_returns_none(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(runtime_resolution.shutil, "which", lambda _cmd: None)
    monkeypatch.setattr(runtime_resolution.sys, "platform", "win32")
    monkeypatch.setenv("APPDATA", str(tmp_path / "AppData" / "Roaming"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "AppData" / "Local"))
    assert runtime_resolution.resolve_command("totally-unknown-binary") is None
