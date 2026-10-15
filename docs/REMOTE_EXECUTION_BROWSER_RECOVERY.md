# Synapse Remote Execution and Browser Recovery

Operational instructions for future AI workers, not proof of permanent infrastructure repair.

## Remote tool failure, 502 or internal error
1. Read Synapse context before operations. Never rotate the MCP URL, secrets, tunnel or restart the daemon as a first response.
2. Run a short, read-only probe such as Write-Output ok with a 10-second timeout. A successful probe means remote execution is currently reachable.
3. Use the asynchronous command executor for browser tests, builds, and long scripts. Poll the returned job ID rather than blocking an HTTP request beyond the tunnel/proxy timeout.
4. If polling returns an internal error, retry a short probe, then poll the SAME job ID. Never repeat a side-effecting command without checking whether it already ran. An expired or unknown job ID after daemon restart does not prove execution failed.
5. Separate large edits from execution. Syntax-check with node --check and python -m py_compile before running tests.
6. Classify failures separately: transport, test-harness, and application. Capture exit code, stdout, stderr, browser locator and workspace state. Do not claim resolution without a passing rerun.

## Browser lifecycle
- Use a fresh temporary workspace per viewport. The desktop run mutates quote status; reusing that state on mobile makes the approval button disappear and causes a misleading timeout.
- Trace the exact quote, job and invoice IDs. Schedule and complete the same job; then find its generated invoice using the invoice job_id relationship. Never use an arbitrary first invoice as proof.
- Assert the browser UI, authenticated workspace state, job and invoice statuses, and no page JavaScript errors.
- Follow-up drafts are review-only: outbound_enabled must remain false. No customer messages or charges are authorized by these tests.
- Localhost Chromium tests do not prove Stripe sandbox, packaging, production authentication, or rollback readiness.

## Reproducible entrypoints
Run scripts/run-fast-money-browser-isolated.py from repository root via asynchronous remote execution. VIEWPORT is a JSON object containing width and height; use a separate invocation for each viewport. Browser assertions live in scripts/verify-fast-money-workflow.cjs.

## Git safety
Other workers share this worktree. Stage, commit and push only exact verified paths; never broad-add, reset or overwrite concurrent changes.
