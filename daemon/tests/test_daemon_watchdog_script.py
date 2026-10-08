"""Regression checks for the Synapse daemon watchdog recovery policy.

These tests intentionally inspect the PowerShell source rather than executing the
infinite watchdog loop. They pin the safety properties that prevent a degraded
MCP executor or low-disk condition from causing a daemon restart storm.
"""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
WATCHDOG = ROOT / "scripts" / "daemon-watchdog-v2.ps1"
WRAPPER = ROOT / "scripts" / "daemon-watchdog.ps1"


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_watchdog_separates_process_liveness_from_mcp_degradation() -> None:
    text = _text(WATCHDOG)

    assert "function Get-DaemonHealth" in text
    assert "BasicOk = $true" in text
    assert "McpOk = $mcpOk" in text
    assert "$consecutiveMcpFailures" in text
    assert "[int]$McpFailureThreshold = 6" in text
    assert "daemon is live; MCP degraded" in text
    assert "MCP recovered on final confirmation; cancelling daemon recovery" in text
    assert "if (Test-DaemonHealthy" not in text


def test_watchdog_protects_startup_and_low_disk_conditions() -> None:
    text = _text(WATCHDOG)

    assert "[int]$GraceSeconds = 120" in text
    assert "MCP is not ready during startup grace" in text
    assert "[int]$LowDiskFreeMB = 512" in text
    assert "suppressing restart because restart cannot repair disk exhaustion" in text
    assert "suppressing daemon restart until disk pressure is relieved" in text


def test_watchdog_logging_cannot_die_with_disk_pressure() -> None:
    text = _text(WATCHDOG)
    start = text.index("function Write-WatchdogLog")
    end = text.index("function Get-DaemonProcessId")
    body = text[start:end]

    assert "try {" in body
    assert "Add-Content" in body
    assert "} catch {" in body


def test_compatibility_wrapper_forwards_new_safety_controls() -> None:
    text = _text(WRAPPER)

    for name in (
        "McpFailureThreshold",
        "McpHealthTimeoutSeconds",
        "LowDiskFreeMB",
        "GraceSeconds",
    ):
        assert f"-{name}" in text
