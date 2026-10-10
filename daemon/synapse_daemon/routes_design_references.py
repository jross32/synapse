"""Semantic visual/design references attached to durable project files."""
from __future__ import annotations
import uuid
from fastapi import APIRouter
from pydantic import BaseModel, Field
from . import projects as projects_module
from .errors import not_found
from .files_storage import get_file
from .storage import Storage
from .time_utils import to_iso, utc_now

class DesignRefIn(BaseModel):
 file_id:str
 role:str=Field(pattern="^(proposed_ui|reference|brand|flow|architecture|other)$")
 title:str=Field(min_length=1,max_length=160)
 description:str|None=None
 is_current:bool=False
 ai_visible:bool=True

def _rows(storage,project_id):
 rows=storage.conn.execute("""SELECT d.*,f.original_name,f.mime,f.size_bytes FROM project_design_references d JOIN project_files f ON f.id=d.file_id WHERE d.project_id=? AND f.deleted_at IS NULL ORDER BY d.is_current DESC,d.updated_at DESC""",(project_id,)).fetchall()
 return [{**dict(r),"is_current":bool(r["is_current"]),"ai_visible":bool(r["ai_visible"]),"url":f"/api/v1/projects/{project_id}/files/{r['file_id']}"} for r in rows]

def build_design_references_router(storage:Storage)->APIRouter:
 router=APIRouter(tags=["design-references"])
 @router.get("/projects/{project_id}/design-references")
 async def list_refs(project_id:str): projects_module.get(storage.conn,project_id); return {"references":_rows(storage,project_id)}
 @router.post("/projects/{project_id}/design-references")
 async def add_ref(project_id:str,payload:DesignRefIn):
  projects_module.get(storage.conn,project_id); f=get_file(storage.conn,payload.file_id)
  if f is None or f.project_id!=project_id or f.deleted_at: raise not_found("file",payload.file_id)
  now=to_iso(utc_now()); rid=str(uuid.uuid4())
  with storage.transaction() as conn:
   if payload.is_current: conn.execute("UPDATE project_design_references SET is_current=0,updated_at=? WHERE project_id=? AND role=?",(now,project_id,payload.role))
   conn.execute("""INSERT INTO project_design_references(id,project_id,file_id,role,title,description,is_current,ai_visible,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)""",(rid,project_id,payload.file_id,payload.role,payload.title,payload.description,int(payload.is_current),int(payload.ai_visible),now,now))
  return {"reference":next(r for r in _rows(storage,project_id) if r["id"]==rid)}
 return router
