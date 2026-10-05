#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import tempfile
from datetime import UTC, datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
EDITOR = REPO / 'templates' / 'skills' / 'ui-forge' / 'scripts' / 'css_style_editor.mjs'


def run(root: Path, request: dict, dry: bool = False):
    spec = root / 'style-request.json'
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
    with tempfile.TemporaryDirectory(prefix='ui-forge-css-style-') as tmp:
        root = Path(tmp)
        (root / 'src').mkdir()
        css = '.shell { display: grid; gap: 12px; }\n.cta { padding: 0 20px; border-radius: 10px; color: white; }\n.cta:hover { padding: 0 99px; }\n.note { color: gray; }\n'
        css_path = root / 'src' / 'styles.css'
        css_path.write_text(css, encoding='utf-8')
        probe = {'tag': 'button', 'id': 'save', 'classes': ['cta', 'primary']}
        request = {'probe': probe, 'declarations': {'padding': '0 30px', 'border-radius': '16px'}}

        dry_code, dry = run(root, request, True)
        checks = {
            'dry_run_resolves_unique_owner': dry_code == 0 and dry.get('ok') is True and dry.get('selector') == '.cta',
            'dry_run_does_not_write': css_path.read_text(encoding='utf-8') == css,
        }
        code, applied = run(root, request)
        after = css_path.read_text(encoding='utf-8')
        checks['apply_succeeds'] = code == 0 and applied.get('ok') is True
        checks['owning_rule_updated'] = 'padding: 0 30px' in after and 'border-radius: 16px' in after
        checks['unrelated_rule_preserved'] = '.note { color: gray; }' in after and '.shell { display: grid; gap: 12px; }' in after
        checks['syntax_reparse_passes'] = applied.get('syntax_reparse_passed') is True
        checks['automatic_owner_ignores_pseudo_state_rules'] = applied.get('selector') == '.cta' and '.cta:hover { padding: 0 99px; }' in after

        # Two equally strong .cta owners must fail closed unless file+selector is explicit.
        (root / 'src' / 'theme.css').write_text('.cta { padding: 4px; }\n', encoding='utf-8')
        amb_code, ambiguous = run(root, request, True)
        checks['ambiguous_owner_fails_closed'] = amb_code != 0 and 'ambiguous CSS ownership' in ambiguous.get('error', '')
        explicit = {**request, 'declarations': {'padding': '0 31px'}, 'file': 'src/styles.css', 'selector': '.cta'}
        exp_code, explicit_result = run(root, explicit, True)
        checks['explicit_owner_resolves_ambiguity'] = exp_code == 0 and explicit_result.get('file') == 'src/styles.css'

        bad_request = {'probe': probe, 'declarations': {'background': 'url(https://example.com/x.png)'}}
        bad_code, bad = run(root, bad_request, True)
        checks['url_values_require_main_coding_path'] = bad_code != 0 and 'url()' in bad.get('error', '')

        result = {
            'schema': 'ui-forge-css-style-benchmark-v1',
            'generated_at': datetime.now(UTC).isoformat(),
            'checks': checks,
            'passed': sum(checks.values()),
            'total': len(checks),
            'overall_pass': all(checks.values()),
            'owner': {'file': applied.get('file'), 'selector': applied.get('selector'), 'score': applied.get('ownership_score')},
            'claims': {'css_owner_edit_gate_proven': all(checks.values()), 'not_a_full_ui_forge_or_lovable_claim': True},
        }
        print(json.dumps(result, indent=2))
        out = Path(__file__).resolve().parent / 'results'
        out.mkdir(parents=True, exist_ok=True)
        (out / 'css-style-latest.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
        return 0 if result['overall_pass'] else 1


if __name__ == '__main__':
    raise SystemExit(main())


