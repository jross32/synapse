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

## What this does not show

The contract arm did not pass. It stopped after three repairs, having reached line 18 of the
acceptance scenario, on a genuine behavioural failure (`get_user_by_email` returning a bare
id instead of a dict carrying the password hash). Contract injection removed the interface
guesswork; it did not make a 7B able to write a correct nine-function stateful module.

The honest summary is that it converted **wasted** repairs into **useful** ones. The budget
now gets spent on behaviour rather than on signatures.

## Caveats, stated plainly

Both arms of the *first* pair of runs terminated on faults in the harness, not the model —
acceptance scenarios that never executed (fixed in v0.1.134) and a scenario that deleted
three guessed database filenames while the model used a fourth, failing every attempt after
the first (fixed in v0.1.137). The numbers above are from runs after both fixes, plus a
pre-fix run that happened to produce the same ratios.

Every earlier escalation figure in this benchmark predates those fixes and should be read as
a lower bound rather than a measurement.

## What follows from it

- Contract-in-prompt is now unconditional in `scaffold/runner.py`. It is the cheapest thing
  in the scaffold: a few dozen tokens, spent before the first draft instead of after it.
- The next variable under test is failure *quality*. The contract arm ended on
  `TypeError: 'int' object is not subscriptable` — a raw traceback that says what broke and
  not what was wanted. This project has already measured that a got-vs-expected message
  turned a four-repair escalation into a one-repair pass, so the scenario's guards were
  rewritten to name the shape they received and the shape they need.
