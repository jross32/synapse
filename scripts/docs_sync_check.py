#!/usr/bin/env python3
"""Docs-sync gate: fail if a commit's docs/version state is out of sync.

Enforces the AGENTS.md commit rules that can be checked mechanically, so "keep the
docs + version in step with the code" is a hard gate, not just a habit:

  1. The three version files agree (package.json / pyproject.toml / __init__.py).
  2. CHANGELOG.md has an entry (`## [<version>]`) for the current version.
  3. README.md's status line names the current version (kept current so the public
     front page never lags the release).

Run it before every commit (`python scripts/docs_sync_check.py`) and in CI. Exit 0 =
in sync; exit 1 = something is stale, with a clear message. The subjective parts
(README reflects *capabilities*, PROGRESS/roadmap narrative) stay human/AI judgement
in the PR-template checklist -- this gate covers the unambiguous invariants.
"""

from __future__ import annotations

import json
import re
import sys
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def _init_version() -> str:
    text = (REPO_ROOT / "daemon" / "synapse_daemon" / "__init__.py").read_text(encoding="utf-8")
    m = re.search(r'__version__\s*=\s*"([^"]+)"', text)
    if not m:
        raise SystemExit("docs-sync: no __version__ in daemon/synapse_daemon/__init__.py")
    return m.group(1)


def _package_json_version() -> str:
    return json.loads((REPO_ROOT / "package.json").read_text(encoding="utf-8"))["version"]


def _pyproject_version() -> str:
    return tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]


def check() -> list[str]:
    """Return a list of problems; empty means fully in sync."""
    problems: list[str] = []
    init_v = _init_version()
    pkg_v = _package_json_version()
    pyproject_v = _pyproject_version()

    if not (init_v == pkg_v == pyproject_v):
        problems.append(
            "version-file drift (run scripts/version-bump.ps1): "
            f"__init__.py={init_v!r}, package.json={pkg_v!r}, pyproject.toml={pyproject_v!r}"
        )

    version = init_v
    changelog = (REPO_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    if f"## [{version}]" not in changelog:
        problems.append(
            f"CHANGELOG.md has no `## [{version}]` entry -- add one describing what this version changed."
        )

    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    if version not in readme:
        problems.append(
            f"README.md does not mention the current version ({version}) -- update the status line so the "
            "front page isn't stale."
        )

    return problems


def main() -> int:
    problems = check()
    if problems:
        print("docs-sync check FAILED:")
        for p in problems:
            print(f"  - {p}")
        return 1
    print(f"docs-sync check OK (version {_init_version()}: versions agree, CHANGELOG + README current).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
