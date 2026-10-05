# Execution Continuity Contract

This reference defines how an autonomous Synapse worker survives uncertain model/tool execution windows without losing work, multiplying chats, or pretending one turn can run forever.

## Principle

Treat every model turn, tool window, browser worker, or remote execution lane as **interruptible**. Do not depend on discovering an exact platform timeout. The exact boundary can vary by runtime, task, tool latency, browser state, or product limits.

Use a soft local budget plus durable checkpoints.

Default soft budget for one worker turn:

- 15 minutes elapsed, or
- 12 material tool/actions,
- checkpoint recommended at 70% of either budget.

These are conservative defaults, not claims about ChatGPT product limits. A Foreman may tune them per runtime.

## Checkpoint triggers

Create a durable checkpoint when any of these occurs:

1. The soft time/action budget reaches 70%.
2. Before a long build, test suite, browser run, package operation, migration, or other action likely to outlive the remaining turn.
3. After a material source mutation that would be expensive to rediscover.
4. After successful verification.
5. Before switching projects, worktrees, or writer lanes.
6. Before handing work to another AI.
7. When tool/network/runtime instability suggests the current lane may disappear.
8. At the end of each verified iteration.
9. Immediately before a known batch/turn boundary.

A checkpoint is not a claim of completion. It is a durable resume point.

## Required checkpoint contents

A useful checkpoint records:

- run id and checkpoint sequence
- project id
- current iteration number and phase
- concise summary of what is true now
- exact next action
- pending actions / unresolved questions
- evidence already collected
- dirty/source state that matters to resumption
- current iteration contract when one is in progress
- soft execution-budget snapshot
- durable chat-home identity when a chat runtime is used
- whether the worker intentionally paused

## Resume protocol

A later AI must not start with a fresh brainstorm when a checkpoint exists.

Resume in this order:

1. Load Synapse orientation and project AI context.
2. Load `.synapse/autonomous-dev-loop.json`.
3. Read the latest checkpoint and its resume token.
4. Re-inspect repository status, active writers, and runtime health to make sure the checkpoint is still safe.
5. If the checkpoint points to an in-progress iteration, continue that iteration before selecting a new one.
6. Re-run only the minimum evidence needed to confirm the world did not materially change.
7. Continue from `next_step`.
8. Create a new checkpoint before the next risky boundary.

If repo/runtime reality contradicts the checkpoint, record the divergence and re-orient. Do not blindly replay stale actions.

## Durable chat policy

For chat-backed runtimes such as ChatGPT Web, the default is:

**one durable home conversation per canonical project checkout.**

Rules:

- Reuse the existing project conversation for later bounded iterations when the runtime supports it.
- In Synapse ChatGPT-Web launches, prefer `reuse_chat_from_work_item_id` when a healthy project home work item exists.
- A new work item does not require a new conversation.
- Create a replacement conversation only when the home chat is missing, corrupted, inaccessible, has reached a conversation-length limit, or the user explicitly requests separation.
- When replacing a home chat, persist the new home identity before retiring the old one.
- Temporary/failed worker records should be archived after handoff; real ChatGPT conversations should only be archived when they are positively identified as redundant and are not the project home chat.
- Never bulk-archive based only on titles or approximate matching.

The durable home identity may include:

- Synapse worker-chat id
- work-item id used as a reuse seed
- canonical conversation URL
- last successful use timestamp

## Chat cleanup safety

Chat cleanup is a separate operation from project iteration.

Before cleanup:

1. Stop launching new worker chats.
2. Let active workers finish or soft-stop them.
3. Select one preserved home chat per project.
4. Generate an explicit archive plan.
5. Archive Synapse worker records first when safe.
6. Archive real chat-provider conversations only from exact known identifiers/URLs and never touch the preserved home set.
7. Verify the remaining home set before re-enabling automatic iteration.

## Foreman behavior

A persistent Foreman/watchdog should implement continuity as a state machine:

`queued -> running -> checkpointing -> paused/resumable -> running -> verified -> handed_off`

The Foreman should never require one worker process or one chat turn to remain alive indefinitely. It should be able to recover after:

- tool-call timeout
- model-turn cutoff
- browser worker death
- machine/service restart
- network interruption
- stale heartbeat
- user-requested pause

Recovery should use the latest durable checkpoint and project home chat, not spawn a fresh conversation and start over.

## Truth rules

- `paused` means state was intentionally preserved for later continuation.
- `checkpointed` means a resume point exists, not that the iteration succeeded.
- `verified` requires objective evidence.
- `completed` must not be inferred from transport text, a disappeared worker, or an interrupted browser response.
- If a turn ends without a checkpoint, the next worker must re-inspect before changing anything.
