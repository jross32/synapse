"""On-demand antivirus scanning for uploaded files (ADR-0003 Phase C · v0.1.32).

Always-on per the ADR: every file that lands in the quarantine directory
gets scanned before it moves to its final location. The result is recorded
in ``project_files.scan_result`` (clean / blocked / unavailable) and
``project_files.scan_engine``.

Engines
-------
- **Windows: Microsoft Defender**, via ``MpCmdRun.exe``. Not on PATH by
  default -- we resolve to ``C:\\Program Files\\Windows Defender\\MpCmdRun.exe``.
  The ADR locked the result mapping to **stdout parsing** ("Threat
  information:") rather than exit codes, because Defender versions return
  inconsistent codes.
- **POSIX: ClamAV**, via ``clamscan`` on PATH. Exit codes ARE stable here
  (0 clean, 1 infected, 2 error).

No third-party APIs (Contract #15). The user gets a clear "scanning
unavailable" banner instead when no engine is present.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

# Defender canonical threat-name line: "Threat                  : <Name>"
# (variable whitespace between the word "Threat" and the colon).
_DEFENDER_THREAT_RE = re.compile(
    r"^\s*Threat\s+:\s*(\S.*)$", re.IGNORECASE | re.MULTILINE
)
# Some Defender versions also use ``Name : <Name>`` inside the threat block.
_DEFENDER_NAME_RE = re.compile(
    r"^\s*Name\s+:\s*(\S.*)$", re.IGNORECASE | re.MULTILINE
)

log = logging.getLogger(__name__)

#: How long we wait for a single-file scan before we treat the engine as
#: unavailable. The ADR fixed this at 30 s; Defender quick-scans a small
#: file in < 1 s in practice, and ClamAV ~ 1-3 s.
SCAN_TIMEOUT_SECONDS = 30.0

#: Recognised result values stored on ``project_files.scan_result``.
SCAN_CLEAN = "clean"
SCAN_BLOCKED = "blocked"
SCAN_UNAVAILABLE = "unavailable"

#: Engine identifiers stored on ``project_files.scan_engine``.
ENGINE_DEFENDER = "defender"
ENGINE_CLAMAV = "clamav"


@dataclass
class ScanResult:
    """Outcome of a single-file scan."""

    result: str             # one of SCAN_{CLEAN, BLOCKED, UNAVAILABLE}
    engine: str | None      # ENGINE_DEFENDER / ENGINE_CLAMAV / None
    threat_name: str | None = None  # human-readable when blocked
    stdout_tail: str | None = None  # last ~512 chars for the audit detail


def _defender_path() -> str | None:
    """Resolve ``MpCmdRun.exe``. Falls back to the standard install path
    if it's not on PATH (which is the default Windows behaviour)."""

    found = shutil.which("MpCmdRun.exe")
    if found:
        return found
    candidate = os.path.expandvars(
        r"%ProgramFiles%\Windows Defender\MpCmdRun.exe"
    )
    if os.path.isfile(candidate):
        return candidate
    return None


def _clamav_path() -> str | None:
    return shutil.which("clamscan")


def detect_engine() -> tuple[str | None, str | None]:
    """Return ``(engine_id, executable_path)`` for the platform's preferred
    engine, or ``(None, None)`` if no scanner is available."""

    if sys.platform == "win32":
        path = _defender_path()
        if path:
            return ENGINE_DEFENDER, path
    cl = _clamav_path()
    if cl:
        return ENGINE_CLAMAV, cl
    return None, None


def is_available() -> bool:
    """Cheap probe -- ``True`` if any scanner is detectable."""

    engine, _ = detect_engine()
    return engine is not None


# ── scanning ────────────────────────────────────────────────────────────────


async def scan_file(path: Path) -> ScanResult:
    """Run the platform AV against a single file. Caps at SCAN_TIMEOUT_SECONDS."""

    engine, exe = detect_engine()
    if engine is None or exe is None:
        return ScanResult(result=SCAN_UNAVAILABLE, engine=None)
    if engine == ENGINE_DEFENDER:
        return await _scan_defender(exe, path)
    return await _scan_clamav(exe, path)


# ── Defender ────────────────────────────────────────────────────────────────


