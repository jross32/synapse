"""Contract #27 — CLI surface."""

from __future__ import annotations

import io
from contextlib import redirect_stdout

import pytest

from synapse_daemon.cli import build_parser, main


def test_parser_has_all_required_commands() -> None:
    parser = build_parser()
    actions = {a.dest for a in parser._actions}
    assert "command" in actions

    # Inspect the subparsers action to get registered commands.
    sub_action = next(a for a in parser._actions if a.dest == "command")
    choices = set(sub_action.choices)  # type: ignore[arg-type]
    assert choices == {"status", "list", "start", "stop", "logs", "snapshot", "restore", "doctor"}


def test_no_args_prints_help_and_succeeds(capsys: pytest.CaptureFixture[str]) -> None:
    rc = main([])
    out = capsys.readouterr().out
    assert rc == 0
    assert "synapse" in out.lower()


def test_doctor_runs_without_daemon(capsys: pytest.CaptureFixture[str]) -> None:
    rc = main(["doctor"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "python" in out


def test_start_requires_project_id() -> None:
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["start"])  # missing project_id


def test_version_flag(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert "synapse" in out


# ── v0.1.36: CLI is no longer a placeholder ──────────────────────────


def test_cli_http_token_env_precedence(monkeypatch: pytest.MonkeyPatch) -> None:
    """SYNAPSE_TOKEN env var wins over the disk file."""

    from synapse_daemon.cli_http import discover_token

    monkeypatch.setenv("SYNAPSE_TOKEN", "from-env-12345")
    monkeypatch.setenv("SYNAPSE_DATA_DIR", "/does-not-exist")
    assert discover_token() == "from-env-12345"


def test_cli_http_token_from_disk(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Falls back to <data-dir>/auth-token when env is unset."""

    from synapse_daemon.cli_http import discover_token

    monkeypatch.delenv("SYNAPSE_TOKEN", raising=False)
    monkeypatch.setenv("SYNAPSE_DATA_DIR", str(tmp_path))
    (tmp_path / "auth-token").write_text("from-disk-7777", encoding="utf-8")
    assert discover_token() == "from-disk-7777"


def test_cli_http_no_token_returns_none(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from synapse_daemon.cli_http import discover_token

    monkeypatch.delenv("SYNAPSE_TOKEN", raising=False)
    monkeypatch.setenv("SYNAPSE_DATA_DIR", str(tmp_path))
    assert discover_token() is None


def test_cli_http_request_without_token_raises(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from synapse_daemon.cli_http import SynapseCliError, request

    monkeypatch.delenv("SYNAPSE_TOKEN", raising=False)
    monkeypatch.setenv("SYNAPSE_DATA_DIR", str(tmp_path))
    with pytest.raises(SynapseCliError, match="No auth token"):
        request("GET", "/health")


def test_cli_http_timeout_is_reported_cleanly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from synapse_daemon import cli_http

    monkeypatch.setenv("SYNAPSE_TOKEN", "timeout-token-123")

    def _timeout(*_args, **_kwargs):
        raise TimeoutError("timed out")

    monkeypatch.setattr(cli_http.urllib_request, "urlopen", _timeout)
    with pytest.raises(cli_http.SynapseCliError, match="Could not reach daemon"):
        cli_http.request("GET", "/health", timeout=0.01)


def test_cli_doctor_reports_token_state(
    tmp_path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`doctor` should surface whether a token was found (without
    printing it whole)."""

    monkeypatch.setenv("SYNAPSE_TOKEN", "abcdefghijklmnopqrstuvwxyz")
    # Point the daemon URL somewhere closed so reach FAILs predictably.
    monkeypatch.setenv("SYNAPSE_DAEMON_BASE", "http://127.0.0.1:1")
    main(["doctor"])
    out = capsys.readouterr().out
    assert "token" in out
    assert "abcdefgh" in out  # first 8 chars only
    assert "reach" in out
    assert "FAIL" in out
