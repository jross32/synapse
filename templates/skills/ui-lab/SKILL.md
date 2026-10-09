---
name: ui-lab
description: Use Synapse UI Lab whenever implementing, reviewing or verifying web/mobile UIs, visual regressions, device responsive behavior, screenshots, or interactions.
---

# Synapse UI Lab — shared AI skill

All Synapse-connected AI workers should load this skill for UI work. Pair with UI Forge, UI Demo Studio, Screen Monitor, Completion Contract, and Quality OS; never duplicate those systems.

## Live tooling

`python tools/ui_lab_matrix.py URL --output artifacts/ui-lab/RUN --engine chromium`

For targeted runs use `--profile iphone-compact` or `--profile iphone-large` and `--timeout-ms 8000`. Run on the Synapse host through its authenticated command tool. Existing Playwright MCP browser tools support navigation, DOM inspection, clicks, keyboard, screenshots, console, upload and viewport resizing; discover their exact names and schemas at runtime before using.

## Required evidence

Run compact iPhone 375x812, large iPhone 430x932, tablet portrait 768x1024, desktop 1440x900. Evaluate viewport overflow, errors, content visibility, interactive user journeys, keyboard focus, network failures, screenshots and before/after diffs. Save artifacts in a per-run folder with a machine-readable report and explicit browser platform/engine/device provenance. Confirm accessibility and privacy and Quality OS blocking gates. Do not turn a passing HTTP/overflow smoke result into a claim that visual or interaction QA passed.

## Browser identity must be truthful

Chromium mobile viewport emulation is NOT real iPhone Safari. Playwright WebKit desktop is NOT native iOS Safari. Native iOS Safari verification requires a genuinely connected physical iPhone browser or iOS simulator with trusted execution and evidence; report `blocked` if absent. Never synthesize or waive native-device results.

## Visual baseline and report contract

Use `docs/UI_LAB_DESIGN.md` for the visual layout/reference and acceptance requirements. Compare baseline and candidate only on the same viewport/engine with stable test data, mask dynamic sensitive regions when necessary, and retain threshold and proof. Report findings with severity, screenshot path, exact navigation step/selector, reproduction and fix/retest result. Disclose missing checks. Quality OS open gates remain open until independently passing evidence is recorded.

## Project UI integration

Provide a visible Verify UI control on each project, and eventually the UI Lab dashboard with device previews, test flow selector, screenshot gallery, defects panel, console/network tabs and evidence history. Do not overwrite concurrent dirty UI files without inspecting and coordinating.

## Progress status

Current baseline: commits 6d2d736 and ca06962; 4/4 Chromium viewport smoke checks passed on local Synapse UI with screenshot/report artifacts in `artifacts/ui-lab-matrix-v2`. Graphical dashboard, project Verify UI, interaction automation, AI defect inspection, visual diff, real Safari provider and Quality OS automated integration are NOT independently verified as complete. Work tracked in Synapse squad d436f07a5443. Always read current context rather than treating this historical status as live.
