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

from . import mcp_servers
from . import projects as projects_module
from .health import HealthProbe
from .projects import Project, ProjectKind, ProjectUpdate, update
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


def resolve_web_scraper_path(
    storage: Storage,
    *,
    parent_dir: Path | None = None,
    source_path: Path | None = None,
) -> Path:
    fallback = (parent_dir or Path.home()) / "wbscrper"

    candidates: list[Path] = []
    if source_path is not None:
        candidates.append(source_path)
    candidates.append(mcp_servers.web_scraper_install_dir(storage.data_dir))
    candidates.append((parent_dir or Path.home()) / "wbscrper")
    candidates.append(Path("C:/Users/justi/wbscrper"))
    for candidate in candidates:
        try:
            resolved = candidate.resolve()
        except OSError:
            resolved = candidate
        if mcp_servers.looks_like_web_scraper_repo(resolved):
            return resolved
    return fallback


def reconcile_web_scraper_project(storage: Storage, *, source_path: Path | None = None) -> bool:
    project = projects_module.get_or_none(storage.conn, WBSCRPER_PROJECT_ID)
    if project is None:
        return False
    preferred = resolve_web_scraper_path(storage, source_path=source_path)
    try:
        preferred_resolved = preferred.resolve()
    except OSError:
        preferred_resolved = preferred
    if not mcp_servers.looks_like_web_scraper_repo(preferred_resolved):
        return False
    current_path = Path(project.path)
    try:
        current_resolved = current_path.resolve()
    except OSError:
        current_resolved = current_path
    if current_resolved == preferred_resolved:
        return False
    if mcp_servers.looks_like_web_scraper_repo(current_resolved):
        return False
    with storage.transaction() as conn:
        update(conn, WBSCRPER_PROJECT_ID, ProjectUpdate(path=str(preferred_resolved)))
    return True


def seed_default_projects(storage: Storage, *, parent_dir: Path | None = None) -> list[str]:
    """Insert any default projects missing from the registry.

    Returns the list of project IDs created in this call (empty on a re-run).
    """

    created: list[str] = []

    wbscrper_path = resolve_web_scraper_path(storage, parent_dir=parent_dir)

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
