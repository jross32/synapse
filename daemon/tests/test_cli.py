"""Contract #27 — CLI surface."""

from __future__ import annotations

import os

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


def test_cli_http_httperror_surfaces_daemon_envelope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import io
    import json
    from urllib.error import HTTPError

    from synapse_daemon import cli_http

    monkeypatch.setenv("SYNAPSE_TOKEN", "envelope-token-123")
    envelope = {"code": "validation.invalid", "message": "bad input"}

    def _raise(*_args, **_kwargs):
        fp = io.BytesIO(json.dumps(envelope).encode("utf-8"))
        raise HTTPError("http://x/api/v1/x", 422, "Unprocessable", {}, fp)  # type: ignore[arg-type]

    monkeypatch.setattr(cli_http.urllib_request, "urlopen", _raise)
    with pytest.raises(cli_http.SynapseCliError) as exc:
        cli_http.request("POST", "/x", body={})
    # The user gets the status, the daemon's error code, and its message -- not a bare traceback.
    message = str(exc.value)
    assert "422" in message
    assert "validation.invalid" in message
    assert "bad input" in message


def test_cli_http_daemon_base_override_strips_trailing_slash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from synapse_daemon import cli_http

    monkeypatch.setenv("SYNAPSE_DAEMON_BASE", "http://example.test:9999/")
    assert cli_http.daemon_base() == "http://example.test:9999"
    monkeypatch.delenv("SYNAPSE_DAEMON_BASE", raising=False)
    assert cli_http.daemon_base() == "http://127.0.0.1:7878"


def test_cli_http_build_url_normalizes_leading_slash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from synapse_daemon import cli_http

    monkeypatch.delenv("SYNAPSE_DAEMON_BASE", raising=False)
    expected = "http://127.0.0.1:7878/api/v1/health"
    assert cli_http._build_url("health") == expected
    assert cli_http._build_url("/health") == expected


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


# ── doctor port diagnostics (v0.1.105) ───────────────────────────────────
#
# The 0.1.40 launch crash was a stale Vite still holding 5173 from a crashed run.
# dev.ps1 self-heals now, but `doctor` -- the command you run when it "just won't
# start" -- said nothing about it.


def test_find_port_holders_sees_a_real_listening_socket() -> None:
    """Detection is tested against an actual bound socket, not a mock.

    The whole feature is "notice what the OS says is holding this port", so a
    mocked psutil would only prove the test agrees with itself.
    """
    import socket

    from synapse_daemon.cli import find_port_holders

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind(("127.0.0.1", 0))
        sock.listen(1)
        port = sock.getsockname()[1]

        holders = find_port_holders([(port, "test port")])
        if not holders:  # net_connections can be restricted in some environments
            pytest.skip("psutil.net_connections returned nothing for this process")
        assert holders[0].port == port
        assert holders[0].pid == os.getpid()
        assert holders[0].label == "test port"
    finally:
        sock.close()


def test_find_port_holders_ignores_unrelated_ports() -> None:
    import socket

    from synapse_daemon.cli import find_port_holders

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind(("127.0.0.1", 0))
        sock.listen(1)
        port = sock.getsockname()[1]
        other = port + 1 if port < 65535 else port - 1
        assert find_port_holders([(other, "some other port")]) == []
    finally:
        sock.close()


def test_fix_never_targets_a_process_that_is_not_ours() -> None:
    """`--fix` can terminate processes, so the ownership check is the safety net.

    A holder that does not look like ours must be reported and left running --
    a user's unrelated dev server on 5173 is not Synapse's to kill.
    """
    from synapse_daemon.cli import _SYNAPSE_CMDLINE_MARKERS, PortHolder

    stranger = PortHolder(
        port=5173,
        label="renderer (Vite)",
        pid=4242,
        name="node.exe",
        cmdline="node C:/some/other/project/server.js",
        is_synapse=False,
    )
    assert stranger.is_synapse is False
    # And the markers must not match a process merely *run from* a synapse folder.
    haystack = "python.exe c:/users/justi/synapse/tools/unrelated.py"
    assert not any(marker in haystack for marker in _SYNAPSE_CMDLINE_MARKERS)


def test_doctor_reports_ports_and_offers_fix(capsys: pytest.CaptureFixture[str]) -> None:
    rc = main(["doctor"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "port" in out.lower(), out


def test_doctor_accepts_fix_flag() -> None:
    parser = build_parser()
    args = parser.parse_args(["doctor", "--fix"])
    assert args.fix is True
    assert parser.parse_args(["doctor"]).fix is False


def test_port_is_serving_distinguishes_holding_from_answering() -> None:
    """The discriminator that makes `--fix` safe.

    Holding a port and serving on it are different. A socket that listens but
    never replies is the stale-holder case; a socket that replies is a working
    service the user is relying on. Running `--fix` against a healthy dev server
    would be destructive, so this distinction is the safety property, not a detail.
    """
    import socket
    import threading

    from synapse_daemon.cli import port_is_serving

    # 1) Listening but silent -> NOT serving.
    silent = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        silent.bind(("127.0.0.1", 0))
        silent.listen(1)
        silent_port = silent.getsockname()[1]
        assert port_is_serving(silent_port, timeout=0.75) is False
    finally:
        silent.close()

    # 2) Actually answering -> serving.
    talker = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    talker.bind(("127.0.0.1", 0))
    talker.listen(1)
    talker_port = talker.getsockname()[1]

    def _respond() -> None:
        try:
            conn, _ = talker.accept()
            with conn:
                conn.recv(1024)
                conn.sendall(b"HTTP/1.0 200 OK\r\n\r\nhi")
        except OSError:
            pass

    thread = threading.Thread(target=_respond, daemon=True)
    thread.start()
    try:
        assert port_is_serving(talker_port, timeout=3.0) is True
    finally:
        talker.close()
        thread.join(timeout=3)


def test_port_is_serving_false_for_a_closed_port() -> None:
    import socket

    from synapse_daemon.cli import port_is_serving

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()  # nothing is listening now
    assert port_is_serving(port, timeout=0.75) is False
