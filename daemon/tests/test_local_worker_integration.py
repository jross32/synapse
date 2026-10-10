"""Regression tests for the local squad-worker launch and durable handoff."""
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from synapse_daemon.agent_squads import AgentExecutionAuthority, argv_for_runtime
from synapse_daemon.routes_agent_squads import _automatic_worker_argv
from synapse_daemon import local_worker


def test_local_runtime_launches_real_python_module(tmp_path):
    prompt = tmp_path / 'instructions.md'
    prompt.write_text('test task')
    argv = _automatic_worker_argv(argv_for_runtime('local'), runtime='local',
        authority=AgentExecutionAuthority.OBSERVE, prompt_file=prompt)
    assert argv[:3] == [sys.executable, '-m', 'synapse_daemon.local_worker']
    assert argv[argv.index('--prompt-file') + 1] == str(prompt)
    assert argv[argv.index('--authority') + 1] == 'observe'


def test_local_worker_success_handoff(tmp_path, monkeypatch):
    prompt = tmp_path / 'instructions.md'
    prompt.write_text('inspect only')
    workspace = tmp_path / 'real-project'
    workspace.mkdir()
    monkeypatch.setenv('SYNAPSE_PROJECT_WORKSPACE', str(workspace))
    monkeypatch.setattr(sys, 'argv', ['local_worker', '--prompt-file', str(prompt),
        '--workspace', str(tmp_path), '--authority', 'observe'])
    seen = {}
    async def fake_agent(**kwargs):
        seen['agent'] = kwargs
        return SimpleNamespace(answer='evidence captured', completed=True, stop_reason='answered', steps=[])
    monkeypatch.setattr(local_worker, 'run_agent', fake_agent)
    monkeypatch.setattr(local_worker, 'handoff', lambda payload: seen.update(handoff=payload))
    assert local_worker.main() == 0
    assert seen['agent']['workspace'] == workspace
    assert seen['agent']['mode'].value == 'plan'
    assert seen['handoff']['status'] == 'handoff'
    assert seen['handoff']['summary_md'] == 'evidence captured'


def test_local_worker_failure_blocks_and_records(tmp_path, monkeypatch):
    prompt = tmp_path / 'instructions.md'
    prompt.write_text('inspect only')
    monkeypatch.setattr(sys, 'argv', ['local_worker', '--prompt-file', str(prompt),
        '--workspace', str(tmp_path)])
    seen = {}
    async def fake_agent(**kwargs):
        raise RuntimeError('inference failed')
    monkeypatch.setattr(local_worker, 'run_agent', fake_agent)
    monkeypatch.setattr(local_worker, 'handoff', lambda payload: seen.update(payload))
    assert local_worker.main() == 1
    assert seen['status'] == 'blocked'
    assert 'inference failed' in seen['blockers_md']


def test_handoff_uses_worker_credential(monkeypatch):
    monkeypatch.setenv('SYNAPSE_API', 'http://127.0.0.1:7878/api/v1')
    monkeypatch.setenv('SYNAPSE_WORK_ITEM_ID', 'test-item')
    monkeypatch.setenv('SYNAPSE_TOKEN', 'secret-token')
    captured = {}
    class Response:
        status = 200
        def __enter__(self): return self
        def __exit__(self, *args): pass
    def fake_urlopen(request, timeout):
        captured['url'] = request.full_url
        captured['token'] = request.get_header('X-synapse-token')
        captured['payload'] = json.loads(request.data)
        return Response()
    monkeypatch.setattr(local_worker.urllib.request, 'urlopen', fake_urlopen)
    local_worker.handoff({'status':'handoff','summary_md':'done'})
    assert captured['url'].endswith('/agent-work-items/test-item/handoff')
    assert captured['token'] == 'secret-token'
    assert captured['payload']['summary_md'] == 'done'
