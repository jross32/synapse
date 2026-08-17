"""Canonical AI execution/accounting regression tests (ADR-0036)."""

from __future__ import annotations

from synapse_daemon import ai_executions
from synapse_daemon import runtime_ledger
from synapse_daemon.storage import Storage


def _storage(tmp_path):
    storage = Storage(tmp_path / 'data')
    storage.open()
    storage.migrate()
    return storage


def test_unknown_usage_is_null_not_zero(tmp_path):
    storage = _storage(tmp_path)
    try:
        with storage.transaction() as conn:
            execution = ai_executions.reserve_execution(
                conn, kind='agent_work_item', project_id=None, runtime_id='claude',
                source_type='agent_work_item', source_id='work-1', pty_session_id='pty-1',
            )
            result = ai_executions.finalize_pty_execution(
                conn, pty_session_id='pty-1', output=b'ordinary answer', exit_code=0,
                work_outcome='handoff',
            )
        assert execution.id == result.id
        assert result.accounting_state == 'unreported'
        assert result.usage == []
    finally:
        storage.close()


def test_copilot_monthly_quota_persists_and_is_not_usable(tmp_path):
    storage = _storage(tmp_path)
    try:
        with storage.transaction() as conn:
            ai_executions.reserve_execution(
                conn, kind='agent_work_item', project_id=None, runtime_id='copilot',
                source_type='agent_work_item', source_id='work-2', pty_session_id='pty-2',
            )
            result = ai_executions.finalize_pty_execution(
                conn, pty_session_id='pty-2',
                output=b'You have exceeded your monthly quota. Upgrade your plan.',
                exit_code=1, work_outcome='blocked',
            )
        assert result.process_outcome == 'quota_exhausted'
        before = {item.runtime_id: item for item in ai_executions.list_capacity(storage.conn)}
        assert before['copilot'].state == ai_executions.RuntimeCapacityState.QUOTA_EXHAUSTED
        assert not before['copilot'].usable_now
        storage.close()
        storage.open()
        after = {item.runtime_id: item for item in ai_executions.list_capacity(storage.conn)}
        assert after['copilot'].state == ai_executions.RuntimeCapacityState.QUOTA_EXHAUSTED
        assert not after['copilot'].usable_now
    finally:
        storage.close()


def test_codex_usage_is_measured_once_when_finalizer_repeats(tmp_path):
    storage = _storage(tmp_path)
    try:
        with storage.transaction() as conn:
            ai_executions.reserve_execution(
                conn, kind='agent_work_item', project_id=None, runtime_id='codex',
                source_type='agent_work_item', source_id='work-3', pty_session_id='pty-3',
            )
            first = ai_executions.finalize_pty_execution(
                conn, pty_session_id='pty-3', output=b'tokens used\n49,912', exit_code=0,
                work_outcome='handoff',
            )
            second = ai_executions.finalize_pty_execution(
                conn, pty_session_id='pty-3', output=b'tokens used\n49,912', exit_code=0,
                work_outcome='handoff',
            )
        assert first.id == second.id
        assert first.accounting_state == 'measured'
        assert len(second.usage) == 1
        assert second.usage[0].total_tokens == 49_912
        assert second.usage[0].provenance == 'runtime_reported'
    finally:
        storage.close()


def test_explicit_zero_is_measured_as_zero(tmp_path):
    storage = _storage(tmp_path)
    try:
        with storage.transaction() as conn:
            ai_executions.reserve_execution(
                conn, kind='agent_work_item', project_id=None, runtime_id='copilot',
                source_type='agent_work_item', source_id='zero', pty_session_id='pty-zero',
            )
            result = ai_executions.finalize_pty_execution(
                conn, pty_session_id='pty-zero', output=b'AI Credits 0 (7s)', exit_code=0,
                work_outcome='handoff',
            )
        assert result.accounting_state == 'measured'
        assert result.usage[0].credits == 0
    finally:
        storage.close()


