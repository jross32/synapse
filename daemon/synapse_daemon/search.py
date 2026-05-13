"""Universal search index (Contract #21).

Every searchable entity contributes a list of lowercase tokens to ``search_index``.
The UI palette (Ctrl+K) queries ``GET /api/v1/search?q=<query>``, which:

1. Lower-cases the query and splits on whitespace.
2. Looks up each query token in ``search_index`` (prefix match).
3. Aggregates hits per entity with token weights.
4. Returns the top N by score.

This module provides the tokeniser + a base class for indexable entities.
Actual SQLite query helpers land in :mod:`synapse_daemon.storage` (Milestone B).
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
