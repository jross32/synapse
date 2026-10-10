# Disposable ChatGPT UI Worker Handoff

## Purpose
Allow a parent Synapse-driven AI to hand a bounded development iteration to a ChatGPT UI worker, including a temporary/disposable chat, while Synapse remains the durable source of truth.

## Parent pre-dispatch gate
Before creating a worker:
1. Run the fail-early supervisory loop through Define proof.
2. Save a durable checkpoint in project AI context: exact goal, current state, relevant files/diff, acceptance criteria, tests, known risks, forbidden scope, and next action.
3. Prefer resuming an existing healthy project ChatGPT UI worker when it reduces context loss. Create a new disposable worker when isolation is more valuable.
4. Verify the ChatGPT UI surface is already authenticated and the Synapse connector is callable. Never authenticate as the user.
5. Give the worker one bounded iteration, not an open-ended vague mission.

## Worker startup contract
The worker must:
- read Synapse project AI context before editing;
- inspect current git status/diff and baseline tests;
- discover applicable Synapse tools/skills before inventing replacements;
- perform a pre-mortem and state proof criteria;
- preserve unrelated/concurrent work;
- make scoped reversible changes;
- test through the real consumer where possible.

## Mandatory durable checkpoint
Before the disposable chat is allowed to be considered complete, it must write back to Synapse:
- files changed and why;
- commands/tests run and exact results;
- browser/user QA evidence when applicable;
- failures encountered and repairs;
- unresolved risks/assumptions;
- current git status/diff scope;
- exact recommended next step;
- whether its acceptance criteria passed.

A chat response saying "done" is not a handoff.

## Parent verification
The parent independently reads the actual diff and reruns critical tests. For UI work, consult Quality OS/browser evidence. Reject or repair unsupported completion claims.

## Fail-closed behavior
If the worker disappears, times out, loses connector access, or fails to write the mandatory checkpoint, mark the iteration incomplete. Recover from Synapse state and the working tree; do not infer success from the vanished chat.

## Temporary chat rule
Temporary mode is an execution surface, not memory. It is acceptable only when all durable project knowledge, evidence, and continuation state are committed back to Synapse before the worker is discarded.

## Loop continuation
After verified handoff, the parent returns to Inspect -> Reconsider rather than blindly launching the next planned task.
