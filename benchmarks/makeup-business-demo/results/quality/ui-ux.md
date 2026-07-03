# UI/UX — 78 (with Synapse) vs. 68 (without Synapse)

Scored by an independent judge agent that read every file in both apps. Excludes visual polish (see `design.md`) — this dimension is interaction clarity, navigation, form usability, and layout hierarchy.

## With Synapse — 78/100

Richer, more deliberate interaction design. A fixed header with scroll-triggered shadow, a fully implemented mobile hamburger menu (toggles an `aria-label` between "Open menu"/"Close menu", auto-closes on link click), clear section hierarchy via repeated eyebrow labels/dividers, and a genuine two-column About section. `scroll-behavior: smooth` makes anchor nav feel responsive.

**Issues found:**
- Form has `novalidate` (`index.html:118`) with zero custom validation in `script.js` — required fields aren't enforced; an empty submission still shows "Message Received!" (see `backend-correctness.md` and `bug-hunt.md` for the full trace).
- After success, the form is hidden with no way to send a second message without reloading.
- The animated down-arrow implies an interactive affordance but is decorative only.

## Without Synapse — 68/100

Simpler, but functionally sound where it matters most: no `novalidate`, so native browser validation actually blocks empty submissions, and the form stays visible/resettable after success — objectively better behavior than the with-Synapse form.

**Issues found:**
- No mobile hamburger/off-canvas menu at all; only one responsive breakpoint (≤480px).
- About section is a single flat paragraph with no supporting visual or eyebrow label.
- Footer has no subheadings for its hours/social groups.
- No `scroll-behavior: smooth`.
- No placeholder text on form inputs.

## Verdict

With Synapse wins on UI/UX overall — more deliberate interaction design and hierarchy — but ships a real correctness bug in the one place a business most needs to trust: the lead-capture form. Without Synapse's form is simpler but actually correct.
