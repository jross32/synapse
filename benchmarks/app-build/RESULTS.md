# Building the same app twice: Claude alone vs local models + Claude

Both arms built **Trailmark** — landing, sign up, log in, and an authenticated dashboard with
per-user trail records — from `shared/SPEC.md`, which was written and frozen before either
build started. Both were graded by `shared/score_app.py`, also written before either app
existed, so the rubric could not be shaped around whatever one of them happened to produce.

---

## Headline

| | Arm A — Claude only | Arm B — local models + Claude |
|---|---|---|
| **Automated score** | **100%** (105/105) | **100%** (105/105) |
| **Wall clock** | **1m 46s** | **54m** (~31× longer) |
| **Claude tokens** | ~14k out (wrote everything) | ~6k out (wrote 1 of 4 modules + harness) |
| **Local tokens** | 0 | **13,652 out / 24,600 in** (free) |
| **Pieces written locally** | 0 of 4 | **3 of 4** (storage, pages, passwords) |
| **Escalated to Claude** | n/a | **1 of 4** (the HTTP layer) |
| **Real bugs shipped** | 0 found | **2 found** (stored XSS, wrong field name) |

The scores are identical and **the scores are misleading**. That is the most useful result
here, and the rest of this document is mostly about why.

---

## What the automated rubric measured, and what it missed

Every functional and security check passed for both. Arm B genuinely earns that: real PBKDF2
hashing, hashed session tokens, per-user SQL scoping, 401s for anonymous callers, 422s for
bad input, no cross-user reads or deletes. For an API, it is correct work.

Then the screenshots and a static pass over the served HTML showed this:

| | Arm A | Arm B |
|---|---:|---:|
| `<label>` elements | 7 | **0** |
| `autocomplete` hints | 4 | **0** |
| 44px tap-target rules | 12 | **0** |
| `:focus` styles | 4 | **0** |
| media queries | 4 | **0** |
| CSS bytes | 9,824 | 1,094 |
| escapes user text | yes | **no** |

And two defects that are not stylistic:

**1. Stored XSS.** Arm B renders trail names straight into `innerHTML`:

```js
item.innerHTML = `<p>${trail.name} - ${trail.distance} km on ${trail.date}</p>`
```

A trail saved as `<img src=x onerror=...>` executes. Arm A escapes every interpolated value.

**2. A field that does not exist.** That same line reads `trail.distance`, but the storage
module — also written by a local model — returns `distance_km`. Every row on the dashboard
renders as "undefined km". Two locally-written modules disagreed about their own contract,
and nothing caught it, because each passed its own test in isolation.

**My rubric gave Arm B 15/15 for frontend.** It checked that the pages were served, were
non-trivial in size, and contained a real password field. It never rendered them. A scorer
that only speaks HTTP cannot see a cross-site scripting hole or an undefined value on screen,
and I would have reported "both perfect" if I had stopped at the number.

---

## Where the local models did well, and where they didn't

Results by piece, in build order:

| Piece | Outcome | Repairs | Local tokens | Time |
|---|---|---:|---:|---:|
| `passwords` | escalated, then **passed** after a harness fix | 4 → 1 | 3,849 | 12m |
| `storage` | **passed first try** | 0 | 1,032 | 3m32s |
| `pages` | **passed first try** | 0 | 1,496 | 5m07s |
| `api` | **escalated to Claude** | 4 + 4 | 7,275 | 30m |

The surprise is which piece was hard. `storage` is the largest and most intricate — nine
functions, three tables, hashed session tokens, per-user scoping — and it passed on the first
attempt with no repairs. `passwords`, two functions and much simpler, took five attempts.

### Failure 1 — self-inconsistency, hidden by defensive code

`hash_password` emitted five `$`-separated fields; `verify_password` unpacked four. Every
verification failed, including correct passwords. The model's own `try/except: return False`
swallowed the `ValueError` that would have explained it, so the repair loop only ever saw
`AssertionError` with no signal — and repeated the same mistake four times.

Rewriting the test to print *what it got versus what it expected* fixed it in **one** repair.
The model was not incapable; it was uninformed, and my harness was what starved it.

### Failure 2 — an invented API, then a framework concept

`api` first called `storage.user_exists()`, a function that never existed, and re-invented it
four times despite an explicit `AttributeError`. The repair prompt carried the error but
never the storage module's actual interface. Injecting the real signatures moved it past that
immediately.

What it could not get past was `Depends`. It wrote:

```python
async def get_trails(token: str = Depends(storage.user_id_for_token)):
```

passing a plain storage function as a FastAPI dependency. FastAPI introspects the signature,
sees a `token` parameter, and treats it as a **query parameter** — so anonymous requests
returned `422 Field required: query.token` instead of `401`. Four more repairs against
"anonymous must be 401" never bridged it, because the message says what is wrong without
hinting at why, and the fix requires knowing that a dependency is a callable the framework
*invokes*, not a value it looks up.

That is a genuine capability limit, and the honest escalation point.

---

## Time and cost

Arm A took **1m 46s** and one attempt. Arm B took **54 minutes**, most of it waiting on a 7B
model running at ~6 tok/s on a 6 GB card, where it spills out of VRAM.

The trade is real but not the one you might expect. Arm B did not save 90% of my tokens; it
saved roughly **55%** — I still wrote the spec, four acceptance test suites, the orchestrator,
the harness fixes, and eventually the entire HTTP layer. The tokens local models replaced were
the *easy* ones: boilerplate CRUD, SQL, HTML scaffolding. The expensive thinking — deciding
the decomposition, defining correctness, diagnosing why `Depends` misbehaved — stayed with me,
because that is the part that could not be checked by running it.

---

## What I would actually recommend

**Use local models for work whose correctness a program can verify, and where you already know
the shape of the answer.** `storage` is the ideal case: a precise interface, obvious semantics,
a test that proves it. It cost 1,032 free tokens and three minutes of unattended time.

**Do not hand them anything user-visible without review.** Both frontend defects — the XSS and
the undefined field — are in the layer nobody wrote a strict test for. A local model will
produce something that *looks* finished and passes a loose check.

**Most of the value is in the harness, not the model.** Two of the three failures here were my
fault: a test that reported nothing useful, and a prompt that withheld the interface. Fixing
those turned a 4-repair escalation into a 1-repair pass. Before concluding a model cannot do
something, check whether it was ever told enough to.

**Budget the wall clock honestly.** 31× slower is fine overnight and unusable in a loop where
you are waiting. The right pattern is what Synapse already does: hand local models the
verifiable pieces, let them grind unattended, and spend frontier tokens on the decomposition,
the review, and whatever escalates.

---

## Files

* `shared/SPEC.md` — the frozen build spec
* `shared/score_app.py` — the rubric, written before either build
* `shared/ux_comparison.json` — the static UX/accessibility comparison
* `arm-a-claude/` — Claude-only build, `score.json`
* `arm-b-synapse-local/` — local-model build, `build_log.json`, `build_log_round2.json`, `score.json`
* `shots/` — screenshots of both, at 390×844
