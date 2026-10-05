# UI Demo Studio Validation Ledger

This file records concrete acceptance and real-product evidence for the bundled Synapse UI Demo Studio tool. It is not a claim of formal WCAG conformance or user-research validation.

## v0.4.0 / Scorecard 3.2

Acceptance suite: `ui-demo-studio-acceptance-v2`
Evidence directory: `data/ui-demo-studio/acceptance-20260909-122605971/`
Result: **6 passed / 0 failed**.

Browser cases:

- Healthy automatic tour: 95 overall, 94 UX, 3 captured scenes, Screencast 8.52s vs 8s target (+0.52s).
- Beautiful but inert: UX 0, overall 39, `ux.no_interaction` hard gate.
- Disabled-only controls: UX 0, overall 39, `ux.no_interaction` hard gate.
- Invisible keyboard focus: `a11y.keyboard_focus` = 65 with 0 detectable focus indicators.
- Trapped modal: UX 34, overall 59, `ux.dialog_keyboard` = 55, `ux.trapped_dialog` hard gate.
- Real Synapse detached action: launcher 2353ms, completed overall 95, Screencast 8.04s vs 8s target (+0.04s).

Real-product calibration using existing captured runs re-benchmarked with Scorecard 3.2:

- Stock Hunter (run `20260909T053826Z-ee4d8a`): overall 95, UI 92, UX 97, Accessibility 97, keyboard focus 98. All 12 sampled controls were reached and had detectable focus indication; 11/12 were initially unobscured.
- WhatIf Web (run `20260909T053948Z-37de2f`): after calibrating the focus-scroll settle window, overall 95, UI 92, UX 99, Accessibility 93, keyboard focus 100. All 20 sampled controls were reached, visibly focused, and visible after focus-scroll settled.

## Methodology guarantees proven by regression tests

- Missing telemetry is not converted into free 100s or fake 0s.
- Not-applicable metrics do not appear as remediation failures.
- Failed benchmark interaction probes stay unmeasured rather than punishing product UX.
- Beautiful-but-inert and disabled-only apps cannot receive high UX grades.
- Trapped dialogs impose a hard UX/overall cap independent of visual polish.
- Before/after deltas require matching scorecard methodology, target, journey, viewport, and duration.
- Keyboard focus visibility/reachability and modal Escape/focus containment are browser-observed evidence.
- Screenshot capture failure is nonfatal: video + DOM evidence survives and the missing PNG is explicitly recorded.

## Interpretation boundary

The deterministic scorecard is laboratory evidence. Visual hierarchy, taste, brand polish, perceived affordance, motion quality, and first-time-user judgment still require inspection of the actual video/screenshots and remain explicitly separated from deterministic telemetry.
