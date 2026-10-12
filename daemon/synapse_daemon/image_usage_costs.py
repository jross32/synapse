"""Append privacy-safe provider image usage receipts for AI cost analytics.

Never estimate a billed cost when it was not supplied by the image provider.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


def record_image_usage(
    data_dir: Path,
    *,
    provider: str,
    model: str,
    project_id: str,
    request_id: str | None,
    image_count: int,
    reported_cost_usd: float | None,
    operation: str = 'generate',
) -> None:
    if image_count < 1:
        return
    path = Path(data_dir) / 'image-usage.jsonl'
    path.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        'at': datetime.now(timezone.utc).isoformat(),
        'provider': provider,
        'model': model,
        'project_id': project_id,
        'request_id': request_id,
        'operation': operation,
        'image_count': image_count,
        'reported_cost_usd': reported_cost_usd,
    }
    with path.open('a', encoding='utf-8', newline='\n') as handle:
        handle.write(json.dumps(entry, separators=(',', ':')) + '\n')
