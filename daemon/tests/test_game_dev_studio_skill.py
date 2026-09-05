from __future__ import annotations
import importlib.util
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "templates" / "skills" / "game-dev-studio" / "scripts" / "game_dev_studio.py"


def _module():
    spec = importlib.util.spec_from_file_location("game_dev_studio_skill", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    previous = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = previous
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


def test_unity_preflight_reports_terms_window_before_launch(monkeypatch):
    mod = _module()
    monkeypatch.setattr(mod, "_find_unity_editors", lambda: [{"version": "x", "path": "Unity.exe"}])
    monkeypatch.setattr(mod, "_disk_headroom", lambda path=None: {"path": "C:/", "free_gb": 20.0, "used_gb": 1.0, "total_gb": 21.0})
    monkeypatch.setattr(mod, "_unity_interactive_blocker", lambda: {
        "blocked_reason": "unity_terms_required",
        "needs_interactive_action": True,
        "message": "Unity Editor is waiting for the user to review and accept its software terms.",
        "window_title": "Unity Editor Software Terms",
    })
    monkeypatch.setattr(mod, "_run", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("Unity must not launch")))
    result = mod.unity_preflight(None, 15.0)
    assert result["ok"] is False
    assert result["blocked_reason"] == "unity_terms_required"
    assert result["needs_interactive_action"] is True
    assert result["window_title"] == "Unity Editor Software Terms"


def test_unity_preflight_classifies_headless_timeout(tmp_path, monkeypatch):
    mod = _module()
    import subprocess

    editor = tmp_path / "Unity.exe"
    editor.write_bytes(b"stub")
    monkeypatch.setattr(mod, "_find_unity_editors", lambda: [{"version": "x", "path": str(editor)}])
    monkeypatch.setattr(mod, "_disk_headroom", lambda path=None: {"path": str(tmp_path), "free_gb": 20.0, "used_gb": 1.0, "total_gb": 21.0})
    monkeypatch.setattr(mod, "_unity_interactive_blocker", lambda: None)

    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd=["Unity.exe"], timeout=180, output="partial out", stderr="partial err")

    monkeypatch.setattr(mod, "_run", timeout)
    result = mod.unity_preflight(None, 15.0)
    assert result["ok"] is False
    assert result["blocked_reason"] == "unity_preflight_timeout"
    assert result["needs_interactive_action"] is False
    assert "partial out" in result["log_tail"]
    assert "partial err" in result["log_tail"]


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

    cpu_samples = iter([92.0, 50.0, 55.0, 54.0])
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


def test_benchmark_wait_treats_probe_failure_as_busy(tmp_path, monkeypatch):
    mod = _module()

    exe = tmp_path / "game.exe"
    exe.write_bytes(b"binary")
    output = tmp_path / "result.json"
    monkeypatch.setattr(mod, "_cpu_load_percent", lambda: 40.0)
    monkeypatch.setattr(mod, "_blocked_processes", lambda names: (_ for _ in ()).throw(TimeoutError("process probe saturated")))
    monkeypatch.setattr(mod, "_run_benchmark_process", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("must not launch")))

    result = mod.benchmark_wait(
        str(exe), str(output), cwd=str(tmp_path), max_cpu_percent=65.0,
        stable_samples=1, sample_interval_seconds=0, wait_timeout_seconds=0,
    )

    assert result["ok"] is False
    assert result["blocked_reason"] == "host_idle_timeout"
    assert result["samples"][-1]["stable_count"] == 0
    assert result["samples"][-1]["blocked_processes"] == ["process_probe_unavailable"]
    assert result["samples"][-1]["probe_errors"][0].startswith("process_probe:TimeoutError")


