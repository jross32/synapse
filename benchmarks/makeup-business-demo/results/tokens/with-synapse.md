# Tokens & time — with Synapse

| Metric | Value | Source |
|---|---|---|
| Active working time | **3m 8s (188s)** | Claude Code CLI's own self-reported "Worked for..." line, read from the live terminal session |
| Wall-clock (prompt accepted → idle) | 5m 29s (329s) | Measured externally (includes polling granularity + initial "thinking" time before tool calls began) |
| Peak live token counter | **~16.1k tokens** | Claude Code CLI's own live token indicator, last observed value before completion |
| Files produced | 3 (`index.html`, `style.css`, `script.js`) | Filesystem |
| Runtime | Claude Code CLI, same account/model as the baseline | Synapse project workbench launch |

**On precision:** an explicit `/cost` query was sent to the session for an exact total-token
readout, but the raw PTY scrollback (a byte stream of terminal control codes, not clean text)
could not be reliably parsed back into a single clean number after the fact — so the number
above is the CLI's own live indicator rather than a `/cost` printout. It is a real,
CLI-reported figure, not an estimate computed by us, but treat the ones-place as approximate.

Real Synapse project + real audit trail: project `benchmark-with-synapse`, PTY session
`2df6ce5ad237`, launched via `POST /api/v1/projects/{id}/workbench` (see `../methodology.md`
for why the workbench launcher was used instead of the full Agent Squads launch path, and the
real bug that caused that).
