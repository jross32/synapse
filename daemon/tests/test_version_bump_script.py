from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest


def test_version_bump_updates_crlf_python_versions_and_preserves_unicode(tmp_path: Path) -> None:
    pwsh = shutil.which("pwsh")
    if pwsh is None:
        pytest.skip("PowerShell 7 is required for the version-bump integration test")

    root = tmp_path / "repo"
    (root / "scripts").mkdir(parents=True)
    (root / "daemon" / "synapse_daemon").mkdir(parents=True)
    source_script = Path(__file__).resolve().parents[2] / "scripts" / "version-bump.ps1"
    shutil.copy2(source_script, root / "scripts" / "version-bump.ps1")

    package = {
        "name": "synapse-test",
        "version": "1.2.3",
        "description": "Synapse ? Unicode must survive",
        "scripts": {"dev": "echo em dash ? stays"},
    }
    (root / "package.json").write_text(json.dumps(package, indent=2), encoding="utf-8")
    (root / "pyproject.toml").write_bytes(b'[project]\r\nname = "x"\r\nversion = "1.2.3"\r\n')
    (root / "daemon" / "synapse_daemon" / "__init__.py").write_bytes(
        b'__version__ = "1.2.3"\r\n'
    )
    (root / "CHANGELOG.md").write_bytes(b'# Changelog\r\n\r\n## [Unreleased]\r\n')

    result = subprocess.run(
        [pwsh, "-NoProfile", "-File", str(root / "scripts" / "version-bump.ps1"), "-Set", "1.2.4"],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout

    package_after = (root / "package.json").read_text(encoding="utf-8-sig")
    bumped = json.loads(package_after)
    assert bumped["version"] == "1.2.4"
    expected_package = (root / "package.json").read_text(encoding="utf-8-sig").replace(
        '"version": "1.2.4"', '"version": "1.2.3"', 1
    )
    original_package = json.dumps(package, indent=2) + "\n"
    assert expected_package == original_package
    assert bumped["description"] == package["description"]
    assert bumped["scripts"]["dev"] == package["scripts"]["dev"]
    assert 'version = "1.2.4"' in (root / "pyproject.toml").read_text(encoding="utf-8-sig")
    assert '__version__ = "1.2.4"' in (
        root / "daemon" / "synapse_daemon" / "__init__.py"
    ).read_text(encoding="utf-8-sig")
