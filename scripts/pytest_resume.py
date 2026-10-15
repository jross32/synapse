"""Resumeable per-file pytest verification with durable JSONL receipts.

Usage: python scripts/pytest_resume.py --max-files 3
Run again without --max-files to continue remaining files.
"""
import argparse
import datetime as dt
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEST_DIR = ROOT / 'daemon' / 'tests'
RESULTS = ROOT / 'data' / 'pytest-verification.jsonl'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--max-files', type=int, default=0, help='0 means all remaining files')
    parser.add_argument('--timeout', type=int, default=1800, help='Seconds per test file')
    parser.add_argument('--retry-failures', action='store_true')
    args = parser.parse_args()
    if args.timeout < 1:
        parser.error('--timeout must be positive')
    files = sorted(TEST_DIR.glob('test_*.py'))
    completed = {}
    if RESULTS.exists():
        for line in RESULTS.read_text(encoding='utf-8').splitlines():
            try:
                entry = json.loads(line)
                completed[entry['file']] = entry['status']
            except (ValueError, KeyError):
                continue
    pending = [p for p in files if completed.get(p.name) != 'passed' and (args.retry_failures or p.name not in completed)]
    if args.max_files:
        pending = pending[:args.max_files]
    RESULTS.parent.mkdir(parents=True, exist_ok=True)
    print(f'Total {len(files)} test files; {sum(x == "passed" for x in completed.values())} previously passed; running {len(pending)}', flush=True)
    failed = 0
    for index, path in enumerate(pending, 1):
        print(f'[{index}/{len(pending)}] {path.name}', flush=True)
        cmd = [sys.executable, '-m', 'pytest', '-q', str(path), '--durations=3']
        try:
            result = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, errors='replace', timeout=args.timeout)
            status = 'passed' if result.returncode == 0 else 'failed'
            output = (result.stdout + '\n' + result.stderr)[-10000:]
        except subprocess.TimeoutExpired as exc:
            status = 'timeout'
            output = f'Exceeded per-file timeout of {args.timeout} seconds: {exc}'
        entry = {'file': path.name, 'status': status, 'timestamp_utc': dt.datetime.now(dt.timezone.utc).isoformat(), 'output': output}
        with RESULTS.open('a', encoding='utf-8') as log:
            log.write(json.dumps(entry, ensure_ascii=False) + '\n')
            log.flush()
        print(f'{path.name}: {status}; receipt saved to {RESULTS}', flush=True)
        if status != 'passed':
            failed += 1
    print(f'Batch finished: {len(pending) - failed} passed, {failed} failed/timed out', flush=True)
    return 1 if failed else 0


if __name__ == '__main__':
    raise SystemExit(main())
