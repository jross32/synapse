---
name: firstrun-studio
description: Professional first-run UX architecture for SaaS/web/mobile apps. Use when the user asks to improve or create a landing page, sign-up, sign-in/login, registration, account creation, invite acceptance, email verification, password recovery, passkey/SSO flow, welcome flow, setup wizard, trial activation, empty-state onboarding, first-run experience, checklist, tooltip tour, product tour, activation flow, or "make onboarding professional/impressive." Inspect the real product first, preserve its brand and auth architecture, define the first meaningful value event before drawing screens, research public references as patterns rather than pixels, and verify the resulting flow in a real browser.
---

# FirstRun Studio

FirstRun Studio turns "make onboarding look professional" into a repeatable product-design and verification process.

It is not a fixed template library. The job is to create a **coherent first-run journey that belongs to the product**:

**promise -> trust -> identity -> intent -> minimum setup -> first value -> contextual continuation**

The best onboarding often feels shorter than it technically is because every step earns its place.

## When to invoke

Use this skill for:
- landing page to signup continuity
- create-account and sign-in experiences
- password, magic-link, passkey, SSO, OTP, invite, and verification UX
- recovery and existing-account detection
- welcome/setup wizards
- first-use empty states
- personalized onboarding
- activation checklists
- contextual tours/tooltips
- trial-to-paid activation surfaces
- onboarding redesigns and UX audits

Do not wait for the user to say "onboarding" if the task is clearly about the product's first-run experience.

## Core rule: define activation before screens

Before choosing layouts, identify the smallest observable event that proves the user received meaningful value.

Examples:
- created and ran the first automation
- imported the first item and saw a result
- connected a source and received the first useful signal
- created a workspace and completed the first real task

Write it as:

`Activation event: <user action> -> <visible proof of value>`

If the product cannot name this event, do not hide the uncertainty behind a beautiful wizard. Inspect the product and make the best evidence-backed proposal.

## The FirstRun loop

### 1. Inspect the real product

Before changing UI:
- read project rules, architecture notes, existing auth routes, design tokens, reusable components, and tests
- inspect current landing, signup, login, reset, verification, invite, and first authenticated screen
- identify the current auth provider and do not replace it unless explicitly requested
- identify responsive breakpoints, theme system, analytics conventions, and route guards
- note concurrent work and avoid unrelated files

Prefer extending the existing design system over introducing a second component system.

### 2. Build a FirstRun brief

Capture:
- product promise
- target user / job to be done
- activation event
- trust concerns
- required identity fields
- optional/deferable profile fields
- supported auth methods
- invite/team path if relevant
- likely returning-user path
- first authenticated destination
- mobile constraints
- brand personality
- existing technical constraints

Use `references/output-contract.md`.

### 3. Research patterns, not pixels

Research only when it materially improves the decision.

Preferred route:
1. Synapse Web Scraper for public/authorized reference pages: structure, forms, headings, screenshots, CSS/design tokens, interactions.
2. Browser/image search for visual pattern discovery.
3. GitHub for public repositories when implementation primitives may help.
4. Verify license before reusing source code.
5. Record the source and what principle was learned.

Never copy:
- proprietary source
- logos/brand assets
- marketing copy
- illustrations
- a distinctive layout pixel-for-pixel
- private/authenticated material without authorization

Use references as evidence for **principles**, then regenerate the design in the target product's own visual language.

Read `references/research-sources.md` and `references/source-license-matrix.md`.

### 4. Choose an experience grammar

Choose intentionally rather than defaulting to a generic centered form.

Useful grammars:
- **Product-preview split**: auth/setup on one side, a live-feeling preview of the destination/value on the other.
- **Focused canvas**: quiet background, one precise task per step, appropriate for high-trust or complex forms.
- **Outcome builder**: user choices immediately transform a preview/result as onboarding progresses.
- **Guided workspace**: enter the real app early; onboarding appears as contextual empty states, checklist, and coach marks.
- **Immersive brand moment**: high-emotion consumer/creative product with restrained motion and a strong transition into the app.
- **Mobile edge-to-edge**: thumb-reachable actions, minimal copy, native-feeling progress, keyboard-safe layout.

Do not choose a grammar because it is fashionable. Choose it because it reduces uncertainty and gets the target user to value.

### 5. Design the journey state machine

Use this default state model as a starting point, not a mandate:

