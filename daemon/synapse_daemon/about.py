"""What's New + Roadmap (ADR-0019).

Serves two things the in-app "path" surface renders:
- the **changelog** (what shipped), parsed from the repo's ``CHANGELOG.md``;
- the **roadmap** (what's coming), read from a curated ``docs/roadmap.json``.

Both degrade to empty rather than erroring, so the surface always renders.
"""

from __future__ import annotations

import json
import re

from pydantic import BaseModel, Field

from .runtime_paths import bundled_changelog, bundled_roadmap

_VERSION_RE = re.compile(r"##\s*\[([^\]]+)\](?:\s*[-–—]+\s*(.+))?\s*$")


class ChangelogSection(BaseModel):
    title: str = ""
    items: list[str] = Field(default_factory=list)


class ChangelogVersion(BaseModel):
    version: str
    date: str | None = None
    summary: str = ""
    sections: list[ChangelogSection] = Field(default_factory=list)


class Changelog(BaseModel):
    versions: list[ChangelogVersion] = Field(default_factory=list)


class RoadmapItem(BaseModel):
    id: str
    title: str
    status: str = "coming"  # shipped | in_progress | coming
    summary: str = ""
    phase: str | None = None
    adr: str | None = None


class Roadmap(BaseModel):
    generated_at: str | None = None
    items: list[RoadmapItem] = Field(default_factory=list)


def parse_changelog(text: str) -> list[ChangelogVersion]:
    versions: list[ChangelogVersion] = []
    current: ChangelogVersion | None = None
    section: ChangelogSection | None = None

    for raw in text.splitlines():
        line = raw.rstrip()
        version_match = _VERSION_RE.match(line) if line.startswith("## [") else None
        if version_match:
            date = (version_match.group(2) or "").strip() or None
            current = ChangelogVersion(version=version_match.group(1), date=date)
            versions.append(current)
            section = None
        elif line.startswith("### ") and current is not None:
            section = ChangelogSection(title=line[4:].strip())
            current.sections.append(section)
        elif line.lstrip().startswith("- ") and current is not None:
            if section is None:
                section = ChangelogSection(title="")
                current.sections.append(section)
            section.items.append(line.lstrip()[2:].strip())
        elif line.strip() and current is not None:
            # continuation of the last bullet, or summary text before any section
            if section is not None and section.items:
                section.items[-1] = f"{section.items[-1]} {line.strip()}".strip()
            elif section is None:
                current.summary = f"{current.summary} {line.strip()}".strip()

    # Drop a placeholder [Unreleased] / empty version with no content.
    return [v for v in versions if v.summary or any(s.items for s in v.sections)]


def load_changelog() -> Changelog:
    try:
        text = bundled_changelog().read_text(encoding="utf-8")
    except Exception:  # noqa: BLE001
        return Changelog()
    return Changelog(versions=parse_changelog(text))


def load_roadmap() -> Roadmap:
    try:
        raw = json.loads(bundled_roadmap().read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return Roadmap()
    items: list[RoadmapItem] = []
    for entry in raw.get("items", []):
        if not isinstance(entry, dict) or not entry.get("id"):
            continue
        try:
            items.append(RoadmapItem(**entry))
        except Exception:  # noqa: BLE001
            continue
    return Roadmap(generated_at=raw.get("generated_at"), items=items)
