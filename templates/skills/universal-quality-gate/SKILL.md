---
name: universal-quality-gate
description: Discover and use Synapse's shared Quality OS browser-proof enforcement for every UI project; fail closed on missing visual evidence.
---

# Universal Quality Gate — Synapse Agent Skill

**Always load for Synapse-connected UI/frontend/color/layout/design work.** This is a discovery and operating guide to the existing Quality OS, not a separate scheduler or browser implementation. Use with `completion-contract` and `browser-ui-audit`.

## Where to find the implementation

- Canonical technical documentation: `docs/UNIVERSAL_VISUAL_QUALITY_GATE.md`
- Shared completion enforcement: `daemon/synapse_daemon/universal_visual_gate.py`
- Browser report validator: `daemon/synapse_daemon/visual_audit_ingest.py`
- API route: `daemon/synapse_daemon/routes_quality_os.py`
- Browser runner: `scripts/visual-qa.mjs`
- Runner and evidence registrar: `scripts/run_visual_qa_and_register.py`
- Quality OS storage and evidence: `daemon/synapse_daemon/quality_os.py`
- Regression tests: `daemon/tests/test_universal_visual_gate.py` and `daemon/tests/test_visual_audit_ingest.py`

## How an agent uses it

1. Read Synapse project AI context and the actual project/URL. Check existing Quality OS gates before changing code.
2. Inspect rendered DOM and computed CSS, then run `browser-ui-audit` on desktop, mobile, and narrow mobile. Capture screenshots, errors, contrast, and overflow.
3. For a Synapse-managed Agent Squad UI work item, run `python scripts/run_visual_qa_and_register.py APP_URL --synapse-url DAEMON_URL --subject-id WORK_ITEM_ID --output FRESH_OUTPUT_DIR`. Set `SYNAPSE_TOKEN` in the environment without logging it. The script submits the audit to `POST /api/v1/visual-audits/import`.
4. Check that the latest browser-proof evidence is PASS for **that exact work item** and that its artifact exists. The shared Agent Squad completion path refuses completion when a blocking quality gate is open.
5. Run separately authorized interaction tests, review actual screenshots, and test deployed/installed builds. A passing read-only visual smoke audit is not proof of every user journey.
6. If browser or account access is unavailable, mark verification **blocked/untested**, never passed. Do not waive quality gates just to get a green status.

## Important boundaries

The shared code currently enforces gates on Synapse Agent Squad UI work items. Other AI cases, manual tasks, and releases still need end-to-end integration. Imported JSON and screenshot paths are not cryptographically trusted; use a trusted daemon-owned runner before claiming tamper-resistant proof. Only Synapse-connected agents that load skills/context receive these instructions automatically; disconnected ChatGPT sessions do not.

## Discovery terms

universal quality gate, visual QA, quality OS, browser proof, CSS colors, mobile contrast, UI testing, screenshot validation, release verification, frontend acceptance, agent completion.
