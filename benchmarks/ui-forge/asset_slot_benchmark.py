#!/usr/bin/env python3
from __future__ import annotations

import json
import struct
import subprocess
import tempfile
import zlib
from datetime import UTC, datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
TOOL = REPO / 'templates' / 'skills' / 'ui-forge' / 'scripts' / 'asset_slot.mjs'


def png_bytes(width: int = 24, height: int = 16, rgb=(40, 160, 220)) -> bytes:
    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data) & 0xFFFFFFFF)
    raw = b''.join(b'\x00' + bytes(rgb) * width for _ in range(height))
    return b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0)) + chunk(b'IDAT', zlib.compress(raw)) + chunk(b'IEND', b'')


def run(*args: str):
    cp = subprocess.run(['node', str(TOOL), *args], cwd=REPO, text=True, capture_output=True, timeout=30)
    try:
        payload = json.loads(cp.stdout)
    except json.JSONDecodeError:
        payload = {'ok': False, 'stdout': cp.stdout, 'stderr': cp.stderr}
    return cp.returncode, payload


def source_pointer(source: str, marker: str, filename='src/App.jsx') -> str:
    idx = source.index(marker)
    prefix = source[:idx]
    line = prefix.count('\n') + 1
    line_start = prefix.rfind('\n') + 1
    col = idx - line_start + 1
    return f'{filename}:{line}:{col}'


