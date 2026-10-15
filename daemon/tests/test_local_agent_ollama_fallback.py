"""Ollama CPU fallback for a failed GPU inference endpoint."""
import asyncio
import io
import json
from unittest.mock import patch
from synapse_daemon import local_agent


class Response:
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False
    def read(self):
        return json.dumps({"message": {"content": "READY"}}).encode()


def test_failed_primary_retries_cpu_fallback(monkeypatch):
    monkeypatch.setenv("SYNAPSE_OLLAMA_FALLBACK_URL", "http://127.0.0.1:11555")
    seen = []
    def fake_open(request, timeout):
        seen.append(request.full_url)
        if request.full_url.startswith("http://127.0.0.1:11434"):
            raise TimeoutError("GPU unavailable")
        return Response()
    with patch.object(local_agent.urllib.request, "urlopen", side_effect=fake_open):
        result = asyncio.run(local_agent._chat("gemma3:270m", [{"role":"user","content":"READY"}], [], 1024, 45))
    assert result["message"]["content"] == "READY"
    assert seen == ["http://127.0.0.1:11434/api/chat", "http://127.0.0.1:11555/api/chat"]
