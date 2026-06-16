"""Unit tests for the AV stdout parsers (ADR-0003 Phase C · v0.1.32).

These don't spawn real engines -- they pin the classifier behaviour against
synthetic stdout the way the live engines print it. The integration test
that actually invokes Defender (slow + environment-dependent) is gated by
``--runav`` and skipped by default.
"""

from __future__ import annotations

from synapse_daemon import files_av
from synapse_daemon.files_av import SCAN_BLOCKED, SCAN_CLEAN, SCAN_UNAVAILABLE, ScanResult


# ── Defender stdout parsing ─────────────────────────────────────────────────


def test_defender_clean_output_is_classified_clean() -> None:
    sample = """\
Scan starting...
CmdTool: Scan started.
Scanning C:\\Users\\justi\\foo.bin
Scan finished.
Scan completed.
"""
    verdict, threat = files_av._classify_defender(sample)
    assert verdict == SCAN_CLEAN
    assert threat is None


def test_defender_threat_info_block_extracts_name() -> None:
    sample = """\
CmdTool: Scan started.
Threat information:
  Name              : Virus:Win32/Test.A
  Id                : 2147XXXX
  Severity          : Severe
Scan finished.
"""
    verdict, threat = files_av._classify_defender(sample)
    assert verdict == SCAN_BLOCKED
    assert threat == "Virus:Win32/Test.A"


def test_defender_garbage_output_is_unavailable() -> None:
    verdict, threat = files_av._classify_defender("garbage from the universe")
    assert verdict == SCAN_UNAVAILABLE
    assert threat is None


def test_defender_threat_information_with_no_name_does_not_crash() -> None:
    """Defective threat block -- still flagged as blocked, threat_name None."""

    verdict, threat = files_av._classify_defender("Threat information:\n")
    assert verdict == SCAN_BLOCKED
    assert threat is None


# ── ScanResult shape ────────────────────────────────────────────────────────


def test_scan_result_carries_engine_and_threat() -> None:
    r = ScanResult(
        result=SCAN_BLOCKED, engine=files_av.ENGINE_DEFENDER, threat_name="X"
    )
    assert r.result == SCAN_BLOCKED
    assert r.engine == "defender"
    assert r.threat_name == "X"
    assert r.stdout_tail is None


# ── Engine detection ────────────────────────────────────────────────────────


def test_detect_engine_returns_none_when_nothing_resolvable(monkeypatch) -> None:
    monkeypatch.setattr(files_av, "_defender_path", lambda: None)
    monkeypatch.setattr(files_av, "_clamav_path", lambda: None)
    assert files_av.detect_engine() == (None, None)
    assert files_av.is_available() is False


def test_detect_engine_prefers_defender_on_windows(monkeypatch) -> None:
    import sys

    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(files_av, "_defender_path", lambda: "X:\\fake\\MpCmdRun.exe")
    monkeypatch.setattr(files_av, "_clamav_path", lambda: "/usr/bin/clamscan")
    engine, exe = files_av.detect_engine()
    assert engine == files_av.ENGINE_DEFENDER
    assert exe.endswith("MpCmdRun.exe")


def test_detect_engine_falls_back_to_clamav_on_posix(monkeypatch) -> None:
    import sys

    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(files_av, "_clamav_path", lambda: "/usr/bin/clamscan")
    engine, exe = files_av.detect_engine()
    assert engine == files_av.ENGINE_CLAMAV
    assert exe == "/usr/bin/clamscan"
