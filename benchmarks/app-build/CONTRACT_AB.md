# Stating the contract up front: a measured A/B

**Question.** A blueprint piece declares the signatures it must expose, and a contract test
asserts them exactly. Until v0.1.131 the model was never shown that declaration — the
`storage` spec described its tables and rules in prose and never listed the nine functions.
How much did enforcing an unstated contract cost?

**Method.** The same piece, built twice, differing in one thing: whether
`ModuleContract.as_prompt()` is appended to the generation prompt. Same model
(`qwen2.5-coder:7b`), same repair budget (10), same acceptance scenario, same machine, run
sequentially — two 7B generations at once on a 6 GB card would measure contention rather
than prompts. Driver: `probe_storage_repairs.py`, which records what every repair attempt
changed.

## Result

| | Contract withheld | Contract stated |
|---|---|---|
| Repair attempts | **10** (budget exhausted) | **3** |
| Distinct failures | 9 | 2 |
| Wall clock | 3269 s | 1974 s |
| How it ended | ran out of budget | stopped early, circling |

Reproduced across two independent runs with the same ratios (10 vs 3 repairs, 9 vs 2
distinct failures), on either side of an unrelated scenario bug fix. That consistency is
worth more than either run alone: local models are noisy, and this ratio was not.

## What the withheld arm actually spent its budget on

The first six repairs, in order:

1. `storage.init_db is missing`
2. `storage.create_user takes ['email', 'password']` — contract says `['email', 'password_hash']`
3. `storage.get_user_by_email is missing`
4. `storage.create_session takes ['email']` — contract says `['user_id']`
5. `storage.user_id_for_token is missing`
6. `storage.delete_session is missing`

That is a model discovering its own interface one function at a time, at roughly 200 seconds
per discovery. Around twenty minutes of local compute spent learning a fact that costs a few
dozen tokens to state, and which was sitting in the blueprint the whole time.

None of it is a reasoning failure. The information was not there.

## Then it passed

A third run, with the contract stated *and* the scenario's failures made teachable — every
guard naming the shape it received and the shape a caller needs, instead of letting a bare
`TypeError` escape:

```
passed=True  attempts=6  1843s
stop_reason: tests passed
scenario positions reached: [18, 21]
```

**The 7B wrote a complete, correct nine-function stateful storage module**, locally, for
free, in 31 minutes. Every signature right and — the part that had never once been right —
every return shape right:

```python
def create_user(email, password_hash):     return user_id
def get_user_by_email(email):              return dict(row)   /  return None
def user_id_for_token(token):              return row[0] if row else None
def delete_record(record_id, user_id):     return deleted
```

Verified independently of the build: the acceptance scenario re-run against the produced
module, three times in a row, from a cleared bytecode cache. Three passes.

Its repair trail is a model being taught: `create_user` returned `None`, then returned a
dict, then returned the id; `get_user_by_email` raised `KeyError: 'password_hash'` before
selecting the column. Each step was a message naming what came back and what a caller needs.

## What actually changed

Not the model. `qwen2.5-coder:7b` throughout, same card, same budget. What changed was
everything around it:

| Fix | Version | What it had been doing |
|---|---|---|
| Contract stated up front | 0.1.131 | six repairs spent rediscovering its own interface |
| Stale bytecode | 0.1.131 | grading the previous attempt's code |
| Scenarios actually execute | 0.1.134 | `NameError` on line 1, every build, never noticed |
| Scenario re-runnable | 0.1.137 | every attempt after the first failed on a stale database |
| Teachable failures | 0.1.138 | `TypeError: 'int' object is not subscriptable` |

Before those, `storage` escalated on every attempt and the reasonable conclusion was that a
7B cannot write a nine-function stateful module. That conclusion was wrong, and it was wrong
because the harness was measuring itself.

## Caveats, stated plainly

Both arms of the *first* pair of runs terminated on faults in the harness, not the model —
acceptance scenarios that never executed (fixed in v0.1.134) and a scenario that deleted
three guessed database filenames while the model used a fourth, failing every attempt after
the first (fixed in v0.1.137). The numbers above are from runs after both fixes, plus a
pre-fix run that happened to produce the same ratios.

Every earlier escalation figure in this benchmark predates those fixes and should be read as
a lower bound rather than a measurement.

## What follows from it

- Contract-in-prompt is unconditional in `scaffold/runner.py`. It is the cheapest thing in
  the scaffold: a few dozen tokens, spent before the first draft instead of after it.
- Failure *quality* is worth as much as failure *detection*. Every guard that can be
  reached by a wrong shape should name what it got and what a caller needs, because the
  difference between `TypeError: 'int' object is not subscriptable` and *"it must return a
  dict the caller can read by name — the login route reads `user['password_hash']`"* was
  the difference between escalating and passing.
- The single-variable A/B is worth its wall-clock. Every one of the five fixes above was
  found by running one deliberately small thing and reading what came back, and none of
  them by reading code.

## Then it passed 1 time in 5

The obvious follow-up — repeat the identical run and report a rate rather than an existence
proof — was run immediately. Four more times:

```
run 1: passed=False  8 repairs   run 3: passed=False  7 repairs
run 2: passed=False  5 repairs   run 4: passed=False  8 repairs
```

**0 of 4.** With the original success, that is **1 pass in 5 runs of the same
configuration.** A 7B on a 6 GB card can produce a correct nine-function stateful module.
It does not do so reliably, and any claim built on the single pass was overstated. This
section exists because that claim had already been made.

### Why the four failed, which is not what the summary said

All four stopped on the **repeated-error guard**, after 5–8 of 10 allowed repairs — none
ran out of budget, though the probe's verdict line said they had. Their fingerprints:

```
a different fix produced the same error, so the model is circling …: AssertionError
```

A bare `AssertionError`. `error_fingerprint` returned only the exception type, so two
entirely unrelated assertion failures compared equal and the loop concluded the model was
going in circles. Each run had in fact reached a *different* assertion.

Worse, this was a regression **introduced by the previous fix**. Making generated tests
actually execute (0.1.141) meant the model's own message-less `assert x == 1` lines started
running — and colliding. The fix that removed one false pass created a false *stop*.

Fingerprints now fall back to the statement that raised, when the exception carries no
detail of its own. Whether that restores the pass rate is the next measurement, and it is
not assumed here.

The 10-vs-3 comparison isolates one variable cleanly. The pass does not: it arrived after
five changes, only one of which was contract injection, so it is evidence that the *stack*
works and not a measurement of any single part. Attributing the pass to teachable messages
alone would be exactly the over-claiming this document exists to avoid.

`storage` is also one piece, on one blueprint, on one model, and local models are noisy.
A single pass is a proof of possibility, not a rate — which the 1-in-5 section above bears
out, and which is why it was worth two hours of free compute to check rather than to
assert.

The pattern across this whole document is worth naming, because it recurred four times in
one day: **the encouraging result arrived first and the correction arrived only because
someone went looking.** A pass, a ratio, a verdict line — each looked conclusive, and each
needed a repeat run, a re-read of the raw log, or an independent re-verification before it
meant what it appeared to mean.
