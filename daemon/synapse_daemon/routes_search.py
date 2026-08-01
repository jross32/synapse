"""Universal AI/UI search route (Contract #21).

The original tokeniser and renderer client shipped years before the daemon
route was mounted. This route scores the daemon's current projects, manifest
tools, MCP servers, pages, actions, and settings directly so results never
depend on a stale secondary index.
"""

from __future__ import annotations

import time
from typing import Any, Literal

from fastapi import APIRouter, Query
from pydantic import BaseModel

from . import mcp_servers, projects
from .search import build_search_tokens, tokenise
from .storage import Storage
from .tools_registry import ToolRegistry


class SearchHit(BaseModel):
    entity_type: Literal["project", "tool", "action", "setting"]
    entity_id: str
    name: str
    description: str | None = None
    score: float
    href: str | None = None
    badge: str | None = None


class SearchResponse(BaseModel):
    query: str
    hits: list[SearchHit]
    took_ms: float


def _candidate(
    entity_type: Literal["project", "tool", "action", "setting"],
    entity_id: str,
    name: str,
    description: str,
    *,
    tags: list[str] | None = None,
    href: str | None = None,
    badge: str | None = None,
) -> dict[str, Any]:
    return {
        "entity_type": entity_type,
        "entity_id": entity_id,
        "name": name,
        "description": description,
        "tokens": build_search_tokens(entity_id, name, description, tags=tags or []),
        "href": href,
        "badge": badge,
    }


def _score(candidate: dict[str, Any], terms: list[str], query: str) -> float:
    tokens = candidate["tokens"]
    name = str(candidate["name"]).lower()
    entity_id = str(candidate["entity_id"]).lower()
    score = 0.0
    for term in terms:
        if term == entity_id or term == name:
            score += 12.0
        elif term in entity_id or term in name:
            score += 6.0
        token_scores = [3.0 if token == term else 1.5 if token.startswith(term) else 0.0 for token in tokens]
        score += max(token_scores, default=0.0)
    if query == name or query == entity_id:
        score += 10.0
    return score


def build_search_router(storage: Storage, registry: ToolRegistry) -> APIRouter:
    router = APIRouter(tags=["search"])

    @router.get("/search", response_model=SearchResponse)
    async def universal_search(
        q: str = Query(min_length=1, max_length=200),
        limit: int = Query(default=20, ge=1, le=50),
    ) -> SearchResponse:
        started = time.perf_counter()
        query = q.strip().lower()
        terms = tokenise(query)
        candidates: list[dict[str, Any]] = []

        for project in projects.list_projects(storage.conn):
            candidates.append(
                _candidate(
                    "project",
                    project.id,
                    project.name,
                    project.description,
                    tags=[*project.tags, project.category, project.kind.value],
                    href="apps:projects",
                    badge="Project",
                )
            )
        for manifest in registry.list_manifests():
            candidates.append(
                _candidate(
                    "tool",
                    manifest.id,
                    manifest.name,
                    manifest.description,
                    tags=[manifest.category, "synapse", "tool"],
                    href="tools:installed",
                    badge="Synapse tool",
                )
            )
        for server in mcp_servers.list_servers(storage.conn):
            candidates.append(
                _candidate(
                    "tool",
                    f"mcp:{server.id}",
                    server.name,
                    server.description,
                    tags=["mcp", "server", server.transport.value, "enabled" if server.enabled else "disabled"],
                    href="tools:mcp",
                    badge="MCP server",
                )
            )

        static = [
            ("action", "open-live", "Open Live View", "Watch connected AIs, squads, tools, and MCP receipts", "live"),
            ("action", "create-squad", "Create an AI squad", "Build a role and personality based AI team", "ai-coding:squads"),
            ("action", "open-review", "Open Review inbox", "Review blockers, handoffs, and AI proposals", "ai-coding:review"),
            ("action", "restart-synapse", "Restart Synapse", "Open the visible measured restart flow", "settings:system"),
            ("setting", "mcp-servers", "MCP Servers", "Enable, auto-attach, and inspect AI tools", "tools:mcp"),
            ("setting", "live-view-mode", "Live View detail mode", "Switch between Deep and Summary View", "live"),
        ]
        for entity_type, entity_id, name, description, href in static:
            candidates.append(
                _candidate(entity_type, entity_id, name, description, href=href, badge=entity_type.title())
            )

        scored = [
            SearchHit(
                entity_type=candidate["entity_type"],
                entity_id=candidate["entity_id"],
                name=candidate["name"],
                description=candidate["description"],
                score=score,
                href=candidate["href"],
                badge=candidate["badge"],
            )
            for candidate in candidates
            if (score := _score(candidate, terms, query)) > 0
        ]
        scored.sort(key=lambda hit: (-hit.score, hit.name.lower(), hit.entity_id))
        return SearchResponse(
            query=q.strip(),
            hits=scored[:limit],
            took_ms=round((time.perf_counter() - started) * 1000, 3),
        )

    return router
