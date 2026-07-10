"""Guards against version-file drift.

`package.json`, `pyproject.toml`, and `synapse_daemon.__version__` must all declare
the same version. This drifted in 0.1.40 (the pyproject bump was missed and had to
be fixed in a follow-up commit); this test makes it a hard gate so it can't happen
silently again. Implements inbox proposal 11ac413441c8.
"""

from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _init_version() -> str:
    text = (REPO_ROOT / "daemon" / "synapse_daemon" / "__init__.py").read_text(encoding="utf-8")
    match = re.search(r'__version__\s*=\s*"([^"]+)"', text)
    assert match is not None, "no __version__ found in synapse_daemon/__init__.py"
    return match.group(1)


def _package_json_version() -> str:
    return json.loads((REPO_ROOT / "package.json").read_text(encoding="utf-8"))["version"]


def _pyproject_version() -> str:
    data = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    return data["project"]["version"]


def test_version_files_agree() -> None:
    init_v = _init_version()
    pkg_v = _package_json_version()
    pyproject_v = _pyproject_version()
    assert init_v == pkg_v == pyproject_v, (
        "version-file drift -- run scripts/version-bump.ps1 to sync all three: "
        f"__init__.py={init_v!r}, package.json={pkg_v!r}, pyproject.toml={pyproject_v!r}"
    )
