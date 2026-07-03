# Adversarial bug hunt — 42 (with Synapse) vs. 96 (without Synapse)

An independent judge agent tasked only with finding and reproducing real defects — not being generous, not counting cosmetic nitpicks. This is the dimension where the with-Synapse app pays for its extra ambition. **Without Synapse wins decisively.**

## With Synapse — 42/100

Two serious, live-reproduced defects plus one real code-quality defect:

1. **Contact form validation is fully bypassed.** `novalidate` on the `<form>` (`index.html:118`) disables native validation for the `required` fields, and `script.js`'s submit handler performs no manual validation. **Reproduced via automated test:** submitting the form with all three fields blank immediately hides the form and shows "Message Received!" with zero data entered.
2. **Mobile nav is visibly broken on every page load at ≤768px.** Confirmed at 375px and 700px on a fresh load: the closed nav menu's math is wrong (`transform: translateY(-110%)` computes against the menu's own ~263px height with a 66px top offset, needing ≥329px clearance but only getting ~289px), so the bottom of the closed menu — including the pink "Book Now" pill — stays visible, overlapping the logo and hamburger icon. **This also makes the hamburger button largely unclickable**: the off-canvas menu intercepts pointer events at the button's natural tap point; only a ~5px sliver at the very edge of the button actually registers a click.
3. Related accessibility bug: because the closed menu is hidden only via CSS transform (no `visibility`/`aria-hidden`/`inert`), its links stay focusable and keyboard-reachable while invisible.
4. Duplicate Google Fonts loading (both a `<link>` and an identical `@import` in the CSS) — a genuine wasted request, not just a nitpick.

## Without Synapse — 96/100

No reproducible functional, structural, or rendering defects found. The form correctly relies on native HTML5 validation (confirmed via `checkValidity()`/`requestSubmit()` testing) and valid submissions correctly show success and reset. Layout checked at 375px, 481px, 550px, and 1280px with no overflow, overlap, or clipping. Only very minor, non-functional omissions (no favicon link, no meta description).

## Verdict

Without Synapse wins decisively on defect count and severity. This is the most important honest finding of the whole benchmark: **the with-Synapse app is more ambitious and more polished, but that extra surface area (an off-canvas mobile menu, a stricter form UX) shipped with two real, user-facing bugs that the simpler app's smaller scope avoided entirely.** See the root README's benchmark section for what this implies.
