"""Provider-reported image usage and cost-alerts for the AI Usage & Costs screen.

Never infer image pricing from model names or zero-cost missing fields.
"""
from __future__ import annotations

import json
from pathlib import Path
from fastapi import APIRouter

from .storage import Storage
from . import activity
from .activity import NotificationLink


def _read_json_lines(path: Path, max_lines: int = 5000) -> list[dict]:
    if not path.is_file():
        return []
    result = []
    with path.open('r', encoding='utf-8-sig', errors='replace') as handle:
        for line in handle:
            try:
                record = json.loads(line)
                if isinstance(record, dict):
                    result.append(record)
            except ValueError:
                continue
    return result[-max_lines:]


def build_ai_usage_costs_router(storage: Storage) -> APIRouter:
    router = APIRouter(prefix='/ai', tags=['ai-usage'])

    @router.get('/usage-images', response_model=None)
    async def list_image_usage():
        entries = _read_json_lines(storage.data_dir / 'image-usage.jsonl')
        return {'items': [
            {'provider': str(e.get('provider') or 'unknown'),
             'model': str(e.get('model') or 'unknown'),
             'operation': str(e.get('operation') or 'generate'),
             'image_count': max(0, int(e.get('image_count') or 0)),
             'reported_cost_usd': e.get('reported_cost_usd'),
             'at': e.get('at') or e.get('created_at')}
            for e in entries if isinstance(e.get('image_count'), (int, float))
        ]}

    def _load_alerts() -> dict:
        paths = [
            storage.data_dir / 'ai-usage-cost-report.json',
            Path(__file__).resolve().parents[2] / 'benchmarks' / 'ai-provider-costs' / 'latest-report.json',
        ]
        for path in paths:
            if not path.is_file():
                continue
            try:
                report = json.loads(path.read_text(encoding='utf-8-sig'))
                if isinstance(report, dict):
                    return report
            except (OSError, ValueError):
                continue
        return {'alerts': [], 'generated_at': None}

    @router.get('/usage-alerts', response_model=None)
    async def list_usage_alerts():
        report = _load_alerts()
        return {'items': report.get('alerts') or [], 'generated_at': report.get('generated_at')}

    @router.post('/usage-alerts/sync', response_model=None)
    async def sync_usage_alerts():
        """Project new measured-price alerts into Synapse's normal notification bell.

        This is idempotent; callers can poll without spamming notifications.
        """
        report = _load_alerts()
        created = 0
        with storage.transaction() as conn:
            for alert in (report.get('alerts') or [])[:10]:
                if not isinstance(alert, dict):
                    continue
                name = str(alert.get('runtime') or alert.get('image_model') or 'Provider')[:90]
                metric = str(alert.get('metric') or 'reported cost')[:70]
                change = alert.get('change_pct')
                if not isinstance(change, (int, float)):
                    continue
                body = f'{name}: {metric} changed by {change:+.2f}% from the measured comparison baseline.'
                existing = conn.execute(
                    'SELECT 1 FROM activity_notifications WHERE kind = ? AND body_md = ? LIMIT 1',
                    ('ai_usage_cost_change', body),
                ).fetchone()
                if existing:
                    continue
                activity.create_notification(
                    conn, kind='ai_usage_cost_change', level='yellow',
                    title=f'AI cost change: {name}', body_md=body,
                    links=[NotificationLink(label='Usage & Costs', intent={'page':'usage-costs'})],
                )
                created += 1
        return {'created': created, 'checked': min(len(report.get('alerts') or []), 10)}

    return router
