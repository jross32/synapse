"""SQLite migrations (Contract #9).

Every schema change is a numbered ``.sql`` file in this folder, in the form
``<NNN>_<slug>.sql``. The daemon applies unapplied migrations on startup
against a ``schema_migrations`` tracking table. **Never edit a shipped
migration** — always add a new one.

The actual runner lives in :mod:`synapse_daemon.migrations.runner` (added in
Milestone B alongside SQLite wiring). For v0.1.1 we only ship the SQL files;
the runner is a stub that lists them in order.
"""

from __future__ import annotations

import re
from importlib import resources
from typing import NamedTuple

MIGRATION_PATTERN = re.compile(r"^(\d{3})_([a-z0-9_]+)\.sql$")


class Migration(NamedTuple):
    """One migration file on disk."""

    number: int
    slug: str
    filename: str


def list_migrations() -> list[Migration]:
    """Return all migrations in this package, sorted by number.

    Used by the runner at startup and by tests to validate naming + ordering.
    """

    pkg = resources.files(__name__)
    found: list[Migration] = []
    for entry in pkg.iterdir():
        match = MIGRATION_PATTERN.match(entry.name)
        if match:
            found.append(
                Migration(
                    number=int(match.group(1)),
                    slug=match.group(2),
                    filename=entry.name,
                )
            )
    found.sort(key=lambda m: m.number)
    return found