`PUBLIC -> AUTH_CHOICE -> IDENTITY -> VERIFY? -> INTENT? -> MINIMUM_SETUP -> FIRST_VALUE -> ACTIVATED`

Optional branches:
- `INVITE_ACCEPTANCE`
- `EXISTING_ACCOUNT`
- `RECOVERY`
- `RESUME_INCOMPLETE`
- `SSO_ORG_DISCOVERY`
- `PAYWALL_OR_PLAN_SELECTION` only when commercially justified

Every state must define:
- user goal
- one primary action
- optional secondary action
- data requested and why
- validation/errors
- loading/pending
- success transition
- back/escape behavior
- resume behavior
- mobile behavior
- analytics event

### 6. Make it feel premium

Premium is coherence, not decoration.

Use:
- semantic design tokens for background depth, surfaces, borders, focus, success, warning, destructive, accent
- a small radius scale
- layered, restrained elevation rather than random shadows
- consistent typography hierarchy and optical spacing
- clear keyboard focus
- purposeful motion that explains state change
- skeleton/pending/success/error states with the same visual quality as the happy path
- a recognizable branded activation moment

Avoid:
- generic gradient blobs with no product meaning
- excessive glassmorphism
- full-screen carousels that delay value
- confetti for routine actions
- asking five profile questions before the user sees the product
- progress indicators that lie about remaining work
- decorative illustration that competes with the form

### 7. Create one signature moment

Each product should have one memorable first-run behavior tied to its value.

Examples:
- the split-screen preview becomes the actual workspace after signup
- user choices build a live recommendation while they answer
- a blank dashboard transforms into the user's first real result
- the activation checklist dissolves into normal navigation when complete
- a branded object/diagram gradually becomes useful product state

The signature moment must communicate product value. It is not a random animation.

### 8. Authentication quality gate

Read `references/auth-and-accessibility.md`.

At minimum:
- preserve password-manager/autofill compatibility
- allow paste
- use correct input types and autocomplete tokens
- support keyboard-only completion
- show clear errors without erasing input
- make verification resend/change-email paths obvious
- provide recovery and existing-account paths
- do not leak whether sensitive accounts exist more than the product's security model allows
- handle double-submit/idempotency
- preserve redirect/invite destination through auth
- do not add passkeys/SSO merely for visual novelty; use methods supported by the product

### 9. Prefer contextual onboarding over tours

A product tour is optional.

Use a tour only when:
- key controls are genuinely hard to discover in context
- the user can interact with the real product
- steps are short and skippable
- completion state is persisted
- it can be replayed from help/resources
- mobile placement remains usable

Prefer:
- strong empty states
- seeded examples
- a small activation checklist
- contextual hints at the moment of need
- first-task templates
- inline assistance

If a tour is justified, license-verified open-source primitives may be considered; see the source matrix.

### 10. Verify like a user

Do not call the work finished from code inspection alone.

Run proportionate proof:
- desktop and mobile browser checks
- keyboard-only path
- empty/error/loading/success states
- password-manager/autofill-friendly markup inspection
- signup -> verification -> destination continuity where testable
- returning login
- reset/recovery
- invite/deep-link preservation if applicable
- refresh/resume during setup
- reduced-motion behavior
- no overflow under mobile keyboard
- contrast/focus/target-size checks
- screenshots at representative states

For a real app, use existing Synapse Quality OS / browser-proof mechanisms when available.

## Required outputs

For a substantial FirstRun task, produce or maintain:
1. FirstRun brief
2. journey/state map
3. screen-by-screen behavior spec
4. component + token plan
5. microcopy
6. analytics map
7. implementation plan
8. verification evidence / unresolved risks

For a small fix, use only the subset needed.

## Originality rule

**Borrow patterns, not pixels.**

A result fails FirstRun Studio if a reviewer could reasonably describe it as "the Userflow/Lovable/Dribbble screen with our logo swapped in."

Synthesize multiple references, preserve the target product's identity, and create at least one product-specific interaction or activation moment.

## Definition of done

Read `references/quality-rubric.md`.

Do not claim "professional", "premium", or "finished" unless:
- critical auth/accessibility/recovery gates pass
- activation is clear
- required state coverage exists
- mobile is verified
- the result visually belongs to the product
- the first-run path reaches real value
- originality is defensible
- browser proof exists for a UI implementation