def _classify_defender(stdout: str) -> tuple[str, str | None]:
    """ADR rule: parse stdout for ``Threat information:`` (or ``Threat ... :``)
    -- the exit code is unreliable across Defender versions.

    Defender prints the structure::

        Threat information:
          Name              : <ThreatName>
          ...
    """

    text = stdout.lower()
    # Detection signals: "Threat information" header, "found N threats" line,
    # or an anchored "Threat                  :" name line.
    blocked = (
        "threat information" in text
        or _DEFENDER_THREAT_RE.search(stdout) is not None
        or re.search(r"found\s+[1-9]\d*\s+threats?", text) is not None
    )
    if blocked:
        m = _DEFENDER_THREAT_RE.search(stdout) or _DEFENDER_NAME_RE.search(stdout)
        threat_name = m.group(1).strip() if m else None
        # "None" / empty strings shouldn't masquerade as a threat name.
        if threat_name and threat_name.lower() in ("none", "(none)"):
            threat_name = None
        return SCAN_BLOCKED, threat_name
    if "scan finished" in text or "scan completed" in text or "no threats" in text:
        return SCAN_CLEAN, None
    return SCAN_UNAVAILABLE, None


async def _scan_defender(exe: str, path: Path) -> ScanResult:
    args = [
        exe,
        "-Scan",
        "-ScanType",
        "3",          # 3 = file scan (one specific path)
        "-File",
        str(path.resolve()),
        "-DisableRemediation",  # we manage the file ourselves; don't quarantine it
    ]
    try:
        proc = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
    except (OSError, FileNotFoundError) as exc:  # pragma: no cover -- defensive
        log.warning("Defender spawn failed: %s", exc)
        return ScanResult(result=SCAN_UNAVAILABLE, engine=ENGINE_DEFENDER)
    try:
        stdout_bytes, _ = await asyncio.wait_for(
            proc.communicate(), timeout=SCAN_TIMEOUT_SECONDS
        )
    except asyncio.TimeoutError:
        try:
            proc.kill()
        except ProcessLookupError:  # pragma: no cover -- race
            pass
        return ScanResult(result=SCAN_UNAVAILABLE, engine=ENGINE_DEFENDER)
    stdout = (stdout_bytes or b"").decode("utf-8", errors="replace")
    verdict, threat = _classify_defender(stdout)
    # Defender real-time protection can also vapourise the file before we
    # finish scanning. If the file is gone after the call AND the verdict
    # is "unavailable", treat that as a block -- RTP did the work.
    if verdict == SCAN_UNAVAILABLE and not path.exists():
        return ScanResult(
            result=SCAN_BLOCKED,
            engine=ENGINE_DEFENDER,
            threat_name="(real-time protection)",
            stdout_tail=stdout[-512:],
        )
    return ScanResult(
        result=verdict,
        engine=ENGINE_DEFENDER,
        threat_name=threat,
        stdout_tail=stdout[-512:],
    )


# ── ClamAV ──────────────────────────────────────────────────────────────────


async def _scan_clamav(exe: str, path: Path) -> ScanResult:
    args = [exe, "--no-summary", "--stdout", str(path.resolve())]
    try:
        proc = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
    except (OSError, FileNotFoundError) as exc:  # pragma: no cover -- defensive
        log.warning("ClamAV spawn failed: %s", exc)
        return ScanResult(result=SCAN_UNAVAILABLE, engine=ENGINE_CLAMAV)
    try:
        stdout_bytes, _ = await asyncio.wait_for(
            proc.communicate(), timeout=SCAN_TIMEOUT_SECONDS
        )
    except asyncio.TimeoutError:
        try:
            proc.kill()
        except ProcessLookupError:  # pragma: no cover
            pass
        return ScanResult(result=SCAN_UNAVAILABLE, engine=ENGINE_CLAMAV)
    stdout = (stdout_bytes or b"").decode("utf-8", errors="replace")
    rc = proc.returncode
    if rc == 0:
        return ScanResult(result=SCAN_CLEAN, engine=ENGINE_CLAMAV, stdout_tail=stdout[-512:])
    if rc == 1:
        # clamscan prints ``<path>: <ThreatName> FOUND``
        threat = None
        for line in stdout.splitlines():
            if "FOUND" in line:
                parts = line.rsplit(":", 1)
                if len(parts) == 2:
                    name = parts[1].replace("FOUND", "").strip()
                    if name:
                        threat = name
                        break
        return ScanResult(
            result=SCAN_BLOCKED,
            engine=ENGINE_CLAMAV,
            threat_name=threat,
            stdout_tail=stdout[-512:],
        )
    return ScanResult(result=SCAN_UNAVAILABLE, engine=ENGINE_CLAMAV, stdout_tail=stdout[-512:])
