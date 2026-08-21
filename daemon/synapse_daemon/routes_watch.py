"""REST for the repo-change long-poll (see repo_watch.py for why this exists).

  POST /api/v1/watch/repo -- bounded wait for a git repo's status to change
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel

from . import repo_watch
from .errors import invalid


class RepoWatchRequest(BaseModel):
    path: str
    timeout_seconds: float = repo_watch.DEFAULT_TIMEOUT_SECONDS


def build_watch_router() -> APIRouter:
    router = APIRouter(prefix="/watch", tags=["watch"])

    @router.post("/repo", response_model=repo_watch.RepoWatchResult)
    async def watch_repo(payload: RepoWatchRequest) -> repo_watch.RepoWatchResult:
        target = Path(payload.path).expanduser()
        if not target.is_absolute():
            raise invalid("path", "path must be absolute.")
        if not target.is_dir():
            raise invalid("path", f"No such directory: {target}")
        return await repo_watch.wait_for_repo_change(
            target, timeout_seconds=payload.timeout_seconds
        )

    return router
