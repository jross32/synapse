# FirstRun Studio research notes

Research snapshot: 2026-09-01.

These are pattern references, not templates to clone.

## Userflow

Reference:
- https://www.userflow.com/solutions/user-onboarding
- https://www.userflow.com/blog/the-saas-onboarding-template-from-sign-up-to-activation
- https://www.userflow.com/blog/what-great-saas-onboarding-looks-like-in-2026

Observed / documented principles:
- Treat signup through activation as one journey.
- Name a measurable activation event.
- Instrument setup steps so drop-off is visible.
- Personalize by role, job-to-be-done, behavior, and completed work.
- Use checklists/resource centers/contextual assistance instead of relying on a one-time static tour.
- Move from user questions/intent to completed tasks where AI can genuinely reduce work.

Local Synapse Web Scraper capture on 2026-09-01:
- public onboarding solution page was successfully captured with Playwright
- page messaging explicitly contrasts adaptive onboarding with static, one-time tours
- sections emphasize guided flows, checklists/resource center, AI assistance, and drop-off visibility

Use Userflow as a product-onboarding strategy reference. Do not copy its proprietary product, source, copy, brand, or visual implementation.

## Lovable

Reference:
- https://lovable.dev/use-cases/websites
- https://docs.lovable.dev/features/design-systems

Observed / documented principles:
- "beautiful defaults" come from typography, spacing, layout, and reusable system quality
- users can begin from prompt, screenshot, Figma, or other references
- design systems act as a reusable source of truth for components + guidance
- when visual identity is unclear, establish an explicit design brief rather than letting styling drift

Local Synapse Web Scraper capture on 2026-09-01 found a disciplined semantic token system:
- multiple neutral depth/surface levels instead of one flat background
- semantic foreground tiers
- explicit accent/focus/success/warning/destructive roles
- consistent radius
- layered surface/input/button shadows
- a separate warm off-white marketing surface from product UI surfaces

Principle to reuse: encode visual quality as a system of semantic decisions, not a pile of one-off CSS values.

Do not copy Lovable's proprietary source, brand, marketing copy, exact token values, or page layout.

## Dribbble

Reference discovery:
- SaaS auth/onboarding examples from Dribbble search and public shots.

Common visual patterns observed:
- split-screen signup with a product/value preview
- centered quiet card with minimal progress
- stepper + focused form canvas
- dark-mode auth with a single high-contrast action
- choice cards for role/use-case selection
- ambient gradients used as framing rather than content

Dribbble is inspiration only. Do not reuse illustration assets, brand elements, screenshot pixels, or exact compositions.

## Open-source implementation references

Consider only after product needs are clear:
- shadcn/ui: editable UI primitives/components; MIT
- React Joyride: React guided-tour primitive; MIT
- Onborda: Next.js onboarding/product-tour primitive with Framer Motion; MIT

Read source-license-matrix.md before copying or adapting source.
