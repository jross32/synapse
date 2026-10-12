"""Browser report ingestion must never certify incomplete or failing audits."""
import json
from pathlib import Path

from synapse_daemon.storage import Storage
from synapse_daemon.visual_audit_ingest import VisualAuditImport, ingest_visual_report


def _report(root: Path, *, broken: bool = False) -> Path:
    pages = []
    for device in ("desktop", "mobile", "small-mobile"):
        (root / f"{device}.png").write_bytes(b"image")
        pages.append({
            "device": device, "status": 200, "errors": [], "consoleErrors": [],
            "overflow": [], "contrast": ([{"ratio": 1.5}] if broken and device == "mobile" else []),
            "horizontalOverflow": False, "screenshots": [f"{device}.png"],
        })
    report = root / "report.json"
    report.write_text(json.dumps({"url": "http://localhost:5215", "pages": pages, "failureCount": int(broken)}), encoding="utf-8")
    return report


def test_import_report_pass_and_failure(tmp_path):
    store = Storage(tmp_path / "db")
    store.open()
    store.migrate()
    report = _report(tmp_path)
    with store.transaction() as conn:
        evidence = ingest_visual_report(conn, VisualAuditImport(
            subject_type="agent_work_item", subject_id="test-1", report_path=str(report)))
        assert evidence.metadata["visual_qa_passed"] is True
        assert evidence.verdict.value == "pass"
    _report(tmp_path, broken=True)
    with store.transaction() as conn:
        evidence = ingest_visual_report(conn, VisualAuditImport(
            subject_type="agent_work_item", subject_id="test-1", report_path=str(report)))
        assert evidence.metadata["visual_qa_passed"] is False
        assert evidence.verdict.value == "fail"
    store.close()


def test_missing_screenshot_fails_closed(tmp_path):
    store = Storage(tmp_path / "db")
    store.open()
    store.migrate()
    report = _report(tmp_path)
    (tmp_path / "mobile.png").unlink()
    with store.transaction() as conn:
        evidence = ingest_visual_report(conn, VisualAuditImport(
            subject_type="agent_work_item", subject_id="test-2", report_path=str(report)))
        assert evidence.verdict.value == "fail"
    store.close()


def test_authenticated_import_endpoint(tmp_path):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from synapse_daemon.routes_quality_os import build_quality_os_router
    store = Storage(tmp_path / 'db')
    store.open()
    store.migrate()
    app = FastAPI()
    app.include_router(build_quality_os_router(store), prefix='/api/v1')
    report = _report(tmp_path)
    with TestClient(app) as client:
        response = client.post('/api/v1/visual-audits/import', json={
            'subject_type': 'agent_work_item', 'subject_id': 'route-1', 'report_path': str(report),
        })
        assert response.status_code == 201, response.text
        assert response.json()['verdict'] == 'pass'
    store.close()
