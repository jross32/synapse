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
    with tempfile.TemporaryDirectory(prefix='ui-forge-responsive-') as tmp:
        root = Path(tmp)
        css_path = root / 'styles.css'
        css = '''.panel { padding: 40px; grid-template-columns: 1fr 1fr; gap: 20px; }
@media (max-width: 640px) {
  .panel { padding: 16px; grid-template-columns: 1fr; gap: 12px; }
}
@media (min-width: 1000px) {
  .panel { padding: 56px; grid-template-columns: 1fr 1fr 1fr; }
}
@media (max-width: 900px) {
  @media (orientation: landscape) {
    .panel { padding: 18px; }
  }
}
'''
        css_path.write_text(css, encoding='utf-8')
        probe = {'tag': 'section', 'id': 'main-panel', 'classes': ['panel']}
        checks: dict[str, bool] = {}

        base_request = {'probe': probe, 'declarations': {'padding': '44px'}}
        code, base = run(root, base_request, True)
        checks['base_resolves_only_base_rule'] = code == 0 and base.get('selector') == '.panel' and base.get('media_chain') == [] and base.get('before_rule',{}).get('declarations',{}).get('padding') == '40px'
        checks['base_dry_run_non_mutating'] = css_path.read_text(encoding='utf-8') == css

        code, base_apply = run(root, base_request)
        after_base = css_path.read_text(encoding='utf-8')
        checks['base_apply_succeeds'] = code == 0 and base_apply.get('media_chain') == []
        checks['base_apply_leaves_media_rules_unchanged'] = 'padding: 16px' in after_base and 'padding: 56px' in after_base and 'padding: 18px' in after_base
        checks['base_apply_changes_only_base_value'] = 'padding: 44px' in after_base and after_base.count('padding: 44px') == 1

        # reset
        css_path.write_text(css, encoding='utf-8')
        mobile_request = {'probe': probe, 'media': '(max-width: 640px)', 'declarations': {'padding': '24px', 'gap': '14px'}}
        code, mobile = run(root, mobile_request, True)
        checks['mobile_resolves_exact_media_owner'] = code == 0 and mobile.get('media_chain') == ['(max-width: 640px)'] and mobile.get('before_rule',{}).get('declarations',{}).get('padding') == '16px'
        checks['mobile_dry_run_non_mutating'] = css_path.read_text(encoding='utf-8') == css
        code, mobile_apply = run(root, mobile_request)
        after_mobile = css_path.read_text(encoding='utf-8')
        checks['mobile_apply_succeeds'] = code == 0 and mobile_apply.get('media_chain') == ['(max-width: 640px)']
        checks['mobile_apply_leaves_base_and_wide_unchanged'] = 'padding: 40px' in after_mobile and 'padding: 56px' in after_mobile and 'padding: 18px' in after_mobile
        checks['mobile_rule_receives_values'] = 'padding: 24px' in after_mobile and 'gap: 14px' in after_mobile

        css_path.write_text(css, encoding='utf-8')
        wide_request = {'probe': probe, 'media_chain': ['(min-width: 1000px)'], 'declarations': {'padding': '60px'}}
        code, wide = run(root, wide_request, True)
        checks['wide_resolves_exact_media_owner'] = code == 0 and wide.get('media_chain') == ['(min-width: 1000px)'] and wide.get('before_rule',{}).get('declarations',{}).get('padding') == '56px'

        nested_request = {'probe': probe, 'media_chain': ['(max-width: 900px)', '(orientation: landscape)'], 'declarations': {'padding': '22px'}}
        code, nested = run(root, nested_request, True)
        checks['nested_media_chain_resolves_exactly'] = code == 0 and nested.get('media_chain') == ['(max-width: 900px)', '(orientation: landscape)'] and nested.get('before_rule',{}).get('declarations',{}).get('padding') == '18px'

        missing_request = {'probe': probe, 'media': '(max-width: 500px)', 'declarations': {'padding': '8px'}}
        code, missing = run(root, missing_request, True)
        checks['missing_media_owner_fails_closed'] = code != 0 and missing.get('media_chain') == ['(max-width: 500px)'] and 'requested media context' in missing.get('error','')

        malformed_request = {'probe': probe, 'media': '(max-width: 640px); .evil { display:none }', 'declarations': {'padding': '8px'}}
        code, malformed = run(root, malformed_request, True)
        checks['structural_media_syntax_is_refused'] = code != 0 and 'media_chain contains unsafe' in malformed.get('error','')

        too_deep = {'probe': probe, 'media_chain': ['(a)','(b)','(c)','(d)','(e)'], 'declarations': {'padding': '8px'}}
        code, deep = run(root, too_deep, True)
        checks['excessive_nested_media_chain_is_refused'] = code != 0 and 'limited to 4' in deep.get('error','')

        explicit_base = {'probe': probe, 'file': 'styles.css', 'selector': '.panel', 'declarations': {'padding': '45px'}}
        code, explicit = run(root, explicit_base, True)
        checks['explicit_file_selector_without_media_still_targets_base'] = code == 0 and explicit.get('media_chain') == [] and explicit.get('before_rule',{}).get('declarations',{}).get('padding') == '40px'

        explicit_mobile = {'probe': probe, 'file': 'styles.css', 'selector': '.panel', 'media': '(max-width: 640px)', 'declarations': {'padding': '25px'}}
        code, explicit_m = run(root, explicit_mobile, True)
        checks['explicit_file_selector_with_media_targets_mobile'] = code == 0 and explicit_m.get('media_chain') == ['(max-width: 640px)'] and explicit_m.get('before_rule',{}).get('declarations',{}).get('padding') == '16px'

        result = {
            'schema': 'ui-forge-responsive-style-benchmark-v1',
            'generated_at': datetime.now(UTC).isoformat(),
            'checks': checks,
            'passed': sum(checks.values()),
            'total': len(checks),
            'overall_pass': all(checks.values()),
            'examples': {'base': base, 'mobile': mobile, 'wide': wide, 'nested': nested},
            'claims': {
                'base_and_media_css_ownership_separated': all(checks.values()),
                'exact_nested_media_context_supported': checks.get('nested_media_chain_resolves_exactly', False),
                'not_a_full_ui_forge_or_lovable_claim': True,
            },
        }
        print(json.dumps(result, indent=2))
        out = Path(__file__).resolve().parent / 'results'; out.mkdir(parents=True, exist_ok=True)
        (out / 'responsive-style-latest.json').write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
        return 0 if result['overall_pass'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