def test_benchmark_wait_fails_closed_when_prelaunch_probe_breaks(tmp_path, monkeypatch):
    mod = _module()

    exe = tmp_path / "game.exe"
    exe.write_bytes(b"binary")
    output = tmp_path / "result.json"
    probe_calls = iter([
        (40.0, [], []),
        (40.0, ["process_probe_unavailable"], ["process_probe:TimeoutError:saturated"]),
    ])
    monkeypatch.setattr(mod, "_probe_host_state", lambda names: next(probe_calls))
    monkeypatch.setattr(mod, "_run_benchmark_process", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("must not launch")))

    result = mod.benchmark_wait(
        str(exe), str(output), cwd=str(tmp_path), max_cpu_percent=65.0,
        stable_samples=1, sample_interval_seconds=0, wait_timeout_seconds=30,
    )

    assert result["ok"] is False
    assert result["blocked_reason"] == "host_probe_failed_before_launch"
    assert result["blocked_processes"] == ["process_probe_unavailable"]
    assert result["probe_errors"][0].startswith("process_probe:TimeoutError")


def test_benchmark_wait_fails_closed_when_host_changes_before_launch(tmp_path, monkeypatch):
    mod = _module()

    exe = tmp_path / "game.exe"
    exe.write_bytes(b"binary")
    output = tmp_path / "result.json"
    probe_calls = iter([
        (40.0, [], []),
        (92.0, [], []),
    ])
    monkeypatch.setattr(mod, "_probe_host_state", lambda names: next(probe_calls))
    monkeypatch.setattr(mod, "_run_benchmark_process", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("must not launch")))

    result = mod.benchmark_wait(
        str(exe), str(output), cwd=str(tmp_path), max_cpu_percent=65.0,
        stable_samples=1, sample_interval_seconds=0, wait_timeout_seconds=30,
    )

    assert result["ok"] is False
    assert result["blocked_reason"] == "host_changed_before_launch"
    assert result["cpu_percent"] == 92.0


def test_reference_scan_unity_source_inventories_architecture_and_license(tmp_path):
    mod = _module()
    (tmp_path / "Assets" / "Scripts").mkdir(parents=True)
    (tmp_path / "ProjectSettings").mkdir()
    (tmp_path / "Packages").mkdir()
    (tmp_path / "ProjectSettings" / "ProjectVersion.txt").write_text("m_EditorVersion: 6000.4.0f1\n", encoding="utf-8")
    (tmp_path / "Packages" / "manifest.json").write_text(
        '{"dependencies":{"com.unity.addressables":"2.3.0","com.unity.cinemachine":"3.1.0","com.unity.render-pipelines.universal":"17.0.3","com.unity.services.multiplayer":"1.0.0"}}',
        encoding="utf-8",
    )
    (tmp_path / "Assets" / "Scripts" / "CreatureData.cs").write_text(
        "using UnityEngine; using UnityEngine.InputSystem; using UnityEngine.UIElements; "
        "public class CreatureData : ScriptableObject {}",
        encoding="utf-8",
    )
    (tmp_path / "Assets" / "Arena.unity").write_text("scene", encoding="utf-8")
    (tmp_path / "LICENSE").write_text("MIT License\nPermission is hereby granted...", encoding="utf-8")
    output = tmp_path / "study.json"

    result = mod.reference_scan(
        str(tmp_path), "https://github.com/example/creature-game", "open-source", "MIT", str(output)
    )

    assert result["source"]["kind"] == "unity_source"
    assert result["inventory"]["engine_version"] == "6000.4.0f1"
    assert result["inventory"]["file_counts"]["csharp"] == 1
    assert result["inventory"]["file_counts"]["scenes"] == 1
    signal_ids = {item["id"] for item in result["inventory"]["architecture_signals"]}
    assert {"scriptable_objects", "input_system", "ui_toolkit", "addressables", "cinemachine", "urp", "multiplayer_services"} <= signal_ids
    assert result["reuse_policy"]["mode"] == "reuse_subject_to_license"
    assert result["reuse_policy"]["automatic_asset_copy"] is False
    assert result["license_evidence"][0]["path"] == "LICENSE"
    assert output.exists()


