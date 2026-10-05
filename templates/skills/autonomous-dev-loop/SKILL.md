---
name: autonomous-dev-loop
description: Reusable model-independent autonomous software-development loop for Synapse projects. Use when the user asks an AI or team of AIs to keep improving, continue building, autonomously iterate, act like a software team, run a Foreman loop, or repeatedly choose and complete the next highest-value development step. The unit of success is a verified improvement to the running project, not activity, prose, or a diff.
---

# Autonomous Dev Loop

Autonomous Dev Loop turns Synapse from a collection of capable AI workers into a durable software-development loop. It is designed for real projects that need repeated, evidence-backed improvement without requiring the human to manually prompt every individual coding step.

The loop is **persistent across workers but bounded inside each worker**. A worker completes a small batch of verified iterations, records durable state and a handoff, then a Synapse Foreman/watchdog or later worker can resume from that exact state. This prevents context drift, infinite thrashing, overlapping writers, and "worked on it" claims without proof.

Read `references/workflow-contract.json` and `references/execution-continuity.md` before running the loop. Use `scripts/autonomous_dev_loop.py` to create and maintain project-local loop state, execution-budget checkpoints, and durable chat-home identity when practical.

## Core rule

The unit of progress is a **verified product improvement**.

Never count these as progress by themselves:
- a plan
- research with no decision
- code that was not exercised
- tests that do not cover the changed behavior
- a screenshot with no acceptance criterion
- a worker saying the task is done
- a large diff
- number of agents spawned

A successful iteration must connect a product hypothesis to objective evidence.

## Phase 0 — Bootstrap and ownership

Before modifying a project:

1. Load Synapse orientation/context.
2. Read the target project's shared AI context and project records/backlog.
3. Inspect repository status, active processes, current app health, and relevant existing skills.
4. Identify concurrent workers and their likely file/worktree ownership.
5. Establish the project goal. Prefer an explicit user goal; otherwise derive it from project description, accepted ADRs, current milestone, and backlog. Do not invent a new product direction merely to stay busy.
6. Create or resume `.synapse/autonomous-dev-loop.json`.
7. Use a unique `run_id` and record the current batch limit and failure budget.

If another writer owns the same files or worktree lane, do not race them. Choose a non-overlapping task, use an isolated worktree when appropriate, or stop as blocked.

## Execution continuity ? survive tool/model boundaries

Do not assume the current model turn or tool window will remain available until the work is complete. Exact product/runtime cutoffs can vary, so use a conservative local execution budget instead of trying to predict one universal timeout.

Default soft turn budget:
- 15 minutes elapsed, or
- 12 material tool/actions
- checkpoint recommended at 70% of either budget

At the beginning of a substantial worker turn, use `turn-start`. After meaningful tool/action batches, use `progress`. When `budget-status` or `progress` recommends a checkpoint ? or before any long/risky tool call ? persist a `checkpoint`.

Checkpoint before:
- long tests/builds/browser runs/package operations/migrations
- switching projects, worktrees, or writer lanes
- handing work to another AI
- likely tool/runtime instability
- a known turn/batch boundary

Checkpoint after:
- material source mutations that would be expensive to rediscover
- successful verification
- every verified iteration

A checkpoint must say what is true now, the exact next action, pending work, evidence already collected, relevant dirty/source state, current iteration state, budget snapshot, and durable chat-home identity. A checkpoint is a **resume point**, not a completion claim.

When a later AI resumes, it must load the checkpoint before choosing new work. If an iteration was in progress, continue it before brainstorming another iteration. Re-inspect repo/runtime/concurrent-writer reality first; if reality conflicts with the checkpoint, record the divergence and re-orient rather than blindly replaying stale steps.

Use Synapse thread tracking alongside checkpoints: `bootstrap -> begin turn -> heartbeat while long-running -> finish turn`. Thread tracking says which AI is alive; the checkpoint says exactly how another AI can continue if it is not.

## Durable chat and sidebar hygiene

For chat-backed runtimes, especially ChatGPT Web, default to **one durable home conversation per canonical project checkout**.

