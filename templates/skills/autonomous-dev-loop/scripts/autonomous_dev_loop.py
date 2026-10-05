#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

STATE_REL = Path('.synapse/autonomous-dev-loop.json')
HISTORY_REL = Path('.synapse/autonomous-dev-history.jsonl')
SCHEMA_VERSION = 2
DEFAULT_SOFT_MINUTES = 15
DEFAULT_SOFT_ACTIONS = 12
CHECKPOINT_FRACTION = 0.70


def now_dt() -> datetime:
    return datetime.now(timezone.utc)


def now_iso() -> str:
    return now_dt().isoformat().replace('+00:00', 'Z')


def parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def paths(root: str | Path) -> tuple[Path, Path]:
    base = Path(root).resolve()
    return base / STATE_REL, base / HISTORY_REL


def migrate_state(state: dict[str, Any]) -> dict[str, Any]:
    state['schema_version'] = SCHEMA_VERSION
    state.setdefault('checkpoint_seq', 0)
    state.setdefault('checkpoint', None)
    state.setdefault('chat_home', None)
    state.setdefault('archive_queue', [])
    state.setdefault('pause_reason', None)
    execution = state.setdefault('execution', {})
    execution.setdefault('turn_started_at', state.get('updated_at') or now_iso())
    execution.setdefault('soft_minutes', DEFAULT_SOFT_MINUTES)
    execution.setdefault('soft_actions', DEFAULT_SOFT_ACTIONS)
    execution.setdefault('actions_used', 0)
    execution.setdefault('last_checkpoint_at', None)
    return state


def read_state(root: str | Path) -> dict[str, Any]:
    state_path, _ = paths(root)
    if not state_path.exists():
        raise SystemExit(f'No loop state at {state_path}. Run init first.')
    raw = json.loads(state_path.read_text(encoding='utf-8-sig'))
    if not isinstance(raw, dict):
        raise SystemExit(f'Loop state at {state_path} must be a JSON object.')
    return migrate_state(raw)


