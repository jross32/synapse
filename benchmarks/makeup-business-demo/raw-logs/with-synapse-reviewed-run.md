# Run log — with Synapse + reviewer pass (`apps/with-synapse-reviewed/`)

The original single-pass with-Synapse build won 4 of 6 quality dimensions but **lost backend-correctness (78 vs 94) and adversarial bug-hunt (42 vs 96)** to two real, live-reproduced bugs (see `../results/quality/summary.md`). The benchmark's honest conclusion was that these are exactly the defects a **reviewer pass** — Synapse's actual differentiator — would catch. The first benchmark never used one because squad launch was broken on Windows.

Now that the Windows squad-launch bug is fixed (`v0.1.36.10`), this run applies the reviewer pass. It is a **review-and-fix pass on the existing with-Synapse app**, correcting ONLY the two documented bugs, minimally, keeping everything else (design, copy, layout, colors) identical.

## The two fixes (surgical, minimal)

1. **Contact form falsely reported success on an empty submission.** Removed `novalidate` from the `<form>` (so the browser enforces the existing `required` + `type="email"` fields), and hardened the submit handler to guard on `contactForm.checkValidity()` (calling `reportValidity()` otherwise) and to `reset()` the form so it stays usable for a second submission instead of being permanently hidden.
2. **Mobile nav menu overlapped the header and was unclickable at ≤768px.** The closed `.nav-links` used `transform: translateY(-110%)`, leaving its bottom visible over the header and intercepting the hamburger's clicks. Added `visibility: hidden` + `pointer-events: none` to the closed state (and `visibility: visible` + `pointer-events: auto` to `.open`).

## Empirical verification (Playwright, 2026-07-04, viewport 375×812)

| Check | Result |
|---|---|
| Closed nav `visibility` | `hidden` ✓ |
| Closed nav `pointer-events` | `none` ✓ |
| `elementFromPoint` at hamburger center | the hamburger's `<span>` (not the nav overlay) ✓ |
| Hamburger clickable when menu closed | `true` ✓ |
| `<form novalidate>` present | `false` (removed) ✓ |
| Empty form `checkValidity()` | `false` ✓ |
| Success message shown after empty submit | `false` ✓ |

Both defects that lost the two dimensions are gone, verified in a real browser — not asserted.

## Status: re-scoring pending

The full independent 6-dimension re-score (to show the reviewed app now leads all 6 at total tokens still under the 51,314-token baseline) **was not run in this session — the reviewer sub-agent hit the account's usage limit (resets 2pm ET).** Per the commit-before-limit discipline, this unit (the fixed + verified reviewed app + this honest log) is committed complete; the re-score resumes after the reset. Token accounting for the "fewer tokens" claim must include this reviewer pass on top of the ~16k build, still expected under the 51k baseline.
