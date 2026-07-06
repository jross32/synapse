"""Per-work-item token accounting (Plan 3 Phase 2, ADR-0025).

PTY squad workers report zero tokens today, so "fewer tokens than a non-Synapse
agent" is unprovable. This records each worker's self-reported token usage and
rolls it up per squad, reusing the benchmark engine's token provenance/source
vocabulary so squad + benchmark efficiency speak one language.

CRUD is module-level functions taking a ``sqlite3.Connection`` (matching
:mod:`project_records` / :mod:`agent_squads`); routes call them inside
``storage.transaction()``.
"""

from __future__ import annotations

import json
import secrets
import sqlite3
from datetime import datetime

from pydantic import BaseModel, Field

from .errors import not_found
from .time_utils import from_iso, to_iso, utc_now

# Default provenance/source for a worker reporting its own CLI usage line --
# the honest, same-source class the token-efficiency benchmark compares within
# (mirrors benchmarks.BenchmarkTokenProvenance / BenchmarkTokenSource).
DEFAULT_PROVENANCE = "reported"
DEFAULT_SOURCE = "runtime_self_report"


class WorkItemTokenUsage(BaseModel):
    id: str
    work_item_id: str
    squad_id: str | None = None
    role_id: str | None = None
    runtime_id: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    token_provenance: str = DEFAULT_PROVENANCE
    token_source: str = DEFAULT_SOURCE
    captured_at: datetime
    metadata: dict = Field(default_factory=dict)


class WorkItemTokenUsageCreate(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0
    # If None, computed as input + output.
    total_tokens: int | None = None
    token_provenance: str = DEFAULT_PROVENANCE
    token_source: str = DEFAULT_SOURCE
    # If None, taken from the work item's preferred_runtime.
    runtime_id: str | None = None
    metadata: dict = Field(default_factory=dict)


class SquadTokenRollup(BaseModel):
    squad_id: str
    entries: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    by_role: dict[str, int] = Field(default_factory=dict)


def _new_id() -> str:
    return secrets.token_hex(6)


def _loads_dict(payload: str | None) -> dict:
    if not payload:
        return {}
    try:
        raw = json.loads(payload)
    except json.JSONDecodeError:
        return {}
    return raw if isinstance(raw, dict) else {}


def _row_to_usage(row: sqlite3.Row) -> WorkItemTokenUsage:
    return WorkItemTokenUsage(
        id=row["id"],
        work_item_id=row["work_item_id"],
        squad_id=row["squad_id"],
        role_id=row["role_id"],
        runtime_id=row["runtime_id"] or "",
        input_tokens=row["input_tokens"],
        output_tokens=row["output_tokens"],
        total_tokens=row["total_tokens"],
        token_provenance=row["token_provenance"],
        token_source=row["token_source"],
        captured_at=from_iso(row["captured_at"]),
        metadata=_loads_dict(row["metadata_json"]),
    )


def get_usage(conn: sqlite3.Connection, usage_id: str) -> WorkItemTokenUsage:
    row = conn.execute("SELECT * FROM work_item_token_usage WHERE id = ?", (usage_id,)).fetchone()
    if row is None:
        raise not_found("work_item_token_usage", usage_id)
    return _row_to_usage(row)


def record_tokens(
    conn: sqlite3.Connection, work_item_id: str, payload: WorkItemTokenUsageCreate
) -> WorkItemTokenUsage:
    wi = conn.execute(
        "SELECT squad_id, assigned_role_id, preferred_runtime FROM agent_work_items WHERE id = ?",
        (work_item_id,),
    ).fetchone()
    if wi is None:
        raise not_found("agent_work_item", work_item_id)
    total = (
        payload.total_tokens
        if payload.total_tokens is not None
        else payload.input_tokens + payload.output_tokens
    )
    runtime = payload.runtime_id if payload.runtime_id is not None else (wi["preferred_runtime"] or "")
    usage_id = _new_id()
    conn.execute(
        "INSERT INTO work_item_token_usage "
        "(id, work_item_id, squad_id, role_id, runtime_id, input_tokens, output_tokens, "
        " total_tokens, token_provenance, token_source, captured_at, metadata_json) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            usage_id,
            work_item_id,
            wi["squad_id"],
            wi["assigned_role_id"],
            runtime,
            payload.input_tokens,
            payload.output_tokens,
            total,
            payload.token_provenance,
            payload.token_source,
            to_iso(utc_now()),
            json.dumps(payload.metadata or {}),
        ),
    )
    return get_usage(conn, usage_id)


def list_for_work_item(conn: sqlite3.Connection, work_item_id: str) -> list[WorkItemTokenUsage]:
    rows = conn.execute(
        "SELECT * FROM work_item_token_usage WHERE work_item_id = ? ORDER BY captured_at",
        (work_item_id,),
    ).fetchall()
    return [_row_to_usage(row) for row in rows]


def sum_squad_tokens(conn: sqlite3.Connection, squad_id: str) -> SquadTokenRollup:
    rows = conn.execute(
        "SELECT role_id, input_tokens, output_tokens, total_tokens "
        "FROM work_item_token_usage WHERE squad_id = ?",
        (squad_id,),
    ).fetchall()
    rollup = SquadTokenRollup(squad_id=squad_id)
    for row in rows:
        rollup.entries += 1
        rollup.input_tokens += row["input_tokens"]
        rollup.output_tokens += row["output_tokens"]
        rollup.total_tokens += row["total_tokens"]
        role = row["role_id"] or "unassigned"
        rollup.by_role[role] = rollup.by_role.get(role, 0) + row["total_tokens"]
    return rollup
