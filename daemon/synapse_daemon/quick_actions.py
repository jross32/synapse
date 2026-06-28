"""Quick-action templates (ADR-0003 Phase F · v0.1.34).

A *quick action* is a curated AI prompt that the Sessions page can launch
with one click. The button opens a workbench PTY in a "scratch" project,
writes the templated prompt to ``PROMPT.md`` in the project's cwd, and
exposes the same prompt through the ``SYNAPSE_QUICK_ACTION_PROMPT`` env
var so a Claude / Codex session sees it on prompt 1.

Honest scope (ADR-0003 verbatim): the daemon does not *do* the work. The
button ships the shortcut; the AI session does the building.

Templates live at ``templates/quick-actions/<id>.json``. Format::

    {
      "id": "new-mcp-server",
      "name": "New MCP server",
      "description": "Scaffold an MCP server using @modelcontextprotocol/sdk.",
      "icon": "server",
      "prompt": "I want to build an MCP server that does X. Use ...",
      "default_argv": ["claude"]
    }

A future marketplace can drop more templates into the same folder.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from collections.abc import Iterable
from pathlib import Path

from .runtime_paths import bundled_quick_actions_dir

log = logging.getLogger(__name__)

# Bundled templates ship in this repo path. Tests may point elsewhere.
_DEFAULT_TEMPLATES_DIR = bundled_quick_actions_dir()

# Same ID alphabet as projects (Contract #10).
_ID_RE = re.compile(r"^[a-z][a-z0-9-]*[a-z0-9]$|^[a-z]$")


class QuickActionError(Exception):
    """Raised when a template file is malformed or missing required fields."""


@dataclass(frozen=True)
class QuickAction:
    """One curated AI prompt the user can launch with a click."""

    id: str
    name: str
    description: str
    prompt: str
    icon: str | None = None
    category: str | None = None
    tags: list[str] = field(default_factory=list)
    default_argv: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "prompt": self.prompt,
            "icon": self.icon,
            "category": self.category,
            "tags": list(self.tags),
            "default_argv": list(self.default_argv),
        }


def _normalize_tags(raw: object) -> list[str]:
    if raw is None:
        return []
    if not isinstance(raw, list) or any(not isinstance(tag, str) for tag in raw):
        raise QuickActionError("tags must be a list of strings.")
    seen: set[str] = set()
    out: list[str] = []
    for tag in raw:
        normalized = tag.strip().lower()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        out.append(normalized)
    return out


def _parse(raw: object, source: str) -> QuickAction:
    if not isinstance(raw, dict):
        raise QuickActionError(f"{source}: expected JSON object, got {type(raw).__name__}")
    missing = [k for k in ("id", "name", "description", "prompt") if not raw.get(k)]
    if missing:
        raise QuickActionError(f"{source}: missing required field(s): {', '.join(missing)}")
    action_id = str(raw["id"]).strip()
    if not _ID_RE.match(action_id):
        raise QuickActionError(
            f"{source}: id {action_id!r} must be kebab-case "
            "(lowercase letters, digits, single hyphens; start with a letter)."
        )
    default_argv = raw.get("default_argv") or []
    if not isinstance(default_argv, list) or any(not isinstance(p, str) for p in default_argv):
        raise QuickActionError(f"{source}: default_argv must be a list of strings.")
    category = raw.get("category")
    if category is not None and not isinstance(category, str):
        raise QuickActionError(f"{source}: category must be a string when set.")
    return QuickAction(
        id=action_id,
        name=str(raw["name"]).strip(),
        description=str(raw["description"]).strip(),
        prompt=str(raw["prompt"]),
        icon=(str(raw["icon"]).strip() if raw.get("icon") else None),
        category=(category.strip().lower() if isinstance(category, str) and category.strip() else None),
        tags=_normalize_tags(raw.get("tags")),
        default_argv=[str(p) for p in default_argv],
    )


def load_templates(
    directory: Path | None = None,
    *,
    extra_directories: Iterable[Path] | None = None,
) -> list[QuickAction]:
    """Read every ``*.json`` in one or more directories.

    Malformed files are logged and skipped -- one bad template never takes
    the whole list down. The result is sorted by ``name`` for stable
    rendering in the Sessions rail.
    """

    directories: list[Path] = [directory or _DEFAULT_TEMPLATES_DIR]
    if extra_directories is not None:
        directories.extend(path for path in extra_directories if path not in directories)
    actions: dict[str, QuickAction] = {}
    for target in directories:
        if not target.is_dir():
            log.info("Quick-action templates dir not found at %s; skipping.", target)
            continue
        for path in sorted(target.glob("*.json")):
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
                action = _parse(raw, str(path))
            except (json.JSONDecodeError, QuickActionError) as exc:
                log.warning("Skipping malformed quick-action template %s: %s", path, exc)
                continue
            if action.id in actions:
                log.warning(
                    "Duplicate quick-action id %r at %s; keeping the first occurrence.",
                    action.id,
                    path,
                )
                continue
            actions[action.id] = action
    return sorted(actions.values(), key=lambda a: a.name.lower())


def find_template(
    template_id: str,
    directory: Path | None = None,
    *,
    extra_directories: Iterable[Path] | None = None,
) -> QuickAction | None:
    """Return one template by id (lazy variant used by the launch route)."""

    for action in load_templates(directory, extra_directories=extra_directories):
        if action.id == template_id:
            return action
    return None