def write_state(root: str | Path, state: dict[str, Any]) -> None:
    state_path, _ = paths(root)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state['schema_version'] = SCHEMA_VERSION
    state['updated_at'] = now_iso()
    tmp = state_path.with_suffix('.json.tmp')
    tmp.write_text(json.dumps(state, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    tmp.replace(state_path)


def emit(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, indent=2, ensure_ascii=False))


def budget_snapshot(state: dict[str, Any]) -> dict[str, Any]:
    execution = state.setdefault('execution', {})
    started = parse_iso(execution.get('turn_started_at'))
    elapsed_seconds = max(0.0, (now_dt() - started).total_seconds()) if started else 0.0
    soft_minutes = max(1, int(execution.get('soft_minutes', DEFAULT_SOFT_MINUTES)))
    soft_actions = max(1, int(execution.get('soft_actions', DEFAULT_SOFT_ACTIONS)))
    actions_used = max(0, int(execution.get('actions_used', 0)))
    time_fraction = elapsed_seconds / (soft_minutes * 60)
    action_fraction = actions_used / soft_actions
    pressure = max(time_fraction, action_fraction)
    return {
        'turn_started_at': execution.get('turn_started_at'),
        'elapsed_seconds': round(elapsed_seconds, 3),
        'soft_minutes': soft_minutes,
        'soft_actions': soft_actions,
        'actions_used': actions_used,
        'time_fraction': round(time_fraction, 4),
        'action_fraction': round(action_fraction, 4),
        'pressure_fraction': round(pressure, 4),
        'checkpoint_recommended': pressure >= CHECKPOINT_FRACTION,
        'soft_boundary_reached': pressure >= 1.0,
    }


def continue_decision(state: dict[str, Any]) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    if state.get('status') != 'active':
        reasons.append(f"status={state.get('status')}")
    if state.get('current_iteration'):
        reasons.append('iteration_in_progress')
    if int(state.get('consecutive_failures', 0)) >= int(state.get('failure_budget', 2)):
        reasons.append('failure_budget_exhausted')
    if int(state.get('batch_completed', 0)) >= int(state.get('max_batch_iterations', 6)):
        reasons.append('batch_limit_reached')
    if state.get('goal_satisfied'):
        reasons.append('goal_satisfied')
    if state.get('human_required'):
        reasons.append('human_required')
    return not reasons, reasons


def update_chat_home(
    state: dict[str, Any],
    *,
    worker_chat_id: str = '',
    work_item_id: str = '',
    conversation_url: str = '',
) -> None:
    if not any((worker_chat_id, work_item_id, conversation_url)):
        return
    current = dict(state.get('chat_home') or {})
    if worker_chat_id:
        current['worker_chat_id'] = worker_chat_id
    if work_item_id:
        current['work_item_id'] = work_item_id
    if conversation_url:
        current['conversation_url'] = conversation_url
    current['updated_at'] = now_iso()
    state['chat_home'] = current


def make_checkpoint(
    state: dict[str, Any],
    *,
    reason: str,
    phase: str,
    summary: str,
    next_step: str,
    pending: str = '',
    evidence: str = '',
    dirty_state: str = '',
    pause: bool = False,
) -> dict[str, Any]:
    seq = int(state.get('checkpoint_seq', 0)) + 1
    state['checkpoint_seq'] = seq
    checkpoint = {
        'resume_token': f"{state.get('run_id')}:{seq}",
        'sequence': seq,
        'created_at': now_iso(),
        'reason': reason,
        'phase': phase,
        'summary': summary,
        'next_step': next_step,
        'pending': pending or None,
        'evidence': evidence or None,
        'dirty_state': dirty_state or None,
        'iteration_number': state.get('iteration_number'),
        'current_iteration': state.get('current_iteration'),
        'budget_snapshot': budget_snapshot(state),
        'chat_home': state.get('chat_home'),
        'paused': bool(pause),
    }
    state['checkpoint'] = checkpoint
    state['next_step'] = next_step or state.get('next_step')
    execution = state.setdefault('execution', {})
    execution['last_checkpoint_at'] = checkpoint['created_at']
    execution['actions_used'] = 0
    execution['turn_started_at'] = now_iso()
    if pause:
        state['status'] = 'paused'
        state['pause_reason'] = f'execution_boundary:{reason}'
    return checkpoint


def cmd_init(args: argparse.Namespace) -> None:
    state_path, _ = paths(args.root)
    if state_path.exists() and not args.force:
        state = read_state(args.root)
        emit({'created': False, 'message': 'Existing loop state resumed.', 'state': state})
        return
    state = {
        'schema_version': SCHEMA_VERSION,
        'skill': 'autonomous-dev-loop',
        'run_id': uuid.uuid4().hex[:12],
        'project_id': args.project_id,
        'goal': args.goal,
        'status': 'active',
        'goal_satisfied': False,
        'human_required': False,
        'human_reason': None,
        'iteration_number': 0,
        'batch_completed': 0,
        'max_batch_iterations': args.max_iterations,
        'failure_budget': args.failure_budget,
        'consecutive_failures': 0,
        'current_iteration': None,
        'last_outcome': None,
        'last_evidence': None,
        'next_step': args.next_step or None,
        'checkpoint_seq': 0,
        'checkpoint': None,
        'chat_home': None,
        'archive_queue': [],
        'pause_reason': None,
        'execution': {
            'turn_started_at': now_iso(),
            'soft_minutes': args.soft_minutes,
            'soft_actions': args.soft_actions,
            'actions_used': 0,
            'last_checkpoint_at': None,
        },
        'created_at': now_iso(),
        'updated_at': now_iso(),
    }
    write_state(args.root, state)
    emit({'created': True, 'state': state})


def cmd_status(args: argparse.Namespace) -> None:
    state = read_state(args.root)
    allowed, reasons = continue_decision(state)
    emit({
        'state': state,
        'budget': budget_snapshot(state),
        'can_begin_new_iteration': allowed,
        'resume_current_iteration': bool(state.get('current_iteration')),
        'stop_reasons': reasons,
    })


def cmd_turn_start(args: argparse.Namespace) -> None:
    state = read_state(args.root)
    execution = state.setdefault('execution', {})
    execution['turn_started_at'] = now_iso()
    execution['actions_used'] = 0
    if args.soft_minutes is not None:
        execution['soft_minutes'] = max(1, args.soft_minutes)
    if args.soft_actions is not None:
        execution['soft_actions'] = max(1, args.soft_actions)
    write_state(args.root, state)
    emit({'turn_started': True, 'budget': budget_snapshot(state), 'checkpoint': state.get('checkpoint')})


def cmd_progress(args: argparse.Namespace) -> None:
    state = read_state(args.root)
    execution = state.setdefault('execution', {})
    execution['actions_used'] = max(0, int(execution.get('actions_used', 0))) + max(0, args.actions)
    write_state(args.root, state)
    snapshot = budget_snapshot(state)
    emit({
        'progress_recorded': True,
        'budget': snapshot,
        'recommendation': 'checkpoint_now' if snapshot['checkpoint_recommended'] else 'continue',
    })


def cmd_budget_status(args: argparse.Namespace) -> None:
    state = read_state(args.root)
    snapshot = budget_snapshot(state)
    emit({
        'budget': snapshot,
        'recommendation': 'checkpoint_now' if snapshot['checkpoint_recommended'] else 'continue',
        'checkpoint': state.get('checkpoint'),
    })
    raise SystemExit(2 if snapshot['soft_boundary_reached'] else 0)


def cmd_begin(args: argparse.Namespace) -> None:
    state = read_state(args.root)
    allowed, reasons = continue_decision(state)
    if not allowed:
        raise SystemExit('Cannot begin iteration: ' + ', '.join(reasons))
    number = int(state.get('iteration_number', 0)) + 1
    state['iteration_number'] = number
    state['current_iteration'] = {
        'number': number,
        'started_at': now_iso(),
        'hypothesis': args.hypothesis,
        'scope': args.scope,
        'acceptance_criteria': args.acceptance,
        'proof_plan': args.proof,
        'files_or_surfaces': args.surfaces,
        'risk': args.risk,
    }
    write_state(args.root, state)
    emit({'began': True, 'iteration': state['current_iteration'], 'run_id': state['run_id']})


def cmd_checkpoint(args: argparse.Namespace) -> None:
    state = read_state(args.root)
    update_chat_home(
        state,
        worker_chat_id=args.worker_chat_id,
        work_item_id=args.work_item_id,
        conversation_url=args.conversation_url,
    )
    checkpoint = make_checkpoint(
        state,
        reason=args.reason,
        phase=args.phase,
        summary=args.summary,
        next_step=args.next_step,
        pending=args.pending,
        evidence=args.evidence,
        dirty_state=args.dirty_state,
        pause=args.pause,
    )
    write_state(args.root, state)
    emit({'checkpointed': True, 'checkpoint': checkpoint, 'state_status': state.get('status')})


def cmd_finish(args: argparse.Namespace) -> None:
    state = read_state(args.root)
    current = state.get('current_iteration')
    if not current:
        raise SystemExit('No iteration is currently in progress.')
    record = {
        'run_id': state['run_id'],
        'project_id': state['project_id'],
        **current,
        'finished_at': now_iso(),
        'outcome': args.outcome,
        'implementation_summary': args.summary,
        'evidence': args.evidence,
        'files_or_surfaces_touched': args.touched or current.get('files_or_surfaces'),
        'residual_risk': args.residual_risk or None,
        'next_step': args.next_step or None,
    }
    _, history_path = paths(args.root)
    history_path.parent.mkdir(parents=True, exist_ok=True)
    with history_path.open('a', encoding='utf-8') as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + '\n')

    state['batch_completed'] = int(state.get('batch_completed', 0)) + 1
    state['current_iteration'] = None
    state['last_outcome'] = args.outcome
    state['last_evidence'] = args.evidence
    state['next_step'] = args.next_step or None
    if args.outcome == 'improved':
        state['consecutive_failures'] = 0
    elif args.outcome in {'neutral', 'failed'}:
        state['consecutive_failures'] = int(state.get('consecutive_failures', 0)) + 1
    elif args.outcome == 'blocked':
        state['status'] = 'blocked'

    checkpoint = make_checkpoint(
        state,
        reason='iteration_complete',
        phase='record',
        summary=args.summary,
        next_step=args.next_step,
        pending=args.residual_risk,
        evidence=args.evidence,
        dirty_state=args.touched,
        pause=False,
    )
    write_state(args.root, state)
    allowed, reasons = continue_decision(state)
    emit({
        'recorded': True,
        'iteration': record,
        'checkpoint': checkpoint,
        'can_continue': allowed,
        'stop_reasons': reasons,
    })


