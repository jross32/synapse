"""Account-bound workspace metadata API with optimistic note versioning."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from .db import Account, RelayDevice, WorkspaceLocation, WorkspaceNote, utc_now

class LocationInput(BaseModel):
    device_id: str = Field(min_length=1, max_length=128)
    path: str = Field(min_length=1, max_length=2048)
    revision: str = Field(default="", max_length=128)

class NoteInput(BaseModel):
    content: str = Field(max_length=200000)
    expected_version: int = Field(ge=0)

def install_workspace_routes(app, current_account, get_db):
    router = APIRouter(prefix="/v1/workspace", tags=["workspace"])

    @router.put("/projects/{project_id}/locations")
    def register_location(project_id: str, payload: LocationInput,
                          account: Account = Depends(current_account),
                          db: Session = Depends(get_db)):
        if not 1 <= len(project_id) <= 128:
            raise HTTPException(422, "Invalid project ID")
        enrolled = db.scalar(select(RelayDevice).where(
            RelayDevice.account_id == account.id, RelayDevice.device_id == payload.device_id,
            RelayDevice.revoked_at.is_(None)))
        if enrolled is None:
            raise HTTPException(403, "Device must be enrolled in this account")
        existing = db.scalar(select(WorkspaceLocation).where(
            WorkspaceLocation.account_id == account.id,
            WorkspaceLocation.project_id == project_id,
            WorkspaceLocation.device_id == payload.device_id))
        if existing is None:
            existing = WorkspaceLocation(
                account_id=account.id, project_id=project_id,
                device_id=payload.device_id, project_path=payload.path)
            db.add(existing)
        existing.project_path = payload.path
        existing.revision = payload.revision
        existing.last_seen_at = utc_now()
        db.flush()
        return {"project_id": project_id, "device_id": payload.device_id}

    @router.get("/projects/{project_id}/locations")
    def get_locations(project_id: str, account: Account = Depends(current_account),
                      db: Session = Depends(get_db)):
        rows = db.scalars(select(WorkspaceLocation).where(
            WorkspaceLocation.account_id == account.id,
            WorkspaceLocation.project_id == project_id)).all()
        return {"locations": [
            {"device_id": r.device_id, "path": r.project_path,
             "revision": r.revision, "last_seen_at": r.last_seen_at.isoformat()}
            for r in rows]}

    @router.get("/projects/{project_id}/notes/{key}")
    def get_note(project_id: str, key: str,
                 account: Account = Depends(current_account),
                 db: Session = Depends(get_db)):
        row = db.scalar(select(WorkspaceNote).where(
            WorkspaceNote.account_id == account.id,
            WorkspaceNote.project_id == project_id,
            WorkspaceNote.note_key == key))
        if row is None:
            raise HTTPException(404, "Note not found")
        return {"content": row.content, "version": row.version,
                "updated_at": row.updated_at.isoformat()}

    @router.put("/projects/{project_id}/notes/{key}")
    def put_note(project_id: str, key: str, payload: NoteInput,
                 account: Account = Depends(current_account),
                 db: Session = Depends(get_db)):
        if not 1 <= len(project_id) <= 128 or not 1 <= len(key) <= 128:
            raise HTTPException(422, "Invalid note identifier")
        if payload.expected_version == 0:
            try:
                with db.begin_nested():
                    db.add(WorkspaceNote(account_id=account.id, project_id=project_id,
                          note_key=key, content=payload.content, version=1))
                    db.flush()
            except IntegrityError as exc:
                raise HTTPException(409, "Note version conflict") from exc
            return {"version": 1}
        result = db.execute(update(WorkspaceNote).where(
            WorkspaceNote.account_id == account.id,
            WorkspaceNote.project_id == project_id,
            WorkspaceNote.note_key == key,
            WorkspaceNote.version == payload.expected_version
        ).values(content=payload.content, version=payload.expected_version + 1,
                 updated_at=utc_now()))
        if result.rowcount != 1:
            raise HTTPException(409, "Note version conflict")
        return {"version": payload.expected_version + 1}

    app.include_router(router)
