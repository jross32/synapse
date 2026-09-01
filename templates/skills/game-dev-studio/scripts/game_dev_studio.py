#!/usr/bin/env python3
"""WhatIf Game Dev Studio helper.

Dependency-light utilities for game-project discovery, local tool detection,
Blender provisioning, durable truthful activity events, and asset provenance.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
import urllib.parse
import re
import uuid

SOURCE = "whatif-game-dev-studio"
EVENT_SCHEMA_VERSION = 1
PROVENANCE_SCHEMA_VERSION = 1


def _now() -> str:
    return dt.datetime.now().astimezone().isoformat()


def _print_json(value: object) -> None:
    print(json.dumps(value, indent=2, ensure_ascii=False))


def _run(args: list[str], timeout: int = 60) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, capture_output=True, text=True, timeout=timeout, check=False)


def _existing(paths: list[Path]) -> list[str]:
    return [str(path) for path in paths if path.exists()]


def _find_unity_editors() -> list[dict[str, str]]:
    editors_root = Path(os.environ.get("PROGRAMFILES", r"C:\Program Files")) / "Unity" / "Hub" / "Editor"
    found: list[dict[str, str]] = []
    if editors_root.exists():
        for version_dir in sorted(editors_root.iterdir(), reverse=True):
            exe = version_dir / "Editor" / "Unity.exe"
            if exe.exists():
                found.append({"version": version_dir.name, "path": str(exe)})
    path_exe = shutil.which("Unity") or shutil.which("Unity.exe")
    if path_exe and not any(item["path"].lower() == path_exe.lower() for item in found):
        found.append({"version": "unknown", "path": path_exe})
    return found


def _find_unreal_editors() -> list[dict[str, str]]:
    roots = [
        Path(os.environ.get("PROGRAMFILES", r"C:\Program Files")) / "Epic Games",
        Path(os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)")) / "Epic Games",
    ]
    found: list[dict[str, str]] = []
    for root in roots:
        if not root.exists():
            continue
        for version_dir in sorted(root.glob("UE_*"), reverse=True):
            exe = version_dir / "Engine" / "Binaries" / "Win64" / "UnrealEditor.exe"
            if exe.exists():
                found.append({"version": version_dir.name.removeprefix("UE_"), "path": str(exe)})
    return found


def _find_godot() -> list[dict[str, str]]:
    candidates: list[str] = []
    for name in ("godot", "godot4", "Godot.exe"):
        path = shutil.which(name)
        if path and path not in candidates:
            candidates.append(path)
    common = Path(os.environ.get("PROGRAMFILES", r"C:\Program Files")) / "Godot"
    if common.exists():
        for exe in common.rglob("*.exe"):
            if "godot" in exe.name.lower() and str(exe) not in candidates:
                candidates.append(str(exe))
    found = []
    for path in candidates:
        proc = _run([path, "--version"], timeout=15)
        version = (proc.stdout or proc.stderr).strip().splitlines()[0] if (proc.stdout or proc.stderr).strip() else "unknown"
        found.append({"version": version, "path": path})
    return found


def _find_blender() -> dict[str, object]:
    candidates: list[str] = []
    path_exe = shutil.which("blender") or shutil.which("blender.exe")
    if path_exe:
        candidates.append(path_exe)
    base = Path(os.environ.get("PROGRAMFILES", r"C:\Program Files")) / "Blender Foundation"
    if base.exists():
        for exe in sorted(base.glob("Blender */blender.exe"), reverse=True):
            if str(exe) not in candidates:
                candidates.append(str(exe))
    if not candidates:
        return {"installed": False, "path": None, "version": None}
    exe = candidates[0]
    proc = _run([exe, "--version"], timeout=20)
    first = (proc.stdout or proc.stderr).splitlines()
    version = first[0].replace("Blender ", "").strip() if first else "unknown"
    return {"installed": True, "path": exe, "version": version}


def _disk_headroom(path: Path | None = None) -> dict[str, object]:
    target = (path or Path.home()).resolve()
    usage = shutil.disk_usage(target)
    return {
        "path": str(target),
        "free_gb": round(usage.free / (1024 ** 3), 2),
        "used_gb": round(usage.used / (1024 ** 3), 2),
        "total_gb": round(usage.total / (1024 ** 3), 2),
    }


def doctor() -> dict[str, object]:
    hub = Path(os.environ.get("PROGRAMFILES", r"C:\Program Files")) / "Unity Hub" / "Unity Hub.exe"
    return {
        "schema_version": 1,
        "observed_at": _now(),
        "platform": sys.platform,
        "python": {"version": sys.version.split()[0], "path": sys.executable},
        "disk": _disk_headroom(),
        "blender": _find_blender(),
        "unity": {"hub": str(hub) if hub.exists() else None, "editors": _find_unity_editors()},
        "unreal": {"editors": _find_unreal_editors()},
        "godot": {"editors": _find_godot()},
        "winget": shutil.which("winget") or shutil.which("winget.exe"),
    }


def unity_preflight(editor: str | None, min_free_gb: float) -> dict[str, object]:
    editors = _find_unity_editors()
    selected = None
    if editor:
        candidate = Path(editor).expanduser().resolve()
        if candidate.exists():
            selected = {"version": "explicit", "path": str(candidate)}
    elif editors:
        selected = editors[0]
    disk = _disk_headroom()
    if selected is None:
        return {
            "ok": False,
            "blocked_reason": "unity_editor_missing",
            "needs_interactive_action": True,
            "message": "No Unity Editor installation was detected.",
            "disk": disk,
        }
    if float(disk["free_gb"]) < min_free_gb:
        return {
            "ok": False,
            "blocked_reason": "low_disk_space",
            "needs_interactive_action": False,
            "message": f"Only {disk['free_gb']} GB is free; Unity work requires at least {min_free_gb:.1f} GB for this job.",
            "editor": selected,
            "disk": disk,
        }

    probe_root = Path(tempfile.mkdtemp(prefix="whatif-unity-preflight-"))
    probe_project = probe_root / "ProbeProject"
    cleanup_performed = False
    try:
        proc = _run([
            selected["path"],
            "-batchmode", "-nographics", "-quit",
            "-createProject", str(probe_project),
            "-logFile", "-",
        ], timeout=180)
        log = (proc.stdout or "") + "\n" + (proc.stderr or "")
        license_missing = proc.returncode == 198 or "No valid Unity Editor license found" in log
        project_locked = "another Unity instance is running with this project open" in log
        if license_missing:
            return {
                "ok": False,
                "blocked_reason": "unity_license_required",
                "needs_interactive_action": True,
                "message": "Unity is installed but no valid Editor license is active. Sign in to Unity Hub and activate a license before headless automation.",
                "editor": selected,
                "disk": disk,
                "command_exit_code": proc.returncode,
                "probe_project": str(probe_project),
                "log_tail": log[-3000:],
            }
        if project_locked:
            return {
                "ok": False,
                "blocked_reason": "unity_project_locked",
                "needs_interactive_action": False,
                "message": "Unity reported the isolated preflight project as locked; inspect running Editor processes before retrying.",
                "editor": selected,
                "disk": disk,
                "command_exit_code": proc.returncode,
                "probe_project": str(probe_project),
                "log_tail": log[-3000:],
            }
        valid_probe = (
            (probe_project / "Assets").exists()
            and (probe_project / "Packages" / "manifest.json").exists()
            and (probe_project / "ProjectSettings" / "ProjectVersion.txt").exists()
        )
        return {
            "ok": proc.returncode == 0 and valid_probe,
            "blocked_reason": None if proc.returncode == 0 and valid_probe else "unity_preflight_failed",
            "needs_interactive_action": False,
            "message": "Unity isolated headless preflight passed." if proc.returncode == 0 and valid_probe else "Unity isolated headless preflight failed; inspect log_tail.",
            "editor": selected,
            "disk": disk,
            "command_exit_code": proc.returncode,
            "probe_valid": valid_probe,
            "probe_project": str(probe_project),
            "log_tail": log[-3000:],
        }
    finally:
        for _ in range(5):
            try:
                if probe_root.exists():
                    shutil.rmtree(probe_root)
                cleanup_performed = not probe_root.exists()
                if cleanup_performed:
                    break
            except OSError:
                import time
                time.sleep(0.25)


def unity_create(project: str, editor: str | None, min_free_gb: float) -> dict[str, object]:
    import time

    root = Path(project).expanduser().resolve()
    if root.exists():
        return {
            "ok": False,
            "blocked_reason": "project_path_exists",
            "cleanup_performed": False,
            "message": "Refusing to create a Unity project in an existing path.",
            "project": str(root),
        }

    preflight = unity_preflight(editor, min_free_gb)
    if not preflight.get("ok"):
        return {
            "ok": False,
            "blocked_reason": preflight.get("blocked_reason") or "unity_preflight_failed",
            "cleanup_performed": False,
            "message": "Unity project creation blocked by preflight.",
            "project": str(root),
            "preflight": preflight,
        }

    selected = preflight.get("editor") or {}
    editor_path = str(selected.get("path") or "")
    if not editor_path:
        return {
            "ok": False,
            "blocked_reason": "unity_editor_missing",
            "cleanup_performed": False,
            "message": "Unity preflight passed without an editor path; refusing creation.",
            "project": str(root),
            "preflight": preflight,
        }

    started = time.perf_counter()
    cleanup_performed = False
    try:
        proc = _run([
            editor_path,
            "-batchmode", "-nographics", "-quit",
            "-createProject", str(root),
            "-logFile", "-",
        ], timeout=300)
        elapsed = round(time.perf_counter() - started, 3)
        log = (proc.stdout or "") + "\n" + (proc.stderr or "")
        valid_project = (
            (root / "Assets").exists()
            and (root / "Packages" / "manifest.json").exists()
            and (root / "ProjectSettings" / "ProjectVersion.txt").exists()
        )
        version = _unity_project_version(root) if valid_project else None
        if proc.returncode == 0 and valid_project and version and version != "UnknownUnityVersion":
            return {
                "ok": True,
                "blocked_reason": None,
                "cleanup_performed": False,
                "message": "Unity project created and structurally verified.",
                "project": str(root),
                "engine_version": version,
                "duration_seconds": elapsed,
                "command_exit_code": proc.returncode,
                "log_tail": log[-3000:],
                "preflight": preflight,
            }

        if root.exists():
            for _ in range(5):
                try:
                    shutil.rmtree(root)
                    cleanup_performed = not root.exists()
                    if cleanup_performed:
                        break
                except OSError:
                    time.sleep(0.25)
        return {
            "ok": False,
            "blocked_reason": "unity_create_failed",
            "cleanup_performed": cleanup_performed,
            "message": "Unity project creation failed verification; partial output was rolled back when possible.",
            "project": str(root),
            "duration_seconds": elapsed,
            "command_exit_code": proc.returncode,
            "valid_project_shape": valid_project,
            "engine_version": version,
            "log_tail": log[-3000:],
            "preflight": preflight,
        }
    except Exception as exc:
        if root.exists():
            for _ in range(5):
                try:
                    shutil.rmtree(root)
                    cleanup_performed = not root.exists()
                    if cleanup_performed:
                        break
                except OSError:
                    time.sleep(0.25)
        return {
            "ok": False,
            "blocked_reason": "unity_create_exception",
            "cleanup_performed": cleanup_performed,
            "message": str(exc),
            "project": str(root),
            "duration_seconds": round(time.perf_counter() - started, 3),
            "preflight": preflight,
        }

def _winget_blender_metadata(winget: str) -> dict[str, str]:
    proc = _run([winget, "show", "--id", "BlenderFoundation.Blender", "--exact", "--accept-source-agreements"], timeout=60)
    if proc.returncode != 0:
        raise RuntimeError(f"winget show failed: {(proc.stderr or proc.stdout).strip()[-1000:]}")
    metadata: dict[str, str] = {}
    for raw in proc.stdout.splitlines():
        line = raw.strip()
        if line.startswith("Version:"):
            metadata["version"] = line.split(":", 1)[1].strip()
        elif line.startswith("Installer Url:"):
            metadata["url"] = line.split(":", 1)[1].strip()
        elif line.startswith("Installer SHA256:"):
            metadata["sha256"] = line.split(":", 1)[1].strip().lower()
    if not all(metadata.get(key) for key in ("version", "url", "sha256")):
        raise RuntimeError("winget did not provide Blender version, installer URL, and SHA256")
    if not metadata["url"].lower().startswith("https://download.blender.org/"):
        raise RuntimeError("Refusing Blender installer URL outside download.blender.org")
    return metadata


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def ensure_blender(install: bool) -> dict[str, object]:
    before = _find_blender()
    if before["installed"]:
        return {"ok": True, "changed": False, "message": "Blender already installed", "blender": before}
    if not install:
        return {
            "ok": False,
            "changed": False,
            "message": "Blender is missing. Re-run with --install to provision it automatically.",
            "blender": before,
        }
    winget = shutil.which("winget") or shutil.which("winget.exe")
    if not winget:
        return {"ok": False, "changed": False, "message": "winget is unavailable; automatic Blender install could not resolve a trusted package."}
    try:
        metadata = _winget_blender_metadata(winget)
        with tempfile.TemporaryDirectory(prefix="whatif-blender-") as temp_dir:
            installer = Path(temp_dir) / f"blender-{metadata['version']}.msi"
            request = urllib.request.Request(metadata["url"], headers={"User-Agent": "Mozilla/5.0 WhatIfGameDevStudio/0.1"})
            with urllib.request.urlopen(request, timeout=120) as response, installer.open("wb") as out:
                shutil.copyfileobj(response, out)
            actual_sha = _sha256(installer)
            if actual_sha.lower() != metadata["sha256"].lower():
                raise RuntimeError(f"Blender installer SHA256 mismatch: expected {metadata['sha256']}, got {actual_sha}")
            proc = _run(["msiexec.exe", "/i", str(installer), "/qn", "/norestart"], timeout=900)
        after = _find_blender()
        return {
            "ok": bool(after["installed"]),
            "changed": bool(after["installed"]),
            "message": "Blender installed" if after["installed"] else "Blender installer completed but Blender was not detected",
            "resolved_version": metadata["version"],
            "installer_source": metadata["url"],
            "installer_sha256": metadata["sha256"],
            "command_exit_code": proc.returncode,
            "stdout_tail": proc.stdout[-2000:],
            "stderr_tail": proc.stderr[-2000:],
            "blender": after,
        }
    except Exception as exc:
        return {"ok": False, "changed": False, "message": str(exc), "blender": _find_blender()}


def _unity_project_version(root: Path) -> str | None:
    file = root / "ProjectSettings" / "ProjectVersion.txt"
    if not file.exists():
        return None
    for line in file.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith("m_EditorVersion:"):
            return line.split(":", 1)[1].strip()
    return None


def detect_project(project: str) -> dict[str, object]:
    root = Path(project).expanduser().resolve()
    if not root.exists():
        raise FileNotFoundError(root)
    signals: list[str] = []
    engine = "unknown"
    version: str | None = None
    if (root / "ProjectSettings" / "ProjectVersion.txt").exists() and (root / "Assets").exists():
        engine = "unity"
        version = _unity_project_version(root)
        signals.extend(["ProjectSettings/ProjectVersion.txt", "Assets/"])
    elif (root / "project.godot").exists():
        engine = "godot"
        signals.append("project.godot")
        for line in (root / "project.godot").read_text(encoding="utf-8", errors="replace").splitlines():
            if "config/features" in line:
                signals.append(line.strip()[:300])
                break
    else:
        uprojs = list(root.glob("*.uproject"))
        if uprojs:
            engine = "unreal"
            signals.append(uprojs[0].name)
            try:
                payload = json.loads(uprojs[0].read_text(encoding="utf-8"))
                version = str(payload.get("EngineAssociation") or "") or None
            except (OSError, json.JSONDecodeError):
                pass
        elif list(root.glob("*.blend")):
            engine = "blender"
            signals.append("*.blend")
        elif (root / "index.html").exists():
            engine = "web"
            signals.append("index.html")
            package_json = root / "package.json"
            if package_json.exists():
                signals.append("package.json")
                try:
                    payload = json.loads(package_json.read_text(encoding="utf-8"))
                    version = str(payload.get("version") or "") or None
                    deps = {**payload.get("dependencies", {}), **payload.get("devDependencies", {})}
                    if "phaser" in deps:
                        engine = "phaser"
                        signals.append("phaser:" + str(deps["phaser"]))
                except (OSError, json.JSONDecodeError, TypeError):
                    pass
    git_dirty = None
    if (root / ".git").exists():
        proc = _run(["git", "status", "--porcelain"], timeout=15)
        git_dirty = bool(proc.stdout.strip()) if proc.returncode == 0 else None
    return {
        "schema_version": 1,
        "observed_at": _now(),
        "project": str(root),
        "engine": engine,
        "engine_version": version,
        "signals": signals,
        "git_dirty": git_dirty,
        "event_log": str(root / ".synapse" / "game-dev-events.jsonl"),
        "provenance_log": str(root / ".synapse" / "asset-provenance.jsonl"),
    }


def web_smoke(url: str) -> dict[str, object]:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in {"http", "https"} or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError("web-smoke only permits loopback game URLs")
    request = urllib.request.Request(url, headers={"User-Agent": "WhatIfGameDevStudio/0.1"})
    with urllib.request.urlopen(request, timeout=15) as response:
        body = response.read(2_000_000).decode("utf-8", errors="replace")
        status = int(response.status)
        content_type = response.headers.get("Content-Type", "")
    title_match = re.search(r"<title[^>]*>(.*?)</title>", body, re.I | re.S)
    title = re.sub(r"\s+", " ", title_match.group(1)).strip() if title_match else None
    return {
        "ok": 200 <= status < 400,
        "url": url,
        "status": status,
        "content_type": content_type,
        "title": title,
        "has_canvas": bool(re.search(r"<canvas\b", body, re.I)),
        "bytes_sampled": len(body.encode("utf-8")),
    }



def _cpu_load_percent() -> float:
    """Return a best-effort whole-host CPU percentage for benchmark gating."""
    if sys.platform == "win32":
        proc = _run([
            "powershell.exe", "-NoProfile", "-NonInteractive", "-Command",
            "(Get-Counter '\\Processor(_Total)\\% Processor Time' -SampleInterval 1 -MaxSamples 1).CounterSamples.CookedValue",
        ], timeout=10)
        if proc.returncode == 0:
            text = (proc.stdout or "").strip().splitlines()
            if text:
                try:
                    return max(0.0, min(100.0, float(text[-1].strip())))
                except ValueError:
                    pass
        proc = _run([
            "powershell.exe", "-NoProfile", "-NonInteractive", "-Command",
            "(Get-CimInstance Win32_Processor | Measure-Object -Property LoadPercentage -Average).Average",
        ], timeout=10)
        if proc.returncode == 0:
            text = (proc.stdout or "").strip().splitlines()
            if text:
                try:
                    return max(0.0, min(100.0, float(text[-1].strip())))
                except ValueError:
                    pass
        raise RuntimeError("unable to measure Windows CPU load")

    if hasattr(os, "getloadavg"):
        load_1m = float(os.getloadavg()[0])
        cpus = max(1, int(os.cpu_count() or 1))
        return max(0.0, min(100.0, (load_1m / cpus) * 100.0))
    raise RuntimeError(f"CPU load measurement is unsupported on {sys.platform}")


def _normalize_process_name(name: str) -> str:
    value = Path(str(name).strip()).name.lower()
    return value[:-4] if value.endswith(".exe") else value


def _blocked_processes(names: list[str]) -> list[str]:
    wanted = {_normalize_process_name(name) for name in names if str(name).strip()}
    if not wanted:
        return []
    observed: set[str] = set()
    if sys.platform == "win32":
        proc = _run([
            "powershell.exe", "-NoProfile", "-NonInteractive", "-Command",
            "Get-Process | Select-Object -ExpandProperty ProcessName",
        ], timeout=10)
        if proc.returncode != 0:
            raise RuntimeError("unable to enumerate Windows processes")
        observed = {_normalize_process_name(line) for line in (proc.stdout or "").splitlines() if line.strip()}
    else:
        proc = _run(["ps", "-A", "-o", "comm="], timeout=10)
        if proc.returncode != 0:
            raise RuntimeError("unable to enumerate processes")
        observed = {_normalize_process_name(line) for line in (proc.stdout or "").splitlines() if line.strip()}
    return sorted(wanted & observed)


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _verify_benchmark_fingerprints(manifest_path: str | None, workdir: Path, executable: Path) -> dict[str, object]:
    if not manifest_path:
        return {"ok": True, "manifest": None, "source_files_checked": 0, "executable_checked": False, "mismatches": []}
    path = Path(manifest_path).expanduser().resolve()
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("fingerprint manifest must be a JSON object")
    mismatches: list[dict[str, object]] = []
    source_map = payload.get("source_file_sha256") or {}
    if not isinstance(source_map, dict):
        raise ValueError("source_file_sha256 must be a JSON object")
    checked = 0
    for raw_path, expected_raw in source_map.items():
        raw = str(raw_path).replace("\\\\", "\\")
        candidate = Path(raw).expanduser()
        if not candidate.is_absolute():
            candidate = workdir / candidate
        candidate = candidate.resolve()
        expected = str(expected_raw).strip().lower()
        checked += 1
        if not candidate.exists():
            mismatches.append({"path": str(candidate), "reason": "missing", "expected_sha256": expected})
            continue
        actual = _file_sha256(candidate)
        if actual != expected:
            mismatches.append({"path": str(candidate), "reason": "sha256_mismatch", "expected_sha256": expected, "actual_sha256": actual})

    build = payload.get("build") if isinstance(payload.get("build"), dict) else {}
    expected_exe_raw = payload.get("executable_sha256") or build.get("exe_sha256")
    executable_checked = bool(expected_exe_raw)
    if expected_exe_raw:
        expected_exe = str(expected_exe_raw).strip().lower()
        if not executable.exists():
            mismatches.append({"path": str(executable), "reason": "missing", "expected_sha256": expected_exe})
        else:
            actual_exe = _file_sha256(executable)
            if actual_exe != expected_exe:
                mismatches.append({"path": str(executable), "reason": "sha256_mismatch", "expected_sha256": expected_exe, "actual_sha256": actual_exe})
    return {
        "ok": not mismatches,
        "manifest": str(path),
        "source_files_checked": checked,
        "executable_checked": executable_checked,
        "mismatches": mismatches,
    }


def _run_benchmark_process(command: list[str], cwd: Path, timeout_seconds: float) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=str(cwd), capture_output=True, text=True, timeout=timeout_seconds, check=False)


def benchmark_wait(
    executable: str,
    output: str,
    command_args: list[str] | None = None,
    *,
    cwd: str | None = None,
    max_cpu_percent: float = 65.0,
    stable_samples: int = 4,
    sample_interval_seconds: float = 4.0,
    wait_timeout_seconds: float = 21600.0,
    process_timeout_seconds: float = 300.0,
    block_processes: list[str] | None = None,
    fingerprint_manifest: str | None = None,
    output_flag: str | None = None,
    overwrite_output: bool = False,
) -> dict[str, object]:
    """Wait for a quiet host, fail closed on drift, then run one benchmark process."""
    exe = Path(executable).expanduser().resolve()
    if not exe.exists():
        return {"ok": False, "blocked_reason": "benchmark_executable_missing", "executable": str(exe)}
    workdir = Path(cwd).expanduser().resolve() if cwd else exe.parent
    if not workdir.exists():
        return {"ok": False, "blocked_reason": "benchmark_cwd_missing", "cwd": str(workdir)}
    out = Path(output).expanduser()
    if not out.is_absolute():
        out = workdir / out
    out = out.resolve()
    if out.exists() and not overwrite_output:
        return {"ok": False, "blocked_reason": "benchmark_output_exists", "output": str(out)}
    if max_cpu_percent <= 0 or max_cpu_percent > 100:
        raise ValueError("max_cpu_percent must be > 0 and <= 100")
    if stable_samples < 1:
        raise ValueError("stable_samples must be >= 1")
    if sample_interval_seconds < 0:
        raise ValueError("sample_interval_seconds must be >= 0")
    if wait_timeout_seconds < 0 or process_timeout_seconds <= 0:
        raise ValueError("timeouts must be non-negative, with process timeout > 0")

    fingerprint = _verify_benchmark_fingerprints(fingerprint_manifest, workdir, exe)
    if not fingerprint["ok"]:
        return {"ok": False, "blocked_reason": "benchmark_fingerprint_mismatch", "fingerprint": fingerprint}

    blockers = list(block_processes or [])
    samples: list[dict[str, object]] = []
    stable = 0
    started = time.monotonic()
    launch_cpu: float | None = None
    while True:
        cpu = round(float(_cpu_load_percent()), 2)
        blocked = _blocked_processes(blockers)
        quiet = cpu <= max_cpu_percent and not blocked
        stable = stable + 1 if quiet else 0
        sample = {"observed_at": _now(), "cpu_percent": cpu, "blocked_processes": blocked, "stable_count": stable}
        samples.append(sample)
        if len(samples) > 100:
            samples = samples[-100:]
        if stable >= stable_samples:
            launch_cpu = cpu
            break
        elapsed = time.monotonic() - started
        if elapsed >= wait_timeout_seconds:
            return {
                "ok": False,
                "blocked_reason": "host_idle_timeout",
                "threshold_cpu_percent": max_cpu_percent,
                "stable_samples_required": stable_samples,
                "elapsed_seconds": round(elapsed, 3),
                "samples": samples,
                "fingerprint": fingerprint,
            }
        if sample_interval_seconds:
            time.sleep(sample_interval_seconds)

    fingerprint = _verify_benchmark_fingerprints(fingerprint_manifest, workdir, exe)
    if not fingerprint["ok"]:
        return {"ok": False, "blocked_reason": "benchmark_fingerprint_changed_before_launch", "fingerprint": fingerprint, "samples": samples}
    blocked_now = _blocked_processes(blockers)
    if blocked_now:
        return {"ok": False, "blocked_reason": "blocked_process_started_before_launch", "blocked_processes": blocked_now, "samples": samples}

    if out.exists() and overwrite_output:
        out.unlink()
    out.parent.mkdir(parents=True, exist_ok=True)
    extra = list(command_args or [])
    if extra and extra[0] == "--":
        extra = extra[1:]
    command = [str(exe), *extra]
    if output_flag:
        command.extend([output_flag, str(out)])
    launched_at = _now()
    try:
        proc = _run_benchmark_process(command, workdir, process_timeout_seconds)
    except subprocess.TimeoutExpired as exc:
        return {
            "ok": False,
            "blocked_reason": "benchmark_process_timeout",
            "command": command,
            "launched_at": launched_at,
            "launch_cpu_percent": launch_cpu,
            "timeout_seconds": process_timeout_seconds,
            "samples": samples,
            "fingerprint": fingerprint,
            "stdout_tail": (exc.stdout or "")[-2000:] if isinstance(exc.stdout, str) else "",
            "stderr_tail": (exc.stderr or "")[-2000:] if isinstance(exc.stderr, str) else "",
        }
    artifact_exists = out.exists()
    return {
        "ok": proc.returncode == 0 and artifact_exists,
        "blocked_reason": None if proc.returncode == 0 and artifact_exists else ("benchmark_output_missing" if not artifact_exists else "benchmark_process_failed"),
        "command": command,
        "cwd": str(workdir),
        "output": str(out),
        "artifact_exists": artifact_exists,
        "artifact_bytes": out.stat().st_size if artifact_exists else 0,
        "process_returncode": proc.returncode,
        "launched_at": launched_at,
        "launch_cpu_percent": launch_cpu,
        "threshold_cpu_percent": max_cpu_percent,
        "stable_samples_required": stable_samples,
        "samples": samples,
        "fingerprint": fingerprint,
        "stdout_tail": (proc.stdout or "")[-2000:],
        "stderr_tail": (proc.stderr or "")[-2000:],
    }


def benchmark_validate(path: str, expect: str, require_screenshot: bool = False, require_controlled_presentation: bool = False) -> dict[str, object]:
    payload_path = Path(path).expanduser().resolve()
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("benchmark payload must be a JSON object")
    required_numeric = (
        "warmup_seconds", "duration_seconds", "average_frame_ms",
        "p95_frame_ms", "max_frame_ms", "average_fps",
    )
    issues: list[str] = []
    warnings: list[str] = []
    for key in required_numeric:
        value = payload.get(key)
        if not isinstance(value, (int, float)):
            issues.append(f"missing_or_non_numeric:{key}")
    warmup = float(payload.get("warmup_seconds", 0) or 0)
    duration = float(payload.get("duration_seconds", 0) or 0)
    average_frame = float(payload.get("average_frame_ms", 0) or 0)
    p95_frame = float(payload.get("p95_frame_ms", 0) or 0)
    max_frame = float(payload.get("max_frame_ms", 0) or 0)
    average_fps = float(payload.get("average_fps", 0) or 0)
    if warmup < 1.0:
        warnings.append("warmup_shorter_than_1s")
    if duration < 5.0:
        warnings.append("sample_window_shorter_than_5s")
    if average_frame <= 0 or p95_frame <= 0 or max_frame <= 0 or average_fps <= 0:
        issues.append("non_positive_frame_metric")
    graphics_device = str(payload.get("graphics_device") or "").strip()
    mode = "headless" if graphics_device.lower() in {"null device", "null", "none"} else "rendered"
    if expect not in {"any", "headless", "rendered"}:
        raise ValueError("expect must be any, headless, or rendered")
    if expect != "any" and mode != expect:
        issues.append(f"mode_mismatch:expected_{expect}:observed_{mode}")
    for name in ("process_working_set", "system_used_memory", "gc_reserved_memory", "draw_calls"):
        valid_key = f"{name}_valid"
        value_key = f"{name}_bytes" if name != "draw_calls" else "draw_calls"
        if valid_key in payload and payload.get(valid_key) is False:
            warnings.append(f"counter_unavailable:{name}")
        elif payload.get(valid_key) is True:
            value = payload.get(value_key)
            if not isinstance(value, (int, float)) or value < 0:
                issues.append(f"invalid_counter:{name}")
    screenshot_verified = False
    screenshot_path_raw = str(payload.get("screenshot_path") or "").strip()
    screenshot_hash = str(payload.get("screenshot_sha256") or "").strip().lower()
    screenshot_bytes = payload.get("screenshot_bytes")
    if screenshot_path_raw:
        screenshot_path = Path(screenshot_path_raw).expanduser()
        if not screenshot_path.is_absolute():
            screenshot_path = (payload_path.parent / screenshot_path).resolve()
        if not screenshot_path.exists():
            issues.append("screenshot_missing")
        elif len(screenshot_hash) != 64:
            issues.append("screenshot_sha256_invalid")
        else:
            actual_hash = hashlib.sha256(screenshot_path.read_bytes()).hexdigest()
            if actual_hash != screenshot_hash:
                issues.append("screenshot_sha256_mismatch")
            elif isinstance(screenshot_bytes, int) and screenshot_bytes != screenshot_path.stat().st_size:
                issues.append("screenshot_size_mismatch")
            else:
                screenshot_verified = True
    elif require_screenshot:
        issues.append("screenshot_required")

    presentation_controlled = False
    if mode == "rendered":
        vsync = payload.get("benchmark_vsync_count")
        target_fps = payload.get("benchmark_target_frame_rate")
        presentation_controlled = isinstance(vsync, int) and isinstance(target_fps, int) and vsync == 0 and target_fps > 0
        if require_controlled_presentation and not presentation_controlled:
            issues.append("controlled_presentation_required")
        elif not presentation_controlled:
            warnings.append("presentation_not_explicitly_controlled")

    comparable_for_rendering = mode == "rendered" and warmup >= 1.0 and duration >= 5.0 and not issues
    return {
        "ok": not issues,
        "input": str(payload_path),
        "mode": mode,
        "expected_mode": expect,
        "comparable_for_rendering": comparable_for_rendering,
        "issues": issues,
        "warnings": warnings,
        "screenshot_verified": screenshot_verified,
        "presentation_controlled": presentation_controlled,
        "summary": {
            "warmup_seconds": warmup,
            "duration_seconds": duration,
            "average_frame_ms": average_frame,
            "p95_frame_ms": p95_frame,
            "max_frame_ms": max_frame,
            "average_fps": average_fps,
            "graphics_device": graphics_device,
        },
    }

def append_event(project: str, phase: str, kind: str, message: str, progress: float | None, detail_raw: str | None) -> dict[str, object]:
    allowed_kinds = {"started", "activity", "artifact", "milestone", "warning", "error", "completed", "heartbeat"}
    if kind not in allowed_kinds:
        raise ValueError(f"Unsupported event kind: {kind}")
    if progress is not None and not 0 <= progress <= 100:
        raise ValueError("progress must be between 0 and 100")
    detail: object = {}
    if detail_raw:
        detail = json.loads(detail_raw)
        if not isinstance(detail, dict):
            raise ValueError("detail must be a JSON object")
    root = Path(project).expanduser().resolve()
    if not root.exists():
        raise FileNotFoundError(root)
    log = root / ".synapse" / "game-dev-events.jsonl"
    log.parent.mkdir(parents=True, exist_ok=True)
    event = {
        "schema_version": EVENT_SCHEMA_VERSION,
        "event_id": str(uuid.uuid4()),
        "timestamp": _now(),
        "project": str(root),
        "phase": phase,
        "kind": kind,
        "message": message,
        "progress": progress,
        "detail": detail,
        "source": SOURCE,
    }
    with log.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False) + "\n")
    return event


def provenance_add(project: str, asset: str, origin: str, license_name: str, commercial_use: str, attribution: str, modifications: str, usage: str) -> dict[str, object]:
    root = Path(project).expanduser().resolve()
    if not root.exists():
        raise FileNotFoundError(root)
    log = root / ".synapse" / "asset-provenance.jsonl"
    log.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "schema_version": PROVENANCE_SCHEMA_VERSION,
        "record_id": str(uuid.uuid4()),
        "timestamp": _now(),
        "asset": asset,
        "origin": origin,
        "license": license_name,
        "commercial_use": commercial_use,
        "attribution": attribution,
        "modifications": modifications,
        "usage": usage,
        "source": SOURCE,
    }
    with log.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    return record


def provenance_list(project: str) -> list[object]:
    log = Path(project).expanduser().resolve() / ".synapse" / "asset-provenance.jsonl"
    if not log.exists():
        return []
    rows: list[object] = []
    for line in log.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="WhatIf Game Dev Studio helper")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("doctor")
    unity = sub.add_parser("unity-preflight")
    unity.add_argument("--editor")
    unity.add_argument("--min-free-gb", type=float, default=15.0)
    unity_create_parser = sub.add_parser("unity-create")
    unity_create_parser.add_argument("--project", required=True)
    unity_create_parser.add_argument("--editor")
    unity_create_parser.add_argument("--min-free-gb", type=float, default=15.0)
    blender = sub.add_parser("ensure-blender")
    blender.add_argument("--install", action="store_true")
    detect = sub.add_parser("detect-project")
    detect.add_argument("--project", required=True)
    smoke = sub.add_parser("web-smoke")
    smoke.add_argument("--url", required=True)
    bench = sub.add_parser("benchmark-validate")
    bench.add_argument("--input", required=True)
    bench.add_argument("--expect", choices=("any", "headless", "rendered"), default="any")
    bench.add_argument("--require-screenshot", action="store_true")
    bench.add_argument("--require-controlled-presentation", action="store_true")
    bench_wait = sub.add_parser("benchmark-wait")
    bench_wait.add_argument("--executable", required=True)
    bench_wait.add_argument("--output", required=True)
    bench_wait.add_argument("--cwd")
    bench_wait.add_argument("--max-cpu-percent", type=float, default=65.0)
    bench_wait.add_argument("--stable-samples", type=int, default=4)
    bench_wait.add_argument("--sample-interval-seconds", type=float, default=4.0)
    bench_wait.add_argument("--wait-timeout-seconds", type=float, default=21600.0)
    bench_wait.add_argument("--process-timeout-seconds", type=float, default=300.0)
    bench_wait.add_argument("--block-process", action="append", default=[])
    bench_wait.add_argument("--fingerprint-manifest")
    bench_wait.add_argument("--output-flag")
    bench_wait.add_argument("--overwrite-output", action="store_true")
    bench_wait.add_argument("command_args", nargs=argparse.REMAINDER)
    event = sub.add_parser("event")
    event.add_argument("--project", required=True)
    event.add_argument("--phase", required=True)
    event.add_argument("--kind", required=True)
    event.add_argument("--message", required=True)
    event.add_argument("--progress", type=float)
    event.add_argument("--detail")
    prov = sub.add_parser("provenance-add")
    prov.add_argument("--project", required=True)
    prov.add_argument("--asset", required=True)
    prov.add_argument("--origin", required=True)
    prov.add_argument("--license", required=True, dest="license_name")
    prov.add_argument("--commercial-use", required=True)
    prov.add_argument("--attribution", default="none")
    prov.add_argument("--modifications", default="none")
    prov.add_argument("--usage", default="unspecified")
    prov_list = sub.add_parser("provenance-list")
    prov_list.add_argument("--project", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "doctor":
            result = doctor()
        elif args.command == "unity-preflight":
            result = unity_preflight(args.editor, args.min_free_gb)
        elif args.command == "unity-create":
            result = unity_create(args.project, args.editor, args.min_free_gb)
        elif args.command == "ensure-blender":
            result = ensure_blender(args.install)
        elif args.command == "detect-project":
            result = detect_project(args.project)
        elif args.command == "web-smoke":
            result = web_smoke(args.url)
        elif args.command == "benchmark-validate":
            result = benchmark_validate(args.input, args.expect, args.require_screenshot, args.require_controlled_presentation)
        elif args.command == "benchmark-wait":
            result = benchmark_wait(
                args.executable, args.output, args.command_args, cwd=args.cwd,
                max_cpu_percent=args.max_cpu_percent, stable_samples=args.stable_samples,
                sample_interval_seconds=args.sample_interval_seconds, wait_timeout_seconds=args.wait_timeout_seconds,
                process_timeout_seconds=args.process_timeout_seconds, block_processes=args.block_process,
                fingerprint_manifest=args.fingerprint_manifest, output_flag=args.output_flag,
                overwrite_output=args.overwrite_output,
            )
        elif args.command == "event":
            result = append_event(args.project, args.phase, args.kind, args.message, args.progress, args.detail)
        elif args.command == "provenance-add":
            result = provenance_add(args.project, args.asset, args.origin, args.license_name, args.commercial_use, args.attribution, args.modifications, args.usage)
        elif args.command == "provenance-list":
            result = provenance_list(args.project)
        else:
            raise AssertionError(args.command)
        _print_json(result)
        if isinstance(result, dict) and result.get("ok") is False:
            return 2
        return 0
    except Exception as exc:
        _print_json({"ok": False, "error": type(exc).__name__, "message": str(exc)})
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
