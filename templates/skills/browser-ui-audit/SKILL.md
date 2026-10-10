# Browser UI Audit / Unified Visual QA

Synapse has a reusable, isolated browser visual auditor. Use **scripts/visual-qa.mjs** before claiming UI complete. It uses Chromium directly via Playwright under the hood but does **not** require the interactive Playwright MCP browser session.

## Run

```powershell
node scripts/visual-qa.mjs http://127.0.0.1:5215 .tmp-visual-qa
```

It tests three isolated viewports (desktop 1365x900, mobile 390x844, small mobile 320x740) and outputs `report.json` and full-page PNG screenshots. It gathers computed foreground/background colors, potential low-contrast text, visible controls without names, JavaScript errors, DOM out-of-viewport elements, and horizontal overflow. Each viewport creates and tears down its own browser context and process, with bounded navigation, screenshot, and browser cleanup. Check the report; `failureCount=0` covers errors/overflow only, **not** all accessibility, workflows, or visual fidelity. Contrast candidates need review because translucent surfaces and overlays can skew computed CSS ratios.

**Important scope:** This runner is a read-only visual smoke audit. It does not authenticate as the user, submit forms, click state-changing buttons, test uploads, crawl protected routes, or compare against an approved screenshot. Those require separate authorized disposable-account interaction tests and approved baseline files. Do not claim such tests passed. Existing `scripts/ui-audit.mjs` remains as a separate public-link crawler.

For full end-to-end UI evidence, add explicitly authorized scenarios to a test suite, launch each as an isolated process, include screenshot/reference comparison with image diff tolerances and inspect failed regions, and persist results. A web-scraper tool can orchestrate browser rendering, but real visual rendering still requires a browser engine and no timeout solution guarantees zero failures. Preserve unrelated concurrent changes in the Synapse working tree.
