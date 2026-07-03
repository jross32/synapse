# Code quality / architecture — 85 (with Synapse) vs. 75 (without Synapse)

Scored by an independent judge agent that read every line of both apps for readability, structure, naming, and maintainability.

## With Synapse — 85/100

Well-organized, semantic, largely production-ready. Proper landmark elements, a working accessible hamburger menu, consistent class naming. `style.css` is the standout: a 10-variable design-token system, rules grouped under clear comment banners across a ~750-line file, shared classes reused across sections instead of per-section duplication, a full 3-tier responsive strategy. `script.js` is short, uses `const` throughout, cleanly separates three concerns with no dead code.

**Issues found:** six unnecessary `!important` flags on `.nav-btn` that nothing in the actual markup requires; the brand pink's RGB value is hand-duplicated as a raw `rgba()` literal in 7 different rules instead of being derived from its token once (a rebrand/maintenance trap); one hardcoded hex color sits outside the `:root` variable system; decorative-only elements add CSS surface area for zero functional value.

## Without Synapse — 75/100

Clean, compact, easy to read — a developer could understand the whole site in under five minutes. Simple, semantic HTML. Good DRY instincts: generic tag-level selectors (`section`, `section h2`) shared across three sections instead of repeating per-section rules. `script.js` is minimal and does exactly one job cleanly.

**Issues found:** the `:root` token system is only partially honored — five-plus hex colors are hardcoded directly in component rules instead of being promoted into it; one `box-shadow` value is duplicated verbatim across two rules instead of shared; `script.js` uses `var` instead of `const`/`let`; no comment structure in the CSS; no mobile nav toggle despite a `.navbar`/`.nav-links` structure that implies one.

## Verdict

With Synapse wins on code quality — a more thorough, well-commented architecture and a fuller (if imperfect) design-token system — at the cost of a handful of unnecessary `!important`s and duplicated color literals. Without Synapse is equally bug-free and arguably terser, but architecturally thinner.
