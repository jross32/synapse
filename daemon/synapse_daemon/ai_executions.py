"""Canonical AI execution, runtime readiness, and usage accounting.

SQLite is the source of truth. Runtime CLI output is an observation with explicit
provenance; a missing measurement remains ``None`` rather than becoming a fake zero.
"""

from __future__ import annotations

import hashlib
import json
import secrets
import sqlite3
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from . import coder_runtimes, runtime_ledger, runtime_usage
from .time_utils import from_iso, to_iso, utc_now


class RuntimeCapacityState(str, Enum):
    UNKNOWN = 'unknown'
    AVAILABLE = 'available'
    DEGRADED = 'degraded'
    COOLDOWN = 'cooldown'
    QUOTA_EXHAUSTED = 'quota_exhausted'
    AUTH_REQUIRED = 'auth_required'
    NOT_INSTALLED = 'not_installed'
    OFFLINE = 'offline'
    DISABLED = 'disabled'


class RuntimeCapacity(BaseModel):
    runtime_id: str
    state: RuntimeCapacityState = RuntimeCapacityState.UNKNOWN
    usable_now: bool = False
    eligible_for_attempt: bool = False
    reason_code: str | None = None
    detail: str | None = None
    evidence_source: str = 'none'
    evidence_at: datetime | None = None
    retry_after: datetime | None = None
    reset_at: datetime | None = None
    updated_at: datetime


class AIUsageObservation(BaseModel):
    id: str
    execution_id: str
    provenance: str
    source: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    cached_tokens: int | None = None
    total_tokens: int | None = None
    cost_usd: float | None = None
    credits: float | None = None
    requests: int | None = None
    parser_version: str | None = None
    evidence_hash: str | None = None
    captured_at: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)


class AIExecution(BaseModel):
    id: str
    kind: str
    project_id: str | None = None
    runtime_id: str
    model: str | None = None
    effort: str | None = None
    authority: str | None = None
    source_type: str
    source_id: str
    pty_session_id: str | None = None
    state: str
    process_outcome: str | None = None
    work_outcome: str | None = None
    accounting_state: str
    exit_code: int | None = None
    started_at: datetime | None = None
    ended_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime
    usage: list[AIUsageObservation] = Field(default_factory=list)