- A new bounded work item does not imply a new conversation.
- Reuse the healthy project home chat for later iterations. In Synapse ChatGPT-Web launches, prefer `reuse_chat_from_work_item_id` when a project home work item exists.
- Persist the home identity with `set-chat-home` or as part of a checkpoint.
- Create a replacement conversation only when the home chat is missing, inaccessible, corrupted, length-limited, or explicitly separated by the user.
- Persist the replacement before retiring the old conversation.
- Queue redundant chats with `retire-chat`; never retire the current home chat.
- Archive real provider conversations only from exact known identifiers/URLs, never approximate titles.
- During bulk cleanup, stop new chat launches first, preserve one home per project, generate an explicit archive plan, then verify the remaining home set before re-enabling automation.

Read `references/execution-continuity.md` for the full checkpoint/resume and cleanup contract.

## Phase 1 — Observe the real product

Gather enough evidence to choose the next iteration intelligently. Depending on the project this may include:
- tests and build status
- app/server health
- browser or desktop interaction
- desktop/mobile UI state
- logs and recent failures
- issue/backlog state
- performance metrics
- screenshots or playtest evidence
- git diff/history
- user-visible friction
- data quality/provenance
- current milestone and unfinished acceptance criteria

Prefer direct observation over assumptions from source code.

## Phase 2 — Prioritize exactly one bounded iteration

Generate a short candidate set, then choose one iteration using this order:

1. broken critical path / regression / data-truth issue
2. blocker preventing verification or shipping
3. incomplete core product loop
4. high-leverage usability, retention, reliability, performance, or correctness improvement
5. validated user-facing feature that advances the declared milestone
6. cleanup only when it materially reduces risk or unlocks future work

Use value, confidence, effort, risk, and reversibility. Do not start several speculative implementations merely because multiple agents are available.

Write an iteration contract containing:
- hypothesis: what should improve and why
- bounded scope
- acceptance criteria
- proof plan
- files/surfaces likely to change
- risk level
- rollback/recovery path when relevant

## Phase 3 — Route specialists without creating writer chaos

Synapse squads may be used when specialization helps.

Good parallel work:
- researcher investigates an API or competitor pattern
- reviewer inspects a proposed change
- tester designs adversarial cases
- UX worker evaluates the running screen

Default writer rule:
**one bounded writer lane owns overlapping source at a time.**

A supervisor/Foreman coordinates the loop. Specialists return evidence and recommendations to the owning iteration. Avoid delegating vague "improve the app" prompts to many workers concurrently.

Use installed Synapse skill packs when the iteration matches them. Examples:
- UI Forge for substantial UI/UX work
- Game Dev Studio for Unity/game work
- Super Internet Digger for deep source/reference research
- FirstRun Studio for onboarding/auth activation UX
- Stock Hunter for equity-research product logic

## Phase 4 — Implement the smallest coherent slice

Implement the iteration contract, preserving working behavior outside scope.

Rules:
- inspect before editing
- prefer project-native architecture and conventions
- do not sweep unrelated dirty changes
- keep diffs reviewable
- do not silently relax tests, quality gates, benchmark thresholds, or product-truth constraints to manufacture a pass
- do not fabricate unavailable data
- do not bypass auth/security controls for convenience
- record material architectural/product decisions in project memory or ADRs

## Phase 5 — Verify fail-closed

Verification must be proportional to the changed behavior.

Use the strongest available proof, such as:
- focused unit/integration tests
- full relevant suite
- lint/type/static checks
- successful build/package
- API smoke test
- real browser interaction
- mobile + desktop checks
- desktop application interaction through Reflex
- gameplay/playtest evidence
- performance benchmark
- screenshot/trace/log evidence
- data/provenance checks

If a verification gate fails, the iteration is **not improved**. Repair within the bounded iteration if the cause is understood. Otherwise record failed/blocked honestly and consume the failure budget.

Do not reinterpret a failing requirement as optional just to continue.

## Phase 6 — Independent review

Before accepting a meaningful iteration, review it with a bug-finding mindset. A separate reviewer is preferred for high-impact changes.

