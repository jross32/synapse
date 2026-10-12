"""Authenticated REST endpoints for Railway cost visibility.

Mounted into the existing Watchdogs router to avoid altering the live daemon app
bootstrap while other workers edit it.
"""
from __future__ import annotations

import math
import os
from pathlib import Path

from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from .railway_cost_monitor import get_status, update_thresholds
from .profile import ProfileManager
from . import railway_oauth


class RailwayBudgetInput(BaseModel):
    warning_usd: float
    critical_usd: float


def build_railway_costs_router(data_dir: Path, profile: ProfileManager) -> APIRouter:
    router = APIRouter(tags=["railway-costs"])

    def require_developer() -> None:
        a = profile.summary(refresh_remote=False)
        pinned = os.getenv("SYNAPSE_DEVELOPER_USER_ID", "").strip()
        if not (a.signed_in and a.email_verified and a.user_id and (a.email or "").strip().casefold() == "justinwross32@gmail.com" and (not pinned or pinned == a.user_id)):
            raise HTTPException(status_code=403, detail="Developer access required")

    @router.get("/system/railway-costs/access")
    async def railway_access():
        try:
            require_developer()
        except HTTPException:
            return {"allowed": False}
        return {"allowed": True}

    @router.get("/system/railway-oauth/status", dependencies=[Depends(require_developer)])
    async def oauth_status():
        return await run_in_threadpool(railway_oauth.status, data_dir, railway_oauth.owner(profile))

    @router.post("/system/railway-oauth/start", dependencies=[Depends(require_developer)])
    async def oauth_start():
        # Registered native redirect URI must match exactly; no user-supplied redirect.
        redirect = os.environ.get("SYNAPSE_RAILWAY_OAUTH_REDIRECT_URI", "http://127.0.0.1:7878/api/v1/system/railway-oauth/callback")
        try:
            return railway_oauth.make_authorization(railway_oauth.owner(profile), redirect)
        except (RuntimeError, ValueError) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @router.delete("/system/railway-oauth", dependencies=[Depends(require_developer)])
    async def oauth_disconnect():
        await run_in_threadpool(railway_oauth.remove, data_dir, railway_oauth.owner(profile))
        return {"connected": False}

    @router.get("/system/railway-costs", dependencies=[Depends(require_developer)])
    async def railway_cost_status(refresh: bool = False):
        return await run_in_threadpool(get_status, data_dir, refresh=refresh, owner_id=railway_oauth.owner(profile))

    @router.post("/system/railway-costs/budget", dependencies=[Depends(require_developer)])
    async def save_budget(body: RailwayBudgetInput):
        if not all(math.isfinite(n) for n in (body.warning_usd, body.critical_usd)):
            raise HTTPException(status_code=422, detail="Budget thresholds must be finite")
        try:
            await run_in_threadpool(update_thresholds, data_dir, body.warning_usd, body.critical_usd)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return await run_in_threadpool(get_status, data_dir, refresh=False, owner_id=railway_oauth.owner(profile))

    return router


def build_railway_callback_router(data_dir: Path, profile: ProfileManager) -> APIRouter:
    callback_router = APIRouter(tags=["railway-oauth"])
    @callback_router.get("/system/railway-oauth/callback")
    async def oauth_callback(request: Request, code: str = "", state: str = "", error: str = ""):
        # Browser redirects carry no X-Synapse-Token; only an exact loopback URL
        # plus a cryptographically random one-time PKCE state may complete auth.
        from fastapi.responses import HTMLResponse
        if request.url.hostname != "127.0.0.1":
            return HTMLResponse("<h2>Railway callback must use local loopback.</h2>", status_code=403)
        if error or not code or not state:
            return HTMLResponse("<h2>Railway connection cancelled.</h2>", status_code=400)
        account = railway_oauth.owner(profile)
        if not account:
            return HTMLResponse("<h2>Synapse developer session is not active.</h2>", status_code=403)
        try:
            await run_in_threadpool(railway_oauth.complete, data_dir, account, state, code)
        except (ValueError, RuntimeError):
            return HTMLResponse("<h2>Railway authorization failed. Return to Synapse and try again.</h2>", status_code=400)
        return HTMLResponse("<h2>Railway connected to Synapse.</h2><p>Return to Synapse Profile to view the connection.</p>")

    return callback_router
