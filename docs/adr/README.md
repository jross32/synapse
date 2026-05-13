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

_No ADRs yet. The first one will likely be `0001-sqlite-vs-postgres.md` or `0001-electron-bundling-strategy.md` during Milestone B/J._
