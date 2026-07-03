# Backend / functional correctness — 78 (with Synapse) vs. 94 (without Synapse)

Scored by an independent judge agent that traced every JS handler, every `href="#id"`, and every asset reference in both apps — and live-tested both forms in a real browser. **Without Synapse wins this dimension.**

## With Synapse — 78/100

All nav anchors, the hamburger menu, and asset references are wired correctly with zero real console errors. The form's submit handler correctly calls `preventDefault()` — but live-testing confirmed a genuine, reproducible bug: the `<form>` has the `novalidate` attribute while its inputs still carry `required`, and the JS submit handler performs no manual validation of its own. **Submitting the form with Name, Email, and Message all completely blank still displays "Message Received! Thank you for reaching out..."** — the business would silently receive zero-content leads while the user is told their submission succeeded. Google Fonts are also loaded twice (once via `<link>`, once via a redundant `@import` in the CSS for the identical family) — wasteful but not breaking.

## Without Synapse — 94/100

Everything traces cleanly: every nav `href` resolves to a real id, every `getElementById` call matches a real DOM node, the submit handler is wrapped in `DOMContentLoaded`. Live-tested and confirmed: the form correctly respects its `required` attributes (no `novalidate`) — submitting empty triggers native browser validation and blocks the success state; submitting valid data correctly shows success and resets the form for reuse. No console errors beyond the default favicon 404.

**Issue found:** no hamburger/mobile-nav collapse — a responsiveness limitation, not a broken reference or malfunctioning script.

## Verdict

Without Synapse wins: every reference resolves and the required-field contract is genuinely enforced. With Synapse ships a form that silently reports success on a completely blank submission — a real, live-reproduced correctness bug, not a nitpick.