def main() -> int:
    checks: dict[str, bool] = {}
    observations = {}
    with tempfile.TemporaryDirectory(prefix='ui-forge-asset-slot-') as tmp:
        root = Path(tmp)
        (root / 'src').mkdir()
        image = root / 'generated.png'
        image.write_bytes(png_bytes())
        source = 'export default function App(){return <main><img id="hero" src="/old.png" alt="Old hero" /></main>}\n'
        app = root / 'src' / 'App.jsx'
        app.write_text(source, encoding='utf-8')
        pointer = source_pointer(source, '<img')

        stage_code, staged = run('stage', str(root), str(image))
        checks['valid_raster_stages'] = stage_code == 0 and staged.get('ok') is True and staged.get('media_type') == 'png'
        checks['dimensions_and_hash_recorded'] = staged.get('width') == 24 and staged.get('height') == 16 and len(staged.get('sha256','')) == 64
        public_asset = root / staged.get('project_asset','missing')
        checks['staged_asset_is_project_local'] = public_asset.is_file() and staged.get('public_url','').startswith('/ui-forge-assets/')
        receipt = staged.get('receipt')
        request = root / 'request.json'
        request.write_text(json.dumps({'source': pointer, 'receipt': receipt, 'alt': 'Generated hero'}, indent=2) + '\n', encoding='utf-8')

        before = app.read_bytes()
        dry_code, dry = run('commit', str(root), str(request), '--dry-run')
        checks['dry_run_validates_commit'] = dry_code == 0 and dry.get('ok') is True and dry.get('syntax_reparse_passed') is True
        checks['dry_run_does_not_mutate_source'] = app.read_bytes() == before
        checks['dry_run_preserves_stage_receipt'] = (root / receipt).is_file()

        commit_code, committed = run('commit', str(root), str(request))
        after = app.read_text(encoding='utf-8')
        checks['commit_succeeds'] = commit_code == 0 and committed.get('ok') is True and committed.get('atomic') is True
        checks['jsx_src_and_alt_are_updated'] = staged['public_url'] in after and 'alt="Generated hero"' in after and '/old.png' not in after
        checks['stage_receipt_promoted'] = not (root / receipt).exists() and (root / '.synapse/ui-forge/assets/committed' / f"{staged['sha256']}.json").is_file()

        # Same bytes stage to the same hash-addressed target; discard should not remove committed asset.
        stage2_code, staged2 = run('stage', str(root), str(image))
        discard2_code, discarded2 = run('discard', str(root), staged2.get('receipt',''))
        checks['dedup_stage_reuses_existing_asset'] = stage2_code == 0 and staged2.get('created_new') is False
        checks['discard_refuses_referenced_asset_and_keeps_file'] = discard2_code != 0 and public_asset.is_file() and 'referenced by project source' in discarded2.get('error','')

        # Invalid image bytes are refused before any receipt/source mutation.
        fake = root / 'fake.png'; fake.write_text('<script>alert(1)</script>', encoding='utf-8')
        bad_code, bad = run('stage', str(root), str(fake))
        checks['disguised_non_image_is_refused'] = bad_code != 0 and 'supported raster image' in bad.get('error','')

        svg = root / 'vector.svg'; svg.write_text('<svg xmlns="http://www.w3.org/2000/svg"><script/></svg>', encoding='utf-8')
        svg_code, svg_result = run('stage', str(root), str(svg))
        checks['svg_is_refused_in_direct_asset_lane'] = svg_code != 0 and 'supported raster image' in svg_result.get('error','')

        # Dynamic src cannot be rewritten by the deterministic lane; staged asset can then be discarded.
        dyn_source = 'export default function Dyn({src}){return <img src={src} alt="Dynamic" />}\n'
        dyn = root / 'src' / 'Dynamic.jsx'; dyn.write_text(dyn_source, encoding='utf-8')
        stage3_code, staged3 = run('stage', str(root), str(root / 'generated2.png')) if False else (None, None)
        image2 = root / 'generated2.png'; image2.write_bytes(png_bytes(12, 12, (200, 80, 40)))
        stage3_code, staged3 = run('stage', str(root), str(image2))
        dyn_req = root / 'dyn-request.json'
        dyn_req.write_text(json.dumps({'source': source_pointer(dyn_source, '<img', 'src/Dynamic.jsx'), 'receipt': staged3['receipt']}, indent=2)+'\n', encoding='utf-8')
        dyn_before = dyn.read_bytes()
        dyn_code, dyn_result = run('commit', str(root), str(dyn_req))
        checks['dynamic_src_fails_closed'] = dyn_code != 0 and 'dynamic' in dyn_result.get('error','')
        checks['dynamic_src_failure_writes_nothing'] = dyn.read_bytes() == dyn_before
        discard3_code, discarded3 = run('discard', str(root), staged3['receipt'])
        checks['rejected_staged_asset_can_be_discarded'] = discard3_code == 0 and discarded3.get('asset_removed') is True and not (root / staged3['project_asset']).exists()

        # Exact source must point to intrinsic img, not another intrinsic element.
        div_source = 'export default function X(){return <div id="x">No image</div>}\n'
        div = root / 'src' / 'Div.jsx'; div.write_text(div_source, encoding='utf-8')
        image3 = root / 'generated3.png'; image3.write_bytes(png_bytes(8, 8, (20, 200, 80)))
        _, staged4 = run('stage', str(root), str(image3))
        div_req = root / 'div-request.json'; div_req.write_text(json.dumps({'source': source_pointer(div_source, '<div', 'src/Div.jsx'), 'receipt': staged4['receipt']})+'\n', encoding='utf-8')
        div_before = div.read_bytes(); div_code, div_result = run('commit', str(root), str(div_req))
        checks['non_img_source_is_refused'] = div_code != 0 and 'intrinsic <img>' in div_result.get('error','')
        checks['non_img_refusal_writes_nothing'] = div.read_bytes() == div_before
        run('discard', str(root), staged4['receipt'])

        observations = {'stage': staged, 'commit': committed, 'dynamic_failure': dyn_result}

    result = {
        'schema': 'ui-forge-asset-slot-benchmark-v1',
        'generated_at': datetime.now(UTC).isoformat(),
        'checks': checks,
        'passed': sum(checks.values()),
        'total': len(checks),
        'overall_pass': all(checks.values()),
        'observations': observations,
        'claims': {
            'project_local_provenance_asset_gate_proven': all(checks.values()),
            'dynamic_or_non_image_edits_fail_closed': checks.get('dynamic_src_fails_closed', False) and checks.get('non_img_source_is_refused', False),
            'not_a_provider_generation_quality_claim': True,
            'not_a_full_ui_forge_or_lovable_claim': True,
        },
    }
    print(json.dumps(result, indent=2))
    out = Path(__file__).resolve().parent / 'results'; out.mkdir(parents=True, exist_ok=True)
    (out / 'asset-slot-latest.json').write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    return 0 if result['overall_pass'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
