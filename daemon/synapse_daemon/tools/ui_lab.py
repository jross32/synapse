"""Durable UI Lab jobs: start quickly, record progress, keep browser work detached."""
from __future__ import annotations

import json
import os
import time
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from ..models import EntityStatus, ErrorRef, ToolState
from . import ToolHandler


class UiLabTool(ToolHandler):
    tool_id = "ui-lab"
    def __init__(self, bus, storage=None):
        self._bus = bus
        self._storage = storage
        self.root = Path(__file__).resolve().parents[3]
        self.jobs = self.root / 'data' / 'ui-lab' / 'jobs'

    def state(self):
        return ToolState(tool_id='ui-lab', status=EntityStatus.IDLE)

    async def run_action(self, action_id, fields, item_id=None):
        if action_id == 'status':
            return self._status(str(fields.get('job_id', '')))
        if action_id != 'verify':
            return self._error('ui_lab.action', 'Unknown UI Lab action')
        target = str(fields.get('target', '')).strip()
        parsed = urlparse(target)
        if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username or parsed.password:
            return self._error('ui_lab.target', 'An HTTP(S) target URL with a hostname is required')
        engine = str(fields.get('engine', 'chromium'))
        profile = str(fields.get('profile', 'iphone-compact'))
        if engine not in ('chromium', 'firefox', 'webkit') or profile not in ('iphone-compact', 'iphone-large', 'tablet-portrait', 'desktop'):
            return self._error('ui_lab.profile', 'Unknown engine or viewport profile')
        job_id = uuid.uuid4().hex[:16]
        job_dir = self.jobs / job_id
        job_dir.mkdir(parents=True, exist_ok=False)
        metadata = {'job_id': job_id, 'status': 'queued', 'target': target, 'engine': engine,
                    'profile': profile, 'started_utc': datetime.now(timezone.utc).isoformat(),
                    'native_safari_verified': False, 'expected_profiles': 1}
        (job_dir / 'job.json').write_text(json.dumps(metadata, indent=2), encoding='utf-8')
        python = self.root / '.venv' / 'Scripts' / 'python.exe'
        if not python.exists():
            python = Path(sys.executable)
        argv = [str(python), str(self.root / 'tools' / 'ui_lab_matrix.py'), target,
                '--engine', engine, '--profile', profile, '--timeout-ms', '8000',
                '--output', str(job_dir)]
        try:
            log = open(job_dir / 'worker.log', 'wb')
            try:
                flags = getattr(subprocess, 'CREATE_NEW_PROCESS_GROUP', 0) | getattr(subprocess, 'DETACHED_PROCESS', 0)
                proc = subprocess.Popen(argv, cwd=str(self.root), stdin=subprocess.DEVNULL,
                                        stdout=log, stderr=subprocess.STDOUT, creationflags=flags,
                                        close_fds=True)
            finally:
                log.close()
        except OSError as exc:
            metadata['status'] = 'error'
            metadata['error'] = str(exc)
            (job_dir / 'job.json').write_text(json.dumps(metadata), encoding='utf-8')
            return self._error('ui_lab.spawn', str(exc))
        metadata['status'] = 'running'
        metadata['pid'] = proc.pid
        (job_dir / 'job.json').write_text(json.dumps(metadata, indent=2), encoding='utf-8')
        return ToolState(tool_id='ui-lab', status=EntityStatus.LAUNCHED,
                         result={'job_id': job_id, 'status': 'running', 'report_path': str(job_dir / 'report.json'),
                                 'dashboard_path': str(job_dir / 'index.html'), 'native_safari_verified': False},
                         message=f'UI Lab job {job_id} launched; poll status with job_id')

    def _status(self, job_id):
        if len(job_id) != 16 or any(c not in '0123456789abcdef' for c in job_id):
            return self._error('ui_lab.job_id', 'Valid job_id required')
        folder = self.jobs / job_id
        if not (folder / 'job.json').exists():
            return self._error('ui_lab.not_found', 'UI Lab job not found')
        metadata = json.loads((folder / 'job.json').read_text(encoding='utf-8'))
        report_file = folder / 'report.json'
        report = None
        if report_file.exists():
            try:
                report = json.loads(report_file.read_text(encoding='utf-8'))
            except (json.JSONDecodeError, OSError):
                pass
        status = metadata.get('status', 'unknown')
        if report is not None and report.get('run_complete') is True and report.get('finished_utc'):
            expected = metadata.get('expected_profiles', 1)
            valid_count = len(report.get('results', [])) == expected
            if valid_count and report.get('failed', 0) == 0 and report.get('blocked', 0) == 0 and report.get('passed', 0) == expected:
                status = 'completed'
            else:
                status = 'failed'
        elif status == 'running':
            started = datetime.fromisoformat(metadata['started_utc'])
            elapsed = (datetime.now(timezone.utc) - started).total_seconds()
            if elapsed > 600:
                status = 'stalled'
        result = {'job_id': job_id, 'status': status, 'report': report,
                  'report_path': str(report_file), 'dashboard_path': str(folder / 'index.html'),
                  'native_safari_verified': False}
        return ToolState(tool_id='ui-lab', status=EntityStatus.LAUNCHED if status in ('running', 'completed') else EntityStatus.ERROR,
                         result=result, message=f'UI Lab job {job_id}: {status}')

    @staticmethod
    def _error(code, message):
        return ToolState(tool_id='ui-lab', status=EntityStatus.ERROR, last_error=ErrorRef(code=code, message=message))
