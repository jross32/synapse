"""Serialized Client Hunter dry-run execution with atomic report writing."""
import json
import os
import threading
from pathlib import Path
from tempfile import NamedTemporaryFile
try:
    from .client_hunter_runner import REPORT, run_cycle
except ImportError:
    from client_hunter_runner import REPORT, run_cycle

_RUN_LOCK = threading.Lock()

def execute_once(report_path=REPORT, pipeline_path=None):
    if not _RUN_LOCK.acquire(blocking=False):
        return {'ok': False, 'busy': True, 'error': 'Client Hunter cycle already running'}
    try:
        result = run_cycle(pipeline_path) if pipeline_path is not None else run_cycle()
        path = Path(report_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = None
        try:
            with NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent,
                                    prefix='.client-hunter-', suffix='.tmp', delete=False) as fh:
                temp_path=Path(fh.name)
                json.dump(result, fh, indent=2)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(temp_path, path)
        finally:
            if temp_path and temp_path.exists():
                temp_path.unlink()
        return {'ok': True, 'mode': result['mode'], 'processed': len(result['actions']),
                'ready_for_outreach': result['summary']['ready_for_outreach'],
                'external_messages_sent': 0}
    finally:
        _RUN_LOCK.release()

