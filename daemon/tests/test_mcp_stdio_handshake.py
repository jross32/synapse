from __future__ import annotations

import queue
from types import SimpleNamespace

from synapse_daemon import mcp_connector


class _QueuedStdout:
    def __init__(self, lines: "queue.Queue[str | None]", state: dict[str, bool]):
        self._lines = lines
        self._state = state

    def __iter__(self):
        return self

    def __next__(self) -> str:
        line = self._lines.get(timeout=2)
        if line is None:
            raise StopIteration
        if '"id":1' in line or '"id": 1' in line:
            self._state["initialize_reply_delivered"] = True
        return line


class _QueuedStderr:
    def __iter__(self):
        return iter(())


class _ProtocolStdin:
    def __init__(self, lines: "queue.Queue[str | None]", state: dict[str, bool]):
        self._lines = lines
        self._state = state

    def write(self, payload: str) -> int:
        if '"method": "initialize"' in payload:
            self._lines.put('{"jsonrpc":"2.0","id":1,"result":{"protocolVersion":"2024-11-05"}}\n')
        elif '"method": "notifications/initialized"' in payload:
            assert self._state["initialize_reply_delivered"], "initialized sent before initialize reply"
            self._state["initialized"] = True
        elif '"method": "tools/call"' in payload:
            assert self._state["initialized"], "tools/call sent before initialized notification"
            self._lines.put('{"jsonrpc":"2.0","id":2,"result":{"content":[{"type":"text","text":"ok"}]}}\n')
        return len(payload)

    def flush(self) -> None:
        pass

    def close(self) -> None:
        pass


class _ProtocolProcess:
    def __init__(self):
        self.state = {"initialize_reply_delivered": False, "initialized": False}
        self.lines: "queue.Queue[str | None]" = queue.Queue()
        self.stdin = _ProtocolStdin(self.lines, self.state)
        self.stdout = _QueuedStdout(self.lines, self.state)
        self.stderr = _QueuedStderr()
        self.returncode = None

    def poll(self):
        return self.returncode

    def kill(self) -> None:
        self.returncode = -9
        self.lines.put(None)

    def wait(self, timeout=None):
        if self.returncode is None:
            self.returncode = 0
        return self.returncode


def test_stdio_mcp_waits_for_initialize_reply_before_tool_call(monkeypatch):
    process = _ProtocolProcess()
    monkeypatch.setattr(mcp_connector.subprocess if hasattr(mcp_connector, "subprocess") else __import__("subprocess"), "Popen", lambda *a, **k: process)
    monkeypatch.setattr(mcp_connector, "resolve_command", lambda command: command)

    server = SimpleNamespace(id="strict-mcp", command="fake-mcp", args=[], env={})
    result = mcp_connector._stdio_mcp(
        server,
        "tools/call",
        {"name": "browser_navigate", "arguments": {"url": "https://example.com"}},
        5,
    )

    assert result["content"][0]["text"] == "ok"
    assert process.state == {"initialize_reply_delivered": True, "initialized": True}

