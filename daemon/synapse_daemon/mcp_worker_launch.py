"""Authenticated local work-item launch from Synapse's own MCP process.

Never return or log the daemon token. The existing REST launch handler owns
concurrency, permissions and worker lifetime. This wrapper cannot bypass it.
"""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from typing import Any

_ITEM = re.compile(r"^[a-zA-Z0-9_-]{6,80}$")


class WorkerLaunchError(RuntimeError):
    pass


def launch_existing_work_item(work_item_id: str, *, local_token: str, port: int = 7878,
                              timeout_seconds: int = 25) -> dict[str, Any]:
    if not _ITEM.fullmatch(work_item_id or ""):
        raise WorkerLaunchError("Invalid work-item identifier")
    if not local_token or not 1 <= port <= 65535 or not 1 <= timeout_seconds <= 30:
        raise WorkerLaunchError("Synapse local daemon authorization is unavailable")
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}/api/v1/agent-work-items/{work_item_id}/launch",
        data=b"{}", method="POST",
        headers={"X-Synapse-Token": local_token, "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            raw = response.read(100_001)
            if response.status not in (200, 201, 202) or len(raw) > 100_000:
                raise WorkerLaunchError("Unexpected worker-launch response")
            parsed = json.loads(raw)
    except urllib.error.HTTPError as exc:
        # Status only; response body may contain details we should not expose.
        raise WorkerLaunchError(f"Worker launch rejected (HTTP {exc.code})") from None
    except (urllib.error.URLError, TimeoutError) as exc:
        raise WorkerLaunchError("Worker-launch endpoint unavailable") from exc
    except (ValueError, TypeError) as exc:
        raise WorkerLaunchError("Invalid worker-launch response") from exc
    if not isinstance(parsed, dict):
        raise WorkerLaunchError("Invalid worker-launch receipt")
    # Return the existing REST handler's authoritative response, never a guess.
    return parsed
