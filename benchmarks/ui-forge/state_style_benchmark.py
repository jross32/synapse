#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import tempfile
from datetime import UTC, datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
EDITOR = REPO / 'templates' / 'skills' / 'ui-forge' / 'scripts' / 'css_style_editor.mjs'


def call(root: Path, request: dict, dry: bool = True):
    spec = root / 'request.json'
    spec.write_text(json.dumps(request, indent=2) + '\n', encoding='utf-8')
    cmd = ['node', str(EDITOR), str(root), str(spec)]
    if dry:
        cmd.append('--dry-run')
    cp = subprocess.run(cmd, cwd=REPO, text=True, capture_output=True, timeout=30)
    try:
        payload = json.loads(cp.stdout)
    except json.JSONDecodeError:
        payload = {'ok': False, 'stdout': cp.stdout, 'stderr': cp.stderr}
    return cp.returncode, payload


def main() -> int:
    with tempfile.TemporaryDirectory(prefix='ui-forge-state-style-') as tmp:
        root = Path(tmp)
        (root / 'styles.css').write_text(
            '.cta { background-color: rgb(10, 20, 30); color: white; }\n'
            '.cta:hover { background-color: rgb(20, 30, 40); transform: translateY(-1px); }\n'
            '.cta:focus-visible { outline: 2px solid white; outline-offset: 2px; }\n'
            '.cta:disabled { opacity: .5; cursor: not-allowed; }\n'
            '.cta:hover:focus { color: yellow; }\n'
            '.other:hover { color: pink; }\n',
            encoding='utf-8',
        )
        probe = {'tag': 'button', 'id': 'save', 'classes': ['cta']}
        checks: dict[str, bool] = {}
        results: dict[str, dict] = {}

        cases = [
            ('base', None, '.cta', {'background-color': 'rgb(11, 22, 33)'}),
            ('hover', 'hover', '.cta:hover', {'background-color': 'rgb(200, 50, 20)'}),
            ('focus_visible', 'focus-visible', '.cta:focus-visible', {'outline': '3px solid lime'}),
            ('disabled', 'disabled', '.cta:disabled', {'opacity': '.35'}),
        ]
        original = (root / 'styles.css').read_text(encoding='utf-8')
        for label, state, expected, decls in cases:
            request = {'probe': probe, 'declarations': decls}
            if state:
                request['state'] = state
            code, payload = call(root, request, True)
            results[label] = payload
            checks[f'{label}_resolves_exact_owner'] = code == 0 and payload.get('ok') is True and payload.get('selector') == expected and payload.get('state') == state
            checks[f'{label}_dry_run_non_mutating'] = (root / 'styles.css').read_text(encoding='utf-8') == original

        missing_code, missing = call(root, {'probe': probe, 'state': 'checked', 'declarations': {'color': 'red'}}, True)
        checks['missing_requested_state_fails_closed'] = missing_code != 0 and 'state :checked' in missing.get('error', '')

        bad_code, bad = call(root, {'probe': probe, 'state': 'visited', 'declarations': {'color': 'red'}}, True)
        checks['unsupported_state_is_refused'] = bad_code != 0 and 'unsupported interaction state' in bad.get('error', '')

        # Applying hover must mutate only :hover, preserving base and combined-state rules.
        apply_request = {'probe': probe, 'state': 'hover', 'declarations': {'background-color': 'rgb(250, 80, 10)', 'transform': 'translateY(-2px)'}}
        apply_code, applied = call(root, apply_request, False)
        after = (root / 'styles.css').read_text(encoding='utf-8')
        checks['hover_apply_succeeds'] = apply_code == 0 and applied.get('selector') == '.cta:hover' and applied.get('state') == 'hover'
        checks['base_rule_is_unchanged_by_hover_edit'] = '.cta { background-color: rgb(10, 20, 30); color: white; }' in after
        checks['combined_state_rule_is_unchanged'] = '.cta:hover:focus { color: yellow; }' in after
        checks['hover_rule_received_requested_values'] = 'background-color: rgb(250, 80, 10)' in after and 'transform: translateY(-2px)' in after

        result = {
            'schema': 'ui-forge-state-style-benchmark-v1',
            'generated_at': datetime.now(UTC).isoformat(),
            'checks': checks,
            'passed': sum(checks.values()),
            'total': len(checks),
            'overall_pass': all(checks.values()),
            'results': results,
            'applied': applied,
            'claims': {
                'exact_pseudo_state_ownership_gate_proven': all(checks.values()),
                'base_and_complex_states_preserved': checks['base_rule_is_unchanged_by_hover_edit'] and checks['combined_state_rule_is_unchanged'],
                'not_a_full_ui_forge_or_lovable_claim': True,
            },
        }
        print(json.dumps(result, indent=2))
        out = Path(__file__).resolve().parent / 'results'
        out.mkdir(parents=True, exist_ok=True)
        (out / 'state-style-latest.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
        return 0 if result['overall_pass'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
