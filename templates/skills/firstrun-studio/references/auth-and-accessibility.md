# Authentication and accessibility contract

Target WCAG 2.2 AA for production first-run surfaces unless the project has a stricter standard.

## Authentication markup

Use semantic labels and native inputs.

Recommended autocomplete tokens where applicable:
- email identity: `email`
- account name: `username`
- signup/reset password: `new-password`
- login password: `current-password`
- verification code: `one-time-code`

Do not:
- block paste
- block password-manager autofill
- clear all fields after one validation error
- require a cognitive puzzle without an accessible alternative/mechanism
- make an icon-only reveal-password button unlabeled
- make users re-enter information already supplied when it can safely be retained

## Method selection

Choose auth methods based on product and backend capability:
- existing SSO/OIDC when the app already supports it
- passkeys/WebAuthn when the security/product architecture supports them
- magic links / OTP where appropriate for product risk and user base
- password flows when needed, implemented password-manager-friendly

Do not bolt on a new provider simply to make onboarding look modern.

## Focus and keyboard

- the entire path must be completable by keyboard
- focus must remain visible and not be obscured by sticky headers, dialogs, or overlays
- modal focus must be trapped correctly and restored on close
- pressing Enter should submit where expected without double-submit
- Escape behavior must be intentional
- use visible focus styling with adequate contrast
- tour overlays must never strand keyboard focus

## Targets and touch

Use at least WCAG 2.2 AA minimum target sizing/spacing; prefer approximately 44x44 CSS px for important touch actions when layout permits.

On mobile:
- keep primary actions reachable above/beside the software keyboard
- never hide validation behind the keyboard
- account for safe areas
- avoid side-by-side fields when they become cramped
- avoid tiny "skip" and "back" hit targets

## Errors

Each error state needs:
- specific human wording
- field association when field-level
- a preserved user input state when safe
- an action to recover
- screen-reader announcement for dynamic errors where appropriate

Do not rely on color alone.

## Verification and recovery

Verification screens should include:
- which destination received the code/link, partially masked if appropriate
- change address/identity action when safe
- resend with honest cooldown/progress
- expiration handling
- pasted full-code support
- deep-link handling when the user returns from email/browser

Recovery should preserve the original intended destination where safe.

## Reduced motion

Honor `prefers-reduced-motion`.
Motion must not be necessary to understand completion or navigation.
A signature activation transition must have a reduced-motion equivalent.

## References

- WCAG 2.2: https://www.w3.org/TR/WCAG22/
- Accessible Authentication: https://www.w3.org/WAI/WCAG22/Understanding/accessible-authentication-minimum.html
- WebAuthn Level 3: https://www.w3.org/TR/webauthn-3/
- MDN autocomplete: https://developer.mozilla.org/en-US/docs/Web/HTML/Reference/Attributes/autocomplete
