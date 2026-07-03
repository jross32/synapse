# Usability & accessibility — 65 (with Synapse) vs. 42 (without Synapse)

Scored by an independent judge agent for semantic HTML, label associations, color contrast (computed against WCAG AA), keyboard/focus behavior, and responsive breakpoints. **Both apps score in a rough-draft range here — neither is production-ready on accessibility.**

## With Synapse — 65/100

Strong structural bones: real landmark elements, correct `label`/`for` pairing on all three form fields, a 3-tier responsive design with a working off-canvas menu, high-contrast heading color, and a custom visible focus ring on inputs.

**Issues found:** the low-contrast gold accent (~2.16:1) fails WCAG AA on section labels and price badges; the primary CTA button (~4.08:1) narrowly misses the 4.5:1 AA threshold; the contact form's `novalidate` bug (see `backend-correctness.md`) means there's no accessible error feedback at all; decorative Unicode glyphs aren't marked `aria-hidden`, so screen readers announce them as noise; the closed mobile nav stays in the tab order (keyboard users can focus off-screen links), and the hamburger button lacks `aria-expanded`; footer heading levels skip from `<h2>` to `<h4>`; the hamburger's hit area is below the 44×44px touch-target minimum.

## Without Synapse — 42/100

Labels are correctly associated, and native (non-`novalidate`) form validation works with its built-in accessible error messaging.

**Issues found:** a pervasive, severe contrast problem — the single accent color is reused for the logo, every heading, the hero `<h1>`, the CTA button, and the footer, all measuring ~2.2–2.4:1 against their backgrounds (badly failing the 4.5:1/3:1 AA thresholds) across most of the page's important text; only one responsive breakpoint for the entire site, with no tablet/phablet handling; no mobile nav pattern at all; footer info groups have no headings or `aria-label`.

## Verdict

With Synapse wins — its contrast failures are confined to secondary accents while primary text stays high-contrast, and it has a real (if imperfect) responsive/mobile-nav system. Without Synapse's single accent color creates pervasive contrast failures on the page's most important elements. Neither app should be shipped as-is without an accessibility pass.
