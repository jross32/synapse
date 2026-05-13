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
