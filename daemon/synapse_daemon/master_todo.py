"""Synapse shared Master To-Do List: standalone atomic JSON-backed planner.

This module is deliberately separate from the project Active Tasks AI dispatcher.
"""
from __future__ import annotations

import json
import os
import shutil
import threading
import uuid
from datetime import date, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

TZ = "America/Chicago"
_LOCK = threading.RLock()
_SEED = [
    {"id": "001", "title": "Create a permanent place for handkerchiefs", "category": "home organization", "budget_usd": 15, "minutes": 30, "energy": "low", "status": "pending", "recurrence": None},
    {"id": "002", "title": "Get spray paint from garage and paint wooden frame outdoors", "category": "home DIY", "budget_usd": 0, "minutes": 60, "energy": "low/moderate", "status": "pending", "recurrence": None},
    {"id": "daily-review", "title": "Review Master To-Do List and choose today's highest-impact actions", "category": "planning", "budget_usd": 0, "minutes": 5, "energy": "low", "status": "pending", "recurrence": "daily"},
]


def _now() -> str:
    return datetime.now(ZoneInfo(TZ)).isoformat()


def _write(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        with temp.open("w", encoding="utf-8") as file:
            json.dump(data, file, ensure_ascii=False, indent=2)
            file.flush()
            os.fsync(file.fileno())
        if path.exists():
            backup = path.with_suffix(path.suffix + ".bak")
            shutil.copy2(path, backup)
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def _load(path: Path) -> dict:
    if not path.exists():
        result = {"version": 1, "revision": 1, "timezone": TZ, "tasks": _SEED, "completions": {}, "events": [], "reminder_time": None}
        _write(path, result)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        backup = path.with_suffix(path.suffix + ".bak")
        if not backup.exists():
            raise
        restored = json.loads(backup.read_text(encoding="utf-8"))
        _write(path, restored)
        return restored


def snapshot(path: str | Path, day: str | None = None) -> dict[str, Any]:
    target = Path(path)
    day = day or datetime.now(ZoneInfo(TZ)).date().isoformat()
    date.fromisoformat(day)
    with _LOCK:
        data = _load(target)
        result = json.loads(json.dumps(data))
    for task in result["tasks"]:
        task["done_today"] = (day in result["completions"].get(task["id"], [])) if task.get("recurrence") == "daily" else task["status"] == "done"
    result["date"] = day
    return result


def change(path: str | Path, action: str, task_id: str | None = None, *, title: str | None = None, day: str | None = None, expected_revision: int | None = None, event_id: str | None = None) -> dict:
    target = Path(path)
    day = day or datetime.now(ZoneInfo(TZ)).date().isoformat()
    date.fromisoformat(day)
    with _LOCK:
        data = _load(target)
        events = data.setdefault("events", [])
        if event_id and any(e.get("event_id") == event_id for e in events):
            prior = next(e for e in events if e.get("event_id") == event_id)
            if prior["action"] != action or prior["task_id"] != task_id or prior["day"] != day:
                raise ValueError("event id reused for different operation")
            return snapshot(target, day)
        if expected_revision is not None and data["revision"] != expected_revision:
            raise ValueError("revision conflict")
        item = next((t for t in data["tasks"] if t["id"] == task_id), None)
        if action == "add":
            if not title or not title.strip():
                raise ValueError("title required")
            task_id = task_id or str(uuid.uuid4())
            if item:
                raise ValueError("duplicate task id")
            data["tasks"].append({"id": task_id, "title": title.strip(), "category": "general", "budget_usd": None, "minutes": None, "energy": None, "status": "pending", "recurrence": None})
        elif action in ("complete", "reopen"):
            if item is None:
                raise KeyError(task_id)
            if item.get("recurrence") == "daily":
                dates = data.setdefault("completions", {}).setdefault(item["id"], [])
                if action == "complete" and day not in dates:
                    dates.append(day)
                if action == "reopen" and day in dates:
                    dates.remove(day)
            else:
                item["status"] = "done" if action == "complete" else "pending"
        else:
            raise ValueError("unsupported action")
        data["revision"] += 1
        events.append({"event_id": event_id or str(uuid.uuid4()), "action": action, "task_id": task_id, "day": day, "at": _now()})
        _write(target, data)
        return snapshot(target, day)


def configure_reminder(path: str | Path, reminder_time: str | None, *, expected_revision: int | None = None) -> dict[str, Any]:
    """Persist a user-selected 24-hour local reminder time; delivery is a separate concern."""
    if reminder_time is not None:
        from datetime import time
        try:
            parsed = time.fromisoformat(reminder_time)
        except ValueError as exc:
            raise ValueError("reminder_time must be HH:MM") from exc
        if parsed.second or parsed.microsecond or len(reminder_time) != 5:
            raise ValueError("reminder_time must be HH:MM")
    target = Path(path)
    with _LOCK:
        data = _load(target)
        if expected_revision is not None and data["revision"] != expected_revision:
            raise ValueError("revision conflict")
        data["reminder_time"] = reminder_time
        data["revision"] += 1
        _write(target, data)
    return snapshot(target)
