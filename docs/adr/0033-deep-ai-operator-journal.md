# ADR-0033: Deep AI operator journal

- **Status:** accepted — shipping in v0.1.93
- **Date:** 2026-08-01
- **Deciders:** Justin (owner), Codex
- **Related:** ADR-0024 (coordination), ADR-0025 (squads), ADR-0028 (AI Activity), ADR-0030 (runtime-neutral MCP injection), Contracts #2, #4, #5, #7, #11, #13, #22, #23, #24, #25

## Context

The first Live View proved that Synapse can number connected AIs, show connection health, persist milestones, stream terminal output, and preview a running app. It did not yet answer the operator's deeper questions: What is the AI focused on now? Why did it choose this direction? What alternatives did it consider? Which squad members are running? Which MCP server was attached or used, and with what authority?

The original renderer also subscribed to several global WebSocket events without fully correlating them to the selected session. That could make unrelated output appear in the wrong session story. A visually impressive feed that mixes identities is not trustworthy.

Models should provide useful explanations, but Synapse must not claim to reveal private hidden chain-of-thought. It must also keep credentials, auth tokens, secret environment values, and raw sensitive tool output out of an operator feed.

## Decision

1. **Persist a structured operator journal.** Migration 029 adds bounded entries for category, state, title, deliberate summary, session, squad, work item, MCP server, tool, authority, source, and UTC time. Categories cover status, plan, reasoning summary, idea, decision, action, evidence, search, blocker, squad, MCP, tool, and result.
2. **Expose one AI-drivable reporting endpoint.** `POST /api/v1/activity/sessions/{session_id}/events` validates the registered session and any linked project/squad/work-item/MCP identities, audits the mutation, persists it, and publishes `v1.activity.journaled`.
3. **Make current focus automatic.** A changed `last_intent` on a coordination heartbeat creates a status journal entry. Heartbeat events now carry the complete session shape so clients update immediately; session release is also journaled.
4. **Project daemon-owned squad truth.** Squad creation, work-item lifecycle, worker launch, and MCP attachment become durable journal receipts. Worker launch events carry the exact enabled, role-scoped MCP IDs. The UI does not infer that an MCP call happened merely because a server was attached.
5. **Use two operator modes.** **Deep View is the default** and includes detailed deliberate summaries, decisions, alternatives, assumptions, evidence, ideas, tools, MCP receipts, squads, and correlated terminal output. **Summary View** keeps current focus, major decisions/actions, blockers, squads/MCPs, and outcomes. The per-window preference persists.
6. **Name the boundary honestly.** Deep View can be highly detailed, but it never claims to expose hidden model chain-of-thought. Generated worker guidance explicitly forbids secrets, credentials, tokens, private hidden reasoning, and raw sensitive tool output. The UI repeats this boundary.
7. **Correlate before displaying.** Session notifications require a matching `session_id`; PTY output requires the selected coordination thread or one of its project squad work-item PTYs; journal events require the selected session or one of the detail view's squad IDs. Lifecycle events trigger targeted refreshes rather than becoming unverified timeline prose.
8. **Show squads and MCPs as first-class state.** A collapsible squad inspector shows the real squad goal, work items, role, state, chosen runtime, and token rollup. Recent MCP/tool identities appear in the session header and receipts state `observe`, `control`, or `execute` authority in text.
9. **Keep local MCP startup isolated.** Enabled stdio servers, including Reflex, are presented as **Auto-attached · starts per AI**. Synapse continues to create isolated per-worker MCP children instead of one shared fixed-port controller. HTTP services such as Web Scraper keep their daemon-level autorun path.

## Consequences

- The operator can watch a detailed, durable explanation of work instead of interpreting uncorrelated terminal noise.
- Summary View remains calm when Deep View is too verbose; Deep View is the initial default as requested.
- Claude, Codex, and Copilot workers receive the same Live View reporting instructions through the generated role prompt and discover the endpoint through `/api/v1/ai/context`.
- Direct stdio MCP traffic is not globally interceptable by Synapse without changing the MCP transport. Attachment is automatic and provable; actual use is shown only when the AI deliberately reports it or when Synapse owns the call path. A future opt-in proxy could add automatic per-call receipts after its credential, performance, and consent risks are reviewed.