def cmd_pause(args: argparse.Namespace) -> None:
    state = read_state(args.root)
    state['status'] = 'paused'
    state['pause_reason'] = args.reason
    if args.summary or args.next_step:
        checkpoint = make_checkpoint(
            state,
            reason='manual_pause',
            phase=args.phase,
            summary=args.summary or args.reason,
            next_step=args.next_step or state.get('next_step') or '',
            pending=args.pending,
            evidence=args.evidence,
            dirty_state=args.dirty_state,
            pause=True,
        )
    else:
        checkpoint = state.get('checkpoint')
    write_state(args.root, state)
    emit({'paused': True, 'reason': args.reason, 'checkpoint': checkpoint})


def cmd_resume(args: argparse.Namespace) -> None:
    state = read_state(args.root)
    if state.get('status') == 'complete':
        raise SystemExit('Cannot resume a completed loop without reinitializing it.')
    state['status'] = 'active'
    state['pause_reason'] = None
    if args.new_batch:
        state['batch_completed'] = 0
    if args.clear_human:
        state['human_required'] = False
        state['human_reason'] = None
    execution = state.setdefault('execution', {})
    execution['turn_started_at'] = now_iso()
    execution['actions_used'] = 0
    write_state(args.root, state)
    allowed, reasons = continue_decision(state)
    emit({
        'resumed': True,
        'resume_current_iteration': bool(state.get('current_iteration')),
        'checkpoint': state.get('checkpoint'),
        'next_step': state.get('next_step'),
        'can_begin_new_iteration': allowed,
        'stop_reasons': reasons,
        'state': state,
    })


