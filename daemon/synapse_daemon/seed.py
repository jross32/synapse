"""First-run seed for the projects table.

We don't ship hardcoded sample data — but we *do* register the user's nearby
wbscrper repo on first run, since that's the canonical demo project for
Synapse v0.1. If the user already has a project with id ``wbscrper`` (because
they edited it, or restored from a snapshot), we leave it alone.

Future tools dropped into ``tools/`` are seeded by their own manifest at
startup; this module only deals with **launchable apps**, not Synapses.
"""

from __future__ import annotations

import logging
from pathlib import Path

from . import projects as projects_module
from .health import HealthProbe
from .projects import Project, ProjectKind
from .runtime_paths import repo_root
from .storage import Storage

log = logging.getLogger(__name__)

WBSCRPER_PROJECT_ID = "wbscrper"
SYNAPSE_SELF_PROJECT_ID = "synapse-self"


def _looks_like_synapse_repo(path: Path) -> bool:
    return (
        (path / "AGENTS.md").exists()
        and (path / "package.json").exists()
        and (path / "daemon").is_dir()
        and (path / "renderer").is_dir()
    )


def resolve_synapse_self_path(*, parent_dir: Path | None = None) -> Path:
    candidates: list[Path] = [repo_root(), Path.cwd()]
    if parent_dir is not None:
        candidates.append(parent_dir / "synapse")
    candidates.append(Path("C:/Users/justi/synapse"))
    for candidate in candidates:
        try:
            resolved = candidate.resolve()
        except OSError:
            resolved = candidate
        if _looks_like_synapse_repo(resolved):
            return resolved
    return repo_root()


def seed_default_projects(storage: Storage, *, parent_dir: Path | None = None) -> list[str]:
    """Insert any default projects missing from the registry.

    Returns the list of project IDs created in this call (empty on a re-run).
    """

    created: list[str] = []

    wbscrper_path = (parent_dir or Path.home()) / "wbscrper"
    if not wbscrper_path.exists():
        wbscrper_path = Path("C:/Users/justi/wbscrper")  # known location on dev machine

    if projects_module.get_or_none(storage.conn, WBSCRPER_PROJECT_ID) is None:
        project = Project(
            id=WBSCRPER_PROJECT_ID,
            name="Web Scraper",
            description="General-purpose Playwright web scraper (MCP server + REST app).",
            category="apps",
            icon="globe",
            path=str(wbscrper_path),
            launch_cmd="npm start",
            expected_port=12345,
            health=HealthProbe(
                kind="http",
                target="http://localhost:12345/api/status",
                interval_seconds=15,
            ),
        )
        with storage.transaction() as conn:
            projects_module.create(conn, project)
        created.append(WBSCRPER_PROJECT_ID)
        log.info("Seeded default project: %s at %s", WBSCRPER_PROJECT_ID, wbscrper_path)

    synapse_self_path = resolve_synapse_self_path(parent_dir=parent_dir)
    if projects_module.get_or_none(storage.conn, SYNAPSE_SELF_PROJECT_ID) is None:
        project = Project(
            id=SYNAPSE_SELF_PROJECT_ID,
            name="Synapse Self",
            description=(
                "The local Synapse repo wired as the default self-improvement "
                "workspace for workbenches, coder threads, and benchmark passes."
            ),
            category="apps",
            icon="sparkles",
            path=str(synapse_self_path),
            launch_cmd="synapse.cmd",
            expected_port=7878,
            kind=ProjectKind.OTHER,
            health=HealthProbe(
                kind="http",
                target="http://127.0.0.1:7878/api/v1/health",
                interval_seconds=15,
            ),
        )
        with storage.transaction() as conn:
            projects_module.create(conn, project)
        created.append(SYNAPSE_SELF_PROJECT_ID)
        log.info("Seeded default project: %s at %s", SYNAPSE_SELF_PROJECT_ID, synapse_self_path)

    return created
