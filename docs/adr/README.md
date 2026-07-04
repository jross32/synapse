# Architecture Decision Records (ADRs)

Each notable architectural decision in Synapse — especially anything that touches a design contract — gets an ADR in this folder.

## When to write one

Write an ADR when you:

- Need to break or amend a design contract in `AGENTS.md`.
- Add a new contract that didn't go through a `0.X.Y.5` review cycle.
- Choose between two non-obvious technical options and want the reasoning kept.
- Reverse an earlier decision.

If you find yourself debating an option for more than ten minutes, the answer is "write an ADR."

## File naming

`<NNNN>-<slug>.md` — e.g. `0001-fastapi-over-aiohttp.md`. Numbers are monotonic; never reuse.

## Template

```markdown
# ADR-NNNN: <Short decision title>

- **Status:** proposed | accepted | superseded by ADR-XXXX | deprecated
- **Date:** YYYY-MM-DD
- **Deciders:** <people>
- **Related contracts:** #N, #M

## Context

What problem are we trying to solve? What are the forces at play?

## Decision

What did we choose? Be specific.

## Consequences

### Positive
- ...

### Negative / trade-offs
- ...

### Follow-ups
- Code changes required: ...
- Docs to update: ...
- Migration plan (if breaks contract): ...
```

## Index

- [`0001-tool-marketplace.md`](./0001-tool-marketplace.md) — two-tier (declarative + curated handler) marketplace for distributing third-party + first-party tools through a registry, with hot install/uninstall and an in-app Browse / Install from URL flow. (Proposed, v0.1.19.)
- [`0020-ai-factory-case-engine.md`](./0020-ai-factory-case-engine.md) — keeps Synapse as the single runtime while splitting AI work into a native AI Factory authoring surface and a separate AI Operating System execution board, backed by structured advanced AI cases. (Accepted, v0.1.36-dev.)
- [`0023-ai-council-review.md`](./0023-ai-council-review.md) — "AI Council Review": a pre/post multi-perspective review gate (adaptive 2–10 reviewers, prioritized findings, synthesis) shipped as a launchable quick-action + workflow discipline for any AI, distinct from the case-engine `challenge` mode. (Accepted, v0.1.36.9.)
