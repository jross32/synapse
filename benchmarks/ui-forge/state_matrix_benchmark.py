#!/usr/bin/env python3
from __future__ import annotations

import http.server
import json
import socket
import subprocess
import tempfile
import threading
from datetime import UTC, datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
RUNNER = REPO / 'templates' / 'skills' / 'ui-forge' / 'scripts' / 'state_matrix_runner.mjs'

APP = r'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<link rel="icon" href="data:,"><title>State Matrix Fixture</title>
<style>
:root{font-family:Inter,system-ui,sans-serif;background:#101418;color:#f6f8fa}*{box-sizing:border-box}body{margin:0;min-width:320px}.shell{width:min(680px,calc(100% - 32px));margin:0 auto;min-height:100vh;display:grid;align-content:center;gap:18px}.panel{border:1px solid #38424b;border-radius:16px;padding:20px;background:#161c22}button{min-height:48px;padding:0 18px;border:0;border-radius:10px;font:inherit;font-weight:700}ul{padding-left:24px}.muted{color:#aeb8c2}
</style>
</head>
<body><main class="shell"><h1>Inventory states</h1><section id="state" class="panel" aria-live="polite"></section></main>
<script>
const root=document.getElementById('state');
function renderLoading(){root.innerHTML='<p id="loading">Loading inventory…</p><button id="refresh" disabled>Refresh</button>'}
function renderError(){root.innerHTML='<div id="error" role="alert"><strong>Could not load inventory.</strong><p class="muted">Try again.</p></div><button id="retry">Try again</button>';document.getElementById('retry').addEventListener('click',load)}
function renderEmpty(){root.innerHTML='<p id="empty">No items yet.</p><button id="add">Add first item</button>'}
function renderSuccess(items){root.innerHTML='<ul id="items">'+items.map((item)=>'<li class="item">'+item.name+'</li>').join('')+'</ul><button id="refresh">Refresh</button>';document.getElementById('refresh').addEventListener('click',load)}
async function load(){renderLoading();try{const response=await fetch('/api/items');if(!response.ok)throw new Error('request failed');const items=await response.json();if(!Array.isArray(items)||items.length===0)renderEmpty();else renderSuccess(items)}catch{renderError()}}
load();
</script></body></html>'''


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args) -> None:  # noqa: A002
        pass


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return int(sock.getsockname()[1])


def run_runner(spec: Path, base_url: str):
    cp = subprocess.run(
        ['node', str(RUNNER), str(spec), '--base-url', base_url],
        cwd=REPO,
        text=True,
        capture_output=True,
        timeout=90,
    )
    try:
        payload = json.loads(cp.stdout)
    except json.JSONDecodeError:
        payload = {'ok': False, 'stdout': cp.stdout, 'stderr': cp.stderr}
    return cp.returncode, payload


def main() -> int:
    with tempfile.TemporaryDirectory(prefix='ui-forge-state-matrix-') as tmp:
        root = Path(tmp)
        (root / 'index.html').write_text(APP, encoding='utf-8')
        port = free_port()
        handler = lambda *args, **kwargs: QuietHandler(*args, directory=str(root), **kwargs)  # noqa: E731
        server = http.server.ThreadingHTTPServer(('127.0.0.1', port), handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base_url = f'http://127.0.0.1:{port}/'

        matrix = {
            'schema': 'ui-forge-state-matrix-v1',
            'required_states': ['loading', 'empty', 'error', 'success', 'recovery'],
            'viewports': [
                {'name': 'desktop', 'width': 1100, 'height': 760},
                {'name': 'mobile', 'width': 390, 'height': 844},
            ],
            'states': [
                {
                    'id': 'loading',
                    'routes': [{'url_pattern': '**/api/items', 'delay_ms': 900, 'body': [{'name': 'Later'}]}],
                    'assertions': [
                        {'type': 'visible', 'selector': '#loading'},
                        {'type': 'disabled', 'selector': '#refresh'},
                        {'type': 'hidden', 'selector': '#error'},
                    ],
                },
                {
                    'id': 'empty',
                    'routes': [{'url_pattern': '**/api/items', 'body': []}],
                    'actions': [{'type': 'wait', 'selector': '#empty'}],
                    'assertions': [
                        {'type': 'visible', 'selector': '#empty'},
                        {'type': 'text_equals', 'selector': '#empty', 'value': 'No items yet.'},
                        {'type': 'visible', 'selector': '#add'},
                    ],
                },
                {
                    'id': 'error',
                    'routes': [{'url_pattern': '**/api/items', 'status': 500, 'body': {'error': 'boom'}}],
                    'actions': [{'type': 'wait', 'selector': '#error'}],
                    'assertions': [
                        {'type': 'visible', 'selector': '#error'},
                        {'type': 'text_contains', 'selector': '#error', 'value': 'Could not load inventory.'},
                        {'type': 'visible', 'selector': '#retry'},
                    ],
                },
                {
                    'id': 'success',
                    'routes': [{'url_pattern': '**/api/items', 'body': [{'name': 'Alpha'}, {'name': 'Beta'}]}],
                    'actions': [{'type': 'wait', 'selector': '#items'}],
                    'assertions': [
                        {'type': 'visible', 'selector': '#items'},
                        {'type': 'count_equals', 'selector': '.item', 'value': 2},
                        {'type': 'text_contains', 'selector': '#items', 'value': 'Alpha'},
                        {'type': 'enabled', 'selector': '#refresh'},
                    ],
                },
                {
                    'id': 'recovery',
                    'routes': [{
                        'url_pattern': '**/api/items',
                        'sequence': [
                            {'status': 500, 'body': {'error': 'first failure'}},
                            {'status': 200, 'body': [{'name': 'Recovered'}]},
                        ],
                    }],
                    'actions': [
                        {'type': 'wait', 'selector': '#retry'},
                        {'type': 'click', 'selector': '#retry'},
                        {'type': 'wait', 'selector': '#items'},
                    ],
                    'assertions': [
                        {'type': 'visible', 'selector': '#items'},
                        {'type': 'text_contains', 'selector': '#items', 'value': 'Recovered'},
                        {'type': 'hidden', 'selector': '#error'},
                        {'type': 'enabled', 'selector': '#refresh'},
                    ],
                },
            ],
        }
        spec = root / 'matrix.json'
        spec.write_text(json.dumps(matrix, indent=2) + '\n', encoding='utf-8')
        try:
            code, payload = run_runner(spec, base_url)
            checks = {
                'matrix_runner_succeeds': code == 0 and payload.get('overall_pass') is True,
                'all_required_states_pass': all(item.get('passed') for item in payload.get('state_summary', [])),
                'desktop_and_mobile_both_run': len(payload.get('cases', [])) == 10 and {case.get('viewport') for case in payload.get('cases', [])} == {'desktop', 'mobile'},
                'loading_disabled_state_proven': all(any(a.get('type') == 'disabled' and a.get('passed') for a in case.get('assertions', [])) for case in payload.get('cases', []) if case.get('state') == 'loading'),
                'error_state_proven': all(case.get('passed') for case in payload.get('cases', []) if case.get('state') == 'error'),
                'recovery_after_failure_proven': all(case.get('passed') and any(a.get('type') == 'text_contains' and a.get('value') == 'Recovered' and a.get('passed') for a in case.get('assertions', [])) for case in payload.get('cases', []) if case.get('state') == 'recovery'),
                'objective_audits_clean': all(not case.get('audit_blockers') for case in payload.get('cases', [])),
                'console_and_page_errors_clean': all(not case.get('console_errors') and not case.get('page_errors') for case in payload.get('cases', [])),
            }

            invalid = dict(matrix)
            invalid['required_states'] = [*matrix['required_states'], 'missing-required']
            invalid_spec = root / 'invalid-matrix.json'
            invalid_spec.write_text(json.dumps(invalid, indent=2) + '\n', encoding='utf-8')
            invalid_code, invalid_payload = run_runner(invalid_spec, base_url)
            checks['missing_required_state_fails_validation'] = invalid_code != 0 and any('required state missing' in error for error in invalid_payload.get('errors', []))

            result = {
                'schema': 'ui-forge-state-matrix-benchmark-v1',
                'generated_at': datetime.now(UTC).isoformat(),
                'checks': checks,
                'passed': sum(checks.values()),
                'total': len(checks),
                'overall_pass': all(checks.values()),
                'matrix_result': payload,
                'claims': {
                    'loading_empty_error_success_recovery_matrix_proven': all(checks.values()),
                    'desktop_mobile_state_proof_proven': checks['desktop_and_mobile_both_run'],
                    'not_a_full_ui_forge_or_lovable_claim': True,
                },
            }
            print(json.dumps(result, indent=2))
            out = Path(__file__).resolve().parent / 'results'
            out.mkdir(parents=True, exist_ok=True)
            (out / 'state-matrix-latest.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
            return 0 if result['overall_pass'] else 1
        finally:
            server.shutdown()
            server.server_close()


if __name__ == '__main__':
    raise SystemExit(main())
