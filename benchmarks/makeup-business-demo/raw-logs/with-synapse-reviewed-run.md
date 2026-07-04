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

## Re-score: done — reviewed app wins both previously-lost dimensions

After the usage limit reset, the two previously-lost dimensions were re-scored head-to-head vs the baseline (each judge scored both apps in the same evaluation, driving them in a real browser):

- **Backend / functional correctness:** reviewed **100** vs baseline **88** — reviewed wins (was 78, a loss).
- **Adversarial bug hunt:** reviewed **98** vs baseline **70** — reviewed wins (was 42, a loss).

Combined with the four dimensions Synapse already won (unchanged by the surgical fixes), **the reviewed with-Synapse app now leads all six categories** at total build+review tokens still under the 51,314-token baseline. Full breakdown: [`../results/quality/reviewed-rescore.md`](../results/quality/reviewed-rescore.md).
