# Synapse Universal Visual Quality Gate — implementation status

This implementation extends existing Quality OS; it does not replace the UI Forge or its browser skill.

## Active source integrations
- Agent Squad UI work-item creation creates a blocking universal-visual-qa gate.
- Agent Squad handoff/status transition to COMPLETED invokes the shared gate check.
- A PASS requires the latest browser-proof evidence for the same work item, a locally readable report artifact, and visual_qa_passed=true.
- Visual audit import API: POST /api/v1/visual-audits/import (authenticated by the daemon's existing API middleware). Body: subject_type, subject_id, report_path.
- Ingestion validates three viewports, clean console/JS/contrast/overflow, successful HTTP statuses, and existing screenshots. Failed audits record FAIL evidence and do not clear completion.
- CLI helper scripts/run_visual_qa_and_register.py runs the read-only browser audit and registers its report; requires SYNAPSE_TOKEN, --synapse-url, --subject-id, --output, and a target URL. It uses no paid AI tokens.
- Browser audit scripts/visual-qa.mjs now fails on contrast candidates and console errors as well as other failures.

## Caveats
- Not a full universal policy yet: other work item types, autonomous agents, AI cases, release/deploy gates and manual completion paths need integration.
- Import requires a trusted, locally generated report. A user or agent could spoof JSON or screenshots; for high assurance, use a trusted daemon-owned runner and cryptographically bind evidence to the task/revision.
- Color sampling currently uses effective CSS backgrounds but does not correctly model all gradients, transparency, images, pseudo-elements or overlapping surfaces; manual screenshot review remains mandatory.
- Authenticated UI and interaction flows need their own scenarios.
- Existing open gate waivers and external status paths require further audit.
- Running daemon, installer and production release have not been updated/verified by these source edits.

## Regression commands
Run with the Synapse virtual environment:
- python -m pytest daemon/tests/test_visual_audit_ingest.py daemon/tests/test_universal_visual_gate.py daemon/tests/test_quality_os.py -q
- node --check scripts/visual-qa.mjs
- python -m py_compile scripts/run_visual_qa_and_register.py

Do not claim release-ready or 100% site coverage on these tests alone.

## 2026-10-12 additional enforcement and installer readiness
- Shared gate helper now supports subject_type `project_backlog` in addition to `agent_work_item`; UI-related project backlog creation opens a blocking gate and setting DONE requires passing scoped browser evidence. Existing unrelated/non-UI backlog items remain unchanged.
- `package.json` extraResources includes the registration CLI `scripts/run_visual_qa_and_register.py`; `docs` filter includes this runbook; all templates including the implicit `universal-quality-gate` skill are already bundled. The frozen daemon bundle must be rebuilt to incorporate backend Python changes; package configuration alone is NOT a verified installer artifact.
- Browser audit run on the actual local Vite Synapse frontend `http://127.0.0.1:5173`: desktop passed the smoke check, mobile 390px and narrow mobile 320px each reported 30 offscreen elements; viewport document scrollWidth did not exceed viewport width. See `.tmp-universal-gate-render-check/report.json` and three screenshots. Audit correctly failed; determine whether these elements are intentionally clipped/hidden or genuine UI defects before clearing it.
- Non-squad AI case and coder-workspace terminal statuses, deployment gates, and manually recorded completion are NOT yet covered. A running-daemon reload and new Windows installer build/installed execution have NOT been verified.
