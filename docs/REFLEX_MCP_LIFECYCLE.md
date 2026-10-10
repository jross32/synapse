# Reflex MCP session lifecycle and release gate

## Failure and root cause

Synapse's generic `_stdio_mcp` launches and closes an MCP child for each tool call. Reflex's permission/control lease belongs to the child process. As a result, `request_control` succeeds within one call while the next `get_control_state` sees a brand-new process and `controlGranted=false`.

## Source fix

`daemon/synapse_daemon/mcp_connector.py` routes the `reflex` server to `_persistent_stdio_mcp`, which keeps one serialized, long-lived stdio child and its JSON-RPC reader/queue across requests. Other stdio MCP servers continue to use the stateless adapter. Real input still requires Reflex `request_control`; overlay, pause, and emergency stop remain the authority. Tool errors do not release an otherwise healthy lease; disconnected children are discarded.

## Tests and validation

Run `.venv\\Scripts\\python.exe -m pytest daemon/tests/test_reflex_persistent_proxy.py daemon/tests/test_mcp_stdio_handshake.py -q`. The former simulates grant -> subsequent read -> release across separate MCP requests; the latter checks handshake ordering. Compile with `.venv\\Scripts\\python.exe -m py_compile daemon/synapse_daemon/mcp_connector.py`.

The installed desktop executable serves its own **bundled** daemon (`%LOCALAPPDATA%\\Programs\\synapse\\resources\\daemon\\synapse-daemon.exe`). Source edits and tests **do not change this live packaged executable**. `npm run build:daemon` packages the current source, and `npm run dist` builds installers; publish and upgrade/restart through the desktop release workflow, preserving user data and concurrent managed processes. Do not replace the installed binary while it is running. Do not launch a source daemon onto port 7878 while the installed daemon owns that port.

## Acceptance gate (must pass before reporting fixed live)

1. Inspect the live daemon process owning port 7878, and confirm the upgraded binary/source build is the one actually running.
2. Run `synapse_call_mcp_tool(reflex, request_control)` with the visible takeover overlay, followed by a **separate** `get_control_state` call. Both must show the same active lease.
3. Perform an authorized, non-destructive action in the intended Chrome window, and verify the result independently.
4. Call `release_control`, and verify a separate `get_control_state` shows it is revoked.
5. Validate the ResellTogether authenticated listing form and original photo transport before the first item publication. Never claim a successful Depop listing without a verified public product URL; no CAPTCHA or security-check evasion.

## Limitations

The targeted source test is not a full end-to-end release or global test-suite pass. `mcp_connector.py` has concurrent edits; isolate its lifecycle hunk from unrelated changes before committing or building. A shared daemon restart/release must coordinate active workers and preserve their work, not force-close their processes.
