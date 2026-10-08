# Desktop OAuth workflow: reusable agent runbook

## Purpose
Safely configure a local desktop OAuth client, request only required scopes, and verify a real API action. This runbook is for any Synapse agent and is not specific to Gmail.

## Preconditions
- Verify project, user account, app ownership, and intended scopes.
- Confirm browser session is already signed in; never request passwords or read authentication cookies.
- Ensure local client credential and token files are excluded from git, logs, and tool responses.
- Acquire exclusive desktop input control and check the actual foreground window.

## Interaction and proof loop
1. Capture a screenshot and identify the target control's screen-space rectangle.
2. Click once using verified absolute coordinates. A successful input API return does not prove UI activation.
3. Capture a fresh screenshot; compare title, URL, visible form, and focus. If unchanged, do not repeat blindly.
4. Fall back to keyboard navigation (Tab, Shift+Tab, Enter, Space) with a screenshot after each meaningful transition.
5. When both input paths fail, diagnose display scaling, window-local versus screen coordinates, foreground HWND, and input-helper integrity level. Test on an innocuous local UI before retrying the OAuth form.
6. Never use raw browser session cookies or bypass user consent to replace OAuth.

## OAuth flow
1. Create consent branding and choose the correct audience; add the owner's test user when applicable.
2. Create a Desktop application OAuth client and register the loopback callback supported by the app.
3. Download client JSON into a private local config directory without printing its contents.
4. Start the local callback server, launch the authorization URL, and let the user complete Google consent.
5. Verify callback state, scope, and token persistence; redact tokens and secrets in all logs.
6. Execute the requested real API action, confirm its returned ID, and verify output/attachment metadata.
7. Record a durable checkpoint, exact tests, and any unresolved blocker. Never claim a send succeeded from a UI click alone.

## Reflex failure notes (2026-10-07)
- Chrome HWND 6162610 showed Google Auth Platform / Clients. Reflex click returned success without navigation.
- Keyboard Tab then Enter **did** advance to the Google Auth Platform branding form.
- Reflex helper on localhost:11309 returned success for key and type operations, but text did not visibly populate the app name field; successful transport is not proof of actual keyboard delivery.
- A mouse click intended for the form instead opened the Google Cloud top-right overflow menu. Screen/window coordinate mapping must be tested.
- As of this checkpoint, OAuth client.json and token.json were absent. The screenshot JPEG existed locally. Gmail sending was not verified.

## Verification matrix
- Input: foreground, focus, click target, typing into harmless test field, keyboard fallback.
- OAuth: branding saved, client downloaded, consent completed, exact scope authorized.
- Connector: initialization, status, token refresh, allowlisted attachment access.
- Delivery: API success ID, recipient, subject, MIME attachment filename/type and byte count.
- Regression: desktop/mobile catalog navigation, build, and tests without overwriting concurrent workers' changes.
