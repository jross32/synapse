"""REST for the What's New + Roadmap surface (ADR-0019)."""

from __future__ import annotations

from fastapi import APIRouter

from . import about
from .about import Changelog, Roadmap


def build_about_router() -> APIRouter:
    router = APIRouter(prefix="/about", tags=["about"])

    @router.get("/changelog", response_model=Changelog)
    async def changelog() -> Changelog:
        return about.load_changelog()

    @router.get("/roadmap", response_model=Roadmap)
    async def roadmap() -> Roadmap:
        return about.load_roadmap()

    return router
