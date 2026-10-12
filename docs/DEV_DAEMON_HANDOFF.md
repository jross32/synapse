# Development daemon controlled handoff

The development app and the installed daemon can independently own TCP listeners on port 7878. In the observed October 12 2026 session, the source checkout had frontend/lockfile 0.2.218 and Python daemon 0.1.209 while both an installed frozen daemon and Python development daemon listened on different interfaces.

## Safety gates
- scripts/dev-daemon-preflight.ps1: read-only PID and source-version diagnosis. Stops developer launch before it forcefully takes an occupied port.
- scripts/dev-daemon-handoff.ps1 -Action Inspect: reports source versions (Electron package, lockfile, Python package and __version__), local interpreter and running listeners.
- scripts/dev-daemon-handoff.ps1 -Action Stage: only copies candidate source to isolated local staging after ALL four version declarations agree. Does not touch database, processes, MCP URL or installed binaries.
- No -Apply action: live daemon takeover MUST be implemented later with an independently owned supervisor capable of draining commands, backing up data, verifying the target's actual health, switching bindings, and rollback. In particular, a remote chat calling its own live connector cannot safely kill the process carrying that connector.

## Verify before a switching implementation
1. Reconcile the Python daemon package and app versions from a source-reviewed release commit, rather than bumping the version string of old code. Verify generated bindings, API contract compatibility, migrations and tests.
2. Resolve dual listeners and identify the listener serving the permanent Cloudflare MCP tunnel. Ensure one service owns the account and device route without rotating its URL.
3. Create an independently supervised stop/start controller that survives the old daemon exiting, with job drain, port handoff and rollback.
4. Ensure both computers register once and can sync account preferences; project-file replication requires its own transport implementation and end-to-end proof.

A successful staging step is NOT proof of synchronization, a successful upgrade or uninterrupted MCP availability.
