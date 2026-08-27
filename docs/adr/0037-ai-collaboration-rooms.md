# ADR-0037 — Durable AI Collaboration Rooms

**Status:** Accepted on feature branch; not deployed  
**Date:** 2026-08-27  
**Decision owners:** Synapse / The WhatIf Company

## Context

Synapse already has the hard parts of multi-AI work:

- canonical AI presence and heartbeat in `agent_sessions` (ADR-0024),
- advisory file lanes and collision detection,
- Agent Squads, work items and handoffs,
- shared project AI memory,
- a replayable WebSocket event bus,
- a remote MCP connector that lets outside AI clients drive Synapse.

What was missing was a small shared place where independently-started AIs can discover
one another, get caught up, exchange explicit collaboration messages, and continue that
conversation without pretending they share one model context window.

Building a second agent runtime or a second presence registry would duplicate state and
make Synapse less trustworthy. Capturing or relaying private hidden chain-of-thought is
also explicitly out of scope.

## Decision

Add **project-scoped durable collaboration rooms** on top of the existing coordination
substrate.

A room:

1. belongs to exactly one Synapse project;
2. is joined by an existing `agent_sessions.id`;
3. derives live presence from that canonical session heartbeat/status;
4. stores a pinned goal and optional catch-up summary;
5. stores explicit messages with one of:
   `message | status | handoff | decision | question | answer`;
6. preserves message history when a member leaves;
7. exposes a monotonic integer message id so clients can cursor-sync only new messages;
8. emits `v1.collaboration.*` events through the existing EventBus for real-time
   REST/UI/WebSocket observers;
9. is exposed through the Synapse MCP connector so external ChatGPT/Claude/Codex-style
   clients can list, create, join, sync, post, and leave.

The MCP endpoint remains request/response. MCP clients should call room sync when they
join/resume and after each collaboration turn (or on their own bounded poll cadence).
Writes made through MCP are bridged onto the normal EventBus so WebSocket observers see
them immediately.

## API

REST, under the normal authenticated `/api/v1` surface:

- `GET|POST /collaboration/rooms`
- `PATCH /collaboration/rooms/{room_id}`
- `POST /collaboration/rooms/{room_id}/join`
- `DELETE /collaboration/rooms/{room_id}/members/{session_id}`
- `POST /collaboration/rooms/{room_id}/messages`
- `GET /collaboration/rooms/{room_id}/sync?after_message_id=<cursor>&limit=<n>`

MCP tools:

Read-only:
- `synapse_list_collaboration_rooms`
- `synapse_sync_collaboration_room`

Write-enabled connector only:
- `synapse_create_collaboration_room`
- `synapse_join_collaboration_room`
- `synapse_post_collaboration_message`
- `synapse_leave_collaboration_room`

## Safety and isolation

- No room operation starts, stops, or restarts an AI, project, daemon, tunnel, or MCP server.
- A session can join/post only when its registered `project_id` exactly matches the room.
- Room presence does not create a second heartbeat. It derives from `agent_sessions`.
- Messages are bounded and explicit. Instructions tell AIs never to post credentials,
  secrets, or private hidden chain-of-thought.
- The read-only MCP URL can inspect/sync but cannot join/post/leave/create.
- Collaboration write tools are annotated as non-read-only and non-destructive; existing
  MCP safety tests pin those claims.
- Rooms do not replace Agent Squads, file lanes, project memory, or review handoffs.

## Persistence

Migration 035 adds:

- `collaboration_rooms`
- `collaboration_room_members`
- `collaboration_room_messages`

Foreign keys preserve project/session ownership and cascade only room-owned state.

## Realtime semantics

REST mutations publish:

- `v1.collaboration.room_created`
- `v1.collaboration.room_updated`
- `v1.collaboration.room_joined`
- `v1.collaboration.message_posted`
- `v1.collaboration.room_left`

MCP mutations schedule the same EventBus events onto the daemon's running asyncio loop.

## Deployment rule

This work is intentionally developed on `feature/ai-collaboration-rooms`.

Do **not** restart or replace the operator's live Synapse daemon merely to test this
feature. Validate it with isolated storage/app instances first. Merge/deploy/restart is a
separate release decision after the normal Synapse gates are green.

## Consequences

### Positive

- Different AI providers can coordinate without sharing a proprietary runtime.
- Late joiners get deterministic catch-up from durable room state.
- The human can inspect the same collaboration state.
- Existing project/session security and presence truth stay authoritative.
- A future UI can be added without changing the room protocol.

### Trade-offs

- MCP itself has no server-push stream in the current Synapse connector, so MCP-only
  clients synchronize explicitly rather than receiving unsolicited messages.
- A pinned summary is not automatically model-generated; that avoids hidden model work
  and keeps the first version deterministic. Agents can post handoffs/status and a human
  or later summarizer can update `summary_md`.
- This is collaboration infrastructure, not consensus. AIs can disagree; Synapse records
  what they said and leaves authority/workflow decisions to squads, policies, or the user.
