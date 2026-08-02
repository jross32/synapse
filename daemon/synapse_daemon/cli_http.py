"""Thin HTTP client for the Synapse CLI (Contract #27).

The CLI never reaches into SQLite directly -- every command POSTs / GETs
the daemon's REST API so the audit log + state transitions match the
desktop UI exactly. This module is the plumbing: token discovery, JSON
helpers, and one ``request()`` function the CLI commands wrap.

No new dependencies. ``urllib`` from the stdlib is plenty for the
endpoints the CLI hits (no streaming, no multipart). The renderer's
``api-client.ts`` is the equivalent surface on the renderer side.

Daemon discovery
----------------
Default base URL: ``http://127.0.0.1:7878``. Override with
``SYNAPSE_DAEMON_BASE`` for a non-default port or remote tunnel.

Token discovery
---------------
1. ``SYNAPSE_TOKEN`` env var (highest precedence; useful for paired
   devices or CI).
2. ``<data-dir>/auth-token`` read from disk. Data dir defaults to
   ``data`` relative to the CWD; override with
   ``SYNAPSE_DATA_DIR``.
3. If neither is present, return ``None`` -- ``request()`` will then
   raise ``SynapseCliError`` so the CLI prints a useful hint.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, NamedTuple
from urllib import error as urllib_error
from urllib import request as urllib_request

DEFAULT_BASE = "http://127.0.0.1:7878"
API_PREFIX = "/api/v1"
_TOKEN_FILE = "auth-token"


class SynapseCliError(Exception):
    """Raised when a CLI call can't complete. The CLI prints the
    message and exits with a non-zero code."""


def daemon_base() -> str:
    return os.environ.get("SYNAPSE_DAEMON_BASE", DEFAULT_BASE).rstrip("/")


def _data_dir() -> Path:
    return Path(os.environ.get("SYNAPSE_DATA_DIR", "data"))


class ResolvedToken(NamedTuple):
    """A token plus *where it came from* -- so diagnostics can describe it.

    `doctor` needs to say "a token was found, and here is which one", and the
    honest way to do that is the source, never the value. Resolution lives in one
    place so the description can never drift from the precedence actually used.
    """

    value: str | None
    source: str | None  # never contains any part of the secret


def resolve_token() -> ResolvedToken:
    """Find the auth token and record which location supplied it."""

    env = os.environ.get("SYNAPSE_TOKEN")
    if env:
        return ResolvedToken(env.strip(), "$SYNAPSE_TOKEN")
    candidate = _data_dir() / _TOKEN_FILE
    if candidate.is_file():
        try:
            return ResolvedToken(candidate.read_text(encoding="utf-8").strip(), str(candidate))
        except OSError:
            return ResolvedToken(None, None)
    return ResolvedToken(None, None)


def discover_token() -> str | None:
    """Return the auth token to use, or None if we couldn't find one."""

    return resolve_token().value


def _build_url(path: str) -> str:
    if not path.startswith("/"):
        path = "/" + path
    return f"{daemon_base()}{API_PREFIX}{path}"


def request(
    method: str,
    path: str,
    body: Any | None = None,
    *,
    timeout: float = 30.0,
) -> Any:
    """Send a JSON request to the daemon and return the parsed body.

    Raises ``SynapseCliError`` on any non-2xx response (with the
    daemon's error envelope inline so the user gets a real reason),
    on connection failures, and on missing-token boot states.
    """

    token = discover_token()
    if token is None:
        raise SynapseCliError(
            "No auth token found. Set SYNAPSE_TOKEN, or run from a "
            "directory whose `data/auth-token` is readable, or pass "
            "--data-dir."
        )

    headers = {
        "Accept": "application/json",
        "X-Synapse-Token": token,
    }
    data: bytes | None = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body).encode("utf-8")

    req = urllib_request.Request(
        _build_url(path), data=data, method=method, headers=headers
    )
    try:
        with urllib_request.urlopen(req, timeout=timeout) as resp:
            payload = resp.read()
            if not payload:
                return None
            return json.loads(payload.decode("utf-8"))
    except urllib_error.HTTPError as exc:
        # The daemon's error handler always returns an ErrorEnvelope.
        try:
            envelope = json.loads(exc.read().decode("utf-8"))
            msg = envelope.get("message", "Unknown error")
            code = envelope.get("code", "")
            tag = f" [{code}]" if code else ""
            raise SynapseCliError(f"HTTP {exc.code}{tag}: {msg}")
        except (json.JSONDecodeError, AttributeError):
            raise SynapseCliError(f"HTTP {exc.code}: {exc.reason}")
    except urllib_error.URLError as exc:
        raise SynapseCliError(
            f"Could not reach daemon at {daemon_base()}: {exc.reason}. "
            "Is Synapse running?"
        )
    except TimeoutError:
        raise SynapseCliError(
            f"Could not reach daemon at {daemon_base()}: timed out. "
            "Is Synapse running?"
        )


# ── helpers used by multiple CLI commands ────────────────────────────────


def print_json(data: Any, *, fp=sys.stdout) -> None:
    json.dump(data, fp, indent=2, default=str)
    fp.write("\n")
