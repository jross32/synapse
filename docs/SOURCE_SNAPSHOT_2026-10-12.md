# Synapse source snapshot — 2026-10-12

This document records a best-effort source-code snapshot taken from the live Windows development tree while other AI workers and builds were active. It is not a release, tested deployable package, database backup, device clone, or guarantee that in-flight edits are included.

## Baseline and source of truth

- Live working folder: `C:\Users\justi\synapse`.
- GitHub repository: `https://github.com/jross32/synapse`.
- Baseline branch: `snapshot/synapse-local-20261010`; parent checkout included two commits ahead of upstream at inspection.
- Snapshot made in an independent clone, not in the live working tree, to avoid staging or interrupting concurrent workers.
- Electron/package source version observed: `0.2.218`; active daemon version observed: `0.1.209`. **Do not interpret this Git snapshot as a successful daemon upgrade.**
- Running daemon port `7878`; dev-daemon handoff remains guarded due to previously observed conflicting listeners and metadata drift.

## Source areas changed since the prior snapshot

- Electron UI: dashboard, connected-brain/3D, navigation, profile, staff, AI coding and usage pages.
- Worker presence, catalog, Chrome companion/grouping, agent squads, shared AI context, active tasks, command/runtime usage and agent integrations.
- Device onboarding, transfer/workspace synchronization, storage provider placeholders, hybrid/local inventory/storage plumbing.
- Image generation, local image-engine groundwork, quality OS/visual gating, AI edit policy and related tests.
- Desktop updater, safe daemon preflight/handoff scripts, installer/download-site source, website redesign.
- Railway/account/staff and cloud cost monitoring features, related integration tests and operating docs.

This is a **work-in-progress inventory**, not certification that each feature works end-to-end.

## Verified evidence and open gaps from shared project records

- The Storage UI and inventory query were previously browser/typecheck-tested, but OAuth, cloud transfers, restoration and agent-granted storage access remained incomplete at that checkpoint.
- Chrome companion source was implemented; one logged-in ChatGPT worker smoke test was observed, **not** proven five-worker orchestration.
- Dev daemon source/version split and dual-listener migration require guarded handoff; no restart was done as part of this snapshot.
- Existing visual quality gates must be checked independently before claiming release-quality UI.
- Background agents may have changed files after the snapshot's per-file copy; compare the live source before any final release merge.

## What this snapshot intentionally excludes

- Local secrets, credentials, browser cookies/sessions, environment overrides and runtime databases.
- Generated installers/releases, packaged binary trees, huge build products, temporary probes, local screenshots and transient AI outputs.
- The locally modified `.synapse/image-assets.jsonl` provenance catalog, which may embed machine-specific state.

## Follow-up procedure

1. Review this commit's contents for secrets and ensure GitHub branch equality to the commit SHA.
2. Run `npm run typecheck` and focused backend tests against a consistent dependency installation; resolve any failures without claiming they passed.
3. Reconcile existing branches and concurrently active workers before merging to another branch.
4. Verify browser UI, local daemon migration, authenticated worker orchestration and production build separately.
5. Keep release binaries/artifacts in an explicitly controlled release channel, not this source snapshot.
