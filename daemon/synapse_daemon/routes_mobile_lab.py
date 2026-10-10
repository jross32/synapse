"""Protected, read-only Mobile Lab capability routes; no downloads or device actions."""
from fastapi import APIRouter, Depends
from .auth import AuthManager, require_token
from .mobile_lab import device_plan, system_capabilities


def build_mobile_lab_router(auth: AuthManager) -> APIRouter:
    router = APIRouter(tags=["mobile-lab"], dependencies=[Depends(require_token(auth))])

    @router.get("/mobile-lab/capabilities")
    async def capabilities() -> dict:
        return system_capabilities()

    @router.get("/mobile-lab/ios/plan")
    async def ios_plan() -> dict:
        return device_plan(system_capabilities())

    return router
