"""Universal-search token helpers (Contract #21).

Every searchable entity contributes lowercase tokens. ``GET /api/v1/search``
currently scores projects, tools, MCP servers, actions, and settings directly
from their live sources of truth so newly discovered MCPs appear immediately.
The token helpers stay shared with future persisted-index optimisations; the
HTTP route and result schema live in :mod:`synapse_daemon.routes_search`.
"""

from __future__ import annotations

import re
from typing import Iterable, Protocol

_TOKEN_PATTERN = re.compile(r"[a-z0-9]+")


def tokenise(text: str) -> list[str]:
    """Lower-case + extract alphanumeric tokens. Identical on daemon + client.

    >>> tokenise("Web-Scraper v2 (alpha)")
    ['web', 'scraper', 'v2', 'alpha']
    """

    return _TOKEN_PATTERN.findall(text.lower())


def build_search_tokens(*fields: str | None, tags: Iterable[str] = ()) -> list[str]:
    """Combine an entity's textual fields + tags into a deduped token list."""

    seen: set[str] = set()
    for value in (*fields, *tags):
        if not value:
            continue
        for tok in tokenise(value):
            if tok not in seen:
                seen.add(tok)
    return sorted(seen)


class Indexable(Protocol):
    """Anything that wants to appear in the Ctrl+K palette."""

    @property
    def entity_type(self) -> str:  # 'project' | 'tool' | 'action' | 'setting'
        ...

    @property
    def entity_id(self) -> str:
        ...

    def search_tokens(self) -> list[str]:
        """Return the tokens to insert into the search index."""
        ...
