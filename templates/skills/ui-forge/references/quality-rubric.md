# UI Forge Quality Rubric

Score the **running application**, not the code diff. Use representative desktop and mobile evidence. A dimension may not receive a high score solely from code inspection.

## Dimensions

### Request fidelity — 15%
- 95–100: visibly matches the user's stated product intent, hierarchy, content priorities, and requested interactions with no material omissions.
- 85–94: strong match with minor non-critical differences.
- 70–84: recognizable but important details or flows drifted.
- <70: the build solved a different problem or relied on generic defaults.

### Visual design — 18%
Judge hierarchy, composition, typography, spacing rhythm, density, color use, iconography, motion restraint, and aesthetic coherence.
- 95–100: intentional, distinctive, balanced, product-specific.
- 85–94: polished and coherent with small rough edges.
- 70–84: serviceable but generic/inconsistent.
- <70: visibly unfinished, cluttered, weak hierarchy, or style drift.

### UX — 15%
Judge discoverability, navigation, primary-action clarity, cognitive load, scrolling burden, recovery, feedback, state clarity, and interaction cost.

### Responsive — 10%
Judge real mobile layout, touch targets, text wrapping, overflow, sticky/fixed regions, keyboard-safe forms, and whether mobile is intentionally composed instead of merely stacked.

### Accessibility — 9%
Judge semantic structure, labels, focus visibility, keyboard completion of critical paths, contrast, target size, and reduced-motion behavior where relevant.

### Runtime correctness — 15%
Judge whether the app actually runs, data/state wiring is truthful, interactions complete, forms behave, routes work, and the UI did not break existing behavior.

### Browser proof — 10%
Judge evidence quality: actual running browser checks, representative viewports, primary-flow interaction, console/runtime error inspection, and screenshots.

### Originality — 8%
Judge whether the result belongs to this product rather than looking like a brand-swapped reference/template. Pattern borrowing is fine; distinctive copying is not.

## Automatic blockers
Any of these is a critical failure:
- primary user path is broken
- page cannot render or has persistent runtime errors
- destructive/data-changing behavior is incorrect or misleading
- fabricated/misrepresented product data used to make UI look complete
- authentication/security regression in a critical path
- mobile critical path is unusable
- inaccessible critical action with no practical alternate path
- copied proprietary source, branding, copy, or distinctive page composition

## Gate
Recommended deterministic pass gate:
- weighted total >= 85
- runtime correctness >= 85
- browser proof >= 80
- zero critical failures

## Review method
1. Use screenshots only for visual/hierarchy questions.
2. Use browser interaction for UX/correctness questions.
3. Use DOM/semantic inspection for accessibility questions.
4. Compare against the original request and project context for fidelity.
5. Deduplicate findings before fixing.
6. Fix blockers and the lowest-scoring dimensions first.
