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


def test_benchmark_validate_rejects_headless_when_rendered_expected(tmp_path):
    mod = _module()
    payload = {
        "warmup_seconds": 2.0, "duration_seconds": 10.0,
        "average_frame_ms": 0.2, "p95_frame_ms": 0.3,
        "max_frame_ms": 2.0, "average_fps": 5000.0,
        "graphics_device": "Null Device", "draw_calls_valid": False,
    }
    path = tmp_path / "headless.json"
    import json
    path.write_text(json.dumps(payload), encoding="utf-8")
    result = mod.benchmark_validate(str(path), "rendered")
    assert result["ok"] is False
    assert result["mode"] == "headless"
    assert any(item.startswith("mode_mismatch") for item in result["issues"])


def test_benchmark_validate_accepts_rendered_with_optional_counter_unavailable(tmp_path):
    mod = _module()
    payload = {
        "warmup_seconds": 2.0, "duration_seconds": 10.0,
        "average_frame_ms": 8.4, "p95_frame_ms": 8.5,
        "max_frame_ms": 16.7, "average_fps": 119.0,
        "graphics_device": "Example GPU",
        "system_used_memory_valid": True, "system_used_memory_bytes": 500_000_000,
        "draw_calls_valid": False,
    }
    path = tmp_path / "rendered.json"
    import json
    path.write_text(json.dumps(payload), encoding="utf-8")
    result = mod.benchmark_validate(str(path), "rendered")
    assert result["ok"] is True
    assert result["comparable_for_rendering"] is True
    assert "counter_unavailable:draw_calls" in result["warnings"]

def test_benchmark_validate_verifies_screenshot_hash(tmp_path):
    mod = _module()
    import json, hashlib
    shot = tmp_path / "proof.png"
    shot.write_bytes(b"png-proof")
    payload = {
        "warmup_seconds": 2.0, "duration_seconds": 10.0,
        "average_frame_ms": 8.3, "p95_frame_ms": 8.4,
        "max_frame_ms": 16.7, "average_fps": 120.0,
        "graphics_device": "Example GPU",
        "benchmark_vsync_count": 0, "benchmark_target_frame_rate": 120,
        "screenshot_path": str(shot), "screenshot_bytes": shot.stat().st_size,
        "screenshot_sha256": hashlib.sha256(shot.read_bytes()).hexdigest(),
    }
    path = tmp_path / "rendered.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    result = mod.benchmark_validate(str(path), "rendered", True, True)
    assert result["ok"] is True
    assert result["screenshot_verified"] is True
    assert result["presentation_controlled"] is True
    payload["screenshot_sha256"] = "0" * 64
    path.write_text(json.dumps(payload), encoding="utf-8")
    bad = mod.benchmark_validate(str(path), "rendered", True, True)
    assert bad["ok"] is False
    assert "screenshot_sha256_mismatch" in bad["issues"]


def test_benchmark_validate_can_require_controlled_presentation(tmp_path):
    mod = _module()
    import json
    payload = {
        "warmup_seconds": 2.0, "duration_seconds": 10.0,
        "average_frame_ms": 8.3, "p95_frame_ms": 8.4,
        "max_frame_ms": 16.7, "average_fps": 120.0,
        "graphics_device": "Example GPU",
    }
    path = tmp_path / "rendered.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    result = mod.benchmark_validate(str(path), "rendered", False, True)
    assert result["ok"] is False
    assert "controlled_presentation_required" in result["issues"]


def test_benchmark_wait_requires_stable_host_and_verifies_fingerprint(tmp_path, monkeypatch):
    mod = _module()
    import hashlib, json, subprocess

    source = tmp_path / "source.cs"
    source.write_text("stable-source", encoding="utf-8")
    exe = tmp_path / "game.exe"
    exe.write_bytes(b"stable-binary")
    output = tmp_path / "result.json"
    manifest = tmp_path / "preflight.json"
    manifest.write_text(json.dumps({
        "source_file_sha256": {
            "source.cs": hashlib.sha256(source.read_bytes()).hexdigest(),
        },
        "build": {
            "exe_sha256": hashlib.sha256(exe.read_bytes()).hexdigest(),
        },
    }), encoding="utf-8")

    cpu_samples = iter([92.0, 50.0, 55.0])
    monkeypatch.setattr(mod, "_cpu_load_percent", lambda: next(cpu_samples))
    monkeypatch.setattr(mod, "_blocked_processes", lambda names: [])
    monkeypatch.setattr(mod.time, "sleep", lambda _seconds: None)

    launched = {}
    def fake_run(command, cwd, timeout_seconds):
        launched["command"] = command
        launched["cwd"] = cwd
        launched["timeout"] = timeout_seconds
        output.write_text("{}", encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, "", "")
    monkeypatch.setattr(mod, "_run_benchmark_process", fake_run)

    result = mod.benchmark_wait(
        str(exe), str(output), ["--", "--demo"], cwd=str(tmp_path),
        max_cpu_percent=65.0, stable_samples=2, sample_interval_seconds=0,
        wait_timeout_seconds=30, process_timeout_seconds=10,
        block_processes=["Unity.exe"], fingerprint_manifest=str(manifest),
        output_flag="--output",
    )

    assert result["ok"] is True
    assert result["launch_cpu_percent"] == 55.0
    assert [item["cpu_percent"] for item in result["samples"]] == [92.0, 50.0, 55.0]
    assert result["fingerprint"]["ok"] is True
    assert result["fingerprint"]["source_files_checked"] == 1
    assert result["fingerprint"]["executable_checked"] is True
    assert launched["command"] == [str(exe.resolve()), "--demo", "--output", str(output.resolve())]


def test_benchmark_wait_fails_closed_on_fingerprint_mismatch(tmp_path, monkeypatch):
    mod = _module()
    import json

    source = tmp_path / "source.cs"
    source.write_text("changed", encoding="utf-8")
    exe = tmp_path / "game.exe"
    exe.write_bytes(b"binary")
    output = tmp_path / "result.json"
    manifest = tmp_path / "preflight.json"
    manifest.write_text(json.dumps({
        "source_file_sha256": {"source.cs": "0" * 64},
    }), encoding="utf-8")
    monkeypatch.setattr(mod, "_run_benchmark_process", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("must not launch")))

    result = mod.benchmark_wait(
        str(exe), str(output), cwd=str(tmp_path), fingerprint_manifest=str(manifest),
        sample_interval_seconds=0, wait_timeout_seconds=0,
    )

    assert result["ok"] is False
    assert result["blocked_reason"] == "benchmark_fingerprint_mismatch"
    assert result["fingerprint"]["mismatches"][0]["reason"] == "sha256_mismatch"


def test_benchmark_wait_times_out_when_host_stays_busy(tmp_path, monkeypatch):
    mod = _module()

    exe = tmp_path / "game.exe"
    exe.write_bytes(b"binary")
    output = tmp_path / "result.json"
    monkeypatch.setattr(mod, "_cpu_load_percent", lambda: 99.0)
    monkeypatch.setattr(mod, "_blocked_processes", lambda names: [])
    monkeypatch.setattr(mod, "_run_benchmark_process", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("must not launch")))

    result = mod.benchmark_wait(
        str(exe), str(output), cwd=str(tmp_path), max_cpu_percent=65.0,
        stable_samples=2, sample_interval_seconds=0, wait_timeout_seconds=0,
    )

    assert result["ok"] is False
    assert result["blocked_reason"] == "host_idle_timeout"
    assert result["samples"][-1]["cpu_percent"] == 99.0
