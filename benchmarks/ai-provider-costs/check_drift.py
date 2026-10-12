"""Compare provider costs and latency against a saved baseline; never invent unknown prices."""
import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent

def load(path):
    data = json.loads(Path(path).read_text(encoding='utf-8-sig'))
    return data.get('samples', [])

def compare(baseline, current):
    prior = {(x.get('provider'), x.get('model'), x.get('task')): x for x in baseline}
    results = []
    for sample in current:
        key = (sample.get('provider'), sample.get('model'), sample.get('task'))
        old = prior.get(key)
        if old is None:
            results.append({'key': key, 'status': 'new_or_noncomparable'})
            continue
        metrics = {}
        for field in ('reported_cost_usd', 'duration_ms', 'reported_total_tokens'):
            a, b = old.get(field), sample.get(field)
            if a is None or b is None:
                metrics[field] = {'status': 'unknown'}
            elif a == 0:
                metrics[field] = {'status': 'baseline_zero', 'current': b}
            else:
                delta = round((b / a - 1) * 100, 2)
                metrics[field] = {'baseline': a, 'current': b, 'change_pct': delta, 'alert': abs(delta) >= 20}
        results.append({'key': key, 'status': 'compared', 'metrics': metrics})
    return results

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('current', nargs='?', default=str(ROOT / 'baseline-2026-10-12.json'))
    parser.add_argument('--baseline', default=str(ROOT / 'baseline-2026-10-12.json'))
    args = parser.parse_args()
    print(json.dumps(compare(load(args.baseline), load(args.current)), indent=2))
