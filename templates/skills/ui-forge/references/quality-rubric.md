# UI Forge Quality Rubric

Score the **running application**, not the code diff. Use representative desktop and mobile evidence. A dimension may not receive a high score solely from code inspection.

When a locked Visual Target Contract exists, reference fidelity is mandatory and the weighted rubric below applies.

## Dimensions

### Request fidelity — 10%
Judge whether the result fulfills the user's stated product intent, hierarchy, content priorities, requested interactions, and product scope rather than solving a narrower technical interpretation.

### Reference fidelity — 15%
Only when a Visual Target Contract/reference is present. Judge composition, information architecture, asset richness, density, typographic hierarchy, imagery/lighting, section presence, device/scene treatment, responsive intent, and emotional/brand character.
- 95–100: the implementation clearly converges on the approved target while remaining product-original.
- 85–94: strong match; remaining differences are small and documented.
- 70–84: recognizable direction but material sections/assets/composition still drift.
- <70: reference was treated as loose inspiration or substituted with generic UI.

Reference fidelity is **not** a raw pixel-diff score. Use real screenshots plus the contract decomposition. Missing required production assets, absent target sections, or placeholder pages cap this dimension below 70.

### Visual design — 15%
Judge hierarchy, composition, typography, spacing rhythm, density, color use, iconography, motion restraint, aesthetic coherence, and whether real assets support the design instead of decorative placeholders.
- 95–100: intentional, distinctive, balanced, product-specific, production-rich.
- 85–94: polished and coherent with small rough edges.
- 70–84: serviceable but generic/inconsistent or asset-light.
- <70: visibly unfinished, placeholder-heavy, weak hierarchy, or style drift.

### UX — 12%
Judge discoverability, navigation, primary-action clarity, cognitive load, scrolling burden, recovery, feedback, state clarity, and interaction cost.

### Responsive — 8%
Judge real mobile layout, touch targets, text wrapping, overflow, sticky/fixed regions, keyboard-safe forms, and whether mobile is intentionally composed instead of merely stacked.

### Accessibility — 8%
Judge semantic structure, labels, focus visibility, keyboard completion of critical paths, contrast, target size, and reduced-motion behavior where relevant.

### Runtime correctness — 15%
Judge whether the app actually runs, data/state wiring is truthful, interactions complete, forms behave, routes work, and the UI did not break existing behavior.

### Browser proof — 10%
Judge evidence quality: actual running browser checks, representative viewports, primary-flow interaction, console/runtime error inspection, screenshots, and state/route coverage.

### Originality — 7%
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
- a locked target requires a production illustration/photo/3D/device asset but the implementation silently substitutes a CSS primitive, generic icon, or empty container
- a required route/surface in the Visual Target Contract is absent or represented only by placeholder copy
- a required target section is missing without an explicit accepted omit/adapt decision
- provider/tool unavailability is hidden by lowering visual fidelity instead of recording a blocker
- the product exposes obvious development-state copy in a required polished surface (for example "next UI slice", "local fallback", or equivalent) without the target calling for it

## Gate
Recommended deterministic pass gate:
- weighted total >= 85
- runtime correctness >= 85
- browser proof >= 80
- if a Visual Target Contract exists: reference fidelity >= 80 and visual_target_gate.py passes
- zero critical failures

A functional test suite passing does **not** satisfy the visual gate.

## Review method
1. Use screenshots for hierarchy, composition, density, asset quality, and reference comparison.
2. Use browser interaction for UX/correctness questions.
3. Use DOM/semantic inspection for accessibility questions.
4. Compare against the original request, locked references, and project context for fidelity.
5. Run prototype_surface_scan.py on meaningful product UI work and investigate its findings.
6. Run visual_target_gate.py when a Visual Target Contract exists.
7. Deduplicate findings before fixing.
8. Fix blockers and the lowest-scoring dimensions first.
9. Recapture and rescore after repair; do not carry forward a stale visual score.
