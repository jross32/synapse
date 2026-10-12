import importlib.util
import tempfile
import json
from pathlib import Path

spec = importlib.util.spec_from_file_location('watch_ledger', Path(__file__).with_name('watch_ledger.py'))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
with tempfile.TemporaryDirectory() as folder:
    p = Path(folder) / 'ledger.jsonl'
    p.write_text('{"runtime":"claude","usage_source":"provider_reported","cost_usd":0.2,"total_tokens":100}\n{"runtime":"codex","usage_source":"untracked","cost_usd":0,"total_tokens":0}\nnot json\n', encoding='utf-8')
    report = module.summarize(module.rows(p))
    assert report['claude']['reported_cost_usd'] == 0.2
    assert report['codex']['unknown_calls'] == 1
    images = module.image_summary([{'provider':'image','model':'test','operation':'generate','image_count':2,'reported_cost_usd':0.08}, {'provider':'image','model':'test','operation':'generate','image_count':1,'reported_cost_usd':None}])
    assert images['image|test|generate']['cost_per_priced_image_usd'] == 0.04
    assert images['image|test|generate']['unknown_images'] == 1
print('cost monitor tests passed')
