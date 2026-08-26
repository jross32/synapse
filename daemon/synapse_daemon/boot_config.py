"""Boot-time daemon configuration (v0.1.35).

The daemon's listen host has to be decided BEFORE FastAPI is constructed,
so we can't store it in SQLite (storage isn't open yet at that point).
A tiny JSON file in the data directory does the job: read at boot, written
by the GET/PATCH /api/v1/system/network route.

Only one knob today (``bind_lan``) but the file is a dict so adding the
next knob is one key, not a migration.

Schema::

    {
      "bind_lan": false,        // true = bind 0.0.0.0, false = 127.0.0.1
      "wan_auto_start": true,   // true = auto-open the Cloudtap WAN tunnel on daemon start
      "public_hostname": null  // e.g. "synapse.example.com" -- a stable hostname the
                                // operator already routes to this port themselves
                                // (a named cloudflared tunnel, a reverse proxy, etc.)
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
    # Auto-open the Cloudtap WAN tunnel on daemon start (default on). The user can
    # turn this off in Settings -> Network; a fresh install ships with WAN on.
    wan_auto_start: bool = True

    # Whether the MCP connector serves its write/dispatch tools.
    #
    # This was an environment variable, and an environment variable is the wrong shape for
    # a user setting: it has to be present in whichever shell happened to launch the app, so
    # it silently reverted every time Synapse was started a different way. Persisted here,
    # it survives restarts and is one toggle in Settings.
    #
    # Default ON. The connector is reachable only with the daemon token, the read-only URL
    # exists for anything that should not write, and a default of OFF meant the tools were
    # advertised-but-refused for most of a day.
    mcp_writes_enabled: bool = True

    # A stable hostname the operator already routes to this daemon's port themselves
    # (most commonly a named cloudflared tunnel, e.g. "synapse.example.com" -- distinct
    # from Cloudtap's own auto-managed ephemeral quick-tunnel, which Synapse cannot tell
    # apart from any other traffic hitting this port). When set, this hostname is used
    # for the MCP connector URL and remote-access links instead of Cloudtap's live
    # tunnel state, which otherwise rotates to a new random hostname on every restart --
    # useless for a connector URL meant to be configured once in ChatGPT/Claude.
    public_hostname: str | None = None

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
    if isinstance(raw.get("wan_auto_start"), bool):
        cfg.wan_auto_start = raw["wan_auto_start"]
    if isinstance(raw.get("mcp_writes_enabled"), bool):
        cfg.mcp_writes_enabled = raw["mcp_writes_enabled"]
    if isinstance(raw.get("public_hostname"), str) and raw["public_hostname"].strip():
        cfg.public_hostname = normalize_hostname(raw["public_hostname"])
    return cfg


def normalize_hostname(value: str) -> str | None:
    """Reduce whatever the user pasted (a bare host, a full URL, trailing slash/path)
    to just the host -- the one thing callers actually need to build a URL from."""

    text = value.strip()
    if not text:
        return None
    if "://" in text:
        text = text.split("://", 1)[1]
    text = text.split("/", 1)[0]
    text = text.strip().rstrip(".")
    return text or None


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
