"""AI Workforce contract smoke: backed by real seeded tables, never mock counts."""
from fastapi import FastAPI
from fastapi.testclient import TestClient
from synapse_daemon.agent_squads import seed_default_role_templates
from synapse_daemon.personalities import seed_default_personalities
from synapse_daemon.staff import seed_staff_foundation
from synapse_daemon.staff_hq_catalog import seed_creator_revenue_staff
from synapse_daemon.staff_operations import seed_staff_operations
from synapse_daemon.routes_staff import build_staff_router
from synapse_daemon.storage import Storage


def test_workforce_snapshot_and_route(tmp_path):
    storage = Storage(tmp_path / 'state')
    storage.open()
    storage.migrate()
    with storage.transaction() as conn:
        seed_default_role_templates(conn)
        seed_default_personalities(conn)
        seed_staff_foundation(conn)
        seed_staff_operations(conn)
        seed_creator_revenue_staff(conn)
    app = FastAPI()
    app.include_router(build_staff_router(storage), prefix='/api/v1')
    client = TestClient(app)
    response = client.get('/api/v1/staff/workforce')
    assert response.status_code == 200, response.text
    data = response.json()
    assert data['metrics']['agents_total'] == len(data['agents']) == 14
    assert data['metrics']['tasks_active'] == 0
    assert data['metrics']['tasks_completed_recorded'] == 0
    assert data['tasks'] == []
    assert data['live_device_presence'] is False
    assert data['data_scope'] == 'local_synapse_records'
    assert 'status_line' in data['agents'][0]
    storage.close()
