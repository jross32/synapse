from pathlib import Path
from fastapi.testclient import TestClient
from synapse_daemon.app import build_app
from synapse_daemon.storage import Storage
from synapse_daemon.ws import EventBus


def test_renderer_put_preflight_is_allowed_but_untrusted_origin_is_not(tmp_path: Path):
    storage = Storage(tmp_path / 'data')
    storage.open()
    storage.migrate()
    try:
        with TestClient(build_app(storage, EventBus())) as client:
            headers = {'Origin': 'http://127.0.0.1:5173', 'Access-Control-Request-Method': 'PUT', 'Access-Control-Request-Headers': 'X-Synapse-Token,Content-Type'}
            allowed = client.options('/api/v1/profile', headers=headers)
            assert allowed.status_code == 200
            assert 'PUT' in allowed.headers['access-control-allow-methods']
            rejected = client.options('/api/v1/profile', headers={**headers, 'Origin': 'https://untrusted.example.test'})
            assert rejected.status_code == 400
            assert 'access-control-allow-origin' not in rejected.headers
    finally:
        storage.close()


def test_frozen_worker_entry_forwards_arguments_without_booting_daemon(monkeypatch):
    from synapse_daemon import __main__ as daemon_main, video_worker
    received = []
    def fake_main(argv):
        received.extend(argv)
        return 23
    monkeypatch.setattr(video_worker, 'main', fake_main)
    args = ['--data-dir', 'QA-data', '--project-id', 'qa-project', '--job-id', 'qa-job']
    assert daemon_main.main(['--video-worker', *args]) == 23
    assert received == args