Ask:
- Did behavior actually improve?
- Did we regress another path?
- Are tests meaningful or merely green?
- Did we preserve data truth/security/auth?
- Does the running product match the acceptance criteria?
- Did scope drift?
- Is there a simpler or safer correction required before accepting?

## Phase 7 — Record durable iteration state

Every iteration must leave enough state that a different model can continue safely.

Update project-local loop state and append a history record containing:
- iteration number
- hypothesis
- scope
- implementation summary
- outcome: `improved`, `neutral`, `failed`, or `blocked`
- exact evidence
- files/surfaces touched
- commit/tag/worktree info when relevant
- failures or residual risks
- highest-value next step

Also capture a concise Synapse project AI-context note for material work. Add unresolved follow-ups to the backlog instead of burying them in prose. Before a risky execution boundary, create a durable checkpoint. `finish` automatically records an iteration-complete checkpoint, but mid-iteration work still needs explicit checkpoints when the execution budget or tool risk warrants it.

## Phase 8 — Decide whether to continue

Continue automatically only if all of these are true:
- the declared project goal is not yet satisfied
- a materially connected next iteration exists
- no user decision, credential, payment, legal acceptance, destructive production action, or other consequential authorization is required
- the failure budget is not exhausted
- no unresolved overlapping writer exists
- verification remains trustworthy
- the current worker's batch limit has not been exceeded

Default batch: **6 iterations**.
Default consecutive failure budget: **2**.

At the batch boundary, do not pretend the current chat can run forever. Persist an execution checkpoint, finish the Synapse thread turn cleanly, and hand off to a persistent Foreman/watchdog or continuation work item. For chat-backed runtimes, reuse the same project home conversation instead of spawning a fresh chat. The next worker resumes the same run/checkpoint instead of starting a new brainstorm.

## Stop and escalation conditions

Stop or pause the loop when:
- the user tells it to pause/stop
- an action needs a secret, payment, external account approval, legal acceptance, production deletion, or similar human authorization
- two consecutive iterations fail or produce no measurable improvement by default
- the baseline is too broken/ambiguous to attribute changes safely
- a concurrent writer owns the needed lane
- objective evidence contradicts the claimed improvement
- the only available work is unrelated polish or scope expansion
- a recurring infrastructure failure prevents trustworthy verification

When stopped, preserve state and state the exact blocker plus the safest next action.

## Continuous mode / Foreman

For true autonomous continuation, use a persistent Synapse Foreman/watchdog outside any single model turn.

The Foreman should:
1. read loop state and latest execution checkpoint
2. resolve the canonical project checkout and durable chat home
3. launch one bounded work item for the current iteration/batch, reusing the project home chat when supported
4. observe worker heartbeat/completion and execution-budget checkpoints
5. require a structured handoff and evidence
6. reconcile stale/failed workers without counting disappearance/transport text as success
7. update project state and retirement queue
8. launch the next continuation only when `can_continue` is true
9. stop on the contract's hard-stop conditions

Do not equate "continuous" with uncontrolled concurrency. Continuous mode means **serial evidence-backed progress with recoverable handoffs**.

## Truthful completion language

Use:
- "Iteration 4 improved X; proof: ..."
- "Iteration failed; the previous behavior remains the accepted baseline."
- "Blocked on human authorization for ..."
- "Batch complete; durable state says the next iteration is ..."

Avoid:
- "fully autonomous now" unless a persistent Foreman is actually active
- "fixed" without proof
- "production-ready" unless release gates prove it
- "better" when only source changed

## Recommended first activation

For an existing project, the first activation should normally:
1. bootstrap state and start a soft execution budget
2. establish baseline health
3. identify the top three candidate iterations
4. execute the single highest-value bounded iteration
5. verify and record it
6. continue through up to six verified iterations
7. checkpoint the exact resume point and leave a continuation handoff if the project still has valuable work
8. preserve/reuse the project's durable chat home for the next bounded worker

The goal is not to maximize iteration count. The goal is to make the project measurably better while preserving enough truth and state for another AI to continue safely.
