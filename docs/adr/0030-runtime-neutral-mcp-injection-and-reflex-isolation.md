# ADR-0030: Runtime-neutral MCP injection and per-worker Reflex isolation

- **Status:** accepted — targeted for v0.1.91
- **Date:** 2026-07-31
- **Deciders:** Justin (owner), Codex
- **Related:** ADR-0017 (MCP marketplace), ADR-0025 (role bindings), ADR-0027 (AI-drivable Synapse), Contracts #2, #4, #15, #25

## Context

Synapse stores one enabled MCP list and lets each squad role bind all, none, or a selected subset. The worker
launcher previously translated that list only into Claude's `--mcp-config` format. Codex workers therefore did
not receive Synapse-managed MCP servers unless the same server happened to be configured separately in the
user's global Codex settings. That violated Synapse's runtime-neutral promise and made behavior depend on which
AI happened to launch the task.

Reflex is a local Windows computer-control MCP. A single shared background copy with a fixed helper port would
mix control state between workers and create port collisions. Reflex's visible lease, pause, release, and
emergency-stop state must belong to one AI session only.

## Decision

1. **Translate at the runtime boundary.** The daemon keeps one canonical `McpServer` model. Claude receives an
   additive generated MCP JSON file; Codex receives supported one-launch `--config mcp_servers.*` overrides;
   GitHub Copilot CLI receives its session-only `--additional-mcp-config` file.
2. **Preserve role bindings.** `None` still means every enabled server, an empty list means none, and an explicit
   list selects only those ids for both Claude and Codex.
3. **Keep secrets out of process arguments.** Synapse places stored MCP environment values in the worker process
   environment. Codex receives only `env_vars` names; Copilot's generated file contains only supported `${NAME}`
   references. Conflicting values for one environment name fail before launch with a structured conflict instead
   of silently choosing one.
4. **Discover the first-party local Reflex checkout.** Production startup looks for a valid `reflex` package in
   the configured/local MCP checkout directory and reconciles it into the installed MCP list as enabled stdio.
5. **Launch Reflex per worker, on demand.** Reflex is not autorun and has no shared `REFLEX_HEALTH_PORT`. Each AI
   host starts its own stdio child when it uses the server, isolating leases, shutdown, and emergency state.
6. **Keep user-level compatibility.** Reflex remains registered in the user's durable Claude and Codex configs,
   while Synapse-launched workers receive the same capability from Synapse itself.

## Consequences

- A fresh Claude, Codex, or GitHub Copilot CLI worker launched by Synapse sees the same enabled MCP set without
  relying on global configuration.
- Multiple workers may use Reflex without sharing a process, port, input lease, or emergency-stop state.
- Stdio MCP startup remains lazy; “automatic” means automatically configured for the worker, not permanently
  running with standing computer-control authority.
- A future runtime needs one small translation adapter before Synapse can advertise managed MCP injection for it.