def cmd_set_chat_home(args: argparse.Namespace) -> None:
    if not any((args.worker_chat_id, args.work_item_id, args.conversation_url)):
        raise SystemExit('At least one chat-home identifier is required.')
    state = read_state(args.root)
    update_chat_home(
        state,
        worker_chat_id=args.worker_chat_id,
        work_item_id=args.work_item_id,
        conversation_url=args.conversation_url,
    )
    write_state(args.root, state)
    emit({'chat_home_updated': True, 'chat_home': state.get('chat_home')})


def cmd_retire_chat(args: argparse.Namespace) -> None:
    if not any((args.worker_chat_id, args.work_item_id, args.conversation_url)):
        raise SystemExit('At least one retired-chat identifier is required.')
    state = read_state(args.root)
    home = state.get('chat_home') or {}
    candidates = {
        'worker_chat_id': args.worker_chat_id or None,
        'work_item_id': args.work_item_id or None,
        'conversation_url': args.conversation_url or None,
    }
    for key, value in candidates.items():
        if value and str(home.get(key) or '') == str(value):
            raise SystemExit(f'Refusing to retire current project home chat ({key}={value}).')
    request = {
        **candidates,
        'reason': args.reason,
        'queued_at': now_iso(),
        'status': 'pending_archive',
    }
    queue = list(state.get('archive_queue') or [])
    if request not in queue:
        queue.append(request)
    state['archive_queue'] = queue
    write_state(args.root, state)
    emit({'retirement_queued': True, 'request': request, 'archive_queue_size': len(queue)})


