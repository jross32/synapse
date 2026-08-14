# Phase C: which reliability changes actually earned their place

Four changes were proposed to make the local tier build a large stateful module reliably.
Each was built as a **switch** rather than a rewrite, so every arm below is the same code
with a different config — editing source between arms is how a comparison quietly stops
being one.

Subject: the `storage` piece of `webapp-auth-crud` — nine functions across users, sessions
and records. `qwen2.5-coder:7b` on a 6 GB card unless stated. Four runs per arm, sequential,
because two 7B generations at once would measure contention rather than prompts.

## Result

| Arm | Piece size | Targeted repair | Model's test | All pieces pass | Median run |
|---|---|---|---|---|---|
| `baseline` | 9 functions | off | **is the gate** | **0/4** | 2310 s |
| `both` | 9 functions | on | advisory | **0/4** | 594 s |
| `deepseek` | 9 functions | on | advisory | **0/4** | 732 s |
| `split-plain` | 3 × 3 functions | off | **is the gate** | **0/2** † | 3132 s |
| **`split`** | **3 × 3 functions** | **on** | **advisory** | **4/4** | **244 s** |

† `split-plain` is **two runs** so far, not four — the remaining two are still going at
~52 minutes each. All four of its pieces failed on both runs, against 12/12 passing across
the `split` arm, which is a wide enough gap to report. It is written as `0/2` rather than
rounded up to `0/4`, because a number nobody measured is the thing this whole benchmark
keeps getting caught by. This line will be updated when the arm finishes.

## The finding is a conjunction, not a winner

The first four arms all fail. Only the last passes, and it is the only one that combines
**small pieces** with **the model's own test demoted to advisory**.

- Splitting alone does not work. `split-plain` is the split blueprint with the other
  switches off, and every piece failed on both runs measured so far — the arm exists precisely
  because "split passed 4/4" would otherwise have been a claim about three changes at once,
  and it would have been the wrong claim.
- The switches alone do not work either. `both` is the monolith with both switches on: 0/4.

So the honest statement is: **on this piece, with this model, small pieces and an advisory
self-test are each necessary and only jointly sufficient.** Neither is the headline.

## Why each part matters

**Piece size.** The failure mode was never incapacity, it was regression: on the monolith,
scenario positions ran `[18, 21, 18]` — `create_user` fixed, next assertion reached,
`create_user` broken again — because a repair asks for the whole module back and the model
rewrites nine functions to change one. Three functions is small enough that a rewrite cannot
lose anything.

**The model's own test.** With it as a gate, the split pieces failed on *its* errors, not
theirs: `TypeError: tuple indices must be integers`, `cannot convert dictionary update
sequence element #0`. It also asserted `user_id == 1`, which is true only of a fresh
database. A model grading its own work against its own expectations fails correct code, and
its message-less assertions collided into a single error fingerprint that stopped the loop
early. The blueprint scenario is the real gate; the self-test is a second opinion.

## Cost, which the gate did not measure

`split` is **9.5× faster** than `baseline` (244 s vs 2310 s) and 13× faster than
`split-plain`. On the free tier that is only time; on the paid tiers of the ladder it is
money.

`deepseek-coder:6.7b` is slower than `qwen2.5-coder:7b` on the same task and no more
reliable. Nothing recommends switching. It stays selectable, not promoted.

## A bug the split exposed

The split build was first reported as failing with:

```
storage.py does not define `create_user(email, password_hash)`. It defines: ['init_db']
```

That was the contract checker, not the code. `public_interface` read `def` statements off
the AST, and a facade exposes its interface through `from store_users import create_user`.
Fixed in v0.1.147. **The best result of the sweep spent a full arm hidden behind a checker
that could not read the shape it was looking at.**

## What this does not show

The monolith never passed, in any arm. If a piece is written as nine coupled functions this
model will not finish it, and nothing in this sweep changed that. The lever is **piece
size** — a property of the blueprint, which an author controls, not of the model.

Four runs bound a rate loosely. 4/4 says the combination is clearly better than never; it
does not say it is infallible. And this is one piece, one blueprint, one model.

## What changed as a result

- Prefer the split shape for storage-like work; `webapp-auth-crud-split` is the reference.
- `Piece.source` exists so a facade is written rather than generated — there is one correct
  way to re-export three modules and no judgement in it.
- Targeted repair and the advisory self-test stay on by default, now on evidence rather
  than expectation.
