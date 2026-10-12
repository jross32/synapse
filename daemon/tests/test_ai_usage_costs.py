"""Focused tests for protected AI usage reporting and image receipts."""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from synapse_daemon.image_usage_costs import record_image_usage
from synapse_daemon.routes_ai_usage_costs import build_ai_usage_costs_router


def test_image_usage_receipts_preserve_unknown_cost_and_privacy(tmp_path: Path) -> None:
    record_image_usage(
        tmp_path, provider='openai', model='image-test', project_id='synapse-self',
        request_id='req-1', image_count=1, reported_cost_usd=None,
    )
    record_image_usage(
        tmp_path, provider='openai', model='image-test', project_id='synapse-self',
        request_id='req-2', image_count=2, reported_cost_usd=0.12, operation='edit',
    )
    lines = (tmp_path / 'image-usage.jsonl').read_text(encoding='utf-8').splitlines()
    assert len(lines) == 2
    assert all(line.startswith('{') and line.endswith('}') for line in lines)
    assert json.loads(lines[0])['reported_cost_usd'] is None
    assert json.loads(lines[1])['operation'] == 'edit'
    assert json.loads(lines[1])['reported_cost_usd'] == 0.12
    assert 'prompt' not in lines[0]


def test_image_cost_api_reads_real_receipts_and_handles_bad_lines(tmp_path: Path) -> None:
    record_image_usage(
        tmp_path, provider='openai', model='model-A', project_id='synapse-self',
        request_id='req-3', image_count=1, reported_cost_usd=None,
    )
    with (tmp_path / 'image-usage.jsonl').open('a', encoding='utf-8') as handle:
        handle.write('not valid json\n')
    app = FastAPI()
    app.include_router(build_ai_usage_costs_router(SimpleNamespace(data_dir=tmp_path)))
    response = TestClient(app).get('/ai/usage-images')
    assert response.status_code == 200
    items = response.json()['items']
    assert len(items) == 1
    assert items[0]['model'] == 'model-A'
    assert items[0]['reported_cost_usd'] is None


def test_alert_sync_is_idempotent_and_visible_in_notification_center(tmp_path: Path) -> None:
    from synapse_daemon.storage import Storage
    storage = Storage(tmp_path)
    storage.open()
    storage.migrate()
    (tmp_path / 'ai-usage-cost-report.json').write_text(json.dumps({
        'alerts': [{'runtime': 'claude', 'metric': 'cost_per_request', 'change_pct': 23.0}],
        'generated_at': '2026-10-12T00:00:00+00:00',
    }), encoding='utf-8')
    app = FastAPI()
    app.include_router(build_ai_usage_costs_router(storage))
    client = TestClient(app)
    assert client.post('/ai/usage-alerts/sync').json()['created'] == 1
    assert client.post('/ai/usage-alerts/sync').json()['created'] == 0
    notification = storage.conn.execute(
        "SELECT kind, title, body_md FROM activity_notifications WHERE kind='ai_usage_cost_change'"
    ).fetchall()
    assert len(notification) == 1
    assert '23.00%' in notification[0]['body_md']
    assert len(client.get('/ai/usage-alerts').json()['items']) == 1
    storage.close()
