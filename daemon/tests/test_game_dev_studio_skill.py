from __future__ import annotations
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "templates" / "skills" / "game-dev-studio" / "scripts" / "game_dev_studio.py"


def _module():
    spec = importlib.util.spec_from_file_location("game_dev_studio_skill", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_unity_create_refuses_existing_path(tmp_path):
    mod = _module()
    target = tmp_path / "existing"
    target.mkdir()
    result = mod.unity_create(str(target), None, 1.0)
    assert result["ok"] is False
    assert result["blocked_reason"] == "project_path_exists"
    assert target.exists()


def test_unity_create_blocked_preflight_leaves_no_project(tmp_path, monkeypatch):
    mod = _module()
    target = tmp_path / "new-project"
    monkeypatch.setattr(mod, "unity_preflight", lambda editor, minimum: {
        "ok": False,
        "blocked_reason": "unity_license_required",
    })
    result = mod.unity_create(str(target), None, 1.0)
    assert result["ok"] is False
    assert result["blocked_reason"] == "unity_license_required"
    assert not target.exists()


def test_unity_preflight_low_disk_does_not_launch_editor(monkeypatch):
    mod = _module()
    monkeypatch.setattr(mod, "_find_unity_editors", lambda: [{"version": "x", "path": "Unity.exe"}])
    monkeypatch.setattr(mod, "_disk_headroom", lambda path=None: {"path": "C:/", "free_gb": 2.0, "used_gb": 1.0, "total_gb": 3.0})
    monkeypatch.setattr(mod, "_run", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("Unity must not launch")))
    result = mod.unity_preflight(None, 15.0)
    assert result["ok"] is False
    assert result["blocked_reason"] == "low_disk_space"


def test_detect_project_recognizes_unity_version(tmp_path):
    mod = _module()
    (tmp_path / "Assets").mkdir()
    settings = tmp_path / "ProjectSettings"
    settings.mkdir()
    (settings / "ProjectVersion.txt").write_text("m_EditorVersion: 6000.4.0f1\n", encoding="utf-8")
    result = mod.detect_project(str(tmp_path))
    assert result["engine"] == "unity"
    assert result["engine_version"] == "6000.4.0f1"
