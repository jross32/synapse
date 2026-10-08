---
name: desktop-automation-studio
description: Reliable desktop interaction, setup and onboarding automation, including Reflex mouse and keyboard diagnostics, screenshot-backed proof, provider authorization boundaries, and safe reusable UI workflows.
---

# Desktop Automation Studio

Use when an agent needs to configure a desktop app, navigate a setup wizard, repair desktop input, install or connect an integration, or verify a GUI action.

## Activation event
A real UI action produces independently observed evidence (changed form state, navigation, saved record, API receipt), not merely a successful input-tool response.

## Method
1. Inspect the app, window geometry, current focus, and visible state before acting. Obtain exclusive control and respect the user's pause or emergency stop.
2. Plan the smallest reversible action; never assume a successful click or keystroke changed the target.
3. Perform one action, then take a fresh screenshot and verify the exact expected change.
4. If no change, compare screen coordinates to window-client coordinates, DPI scaling, active HWND, overlay interception, and keyboard focus. Test in a harmless local field.
5. Fall back to Tab/Shift+Tab/Enter/Space with focus verification. Never repeat blind clicks in a loop.
6. For authentication, let the provider handle user consent. Do not capture passwords, tokens, cookies, recovery codes, or print client secrets.
7. Store credentials only in the approved private local path. Request the least privilege; use explicit test users where applicable.
8. Confirm the final state through a separate status/API check and a real end-to-end test. Distinguish configured, authorized, and verified.
9. Record steps, screenshots or safe hashes, failure diagnosis, and a durable handoff. Avoid changing concurrent workers' files.

## Stop and recovery
- If a control is unresponsive after two verified attempts, diagnose rather than hammer it.
- If the screen changed unexpectedly, stop and recapture.
- If consent or user approval is required, wait for the user to approve in the provider UI.
- Never mark an external side effect complete without a provider receipt.

## Reference
See `references/desktop-oauth.md` for an example-specific failure and verification checklist.