def test_relaunch_creates_a_new_execution_attempt(tmp_path):
    storage = _storage(tmp_path)
    try:
        with storage.transaction() as conn:
            first = ai_executions.reserve_execution(
                conn, kind='agent_work_item', project_id=None, runtime_id='codex',
                source_type='agent_work_item', source_id='same-work', pty_session_id='pty-first',
            )
            ai_executions.finalize_pty_execution(
                conn, pty_session_id='pty-first', output=b'tokens used: 10', exit_code=0,
                work_outcome='handoff',
            )
            second = ai_executions.reserve_execution(
                conn, kind='agent_work_item', project_id=None, runtime_id='codex',
                source_type='agent_work_item', source_id='same-work', pty_session_id='pty-second',
            )
            ai_executions.finalize_pty_execution(
                conn, pty_session_id='pty-second', output=b'tokens used: 20', exit_code=0,
                work_outcome='handoff',
            )
        assert first.id != second.id
        rows = ai_executions.list_executions(storage.conn, runtime_id='codex')
        assert len(rows) == 2
        assert {row.usage[0].total_tokens for row in rows} == {10, 20}
    finally:
        storage.close()


def test_timeout_outcome_is_sticky_after_late_exit(tmp_path):
    storage = _storage(tmp_path)
    try:
        with storage.transaction() as conn:
            execution = ai_executions.reserve_execution(
                conn, kind='agent_work_item', project_id=None, runtime_id='claude',
                source_type='agent_work_item', source_id='timeout', pty_session_id='pty-timeout',
            )
            timed_out = ai_executions.finalize_pty_execution(
                conn, pty_session_id='pty-timeout', output=b'partial answer', exit_code=None,
                work_outcome='blocked', process_outcome_override='timed_out',
            )
            late = ai_executions.finalize_pty_execution(
                conn, pty_session_id='pty-timeout', output=b'late success', exit_code=0,
                work_outcome='completed',
            )
        assert timed_out.id == execution.id == late.id
        assert late.process_outcome == 'timed_out'
        assert late.work_outcome == 'blocked'
        capacity = {item.runtime_id: item for item in ai_executions.list_capacity(storage.conn)}
        assert capacity['claude'].state == ai_executions.RuntimeCapacityState.UNKNOWN
    finally:
        storage.close()


def test_reservation_is_idempotent_per_pty_attempt(tmp_path):
    storage = _storage(tmp_path)
    try:
        with storage.transaction() as conn:
            one = ai_executions.reserve_execution(
                conn, kind='agent_work_item', project_id=None, runtime_id='codex',
                source_type='agent_work_item', source_id='same', pty_session_id='pty-a',
            )
            two = ai_executions.reserve_execution(
                conn, kind='agent_work_item', project_id=None, runtime_id='codex',
                source_type='agent_work_item', source_id='same', pty_session_id='pty-a',
            )
        assert one.id == two.id
        count = storage.conn.execute('SELECT COUNT(*) AS n FROM ai_executions').fetchone()['n']
        assert count == 1
    finally:
        storage.close()


def test_legacy_latest_exhaustion_is_imported_once(tmp_path):
    storage = _storage(tmp_path)
    ledger = tmp_path / 'runtime-ledger.jsonl'
    try:
        runtime_ledger.record(runtime_ledger.Entry(
            at='2026-08-15T01:00:00Z', runtime='copilot', ok=False,
            exhausted='You have exceeded your monthly quota',
        ), path=ledger)
        with storage.transaction() as conn:
            ai_executions.import_legacy_exhaustion(conn, ledger)
            ai_executions.import_legacy_exhaustion(conn, ledger)
        states = {item.runtime_id: item for item in ai_executions.list_capacity(storage.conn)}
        assert states['copilot'].state == ai_executions.RuntimeCapacityState.QUOTA_EXHAUSTED
        count = storage.conn.execute(
            "SELECT COUNT(*) AS n FROM ai_runtime_capacity WHERE runtime_id = 'copilot'"
        ).fetchone()['n']
        assert count == 1
    finally:
        storage.close()
