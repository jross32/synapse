"""Read Synapse's existing runtime ledger and emit a safe cost-drift report.

Read-only against the live ledger. Optional image records are supplied as JSONL
with provider, model, operation, image_count and provider-reported total cost.
"""
import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def rows(path):
    if not path.is_file():
        return []
    output = []
    for line in path.read_text(encoding='utf-8-sig', errors='replace').splitlines():
        try:
            value = json.loads(line)
            if isinstance(value, dict):
                output.append(value)
        except (ValueError, TypeError):
            continue
    return output


def summarize(entries):
    summary = {}
    for entry in entries:
        runtime = str(entry.get('runtime') or 'unknown')
        group = summary.setdefault(runtime, {'calls': 0, 'tracked_calls': 0, 'unknown_calls': 0, 'reported_cost_usd': 0.0, 'reported_tokens': 0, 'seconds': 0.0})
        group['calls'] += 1
        group['seconds'] += float(entry.get('seconds') or 0)
        source = entry.get('usage_source')
        if source == 'untracked' or (source != 'provider_reported' and not any(entry.get(k) for k in ('total_tokens', 'cost_usd', 'credits', 'requests'))):
            group['unknown_calls'] += 1
        else:
            group['tracked_calls'] += 1
            group['reported_cost_usd'] += float(entry.get('cost_usd') or 0)
            group['reported_tokens'] += int(entry.get('total_tokens') or 0)
    return summary


def image_summary(entries):
    groups = {}
    for entry in entries:
        key = (str(entry.get('provider') or 'unknown'), str(entry.get('model') or 'unknown'), str(entry.get('operation') or 'generate'))
        group = groups.setdefault('|'.join(key), {'images': 0, 'priced_images': 0, 'reported_cost_usd': 0.0, 'unknown_images': 0})
        count = max(0, int(entry.get('image_count') or 0))
        group['images'] += count
        if entry.get('reported_cost_usd') is None:
            group['unknown_images'] += count
        else:
            group['priced_images'] += count
            group['reported_cost_usd'] += float(entry['reported_cost_usd'])
    for group in groups.values():
        group['cost_per_priced_image_usd'] = round(group['reported_cost_usd'] / group['priced_images'], 6) if group['priced_images'] else None
    return groups


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--ledger', type=Path, default=ROOT / 'data' / 'runtime-ledger.jsonl')
    parser.add_argument('--images', type=Path, default=ROOT / 'data' / 'image-usage.jsonl')
    parser.add_argument('--output', type=Path, default=HERE / 'latest-report.json')
    parser.add_argument('--previous', type=Path, default=HERE / 'latest-report.json')
    parser.add_argument('--alert-percent', type=float, default=20)
    args = parser.parse_args()
    prior = json.loads(args.previous.read_text(encoding='utf-8-sig')) if args.previous.exists() else {}
    current = summarize(rows(args.ledger))
    images = image_summary(rows(args.images))
    alerts = []
    for name, item in current.items():
        old = prior.get('runtimes', {}).get(name, {})
        a, b = old.get('reported_cost_usd'), item['reported_cost_usd']
        if a is not None and a > 0 and old.get('tracked_calls') == item['tracked_calls'] and abs(b / a - 1) * 100 >= args.alert_percent:
            alerts.append({'runtime': name, 'metric': 'reported_cost_usd', 'change_pct': round((b / a - 1) * 100, 2)})
    for name, item in images.items():
        old = prior.get('images', {}).get(name, {})
        a, b = old.get('cost_per_priced_image_usd'), item['cost_per_priced_image_usd']
        if a is not None and b is not None and a > 0 and abs(b / a - 1) * 100 >= args.alert_percent:
            alerts.append({'image_model': name, 'metric': 'cost_per_priced_image_usd', 'change_pct': round((b / a - 1) * 100, 2)})
    report = {'generated_at': datetime.now(timezone.utc).isoformat(), 'ledger': str(args.ledger), 'runtimes': current, 'images': images, 'alerts': alerts, 'caveat': 'Aggregate cumulative totals, not per-task billing. Unknown calls excluded from reported cost; image prices require explicit provider-reported image entries.'}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    # Publish to the daemon's persistent profile data directory as well as the repo.
    # Packaged Synapse must not rely on a source-code-relative report path.
    appdata = os.getenv('APPDATA')
    if appdata:
        profile_data = Path(appdata) / 'Synapse' / 'data'
        if profile_data.is_dir():
            (profile_data / 'ai-usage-cost-report.json').write_text(
                json.dumps(report, indent=2) + '\n', encoding='utf-8'
            )
    print(json.dumps({'runtimes': len(current), 'image_models': len(images), 'alerts': alerts, 'output': str(args.output)}))

if __name__ == '__main__':
    main()
