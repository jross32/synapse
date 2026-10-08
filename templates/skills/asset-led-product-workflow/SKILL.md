# Asset-Led Product Workflow (optional)

This pack captures transferable engineering habits from TechSwap. It is NOT a mandatory TechSwap theme, color palette, marketplace layout, or UI style. AI agents may choose a different approach when the product calls for it. Prefer the existing UI Forge for visual work, Image Studio for original assets, and autonomous-dev-loop for verification/continuity. This pack complements them rather than duplicating them.

## When to use
When an agent wants a deliberate visual system and reusable media for a site/app, or is repairing broken images. Ask what the product, audience, brand, constraints, and visual differentiation actually need. Do not apply by default to backend-only work.

## Repeatable workflow
1. Inspect current UI and real behavior before proposing visuals; document the target user, primary journeys, existing styles, breakpoints, accessibility and failure states.
2. Research references as inspiration, not copying. Form at least two credible directions; explain why one fits this product. Never inherit TechSwap colors by default.
3. Establish design tokens and component patterns where they reduce inconsistency. Specify typography, spacing, contrast, image ratios, mobile layout, and interactive states.
4. Create a living asset manifest (brand, categories, empty states, trust/status, product imagery, social images), with semantic names, source/provenance, intended use, alt policy, version and license where applicable. Reuse assets first; create or obtain new originals when needed. Avoid repetitive generic illustrations.
5. Integrate real asset paths in actual screens. Serve correct MIME types: SVG image/svg+xml, PNG image/png, JPEG image/jpeg, WebP image/webp; verify Content-Type, CSP, caching and decoding, not merely HTTP 200. Use cache-busting versioned URLs after changing broken cached responses. Avoid unicode-to-question-mark corruption by checking actual rendered glyphs or use ASCII/icon SVG fallbacks.
6. Implement small reversible changes; test responsive, keyboard, focus, empty/error/loading states, authentication, mobile, and real interactions. Browser visual QA is required for a visual verification claim. HTTP-only proof is not visual proof.
7. Run tests and diff checks, verify deployment and images at public origin, record evidence and outstanding gaps. Do not call 100% verified when browser QA is unavailable.
8. Persist a handoff and asset inventory in Synapse. Preserve unrelated changes. Revisit whether the asset system actually helps user comprehension and performance.

## TechSwap case study (not a theme preset)
- Good: named asset folders, explicit manifest, responsive category art and trust rail, incremental tests, production health checks.
- Failure: SVG files returned 200 but were served application/octet-stream; browser images failed. Cached responses kept the broken MIME after fixing origin. Repair used image/svg+xml plus URL versioning.
- Failure: shell/file encoding turned checkmarks and punctuation into literal question marks. Repair must test both source bytes and rendered UI.
- Warning: claims such as protected/verified can overpromise. Use precise copy tied to implemented functionality, not decorative trust signals.
- Remaining proof: real mobile browser render/interaction, image decode, and accessibility audits.

## Evidence checklist
- Asset manifest entries point to existing files
- Correct MIME and CSP from deployed origin
- No missing, broken or duplicate images; image decode succeeds in browser
- No corrupted glyphs/question marks in icon slots
- Responsive screenshot at phone and desktop widths
- Meaningful alt or empty alt for decoration
- Functional regression tests and no unrelated changes
- Honest release note, reproducible steps, durable Synapse handoff
