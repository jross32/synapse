"""Runtime path helpers for source-tree and packaged Synapse builds.

The daemon can run in two very different environments:

1. Editable/source mode from the repo root.
2. Bundled mode as a Windows executable launched by Electron from
   ``resources/daemon/``.

These helpers keep resource lookups (tools, templates, mobile shell, bundled
docs) cwd-independent in both cases.
"""

from __future__ import annotations

import sys
from pathlib import Path


def is_frozen() -> bool:
    """Return True when running from a bundled executable."""

    return bool(getattr(sys, "frozen", False))


def repo_root() -> Path:
    """Return the source checkout root when running from Python source."""

    return Path(__file__).resolve().parent.parent.parent


def resources_root() -> Path:
    """Return the root that holds runtime resources for this daemon."""

    if not is_frozen():
        return repo_root()

    exe_dir = Path(sys.executable).resolve().parent
    if exe_dir.name.lower() == "daemon":
        return exe_dir.parent
    return exe_dir


def bundled_tools_dir() -> Path:
    return resources_root() / "tools"


def bundled_dist_dir() -> Path:
    return resources_root() / "dist"


def bundled_mobile_dir() -> Path:
    return resources_root() / "mobile"


def bundled_templates_dir() -> Path:
    return resources_root() / "templates"


def bundled_quick_actions_dir() -> Path:
    return bundled_templates_dir() / "quick-actions"


def bundled_docs_dir() -> Path:
    return resources_root() / "docs"


def bundled_marketplace_sample() -> Path:
    return bundled_docs_dir() / "marketplace-sample.json"


def bundled_models_sample() -> Path:
    return bundled_docs_dir() / "models-sample.json"


def bundled_mcp_servers_sample() -> Path:
    return bundled_docs_dir() / "mcp-servers-sample.json"
