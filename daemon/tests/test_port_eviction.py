"""Startup port-eviction: a stale Synapse daemon on the bind port is killed so a fresh daemon can
start (root-cause fix for the "app stuck loading everything / WAN dead" symptom). The critical
safety property is that it NEVER kills an unrelated process that merely happens to hold the port.
"""

from __future__ import annotations

import socket
import subprocess
import sys
import time

from synapse_daemon.__main__ import _evict_stale_daemon_on_port


def test_evict_is_noop_on_free_port() -> None:
    # Grab a free port, release it, then evict -- must not raise.
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    _evict_stale_daemon_on_port(port)  # nothing there -> no-op, no exception


def test_evict_leaves_non_synapse_process_alone() -> None:
    # A non-synapse process holding a port (cmdline is `python -c ...`, not `synapse_daemon`).
    code = (
        "import socket,time;"
        "s=socket.socket();s.bind(('127.0.0.1',0));s.listen();"
        "print(s.getsockname()[1],flush=True);time.sleep(30)"
    )
    proc = subprocess.Popen([sys.executable, "-c", code], stdout=subprocess.PIPE, text=True)
    try:
        port = int(proc.stdout.readline().strip())
        time.sleep(0.2)  # let it reach LISTEN
        _evict_stale_daemon_on_port(port)  # must NOT kill it -- it is not a synapse daemon
        time.sleep(0.3)
        assert proc.poll() is None, "eviction wrongly killed a non-synapse process on the port"
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
