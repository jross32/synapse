# EchoTwin visual benchmark → reusable Synapse UI pipeline

Owner-approved visual direction: premium near-black voice assistant/digital twin UI, cyan/violet luminous details, expressive waveform, sophisticated responsive layouts. Reference pictures appeared in ChatGPT UI and are not available as source files to Synapse; do not assert exact pixel reference matching until explicit image assets are acquired.

## Reusable producer route
1. Acquire approved visual reference image(s), hash and register their provenance and permitted usage. Persist at project-scoped visual reference path.
2. Decompose into design tokens, layout, nav, feature regions, and image/3D asset slots.
3. Probe Image Studio provider separately from installed/runnable status. Log readiness/errors; never fabricate generated images. Route abstract 3D artwork/device mockups to Blender Studio where quality fits; do not downgrade photoreal scenes to CSS placeholders.
4. Use UI Forge and Asset-Led Product Workflow with manifests for production assets, editable sources, version hashes, responsive crops and accessibility.
5. Capture the actual running app via UI Lab/Playwright at 375x812, 430x932, 768x1024 and 1440x900; exercise real controls, auth and voice permissions, keyboard, overflows, below-fold, and nav.
6. Compare reference vs screenshots for hierarchy, spacing, iconography, typography, images, missing sections and task flows. Iterate until acceptance gates pass; record discrepancies/repairs.
7. Verify native iOS Safari on real device/provider separately; Chromium emulation does not count as native Safari proof.
8. Run tests and deploy verification; register proven improvements as versioned globally discoverable packs, not just EchoTwin custom scripts.

## Current blockers / required verification
- Image Studio exists but EchoTwin project context reports generator provider not configured; investigate with a real generation request and provider diagnostics before accepting.
- ChatGPT reference images not transferred; visual target is textual until imported and hashed.
- AI runtime status 2026-10-09: Claude OAuth expired, Codex/Copilot/Gemini quota ledger exhausted; local usable but unreliable. Do not falsely claim autonomous worker execution.
- Global Synapse tree has concurrent uncommitted changes; isolate patches, don't restart daemon or stage unrelated changes.

## Initial acceptance evidence
For each UI surface: source screenshot, app screenshot, visual discrepancy report, asset manifest, browser result/log, regression tests, native Safari status, Git revision, owner decision. No production-ready claim on incomplete gates.
