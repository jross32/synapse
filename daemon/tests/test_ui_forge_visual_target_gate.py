from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GATE = ROOT / "templates" / "skills" / "ui-forge" / "scripts" / "visual_target_gate.py"
SCAN = ROOT / "templates" / "skills" / "ui-forge" / "scripts" / "prototype_surface_scan.py"


def _run(script: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(script), *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def test_visual_target_gate_passes_complete_fixture(tmp_path: Path) -> None:
    (tmp_path / "reference.png").write_bytes(b"reference")
    (tmp_path / "actual.png").write_bytes(b"actual")
    (tmp_path / "hero.png").write_bytes(b"hero")

    contract = {
        "schema": "ui-forge-visual-target-v1",
        "project_id": "fixture",
        "references": [{"id": "target", "path": "reference.png", "role": "proposed_ui"}],
        "global": {"minimum_visual_score": 85, "forbid_placeholder_surfaces": True},
        "surfaces": [{
            "id": "landing.desktop",
            "route": "/",
            "required_sections": ["header", "hero", "footer"],
            "required_assets": [{
                "id": "hero-scene",
                "kind": "production-illustration",
                "minimum_kind": "production-illustration",
                "required": True,
            }],
            "forbidden_signals": ["local fallback", "next ui slice"],
        }],
    }
    evidence = {
        "surfaces": [{
            "surface_id": "landing.desktop",
            "route": "/",
            "screenshot": "actual.png",
            "sections_present": ["header", "hero", "footer"],
            "assets": [{
                "id": "hero-scene",
                "kind": "production-illustration",
                "status": "approved",
                "path": "hero.png",
            }],
            "visible_signals": [],
            "visual_score": 92,
            "placeholder_surface": False,
            "unresolved_differences": [],
        }],
        "blockers": [],
    }
    cp = tmp_path / "contract.json"
    ep = tmp_path / "evidence.json"
    cp.write_text(json.dumps(contract), encoding="utf-8")
    ep.write_text(json.dumps(evidence), encoding="utf-8")

    result = _run(GATE, str(cp), str(ep), "--project-root", str(tmp_path))
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads(result.stdout)
    assert report["pass"] is True
    assert report["issue_count"] == 0


def test_visual_target_gate_rejects_downgrade_placeholder_and_missing_section(tmp_path: Path) -> None:
    (tmp_path / "reference.png").write_bytes(b"reference")
    (tmp_path / "actual.png").write_bytes(b"actual")

    contract = {
        "schema": "ui-forge-visual-target-v1",
        "project_id": "fixture",
        "references": [{"id": "target", "path": "reference.png"}],
        "global": {"minimum_visual_score": 85, "forbid_placeholder_surfaces": True},
        "surfaces": [{
            "id": "landing.desktop",
            "route": "/",
            "required_sections": ["header", "hero", "device-showcase", "footer"],
            "required_assets": [{
                "id": "hero-scene",
                "kind": "production-illustration",
                "minimum_kind": "production-illustration",
                "required": True,
            }],
            "forbidden_signals": ["local fallback"],
        }],
    }
    evidence = {
        "surfaces": [{
            "surface_id": "landing.desktop",
            "route": "/",
            "screenshot": "actual.png",
            "sections_present": ["header", "hero", "footer"],
            "assets": [{"id": "hero-scene", "kind": "css-primitive", "status": "resolved"}],
            "visible_signals": ["conversation engine: local fallback"],
            "visual_score": 61,
            "placeholder_surface": True,
        }],
        "blockers": [],
    }
    cp = tmp_path / "contract.json"
    ep = tmp_path / "evidence.json"
    cp.write_text(json.dumps(contract), encoding="utf-8")
    ep.write_text(json.dumps(evidence), encoding="utf-8")

    result = _run(GATE, str(cp), str(ep), "--project-root", str(tmp_path))
    assert result.returncode == 2
    codes = {item["code"] for item in json.loads(result.stdout)["issues"]}
    assert {"section_missing", "asset_downgrade", "forbidden_signal", "placeholder_surface", "visual_score_low"} <= codes


def test_prototype_surface_scan_flags_prompt_and_placeholder_copy(tmp_path: Path) -> None:
    source = tmp_path / "app.js"
    source.write_text(
        'const name = prompt("Twin name");\n'
        'panel.textContent = "This dedicated studio is the next UI slice.";\n',
        encoding="utf-8",
    )
    result = _run(SCAN, str(tmp_path), "--fail-on", "prototype")
    assert result.returncode == 2
    codes = {item["code"] for item in json.loads(result.stdout)["findings"]}
    assert "blocking_prompt" in codes
    assert "next_slice" in codes
