# Synapse Visual QA — default for all Synapse-connected AI web/UI development

**Implicit/default invocation:** Apply automatically whenever an AI using Synapse creates, redesigns, fixes, reviews or releases a user-facing website/app UI. This extends the existing Completion Contract, Visual Fidelity Loop, UI Lab and Quality OS. Do not create competing schedulers or assume that a tool registration alone guarantees execution by disconnected external agents.

## Mandatory visual smoke gate

From Synapse source directory run:

```powershell
node scripts/visual-qa.mjs http://127.0.0.1:5215 .tmp-visual-qa
```

Replace the example URL with the actual target and use a fresh artifact directory per run. The runner launches its own isolated Chromium browser sessions at desktop (1365x900), phone (390x844) and narrow phone (320x740). It records actual CSS colors/backgrounds, estimated contrast risks, horizontal overflow, offscreen elements, accessible control-name candidates, JavaScript errors and full-page PNGs in report.json. Each viewport is isolated and browser cleanup is bounded. Review screenshots; verify contrast candidates manually, especially when elements are translucent or gradients. A zero failure count does NOT mean complete UI/UX readiness.

## Isolated authenticated E2E runner

For explicitly authorized test scenarios (disposable account/workspace), create a JSON manifest and run:

```powershell
node scripts/visual-qa-suite.mjs path/to/test-manifest.json artifacts/visual-qa-e2e
```

Manifest shape:

```json
{
  "baseUrl": "http://127.0.0.1:5215",
  "authorizedTestEnvironment": true,
  "scenarios": [{
    "name": "Create draft",
    "path": "/",
    "viewport": {"width": 390, "height": 844},
    "allowInteractions": true,
    "storageStatePath": "path/to/authorized-test-session.json",
    "steps": [
      {"action": "expectVisible", "selector": "#app"},
      {"action": "click", "selector": "#addButton"},
      {"action": "fill", "selector": "#title", "value": "Test garment"},
      {"action": "upload", "selector": "input[type=file]", "file": "test-fixture.jpg"},
      {"action": "expectText", "selector": "#status", "text": "Ready"}
    ],
    "baseline": "approved-reference.png",
    "requireVisualMatch": true
  }]
}
```

This example is a schema illustration, not a verified ResellTogether selector inventory. Use actual selectors/fixtures. Supported steps: click, fill, upload, check, press, expectVisible, expectText, expectValue, expectUrl, waitFor and screenshot. Mutation-capable actions refuse to run unless BOTH `authorizedTestEnvironment` and `allowInteractions` are true. Each scenario launches independently with a process watchdog, records screenshot, errors, colors, overflow and step evidence. `baseline` invokes `tools/ui_lab_reference_compare.py` (no silent resize). `requireVisualMatch` without baseline returns BLOCKED. The runner does not create login credentials or claim the owner's existing logged-in session. No scenario means no E2E proof.
## Additional required acceptance gates

1. **Authenticated routes:** use a disposable authorized test account and test workspace. Enumerate actual screens, dialogs, empty/loading/error states and both supported languages. Do not reuse the owner's data for destructive actions.
2. **Interactions:** exercise representative buttons, links, keyboard/focus actions, forms, photo uploads and workflow transitions using independent short-lived browser jobs. Verify server-side effects and permission failures. Record untested actions rather than claiming they work.
3. **Visual fidelity:** only compare against approved screenshot assets if the original bytes are accessible, and call `tools/ui_lab_reference_compare.py` to produce difference/overlay and threshold evidence. Do not infer that a verbal design or ChatGPT-only image has transferred to Windows.
4. **Errors:** review route/network/console errors, usability at narrow mobile, contrast findings, and Quality OS blockers. If a browser job times out, mark that job blocked, record evidence, recover or retry with a bounded new session; never convert a timeout into a pass.
5. **Release:** report exact tests, artifact paths, pass/fail/untested matrix and revision. Do not mark complete unless full acceptance and relevant quality gates pass.

The scraper is useful for lightweight structure, asset and route checks, but **real color/layout measurement and screenshots still require a browser engine**. This skill is available to Synapse-connected AIs that retrieve installed skills; it cannot silently change disconnected ChatGPT, Claude, Codex or other sessions.