def test_reference_scan_unity_build_is_observation_only(tmp_path):
    mod = _module()
    data = tmp_path / "ExampleGame_Data"
    managed = data / "Managed"
    managed.mkdir(parents=True)
    (managed / "Assembly-CSharp.dll").write_bytes(b"managed")
    (data / "globalgamemanagers").write_bytes(b"unity")
    (tmp_path / "ExampleGame.exe").write_bytes(b"exe")

    result = mod.reference_scan(str(tmp_path), rights_basis="user-owned")

    assert result["source"]["kind"] == "unity_build"
    assert result["inventory"]["scripting_backend"] == "mono"
    assert "Assembly-CSharp.dll" in result["inventory"]["managed_assemblies"]
    assert result["inventory"]["extraction_performed"] is False
    assert result["reuse_policy"]["mode"] == "analysis_only_unless_separate_reuse_rights"
    assert result["reuse_policy"]["automatic_code_copy"] is False


def test_reference_scan_rom_fingerprints_without_extracting(tmp_path):
    mod = _module()
    import hashlib

    rom = tmp_path / "owned-game.gba"
    rom.write_bytes(b"owned-rom-fixture")
    result = mod.reference_scan(str(rom), rights_basis="user-owned")

    assert result["source"]["kind"] == "rom_binary"
    assert result["inventory"]["sha256"] == hashlib.sha256(rom.read_bytes()).hexdigest()
    assert result["inventory"]["extraction_performed"] is False
    assert result["reuse_policy"]["code_reuse"] == "binary_observation_only_by_default"
    assert result["reuse_policy"]["automatic_asset_copy"] is False


def test_reference_scan_unknown_rights_fails_safe_with_warning(tmp_path):
    mod = _module()
    source = tmp_path / "mystery.dat"
    source.write_bytes(b"mystery")

    result = mod.reference_scan(str(source))

    assert result["reuse_policy"]["mode"] == "analysis_only_pending_rights_review"
    assert "rights_basis_unknown:analysis_only" in result["warnings"]


def test_reference_scan_finds_single_nested_unity_project_root(tmp_path):
    mod = _module()
    project = tmp_path / "UnityGame"
    (project / "Assets").mkdir(parents=True)
    (project / "ProjectSettings").mkdir()
    (project / "ProjectSettings" / "ProjectVersion.txt").write_text("m_EditorVersion: 2022.3.1f1\n", encoding="utf-8")
    (project / "Assets" / "Player.cs").write_text("using UnityEngine; public class Player : MonoBehaviour {}", encoding="utf-8")
    (tmp_path / "LICENSE").write_text("MIT License", encoding="utf-8")

    result = mod.reference_scan(str(tmp_path), rights_basis="open-source", license_name="MIT")

    assert result["source"]["kind"] == "unity_source"
    assert result["source"]["analysis_root"] == str(project.resolve())
    assert result["inventory"]["engine_version"] == "2022.3.1f1"
    assert result["inventory"]["file_counts"]["csharp"] == 1


def test_reference_scan_prunes_generated_dirs_and_orders_signals(tmp_path):
    mod = _module()
    (tmp_path / 'Assets').mkdir()
    (tmp_path / 'ProjectSettings').mkdir()
    (tmp_path / 'Packages').mkdir()
    (tmp_path / 'ProjectSettings' / 'ProjectVersion.txt').write_text('m_EditorVersion: 6000.4.0f1\n', encoding='utf-8')
    (tmp_path / 'Packages' / 'manifest.json').write_text('{\"dependencies\":{\"com.unity.render-pipelines.universal\":\"17.0.3\",\"com.unity.cinemachine\":\"3.1.0\"}}', encoding='utf-8')
    (tmp_path / 'Assets' / 'Gameplay.cs').write_text('using UnityEngine.InputSystem; public class Gameplay {}', encoding='utf-8')
    generated = tmp_path / 'Assets' / 'Library' / 'Generated'
    generated.mkdir(parents=True)
    (generated / 'ShouldNotCount.cs').write_text('using Unity.Netcode; class ShouldNotCount {}', encoding='utf-8')

    result = mod.reference_scan(str(tmp_path), rights_basis='licensed', license_name='example')

    assert result['inventory']['file_counts']['csharp'] == 1
    ids = [item['id'] for item in result['inventory']['architecture_signals']]
    assert ids == sorted(ids)
    assert 'netcode' not in ids
