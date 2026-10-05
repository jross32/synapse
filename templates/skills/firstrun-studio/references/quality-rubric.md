# FirstRun Studio quality rubric

Score implemented first-run work on 12 dimensions, 0-5 each.

0 = absent/broken
1 = serious problems
2 = incomplete
3 = solid baseline
4 = polished
5 = exceptional and product-specific

## Dimensions

1. **Promise continuity**
   Landing-page promise and post-auth destination feel like one product and one story.

2. **Activation clarity**
   A measurable first-value event is defined and the path prioritizes reaching it.

3. **Friction discipline**
   Only necessary information is required before first value; optional setup is deferred.

4. **Trust**
   Security/privacy/terms/identity prompts are understandable and appropriately placed.

5. **Auth robustness**
   Login/signup/verification/recovery/existing-account/deep-link behavior is coherent.

6. **State completeness**
   Loading, empty, validation, failure, pending, success, retry, and resume states are designed.

7. **Accessibility**
   Semantic forms, keyboard, focus, target sizing, autofill/password managers, reduced motion, and readable errors pass.

8. **Responsive quality**
   Desktop/tablet/mobile work intentionally; software keyboard and small-height screens are checked.

9. **Visual-system coherence**
   Typography, spacing, depth, tokens, states, radii, elevation, and motion are systematic rather than one-off.

10. **Contextual guidance**
    The design teaches by doing; tours/checklists/hints appear only when useful and can be skipped/replayed appropriately.

11. **Originality / brand fit**
    The result belongs to the target product and includes a value-linked signature moment rather than copying a reference.

12. **Measurement / iteration**
    Important funnel events and drop-offs can be observed without invasive tracking.

## Critical gates

Regardless of total score, mark FAIL if any are true:
- primary auth path cannot be keyboard-completed
- password manager / paste is intentionally blocked without a justified accessible alternative
- user can get trapped with no recovery path after verification/reset failure
- destructive or duplicate submission can occur from normal double interaction
- mobile primary action is inaccessible due to overflow/keyboard
- the flow cannot reach real product value
- implementation substantially copies proprietary assets/layout/copy
- sensitive data/secrets are exposed in client UI/logging

## Result bands

- 54-60: exceptional
- 48-53: professional
- 42-47: strong but needs polish
- 36-41: usable baseline
- below 36: redesign/rework before calling it professional

For a "professional/impressive" claim, require:
- >= 48/60
- every dimension >= 3
- all critical gates pass
- real browser proof on desktop + mobile