def _loads(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _usage_from_row(row: sqlite3.Row) -> AIUsageObservation:
    return AIUsageObservation(
        id=row['id'], execution_id=row['execution_id'], provenance=row['provenance'],
        source=row['source'], input_tokens=row['input_tokens'], output_tokens=row['output_tokens'],
        cached_tokens=row['cached_tokens'], total_tokens=row['total_tokens'], cost_usd=row['cost_usd'],
        credits=row['credits'], requests=row['requests'], parser_version=row['parser_version'],
        evidence_hash=row['evidence_hash'], captured_at=from_iso(row['captured_at']),
        metadata=_loads(row['metadata_json']),
    )


def get_execution(conn: sqlite3.Connection, execution_id: str) -> AIExecution | None:
    row = conn.execute('SELECT * FROM ai_executions WHERE id = ?', (execution_id,)).fetchone()
    if row is None:
        return None
    usage_rows = conn.execute(
        'SELECT * FROM ai_usage_observations WHERE execution_id = ? ORDER BY captured_at',
        (execution_id,),
    ).fetchall()
    return AIExecution(
        id=row['id'], kind=row['kind'], project_id=row['project_id'], runtime_id=row['runtime_id'],
        model=row['model'], effort=row['effort'], authority=row['authority'], source_type=row['source_type'],
        source_id=row['source_id'], pty_session_id=row['pty_session_id'], state=row['state'],
        process_outcome=row['process_outcome'], work_outcome=row['work_outcome'],
        accounting_state=row['accounting_state'], exit_code=row['exit_code'],
        started_at=from_iso(row['started_at']) if row['started_at'] else None,
        ended_at=from_iso(row['ended_at']) if row['ended_at'] else None,
        metadata=_loads(row['metadata_json']), created_at=from_iso(row['created_at']),
        updated_at=from_iso(row['updated_at']), usage=[_usage_from_row(item) for item in usage_rows],
    )


def get_execution_by_pty(conn: sqlite3.Connection, pty_session_id: str) -> AIExecution | None:
    row = conn.execute('SELECT id FROM ai_executions WHERE pty_session_id = ?', (pty_session_id,)).fetchone()
    return get_execution(conn, row['id']) if row else None


def reserve_execution(
    conn: sqlite3.Connection, *, kind: str, project_id: str | None, runtime_id: str,
    source_type: str, source_id: str, pty_session_id: str | None = None,
    model: str | None = None, effort: str | None = None, authority: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> AIExecution:
    existing = conn.execute(
        'SELECT id FROM ai_executions WHERE pty_session_id = ?', (pty_session_id,)
    ).fetchone() if pty_session_id else None
    if existing:
        return get_execution(conn, existing['id'])  # type: ignore[return-value]
    now = to_iso(utc_now())
    execution_id = secrets.token_hex(8)
    conn.execute(
        'INSERT INTO ai_executions '
        '(id, kind, project_id, runtime_id, model, effort, authority, source_type, source_id, '
        'pty_session_id, state, accounting_state, started_at, metadata_json, created_at, updated_at) '
        'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
        (execution_id, kind, project_id, runtime_id, model, effort, authority, source_type, source_id,
         pty_session_id, 'running', 'pending', now, json.dumps(metadata or {}), now, now),
    )
    return get_execution(conn, execution_id)  # type: ignore[return-value]


def finalize_spawn_failure(conn: sqlite3.Connection, execution_id: str, detail: str) -> AIExecution | None:
    execution = get_execution(conn, execution_id)
    if execution is None or execution.state == 'finalized':
        return execution
    now = to_iso(utc_now())
    metadata = {**execution.metadata, 'spawn_failure': detail[:500]}
    conn.execute(
        'UPDATE ai_executions SET state = ?, process_outcome = ?, work_outcome = ?, '
        'accounting_state = ?, ended_at = ?, updated_at = ?, metadata_json = ? WHERE id = ?',
        ('finalized', 'spawn_failed', 'blocked', 'unreported', now, now,
         json.dumps(metadata), execution_id),
    )
    return get_execution(conn, execution_id)


def finalize_pty_execution(
    conn: sqlite3.Connection, *, pty_session_id: str, output: bytes, exit_code: int | None,
    work_outcome: str | None, process_outcome_override: str | None = None,
) -> AIExecution | None:
    execution = get_execution_by_pty(conn, pty_session_id)
    if execution is None or execution.state == 'finalized':
        return execution
    text = output.decode('utf-8', errors='replace')
    parsed = runtime_usage.parse_usage(execution.runtime_id, text)
    values = parsed.model_dump() if hasattr(parsed, 'model_dump') else vars(parsed)
    reported_fields = set(values.get('reported_fields') or set())
    measured = bool(reported_fields)
    exhausted = coder_runtimes.looks_exhausted(text, exit_code if exit_code is not None else 1)
    now = to_iso(utc_now())
    if measured:
        conn.execute(
            'INSERT OR IGNORE INTO ai_usage_observations '
            '(id, execution_id, provenance, source, input_tokens, output_tokens, cached_tokens, '
            'total_tokens, cost_usd, credits, requests, parser_version, evidence_hash, captured_at, metadata_json) '
            'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
            (secrets.token_hex(8), execution.id, 'runtime_reported', 'pty_finalizer',
             values.get('input_tokens') if 'input_tokens' in reported_fields else None,
             values.get('output_tokens') if 'output_tokens' in reported_fields else None, None,
             values.get('total_tokens') if 'total_tokens' in reported_fields else None,
             values.get('cost_usd') if 'cost_usd' in reported_fields else None,
             values.get('credits') if 'credits' in reported_fields else None,
             values.get('requests') if 'requests' in reported_fields else None, 'runtime_usage/v1',
             hashlib.sha256(text.encode('utf-8')).hexdigest(), now, '{}'),
        )
    process_outcome = process_outcome_override or (
        'quota_exhausted' if exhausted else ('exited' if exit_code == 0 else 'failed')
    )
    accounting_state = 'measured' if measured else 'unreported'
    conn.execute(
        'UPDATE ai_executions SET state = ?, process_outcome = ?, work_outcome = ?, '
        'accounting_state = ?, exit_code = ?, ended_at = ?, updated_at = ? WHERE id = ?',
        ('finalized', process_outcome, work_outcome, accounting_state, exit_code, now, now, execution.id),
    )
    capacity_state = RuntimeCapacityState.QUOTA_EXHAUSTED.value if exhausted else (
        RuntimeCapacityState.AVAILABLE.value if exit_code == 0 else None)
    if capacity_state is not None:
        conn.execute(
        'INSERT INTO ai_runtime_capacity '
        '(runtime_id, state, reason_code, detail, evidence_source, evidence_at, updated_at) '
        'VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT(runtime_id) DO UPDATE SET '
        'state=excluded.state, reason_code=excluded.reason_code, detail=excluded.detail, '
        'evidence_source=excluded.evidence_source, evidence_at=excluded.evidence_at, updated_at=excluded.updated_at',
            (execution.runtime_id, capacity_state, 'provider.quota_exhausted' if exhausted else None,
             exhausted or None, 'pty_finalizer', now, now),
        )
    return get_execution(conn, execution.id)


def list_executions(
    conn: sqlite3.Connection, *, project_id: str | None = None, runtime_id: str | None = None,
    limit: int = 100,
) -> list[AIExecution]:
    clauses: list[str] = []
    args: list[Any] = []
    if project_id is not None:
        clauses.append('project_id = ?')
        args.append(project_id)
    if runtime_id is not None:
        clauses.append('runtime_id = ?')
        args.append(runtime_id)
    where = f" WHERE {' AND '.join(clauses)}" if clauses else ''
    args.append(max(1, min(limit, 500)))
    rows = conn.execute(f'SELECT id FROM ai_executions{where} ORDER BY created_at DESC LIMIT ?', args).fetchall()
    return [item for row in rows if (item := get_execution(conn, row['id'])) is not None]


def list_capacity(conn: sqlite3.Connection) -> list[RuntimeCapacity]:
    rows = {row['runtime_id']: row for row in conn.execute('SELECT * FROM ai_runtime_capacity').fetchall()}
    now = utc_now()
    result: list[RuntimeCapacity] = []
    for runtime in coder_runtimes.DEFAULT_LADDER:
        installed = coder_runtimes.available(runtime)
        row = rows.get(runtime.value)
        state = RuntimeCapacityState(row['state']) if row else (
            RuntimeCapacityState.UNKNOWN if installed else RuntimeCapacityState.NOT_INSTALLED)
        result.append(RuntimeCapacity(
            runtime_id=runtime.value, state=state,
            usable_now=installed and state in {
                RuntimeCapacityState.AVAILABLE, RuntimeCapacityState.DEGRADED,
            },
            eligible_for_attempt=installed and state in {
                RuntimeCapacityState.UNKNOWN, RuntimeCapacityState.AVAILABLE,
                RuntimeCapacityState.DEGRADED,
            },
            reason_code=row['reason_code'] if row else None, detail=row['detail'] if row else None,
            evidence_source=row['evidence_source'] if row else 'binary_probe',
            evidence_at=from_iso(row['evidence_at']) if row and row['evidence_at'] else None,
            retry_after=from_iso(row['retry_after']) if row and row['retry_after'] else None,
            reset_at=from_iso(row['reset_at']) if row and row['reset_at'] else None,
            updated_at=from_iso(row['updated_at']) if row else now,
        ))
    return result


def import_legacy_exhaustion(conn: sqlite3.Connection, path) -> None:  # noqa: ANN001
    """Import only durable exhaustion evidence from the old JSONL ledger.

    This is deliberately one-way compatibility. New executions use SQLite; the
    historical file remains an export and is never treated as the live source.
    A later successful legacy call clears an older failure for that runtime.
    """
    latest: dict[str, runtime_ledger.Entry] = {}
    for entry in runtime_ledger.read_entries(path):
        if not entry.at:
            continue
        current = latest.get(entry.runtime)
        if current is None or entry.at > current.at:
            latest[entry.runtime] = entry
    now = to_iso(utc_now())
    for runtime_id, entry in latest.items():
        if not entry.exhausted:
            continue
        exists = conn.execute(
            'SELECT 1 FROM ai_runtime_capacity WHERE runtime_id = ?', (runtime_id,)
        ).fetchone()
        if exists:
            continue
        conn.execute(
            'INSERT INTO ai_runtime_capacity '
            '(runtime_id, state, reason_code, detail, evidence_source, evidence_at, updated_at) '
            'VALUES (?, ?, ?, ?, ?, ?, ?)',
            (runtime_id, RuntimeCapacityState.QUOTA_EXHAUSTED.value,
             'provider.quota_exhausted', entry.exhausted, 'legacy_runtime_ledger', entry.at, now),
        )


def acknowledge_provider_reset(
    conn: sqlite3.Connection, runtime_id: str, *, note: str
) -> RuntimeCapacity:
    """Clear stale quota evidence to UNKNOWN after an explicit local-user action.

    This never claims the provider is available. It permits one new attempt whose
    observed result will establish fresh capacity evidence.
    """
    runtime = coder_runtimes.CoderRuntime(runtime_id)
    now = to_iso(utc_now())
    conn.execute(
        'INSERT INTO ai_runtime_capacity '
        '(runtime_id, state, reason_code, detail, evidence_source, evidence_at, updated_at) '
        'VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT(runtime_id) DO UPDATE SET '
        'state=excluded.state, reason_code=excluded.reason_code, detail=excluded.detail, '
        'evidence_source=excluded.evidence_source, evidence_at=excluded.evidence_at, '
        'retry_after=NULL, reset_at=NULL, updated_at=excluded.updated_at',
        (runtime.value, RuntimeCapacityState.UNKNOWN.value, 'operator.provider_reset_acknowledged',
         note, 'local_operator', now, now),
    )
    return next(item for item in list_capacity(conn) if item.runtime_id == runtime.value)


def set_operator_capacity(
    conn: sqlite3.Connection,
    runtime_id: str,
    *,
    state: RuntimeCapacityState,
    note: str,
) -> RuntimeCapacity:
    """Persist explicit local-operator knowledge without calling a provider."""
    runtime = coder_runtimes.CoderRuntime(runtime_id)
    allowed = {
        RuntimeCapacityState.UNKNOWN,
        RuntimeCapacityState.QUOTA_EXHAUSTED,
        RuntimeCapacityState.DISABLED,
    }
    if state not in allowed:
        raise ValueError(f"Operator capacity state must be one of: {', '.join(sorted(x.value for x in allowed))}")
    now = to_iso(utc_now())
    reason = {
        RuntimeCapacityState.UNKNOWN: 'operator.capacity_unknown',
        RuntimeCapacityState.QUOTA_EXHAUSTED: 'operator.quota_exhausted',
        RuntimeCapacityState.DISABLED: 'operator.disabled',
    }[state]
    conn.execute(
        'INSERT INTO ai_runtime_capacity '
        '(runtime_id, state, reason_code, detail, evidence_source, evidence_at, updated_at) '
        'VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT(runtime_id) DO UPDATE SET '
        'state=excluded.state, reason_code=excluded.reason_code, detail=excluded.detail, '
        'evidence_source=excluded.evidence_source, evidence_at=excluded.evidence_at, '
        'retry_after=NULL, reset_at=NULL, updated_at=excluded.updated_at',
        (runtime.value, state.value, reason, note, 'user_reported', now, now),
    )
    return next(item for item in list_capacity(conn) if item.runtime_id == runtime.value)
