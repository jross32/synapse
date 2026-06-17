"""Boot-time daemon configuration (v0.1.35).

The daemon's listen host has to be decided BEFORE FastAPI is constructed,
so we can't store it in SQLite (storage isn't open yet at that point).
A tiny JSON file in the data directory does the job: read at boot, written
by the GET/PATCH /api/v1/system/network route.

Only one knob today (``bind_lan``) but the file is a dict so adding the
next knob is one key, not a migration.

Schema::

    {
      "bind_lan": false        // true = bind 0.0.0.0, false = 127.0.0.1
    }

Missing file / bad JSON / unknown keys all degrade gracefully to defaults.
We never crash the daemon over a config file.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field, asdict
from pathlib import Path

log = logging.getLogger(__name__)

_FILENAME = "boot-config.json"


@dataclass
class BootConfig:
    """User-overridable boot settings. See module docstring."""

    bind_lan: bool = False

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _path_for(data_dir: Path) -> Path:
    return data_dir / _FILENAME


def load(data_dir: Path) -> BootConfig:
    """Read the config from disk. Returns the defaults if the file is
    missing or unreadable; never raises on user input."""

    target = _path_for(data_dir)
    if not target.is_file():
        return BootConfig()
    try:
        raw = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        log.warning("Could not read %s (%s); falling back to defaults", target, exc)
        return BootConfig()
    if not isinstance(raw, dict):
        log.warning("%s did not contain a JSON object; falling back to defaults", target)
        return BootConfig()
    cfg = BootConfig()
    if isinstance(raw.get("bind_lan"), bool):
        cfg.bind_lan = raw["bind_lan"]
    return cfg


def save(data_dir: Path, cfg: BootConfig) -> None:
    """Write the config to disk. Creates the data dir if needed.

    The file is rewritten atomically (write-to-temp, then rename) so a
    crash mid-write never leaves the daemon with a half-truncated JSON
    file it can't parse on the next boot.
    """

    data_dir.mkdir(parents=True, exist_ok=True)
    target = _path_for(data_dir)
    tmp = target.with_suffix(target.suffix + ".tmp")
    tmp.write_text(json.dumps(cfg.to_dict(), indent=2), encoding="utf-8")
    tmp.replace(target)
