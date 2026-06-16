"""Shared pytest fixtures for the daemon test suite."""

from __future__ import annotations

import pytest

from synapse_daemon import files_av
from synapse_daemon.files_av import SCAN_CLEAN, ScanResult


@pytest.fixture(autouse=True)
def _mock_av_clean(monkeypatch: pytest.MonkeyPatch) -> None:
    """Default behaviour: pretend every file is AV-clean.

    The real engine (Defender on Windows, ClamAV on POSIX) is slow and
    can vapourise quarantine files via real-time protection mid-test --
    neither makes for stable test runs. Tests that specifically want to
    exercise the blocked / unavailable paths override this with their
    own monkeypatch.

    Patches BOTH the source module and the route's re-export so any call
    site is covered.
    """

    async def _fake_scan(_path) -> ScanResult:  # noqa: ANN001
        return ScanResult(result=SCAN_CLEAN, engine="defender")

    monkeypatch.setattr(files_av, "scan_file", _fake_scan)
    # routes_files imports scan_file at module load -- patch the bound name too.
    from synapse_daemon import routes_files

    monkeypatch.setattr(routes_files, "scan_file", _fake_scan)
