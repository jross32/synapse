"""Authenticated personal Master To-Do List REST routes."""
from pathlib import Path
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from .master_todo import snapshot, change, configure_reminder


class Mutation(BaseModel):
    action: str
    task_id: str | None = None
    title: str | None = None
    day: str | None = None
    expected_revision: int | None = None
    event_id: str = Field(min_length=1)


def build_master_todo_router(data_dir: Path) -> APIRouter:
    router = APIRouter(tags=["master-todo"])
    path = Path(data_dir) / "master-todo" / "tasks.json"

    @router.get("/master-todo")
    def get_master_todo(day: str | None = None):
        try:
            return snapshot(path, day)
        except ValueError as error:
            raise HTTPException(422, str(error))

    @router.post("/master-todo")
    def mutate_master_todo(payload: Mutation):
        try:
            return change(path, payload.action, payload.task_id, title=payload.title, day=payload.day, expected_revision=payload.expected_revision, event_id=payload.event_id)
        except KeyError:
            raise HTTPException(404, "Task not found")
        except ValueError as error:
            if "revision conflict" in str(error):
                raise HTTPException(409, str(error))
            raise HTTPException(422, str(error))
    class ReminderConfig(BaseModel):
        reminder_time: str | None = None
        expected_revision: int | None = None

    @router.put("/master-todo/reminder")
    def put_reminder(payload: ReminderConfig):
        try:
            return configure_reminder(path, payload.reminder_time, expected_revision=payload.expected_revision)
        except ValueError as error:
            if "revision conflict" in str(error):
                raise HTTPException(409, str(error))
            raise HTTPException(422, str(error))

    return router