def cmd_chat_status(args: argparse.Namespace) -> None:
    state = read_state(args.root)
    emit({
        'chat_home': state.get('chat_home'),
        'archive_queue': state.get('archive_queue') or [],
        'policy': 'one durable home conversation per canonical project checkout',
    })


def cmd_resume_plan(args: argparse.Namespace) -> None:
    state = read_state(args.root)
    checkpoint = state.get('checkpoint') or {}
    current = state.get('current_iteration')
    plan = {
        'run_id': state.get('run_id'),
        'project_id': state.get('project_id'),
        'status': state.get('status'),
        'resume_token': checkpoint.get('resume_token'),
        'resume_current_iteration': bool(current),
        'current_iteration': current,
        'checkpoint_phase': checkpoint.get('phase'),
        'checkpoint_summary': checkpoint.get('summary'),
        'next_step': checkpoint.get('next_step') or state.get('next_step'),
        'pending': checkpoint.get('pending'),
        'evidence': checkpoint.get('evidence'),
        'dirty_state': checkpoint.get('dirty_state'),
        'chat_home': state.get('chat_home'),
        'budget': budget_snapshot(state),
        'archive_queue_size': len(state.get('archive_queue') or []),
    }
    emit({'resume_plan': plan})


def cmd_human(args: argparse.Namespace) -> None:
    state = read_state(args.root)
    state['human_required'] = True
    state['human_reason'] = args.reason
    write_state(args.root, state)
    emit({'human_required': True, 'reason': args.reason})


def cmd_complete(args: argparse.Namespace) -> None:
    state = read_state(args.root)
    if state.get('current_iteration'):
        raise SystemExit('Finish the current iteration before marking the goal complete.')
    state['goal_satisfied'] = True
    state['status'] = 'complete'
    state['completion_reason'] = args.reason
    checkpoint = make_checkpoint(
        state,
        reason='goal_complete',
        phase='record',
        summary=args.reason,
        next_step='',
        evidence=state.get('last_evidence') or '',
        pause=False,
    )
    write_state(args.root, state)
    emit({'complete': True, 'reason': args.reason, 'checkpoint': checkpoint})


