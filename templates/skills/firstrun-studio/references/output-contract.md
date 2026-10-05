# FirstRun Studio output contract

Use this structure for substantial work.

## 1. FirstRun brief

- Product:
- Audience:
- Primary job-to-be-done:
- Public promise:
- Activation event:
- First authenticated destination:
- Existing auth provider/methods:
- Required identity data:
- Deferrable setup:
- Trust concerns:
- Mobile constraints:
- Brand traits:
- Existing design-system primitives:
- Technical constraints:

## 2. Journey map

Provide a Mermaid state diagram when helpful.

Each state records:
- id
- entry condition
- user goal
- primary action
- secondary/escape action
- data collected
- success transition
- failure/recovery transition
- resume behavior

## 3. Screen specification

For each screen/surface:
- purpose
- information hierarchy
- primary CTA
- secondary CTA
- component inventory
- microcopy
- validation
- loading
- error
- success
- responsive behavior
- keyboard/focus behavior
- analytics event

## 4. Visual-system delta

List what is reused from the product and what new reusable tokens/components are needed.

Prefer:
- semantic surface/depth tokens
- foreground hierarchy
- explicit border/focus states
- state colors
- restrained elevation
- small radius scale
- motion duration/easing roles

Do not dump arbitrary hex values into individual components.

## 5. Signature moment

Describe one product-specific transition/interaction that communicates value.

It must state:
- what changes visually
- what product value it reveals
- reduced-motion alternative
- why it is not decorative noise

## 6. Analytics map

Minimum useful funnel:
- landing CTA
- auth method selected
- auth success/failure
- verification requested/completed
- setup step viewed/completed/skipped
- activation event
- onboarding dismissed/replayed if relevant

Do not collect sensitive field contents.

## 7. Verification matrix

Rows:
- new user
- returning user
- invalid credentials
- verification delay/expiry
- recovery
- refresh/resume
- invite/deep link if applicable
- desktop
- mobile
- keyboard-only
- reduced motion

Columns:
- expected outcome
- evidence
- status
- unresolved issue

## 8. Handoff

Summarize:
- files changed
- routes changed
- auth/backend assumptions
- tests run
- browser proof
- rubric score
- unresolved risks
- next recommended experiment

A substantial implementation is not complete with screenshots alone; behavior, recovery, and first-value proof matter.
