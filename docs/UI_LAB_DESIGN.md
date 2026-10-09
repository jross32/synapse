# Synapse UI Lab — design reference and implementation contract

Status: approved concept, foundation investigation 2026-10-09; not yet complete.

## Visual reference / copied layout specification
Original conversation reference: dark premium cross-device QA dashboard illustration presented in ChatGPT on 2026-10-09. The generated/search-rendered picture is not exposed as a transferable local file or permanent URL via this connector, so DO NOT claim image bytes were saved. This document is the durable, reproducible design reference instead.

Layout: dark charcoal canvas; compact left navigation (Projects, Device Lab, Test Flows, Reports, Evidence); top project+URL selector and Run verification action; center primary live preview in device frame with responsive width/orientation chooser; side-by-side compact/large iPhone, tablet, and desktop previews; right inspector with actionable findings, severity, CSS selector, screenshot evidence and rerun controls; bottom tab strip for console/network/accessibility/trace, and before-versus-after visual diff. Premium restrained typography, generous spacing, no neon clutter. Clearly mark the real engine and evidence confidence of each preview.

## Audit of existing foundation
- Registered runnable UI Demo Studio offers recordings, benchmarks, mobile, accessibility, reliability, evidence and remediation briefs.
- Registered Playwright MCP supports resizing, DOM accessibility snapshots, interaction, screenshots, and console messages; inspect actual available names at runtime.
- Quality OS quality gates exist; open blocking gates are not to be waived by new tooling.
- Existing tools/iphone_safari_audit.py checks 375x812 and 430x932 via Chromium mobile emulation only; not real Safari.
- UI Forge browser_audit.js, visual target gate, Screen Monitor rubric, completion-contract skill already exist. Prefer composition over duplication.

## Standardized tool API target
ui_lab.open(project_id, url, device_profile, engine); ui_lab.inspect(session_id, checks); ui_lab.test_flow(session_id, flow_id); ui_lab.compare(baseline_id, candidate_id); ui_lab.report(run_id). Implement adapters to existing Playwright, screenshot evidence, UI Demo Studio and Quality OS before inventing a second runner.

## Verification matrix
Minimum: iPhone compact 375x812, iPhone large 430x932, tablet portrait 768x1024, desktop 1440x900; orientations as appropriate; Chromium and WebKit desktop emulation where runnable. Actual native iOS Safari requires iOS simulator/macOS or real-device browser service and must be reported unavailable otherwise. Native Safari VERIFIED must never be set by Chromium viewport simulation.

## Acceptance criteria
1. Every preview/evidence artifact records browser engine, platform, viewport, orientation, timestamp, URL, test flow and simulator/physical-device status.
2. Run navigation, tap/click, keyboard/input, file upload, modal, scrolling and responsive overflow checks with isolated test data.
3. Record screenshots, console errors, failed network calls, accessibility alerts, traces and diff thresholds; ensure no exposed auth secrets or uploaded private user data.
4. Report pass/fail/blocked/untested per check; on defects trigger AI repair and rerun; do not claim done when blocker remains.
5. UI command discoverability for workers and Verify UI action on every project; do not regress existing UI Demo Studio and Quality OS.
6. Initial pilot: ResellTogether My Closet on desktop + mobile; test navigation, photo cards, bottom bar, add/edit workflow and appearance in dark mode.
7. Tests and docs; use isolated feature changes, preserve concurrent dirty worktree, no daemon restart without coordination.

## Delivery phases
Phase 1 compose existing tool APIs, device profiles, screenshots, evidence and simple design dashboard. Phase 2 deterministic browser journeys, accessibility, visual diffs, QA reports. Phase 3 AI fix/test loop, release gate integration, actual device-provider bridge for native Safari.
