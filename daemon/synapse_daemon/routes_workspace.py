"""Authenticated local workspace registry routes (no arbitrary remote execution)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from .auth import AuthManager, require_token
from .profile import ProfileManager
from .machine_fleet import ensure_machine_id
from .workspace_catalog import WorkspaceCatalog


class RegisterProject(BaseModel):
    project_id: str = Field(min_length=1, max_length=128)
    project_path: str = Field(min_length=1, max_length=4096)
    revision: str = Field(default='', max_length=200)


class NoteUpdate(BaseModel):
    content: str = Field(max_length=200000)
    expected_version: int | None = Field(default=None, ge=0)


def build_workspace_router(auth: AuthManager, profile: ProfileManager, data_dir) -> APIRouter:
    router = APIRouter(prefix='/workspace', tags=['workspace'], dependencies=[Depends(require_token(auth))])
    catalog = WorkspaceCatalog(data_dir / 'workspace-catalog.sqlite')

    def owner() -> str:
        state = profile.summary(refresh_remote=False)
        if not state.signed_in or not state.user_id:
            raise HTTPException(status_code=401, detail='Synapse account sign-in required')
        return state.user_id

    @router.get('/projects/{project_id}/locations')
    async def locations(project_id: str) -> dict:
        return {'project_id': project_id, 'locations': catalog.locations(owner(), project_id)}

    @router.post('/projects/locations')
    async def register(payload: RegisterProject) -> dict:
        from pathlib import Path
        # Never accept a path to a missing directory or fabricate a remote host.
        root = Path(payload.project_path).resolve(strict=True)
        if not root.is_dir() or Path.home().resolve() not in root.parents:
            raise HTTPException(status_code=403, detail='Only local project directories within the user home are allowed')
        device = ensure_machine_id(data_dir)
        catalog.register(owner(), payload.project_id, device, str(root), payload.revision)
        return {'project_id': payload.project_id, 'device_id': device, 'registered': True}

    @router.get('/projects/{project_id}/notes/{note_key}')
    async def note(project_id: str, note_key: str) -> dict:
        result = catalog.get_note(owner(), project_id, note_key)
        if result is None:
            raise HTTPException(status_code=404, detail='Note not found')
        return result

    @router.put('/projects/{project_id}/notes/{note_key}')
    async def update_note(project_id: str, note_key: str, payload: NoteUpdate) -> dict:
        try:
            version = catalog.set_note(owner(), project_id, note_key, payload.content, payload.expected_version)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return {'project_id': project_id, 'note_key': note_key, 'version': version}

    return router
