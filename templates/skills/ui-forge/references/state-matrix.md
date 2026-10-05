# UI Forge State Matrix

`state_matrix_runner.mjs` turns critical UI-state coverage into an executable browser contract.

## Purpose

Use it for data-driven or stateful screens where completion depends on more than the happy path. Typical required states are loading, empty, error, success, disabled, and recovery. A required state is not proven until it passes every configured representative viewport.

## Contract

The matrix is JSON with schema `ui-forge-state-matrix-v1` and contains:
- `base_url`
- `required_states`
- optional custom `viewports`
- `states[]`, each with an `id`, optional routes/actions, and required assertions

Each state runs in a fresh browser context so storage, network mocks, and DOM state cannot leak between cases.

## Network-state proof

Use state-local `routes` to create deterministic API conditions. Routes may return one response or a `sequence` of responses. Sequences are intended for recovery proof, such as:
1. first `/api/items` request returns 500,
2. the UI presents a visible Retry action,
3. Retry causes the second request to return success,
4. the error surface disappears and the recovered data surface is asserted.

A mocked route that explicitly declares a >=400 response may generate the browser's normal `Failed to load resource` console entry. UI Forge records that entry under `expected_failure_console_errors` and does not treat it as a regression. Unexpected console errors and page errors still fail the case.

## Actions

Supported bounded actions include click, fill, check, uncheck, hover, focus, key press, wait, and reload. Prefer deterministic selectors and explicit post-action assertions.

## Assertions

Supported assertions include visible/hidden, exact/contained text, input value, attribute value, enabled/disabled, checked/unchecked, element count, and URL substring.

Assertions should prove the user-visible state, not merely internal implementation flags.

## Objective audit

Every case runs `browser_audit.js` unless explicitly skipped. Horizontal overflow, missing accessible names, unlabeled controls, missing image alt text, and heading-level jumps are blockers. Console/page errors are also blockers except declared mocked network failures as described above.

## Completion rule

For a substantial data-driven UI, include every relevant required state in the matrix and require all of them to pass on every configured viewport. Missing required states fail validation before the browser run starts.

The matrix is evidence, not a design generator. If a state fails, repair the product and rerun the matrix rather than weakening assertions or deleting required states.
