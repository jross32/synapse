# Run 1: three of four pieces passed, and two of them did not work

> **Correction (same day).** This file first said all three passing pieces were unusable,
> and named `pages` as one of them. That was wrong, and it was wrong for exactly the reason
> the rest of this document is about: the check that condemned `pages` asserted the string
> `"kit.css"` appeared in the rendered HTML, but the supplied `page()` helper *inlines* the
> stylesheet rather than linking it. So a page built correctly failed. When the assertion
> was fixed to look for the kit's own tokens, run 1's `pages` passed — it had been using
> `scaffold_partials` all along.
>
> A first draft of a checker produced a false failure, and I reported it before verifying
> the checker in both directions. That is the same mistake as a false pass wearing different
> clothes, and it is recorded here rather than quietly edited out.


This directory is kept as evidence. It is the output of the first blueprint build, the one
that reported:

```
3/4 pieces built locally, 1 escalation(s), 0 local tokens, 2792s
  passwords  PASS      repairs=0    117s  checks={'contract': 'pass'}
  storage    PASS      repairs=7   1486s  checks={'contract': 'pass'}
  pages      PASS      repairs=0    405s  checks={}
  api        ESCALATE  repairs=3    784s
```

That number was reported as an improvement on Arm B's 2/4. It was not an improvement. It
was not even a measurement — every one of the three "passing" modules is unusable by the
only caller it has.

## What each passing piece actually did

**`passwords` — crashes on its primary function.**

```
>>> h = passwords.hash_password('abc12345')          # fine
>>> passwords.verify_password('abc12345', h)
NameError: name 'hmac' is not defined
```

`verify_password` calls `hmac.compare_digest` and the module never imports `hmac`. No
password can ever be checked. This was graded a clean pass in 117 seconds with **zero**
repair attempts.

**`storage` — every signature right, every return value wrong.**

| Function | Contract | What it returned |
|---|---|---|
| `create_user(email, password_hash)` | the new user's id | `None` |
| `get_user_by_email(email)` | the user | a bare `(id,)` tuple — and never selected `password_hash` at all |
| `user_id_for_token(token)` | the user id | a row tuple |
| `delete_record(record_id, user_id)` | whether it deleted | `None` |

The login route cannot check a password against a record that does not contain the hash.
The signup route cannot open a session for a user whose id it was never given. The delete
route cannot tell "deleted" from "not found", so it can never answer 404.

Worth noting: `delete_record(record_id, user_id)` has its arguments in the **correct**
order here. That was the drift contract-checking was built to catch, and it caught it. The
contract did its job. Its job was just much smaller than the reported pass implied.

**`pages` — never used the UI kit.**

Phase 1 of the plan exists to stop models inventing CSS, on the measured basis that the
build-off's local model produced 1,094 bytes of ad-hoc CSS against the kit's 9,824. The kit
was installed into the workspace, the exemplar was injected into the prompt, and the model
wrote its own markup without going through `scaffold_partials.page()` anyway. Nothing
checked, so nothing noticed. The central design-asset claim of the whole scaffold was
sitting unverified.

## Why the checks passed it

Two independent holes, both mine:

1. **The contract only compares names and argument lists.** It never calls anything. A
   module can satisfy it completely while returning `None` from every function — which is
   very nearly what `storage` did.

2. **The blueprint format has a `tests` field per piece, and the runner never read it.**
   `passwords`, `storage` and `pages` all shipped with `tests: ""`, so the only behavioural
   check was the test the model wrote *about its own code* — which is exactly the thing
   that cannot be trusted to be independent.

The `passwords` case is worse than the other two, because the model's own test *did* call
`verify_password` and would have raised. How it passed anyway is not recoverable from this
run: every piece wrote its test to the same `_pipeline_test.py`, so by the time the build
finished, the test that waved `passwords` through had been overwritten twice. **A verdict
was recorded and the evidence for it was deleted by the next piece.**

## What changed as a result

- `piece.tests` is now fed into the repair loop, so a scenario failure is repaired locally
  and free rather than discovered afterwards (or never).
- The three scenarios are written into the blueprint, each one shaped like the real call
  site in `api.py`, and each verified in **both** directions before use: it must reject the
  module that shipped here, and accept a correct one. A checker only tested against
  failures can be one that always fails.
- `scenario` is reported as its own check, separate from `contract`. A piece that passes
  the contract and fails the scenario is the exact case that mattered, and one merged tick
  would hide it again.
- Each piece keeps its own `_test_<module>.py`, and `PieceOutcome.test_source` records the
  test behind the verdict. A false pass should be diagnosable, not just observable.
- `daemon/tests/test_scaffold_scenarios.py` pins all of it, including the `hmac` module
  verbatim.

## The general lesson, restated

This is the fourth time in this project that the instrument, not the model, was the thing
that was broken: the XSS probe that passed a vulnerable app, the benchmark that
under-reported reasoning by 20 points, the skill-pack conversion that silently dropped 27%
of its checks, and now a build gate that certified three unusable modules.

The pattern is the same every time — **a check that can produce a false pass is worse than
no check**, because no check leaves you looking, and a false pass makes you stop.

A passing build is a claim about the future. It says: wire these pieces together and they
will work. Three green ticks made that claim here, and every one of them was false.
