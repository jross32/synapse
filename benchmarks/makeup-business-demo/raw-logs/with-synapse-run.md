# Run log — with Synapse

Chronological, real timestamps (UTC) from the actual run against the live daemon on `localhost:7878`.

1. `15:16:04` — `POST /api/v1/projects` registers `benchmark-with-synapse`, pointed at `apps/with-synapse`.
2. `15:16:49` — `POST /api/v1/agent-squads` creates squad `af5d822882da` ("Glow Studio build squad").
3. `15:17:16` — `POST /api/v1/agent-squads/{id}/work-items` creates work item `eef21d828e93` with the full app spec as `instructions_md`, `preferred_runtime: "claude"`.
4. `15:18:02` — `POST /api/v1/agent-work-items/{id}/launch`. PTY session `e992dda24eeb` spawns `claude.CMD --mcp-config <path>`.
5. **Failure.** Scrollback shows `'--mcp-config' is not recognized as an internal or external command, operable program or batch file.` — the child process exits (code 1) without ever starting Claude Code. Isolated with a second manual test (`POST /api/v1/pty` with `["claude.CMD", "--version"]`) — same failure. Confirmed: any multi-element `argv` for a `.CMD`-shimmed runtime fails to spawn correctly on this Windows machine. Filed as a follow-up bug (see `../methodology.md`).
6. `15:18:xx`–`15:29:00` — Diagnosed the bug by reading `daemon/synapse_daemon/routes_agent_squads.py` and `agent_squads.py` (`argv_for_runtime`, `_write_mcp_config`).
7. `~15:29:00` — Squad `af5d822882da` stopped via `POST /api/v1/agent-squads/{id}/stop` to clean up the dead work item (`stopped_sessions: 1`).
8. `15:29:03` — `POST /api/v1/projects/benchmark-with-synapse/workbench` (no `argv` override) spawns PTY session `2df6ce5ad237` with a single-element argv — works, Claude Code v2.1.185 loads normally ("Welcome back Justin!").
9. `15:29:xx` — First prompt-input attempt (`POST /api/v1/pty/{id}/input`, multi-line text + `\r`) is garbled — Claude Code reports "Your message appears to have been cut off."
10. `15:3x` — Second attempt (single-line, no embedded newlines) is also garbled/truncated.
11. `15:33:33` — Third attempt, wrapped in a bracketed-paste sequence (`\x1b[200~ ... \x1b[201~`) + `\r`, is accepted cleanly. **This is the real start time used for the benchmark.**
12. `15:33:33`–`15:39:02` — Claude Code works (visible via live scrollback: "Incubating", tool calls, token counter climbing to ~16.1k). Writes `index.html`, then `style.css`, then `script.js`.
13. `15:39:02` — Session returns to an idle prompt with a completion summary ("Done. Three files created...") and a self-reported "Worked for 3m 8s" line.
14. Attempted `/cost` for an exact token readout; PTY scrollback is a raw ANSI byte stream and couldn't be reliably re-parsed into a clean number after the fact, so the ~16.1k figure is the CLI's own live counter, not a `/cost` printout (see `../results/tokens/with-synapse.md`).
15. PTY session `2df6ce5ad237` closed (`DELETE /api/v1/pty/{id}`) for cleanup.

Everything above is reconstructable from the daemon's own audit log and PTY scrollback while the daemon is running; this file is the durable record now that it's been stopped.
