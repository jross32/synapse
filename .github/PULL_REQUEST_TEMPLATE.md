<!-- Synapse PR template. The checklist mirrors AGENTS.md "Commit rules" + Rule #6 (E2E on version bump). -->

## What & why

<!-- One or two sentences: what changed and why. Link the ADR / roadmap item / review-inbox proposal if any. -->

## Changes

-

## Verification

<!-- How you proved it works. Be specific. -->

- [ ] `cd daemon && python -m pytest -q` green
- [ ] `npm run typecheck` (renderer + electron) green
- [ ] Live / E2E check where the change is observable (curl the endpoint, drive the UI, screenshot) — describe below
- [ ] New tests added for new routes / models / behavior (or explain why not)

## Docs & versioning (per AGENTS.md)

- [ ] Version bumped consistently (`package.json` + `pyproject.toml` + `daemon/synapse_daemon/__init__.py`)
- [ ] `CHANGELOG.md` entry added under the new version
- [ ] Docs synced as needed (`README.md`, `PROGRESS.md`, `docs/roadmap.json`, a new `docs/adr/*` for a real decision)
- [ ] No secrets / tokens / `.env` values committed

## Multi-AI coordination (if editing shared files)

- [ ] Checked `GET /api/v1/coordination/snapshot` and claimed a lane where relevant (see `docs/MULTI-AI-WORKFLOW.md`)
