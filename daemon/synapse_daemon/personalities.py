"""AI personalities (ADR-0018, MW3).

A **worker** = a role + a personality. Two workers can share a role (e.g. two
UI designers) but carry different personalities, so they bring different voices
to the same job and genuinely collaborate / debate instead of echoing each
other. A personality is a small prompt-preamble layer + display metadata.
"""

from __future__ import annotations

import json
import secrets
import sqlite3

from pydantic import BaseModel, Field

from .errors import conflict, not_found
from .time_utils import to_iso, utc_now


class Personality(BaseModel):
    id: str
    name: str
    blurb: str = ""
    traits: list[str] = Field(default_factory=list)
    prompt_preamble_md: str = ""
    voice: str | None = None
    builtin: bool = False
    sort_order: int = 0
    created_at: str
    updated_at: str


class PersonalityCreate(BaseModel):
    id: str | None = None
    name: str
    blurb: str = ""
    traits: list[str] = Field(default_factory=list)
    prompt_preamble_md: str = ""
    voice: str | None = None
    sort_order: int = 0


class PersonalityUpdate(BaseModel):
    name: str | None = None
    blurb: str | None = None
    traits: list[str] | None = None
    prompt_preamble_md: str | None = None
    voice: str | None = None
    sort_order: int | None = None


def _new_id() -> str:
    return secrets.token_hex(6)


def _row(r: sqlite3.Row) -> Personality:
    return Personality(
        id=r["id"],
        name=r["name"],
        blurb=r["blurb"] or "",
        traits=json.loads(r["traits_json"] or "[]"),
        prompt_preamble_md=r["prompt_preamble_md"] or "",
        voice=r["voice"],
        builtin=bool(r["builtin"]),
        sort_order=r["sort_order"],
        created_at=r["created_at"],
        updated_at=r["updated_at"],
    )


def list_personalities(conn: sqlite3.Connection) -> list[Personality]:
    rows = conn.execute("SELECT * FROM personalities ORDER BY sort_order, name").fetchall()
    return [_row(r) for r in rows]


def get_personality(conn: sqlite3.Connection, pid: str) -> Personality:
    r = conn.execute("SELECT * FROM personalities WHERE id = ?", (pid,)).fetchone()
    if r is None:
        raise not_found("personality", pid)
    return _row(r)


def create_personality(conn: sqlite3.Connection, payload: PersonalityCreate, *, builtin: bool = False) -> Personality:
    pid = (payload.id or _new_id()).strip()
    if conn.execute("SELECT id FROM personalities WHERE id = ?", (pid,)).fetchone():
        raise conflict("personality", f"Personality '{pid}' already exists.")
    now = to_iso(utc_now())
    conn.execute(
        "INSERT INTO personalities (id, name, blurb, traits_json, prompt_preamble_md, voice, builtin, sort_order, "
        "created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            pid,
            payload.name,
            payload.blurb,
            json.dumps(payload.traits or []),
            payload.prompt_preamble_md,
            payload.voice,
            1 if builtin else 0,
            payload.sort_order,
            now,
            now,
        ),
    )
    return get_personality(conn, pid)


def update_personality(conn: sqlite3.Connection, pid: str, patch: PersonalityUpdate) -> Personality:
    get_personality(conn, pid)
    fields = patch.model_dump(exclude_unset=True)
    sets: list[str] = []
    args: list[object] = []
    for key, value in fields.items():
        col = "traits_json" if key == "traits" else key
        if key == "traits":
            value = json.dumps(value)
        sets.append(f"{col} = ?")
        args.append(value)
    if sets:
        sets.append("updated_at = ?")
        args.append(to_iso(utc_now()))
        args.append(pid)
        conn.execute(f"UPDATE personalities SET {', '.join(sets)} WHERE id = ?", args)
    return get_personality(conn, pid)


def delete_personality(conn: sqlite3.Connection, pid: str) -> None:
    get_personality(conn, pid)
    conn.execute("DELETE FROM personalities WHERE id = ?", (pid,))


# Starter personalities -- a small, opinionated set that creates useful tension
# when mixed on a squad.
_DEFAULTS = [
    PersonalityCreate(
        id="pragmatist",
        name="The Pragmatist",
        blurb="Ships the simplest thing that works.",
        traits=["practical", "decisive", "lean"],
        prompt_preamble_md=(
            "Your personality is **pragmatic**: prefer the simplest solution that works, avoid "
            "over-engineering, and ship. Push back on gold-plating."
        ),
        sort_order=10,
    ),
    PersonalityCreate(
        id="perfectionist",
        name="The Perfectionist",
        blurb="Sweats the details + edge cases.",
        traits=["meticulous", "thorough", "quality"],
        prompt_preamble_md=(
            "Your personality is a **perfectionist**: care about correctness, edge cases, naming, and "
            "polish. Call out anything sloppy or half-done."
        ),
        sort_order=20,
    ),
    PersonalityCreate(
        id="skeptic",
        name="The Skeptic",
        blurb="Questions assumptions, hunts for flaws.",
        traits=["critical", "rigorous", "adversarial"],
        prompt_preamble_md=(
            "Your personality is a **skeptic**: question assumptions, look hard for what could go wrong, "
            "and demand evidence before agreeing."
        ),
        sort_order=30,
    ),
    PersonalityCreate(
        id="visionary",
        name="The Visionary",
        blurb="Thinks big, proposes bold ideas.",
        traits=["creative", "ambitious", "big-picture"],
        prompt_preamble_md=(
            "Your personality is a **visionary**: think big, propose ambitious ideas and better "
            "approaches, and connect the work to the larger goal."
        ),
        sort_order=40,
    ),
    PersonalityCreate(
        id="mediator",
        name="The Mediator",
        blurb="Synthesizes views, finds the balance.",
        traits=["balanced", "diplomatic", "synthesizing"],
        prompt_preamble_md=(
            "Your personality is a **mediator**: weigh the different views on the team, synthesize them, "
            "and steer toward the best balanced decision."
        ),
        sort_order=50,
    ),
]


def seed_default_personalities(conn: sqlite3.Connection) -> None:
    existing = {p.id for p in list_personalities(conn)}
    for default in _DEFAULTS:
        if default.id not in existing:
            create_personality(conn, default, builtin=True)
