"""Regression: Synapse must not discard Reflex safety state after every MCP call."""
import ast
from pathlib import Path
root=Path(__file__).resolve().parents[1]
source=(root/'synapse_daemon'/'mcp_connector.py').read_text(encoding='utf-8')
ast.parse(source)
assert '_persistent_stdio_mcp if server_id == "reflex" else _stdio_mcp' in source
assert '_persistent_stdio_sessions' in source
assert 'with _persistent_stdio_lock:' in source
assert 'proc.poll() is not None' in source
assert 'proc.kill()' in source
assert 'notifications/initialized' in source
assert 'except Exception:' in source
print('Reflex persistent session safety regression PASS')
