# Synapse long-running command workflow

Use `synapse_run_command_async` for builds and test suites; poll with `synapse_get_command_result`. Keep `synapse_run_command` for short probes only (its synchronous deadline is 90 seconds).

If an AI connector does not advertise the async tools, inspect its published MCP tool list and reconnect or refresh the connector. Do not repeatedly launch the same build after a timeout: first inspect the process tree and logs.

Verification: run a short async command, poll for its exit code, then run a representative TypeScript build and Python test suite. Record elapsed time and outputs. Avoid terminating unrelated application processes.

Known limitations: job records are in memory and lost on daemon restart; no durable log streaming or concurrency budget yet.
