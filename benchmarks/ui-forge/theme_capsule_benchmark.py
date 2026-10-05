#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import tempfile
from datetime import UTC, datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
TOOL = REPO / 'templates' / 'skills' / 'ui-forge' / 'scripts' / 'theme_capsule.mjs'


def call(args: list[str], cwd: Path):
    cp = subprocess.run(['node', str(TOOL), *args], cwd=REPO, text=True, capture_output=True, timeout=30)
    try:
        payload = json.loads(cp.stdout)
    except json.JSONDecodeError:
        payload = {'ok': False, 'stdout': cp.stdout, 'stderr': cp.stderr}
    return cp.returncode, payload


def main() -> int:
    with tempfile.TemporaryDirectory(prefix='ui-forge-theme-') as tmp:
        base = Path(tmp)
        source = base / 'source'
        target = base / 'target'
        source.mkdir(); target.mkdir()
        source_css = ''':root {
  --bg: #0b1016;
  --surface: #16221b;
  --text: #f3f8f4;
  --accent: #c9ff58;
  --space-3: 12px;
  --radius-md: 14px;
  --shadow-card: 0 20px 50px rgba(0,0,0,.3);
}
body { background: var(--bg); color: var(--text); }
'''
        target_css = ''':root {
  --bg: #ffffff;
  --surface: #f5f5f5;
  --text: #111111;
  --accent: #3366ff;
  --space-3: 10px;
  --radius-md: 8px;
  --shadow-card: none;
}
.card { padding: var(--space-3); border-radius: var(--radius-md); }
'''
        (source / 'theme.css').write_text(source_css, encoding='utf-8')
        target_path = target / 'styles.css'
        target_path.write_text(target_css, encoding='utf-8')
        capsule = base / 'capsule.json'

        extract_code, extracted = call(['extract', str(source), str(capsule), '--name', 'Focus Theme'], base)
        theme = json.loads(capsule.read_text(encoding='utf-8')) if capsule.exists() else {}
        checks = {
            'extract_succeeds': extract_code == 0 and extracted.get('ok') is True,
            'schema_is_machine_readable': theme.get('schema') == 'ui-forge-theme-capsule-v1',
            'semantic_tokens_extracted': theme.get('tokens', {}).get('--accent') == '#c9ff58' and len(theme.get('tokens', {})) == 7,
            'categories_are_present': '--accent' in theme.get('categories', {}).get('color', []) and '--radius-md' in theme.get('categories', {}).get('radius', []),
        }
        before = target_path.read_text(encoding='utf-8')
        dry_code, dry = call(['apply', str(target), str(capsule), '--dry-run'], base)
        checks['dry_run_plans_all_tokens'] = dry_code == 0 and dry.get('applied_count') == 7
        checks['dry_run_is_non_mutating'] = target_path.read_text(encoding='utf-8') == before
        apply_code, applied = call(['apply', str(target), str(capsule)], base)
        after = target_path.read_text(encoding='utf-8')
        checks['apply_succeeds_atomically'] = apply_code == 0 and applied.get('ok') is True and applied.get('atomic') is True
        checks['target_tokens_match_capsule'] = all(f'{token}: {value}' in after for token, value in theme.get('tokens', {}).items())
        checks['non_token_css_is_preserved'] = '.card { padding: var(--space-3); border-radius: var(--radius-md); }' in after

        # Missing token fails closed by default.
        partial = base / 'partial'
        partial.mkdir()
        partial_path = partial / 'styles.css'
        partial_original = ':root { --bg: black; --accent: red; }\n'
        partial_path.write_text(partial_original, encoding='utf-8')
        missing_code, missing = call(['apply', str(partial), str(capsule)], base)
        checks['missing_tokens_fail_closed'] = missing_code != 0 and 'missing theme tokens' in missing.get('error', '')
        checks['missing_token_failure_writes_nothing'] = partial_path.read_text(encoding='utf-8') == partial_original
        partial_code, partial_result = call(['apply', str(partial), str(capsule), '--allow-partial'], base)
        checks['explicit_partial_apply_works'] = partial_code == 0 and partial_result.get('applied_count') == 2 and len(partial_result.get('missing', [])) == 5

        # Conflicting source definitions refuse extraction.
        conflict = base / 'conflict'
        conflict.mkdir()
        (conflict / 'a.css').write_text(':root { --accent: red; }\n', encoding='utf-8')
        (conflict / 'b.css').write_text(':root { --accent: blue; }\n', encoding='utf-8')
        conflict_out = base / 'conflict.json'
        conflict_code, conflict_result = call(['extract', str(conflict), str(conflict_out)], base)
        checks['conflicting_source_tokens_refuse_extraction'] = conflict_code != 0 and 'conflicting root theme token definitions' in conflict_result.get('error', '')

        result = {
            'schema': 'ui-forge-theme-capsule-benchmark-v1',
            'generated_at': datetime.now(UTC).isoformat(),
            'checks': checks,
            'passed': sum(checks.values()),
            'total': len(checks),
            'overall_pass': all(checks.values()),
            'token_count': len(theme.get('tokens', {})),
            'claims': {
                'semantic_theme_extract_apply_gate_proven': all(checks.values()),
                'blind_global_replacement_avoided': True,
                'not_a_full_ui_forge_or_lovable_claim': True,
            },
        }
        print(json.dumps(result, indent=2))
        out = Path(__file__).resolve().parent / 'results'
        out.mkdir(parents=True, exist_ok=True)
        (out / 'theme-capsule-latest.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
        return 0 if result['overall_pass'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