def cmd_can_continue(args: argparse.Namespace) -> None:
    state = read_state(args.root)
    allowed, reasons = continue_decision(state)
    emit({
        'can_continue': allowed,
        'stop_reasons': reasons,
        'next_step': state.get('next_step'),
        'run_id': state.get('run_id'),
        'checkpoint': state.get('checkpoint'),
    })
    raise SystemExit(0 if allowed else 2)


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description='Durable state controller for Synapse Autonomous Dev Loop.')
    p.add_argument('--root', default='.', help='Target project root (default: current directory).')
    sub = p.add_subparsers(dest='command', required=True)

    init = sub.add_parser('init')
    init.add_argument('--project-id', required=True)
    init.add_argument('--goal', required=True)
    init.add_argument('--max-iterations', type=int, default=6)
    init.add_argument('--failure-budget', type=int, default=2)
    init.add_argument('--soft-minutes', type=int, default=DEFAULT_SOFT_MINUTES)
    init.add_argument('--soft-actions', type=int, default=DEFAULT_SOFT_ACTIONS)
    init.add_argument('--next-step', default='')
    init.add_argument('--force', action='store_true')
    init.set_defaults(func=cmd_init)

    status = sub.add_parser('status')
    status.set_defaults(func=cmd_status)

    turn = sub.add_parser('turn-start')
    turn.add_argument('--soft-minutes', type=int)
    turn.add_argument('--soft-actions', type=int)
    turn.set_defaults(func=cmd_turn_start)

    progress = sub.add_parser('progress')
    progress.add_argument('--actions', type=int, default=1)
    progress.set_defaults(func=cmd_progress)

    budget = sub.add_parser('budget-status')
    budget.set_defaults(func=cmd_budget_status)

    begin = sub.add_parser('begin')
    begin.add_argument('--hypothesis', required=True)
    begin.add_argument('--scope', required=True)
    begin.add_argument('--acceptance', required=True)
    begin.add_argument('--proof', required=True)
    begin.add_argument('--surfaces', default='')
    begin.add_argument('--risk', choices=['low', 'medium', 'high', 'critical'], default='medium')
    begin.set_defaults(func=cmd_begin)

    checkpoint = sub.add_parser('checkpoint')
    checkpoint.add_argument('--reason', required=True)
    checkpoint.add_argument('--phase', default='implement')
    checkpoint.add_argument('--summary', required=True)
    checkpoint.add_argument('--next-step', required=True)
    checkpoint.add_argument('--pending', default='')
    checkpoint.add_argument('--evidence', default='')
    checkpoint.add_argument('--dirty-state', default='')
    checkpoint.add_argument('--worker-chat-id', default='')
    checkpoint.add_argument('--work-item-id', default='')
    checkpoint.add_argument('--conversation-url', default='')
    checkpoint.add_argument('--pause', action='store_true')
    checkpoint.set_defaults(func=cmd_checkpoint)

    finish = sub.add_parser('finish')
    finish.add_argument('--outcome', choices=['improved', 'neutral', 'failed', 'blocked'], required=True)
    finish.add_argument('--summary', required=True)
    finish.add_argument('--evidence', required=True)
    finish.add_argument('--touched', default='')
    finish.add_argument('--residual-risk', default='')
    finish.add_argument('--next-step', default='')
    finish.set_defaults(func=cmd_finish)

    pause = sub.add_parser('pause')
    pause.add_argument('--reason', required=True)
    pause.add_argument('--phase', default='record')
    pause.add_argument('--summary', default='')
    pause.add_argument('--next-step', default='')
    pause.add_argument('--pending', default='')
    pause.add_argument('--evidence', default='')
    pause.add_argument('--dirty-state', default='')
    pause.set_defaults(func=cmd_pause)

    resume = sub.add_parser('resume')
    resume.add_argument('--new-batch', action='store_true')
    resume.add_argument('--clear-human', action='store_true')
    resume.set_defaults(func=cmd_resume)

    set_home = sub.add_parser('set-chat-home')
    set_home.add_argument('--worker-chat-id', default='')
    set_home.add_argument('--work-item-id', default='')
    set_home.add_argument('--conversation-url', default='')
    set_home.set_defaults(func=cmd_set_chat_home)

    retire = sub.add_parser('retire-chat')
    retire.add_argument('--worker-chat-id', default='')
    retire.add_argument('--work-item-id', default='')
    retire.add_argument('--conversation-url', default='')
    retire.add_argument('--reason', required=True)
    retire.set_defaults(func=cmd_retire_chat)

    chat_status = sub.add_parser('chat-status')
    chat_status.set_defaults(func=cmd_chat_status)

    resume_plan = sub.add_parser('resume-plan')
    resume_plan.set_defaults(func=cmd_resume_plan)

    human = sub.add_parser('require-human')
    human.add_argument('--reason', required=True)
    human.set_defaults(func=cmd_human)

    complete = sub.add_parser('complete')
    complete.add_argument('--reason', required=True)
    complete.set_defaults(func=cmd_complete)

    can = sub.add_parser('can-continue')
    can.set_defaults(func=cmd_can_continue)
    return p


if __name__ == '__main__':
    args = parser().parse_args()
    args.func(args)
