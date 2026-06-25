"""REST for AI personalities (ADR-0018, MW3)."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from . import personalities as personalities_module
from .audit import AuditRecord, audit
from .errors import conflict
from .models import AuditSource
from .personalities import Personality, PersonalityCreate, PersonalityUpdate
from .storage import Storage


class PersonalityList(BaseModel):
    personalities: list[Personality]


def build_personalities_router(storage: Storage) -> APIRouter:
    router = APIRouter(prefix="/personalities", tags=["personalities"])

    @router.get("", response_model=PersonalityList)
    async def list_all() -> PersonalityList:
        return PersonalityList(personalities=personalities_module.list_personalities(storage.conn))

    @router.post("", response_model=Personality, status_code=201)
    async def create(payload: PersonalityCreate) -> Personality:
        with storage.transaction() as conn:
            personality = personalities_module.create_personality(conn, payload)
            audit(
                conn,
                AuditRecord(
                    entity_type="personality",
                    entity_id=personality.id,
                    action="create",
                    source=AuditSource.DESKTOP,
                    result="success",
                    details={"name": personality.name},
                ),
            )
        return personality

    @router.patch("/{personality_id}", response_model=Personality)
    async def update(personality_id: str, payload: PersonalityUpdate) -> Personality:
        with storage.transaction() as conn:
            personality = personalities_module.update_personality(conn, personality_id, payload)
            audit(
                conn,
                AuditRecord(
                    entity_type="personality",
                    entity_id=personality.id,
                    action="update",
                    source=AuditSource.DESKTOP,
                    result="success",
                ),
            )
        return personality

    @router.delete("/{personality_id}", status_code=204, response_model=None)
    async def delete(personality_id: str) -> None:
        with storage.transaction() as conn:
            existing = personalities_module.get_personality(conn, personality_id)
            if existing.builtin:
                raise conflict("personality", "Built-in personalities can't be deleted — edit it instead.")
            personalities_module.delete_personality(conn, personality_id)

    return router
