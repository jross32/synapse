# Synapse Staff HQ — Creator & Revenue Expansion

Status: **SOURCE IMPLEMENTED / INTEGRATION TESTED / NOT RELEASED** (October 10, 2026).
Owner brief: one AI employee system usable *inside Synapse* and from an optional
companion Staff HQ window. Money-making support is the priority; streaming,
content production and social distribution should ultimately become a pipeline.

## One truth store, two presentation surfaces

- Existing My AI Staff page: `renderer/pages/Staff.tsx` (unchanged employee workflows)
- New HQ: `renderer/components/StaffHQWorkspace.tsx`
- Entry within Staff: **Open Staff HQ**; **Original Staff view** returns to original page
- Optional pop-out: **Pop out** opens the same renderer with `?staff_hq=1`.
  `electron/main.ts` only allows a companion popup for the exact same renderer
  document with that parameter, using Electron isolation/preload and no Node
  integration. Other origins cannot use this popup exception.
- **No separate employees database, authentication service, or duplicated API.**
  Both surfaces use `renderer/lib/staff-client.ts` and existing Synapse
  `/api/v1/staff` authenticated routes.

## Staff organization

Preserved: Maya (Growth), Adrian (Business Finance), Sofia (Marketing), Jordan
(Sales), Riley (Research), Marcus (Product).

Added by `daemon/synapse_daemon/staff_hq_catalog.py` idempotent seed:
- Lena — personal money adviser, advice-only; distinct from Adrian
- Eli — live-stream technical director and creator coach
- Nova — video production, clips and post-production
- Zoe — social media operations and community
- Iris — creative/brand and thumbnails/overlays
- Felix — partnerships, sponsorship and affiliates
- Tess — chief of staff, project handoffs, personal priorities
- Sam — customer success, support and onboarding

Every new person has role + distinct personality + specialty/goals + safe default
authority + KPI placeholders + staff responsibilities + in-app channel + daily
review trigger (created **disabled**) + approval-first sensitive permissions.
Idempotent seeding does not overwrite a member's edited status or profile.
Existing employee records are never duplicated.

Keyword routing in `staff_operations.py` recognizes the eight specialists
in ordinary task descriptions; explicit `@handle` routing remains supported.

## Permissions / truthfulness

Staff-level `advise_only`, `prepare_for_approval` and `act_within_limits`
are broad policy settings, not credentials and not permission to perform
sensitive operations. New staff have explicit `ask` entries for camera,
microphone, screen_capture, obs_control, account_access, publish, send, spend,
transfer, trade, credential_change, public_broadcast.

Money figures remain unknown until connected to authorized verifiable data.
No stock trades, transactions, account edits, posting, emailing, uploads or
broadcast changes are initiated by the new UI.
No credentials should be logged; OBS password is kept in local component
state for only the handshake and then cleared.

## Proactivity that really runs (and what does not)

`staff_hq_proactivity.py` is a lightweight scheduler integrated with the daemon
startup/shutdown. Every 15 min it checks **only opted-in** daily review triggers.
A due trigger appends a source-labeled `proactive_review_due` staff event in
Synapse's existing event table with an atomic `last_run_at/next_run_at` checkpoint,
preventing duplicate reminders. Minimum frequency is one per 24 hours per trigger.
Users enable/pause triggers from Staff HQ; REST PATCH
`/api/v1/staff/{staff_id}/triggers/{trigger_id}` accepts `{ "enabled": true|false }`.
Only schedule triggers with the supported daily cadence may be enabled.

This is an in-app **review nudge** and does not call a model or dispatch workers.
It is **not** a complete autonomous employee planner. Users must explicitly
start/create an assignment through existing staff routing/council workflows.
A real continuous model-driven loop needs budgeting, quiet hours, dedupe,
lease/recovery, permission checking, provenance and model-ready runtime proof.

## Creator Cockpit (Eli)

- Explicit opt-in camera preview via browser media permission; video only.
- Explicit opt-in screen preview; browser selects surface.
- Both are local-only video elements; **no recording / remote upload / AI vision**
  occurs by using the preview.
- Stop each capture or Stop all. Unmount stops tracks.
- OBS Studio 28+ WebSocket v5 local connector: connect with temporary password;
  authenticated SHA256 challenge-response; read `GetSceneList` and
  `GetStreamStatus`; only user-clicked `SetCurrentProgramScene` scene switches.
  No stream start/stop, settings changes, implicit credential persistence.
  Actual OBS integration needs real OBS installation + authenticated handshake
  and live scene-change verification before marking the connector proven.
- The UI clearly labels not-yet-connected AI live vision, live voice, media edit
  queue, and streaming-assistant capabilities.

OBS primary reference:
https://github.com/obsproject/obs-websocket/blob/master/docs/generated/protocol.md
Official remote setup: https://obsproject.com/kb/remote-control-guide

## Workflow surface

Staff HQ shows source-backed team counts/actual working state, filtered roster,
personal money desk vs business finance, briefing attention inbox, read-only
employee details/goals/KPIs/permissions/triggers and direct staff conversation.
A council action creates linked Synapse squad work items for a selected project
and objective. It **does not auto-launch** agents or make external commitments.
Conversation uses the current staff chat runtime and surfaces actual failures.

## Checks so far

Focused new tests (6 passed):
`daemon/tests/test_staff_hq_catalog.py`
`daemon/tests/test_staff_hq_proactivity.py`
`daemon/tests/test_staff_hq_api.py`

- Seed 14 with six preserved, idempotent, safe permissions, disabled triggers,
  unpopulated KPIs and edited staff continuity.
- Natural task routing to all eight specialists.
- Opt-in due/paused reminder receipts, no duplicates and wrong-staff refusal.
- REST GET roster/profile/dashboard/briefing and PATCH scheduled reminder.
- Frontend fast bundle check via esbuild: OK (~45KB).
- New TS/TSX and Electron files parsed via esbuild: OK.
- Python py_compile and git diff --check: OK.

**Not yet proven:** full TypeScript typecheck (timed out under resource pressure),
real Electron popup, OBS handshake with live OBS, camera/screen permissions on a
physical device, Playwright UI E2E, compiled release/installer smoke, GitHub
commit/push, real proactive model worker loop, 24/7 reliability.

## Deployment blocker / preservation

Installed Windows `synapse-daemon.exe` serves version 0.1.212 with
`GET /api/v1/staff` HTTP404, while development source returns HTTP200 via a
TestClient. Thus Staff HQ won't be functional in the installed build until the
staff foundation and these additions are included in a coordinated packaged
release. Prior local build attempts under <1GB free RAM failed; do **not**
restart live daemon / overwrite installed EXE or stage all dirty files.
Other writers own untracked staff foundation modules and unrelated work.

Release acceptance: source/packaged parity; full team API 200 + security token
guard + existing six + eight new staff; prior tests; TS typecheck; desktop/mobile
QA; OBS direct connection test with user's permission; safe restart after worker
quiescence; verified PID/code/version; rollback on failure.

## Next development milestones

1. Real person-to-person staff conversation/voice experience, interruption
   controls, scheduled model execution only when budgeted/authorized.
2. Eli can *with explicit session consent* receive camera/screen frames for
   actual AI observations and natural speech coaching (not implemented).
3. Connect OBS status, scene and audio meters with robust reconnect and
   per-action authorization, while broadcasts remain explicit user commands.
4. Studio: video recording/import, clip marks, transcription, editable cuts,
   generated captions, export receipts, Nova handoff.
5. Graphics: reusable brand kit, Iris prompts/assets from connected image
   generation, overlay templates, thumbnail comparisons.
6. Zoe: authorized social account connections, post calendar, approval queue,
   receipts, platform policy-compliant publish paths and analytics.
7. Felix/Sam: lead/partnership and support case objects with consented
   account access and outbound approvals.
8. Lena/Adrian: opt-in verified personal/business financial connectors,
   cash-runway/ROI dashboards, no trades or financial movements.
9. True autonomous employee execution: durable worker leases, budgets,
   idempotent events, human approvals, quiet hours, in-app/mobile alerts,
   automatic resumability, measurable user/business outcomes.
10. Ship shared Staff HQ source into installed Windows release with isolated
    build, rollback and live tests after hardware resources recover.


## Incremental functionality added after initial design

- **Staff assignment panel**: select project, assign a direct job to an
  individual employee through existing `summonStaff`. This creates a genuine
  Synapse squad and work item, **not a launched worker**. Change personal
  `authority_policy` in the same panel; changing to `act_within_limits`
  requires a confirmation, while sensitive permissions remain ask-by-default.
- **Creator moment markers**: an owner-started session clock and manual notes
  create durable `staff_memories` observations for Nova, with relative
  timecodes. User can download a plain-text timecode list. The clock does not
  record media, and markers explicitly say footage is not verified.
- **Opt-in spoken alerts**: every 60 seconds while HQ is visible, client
  refreshes the real staff briefing. Newly seen event IDs may be read aloud
  using the browser's local speech synthesis *only* after enabling Voice
  Alerts; the microphone is never enabled for alerts. The default is OFF.
  This is event readout, not model-driven conversation.
- **OBS protocol smoke**: pure client-side v5 authentication and mock WebSocket
  handshake verified, including scene list, stream status and explicit scene
  change request. Node smoke: `node tools/staff_hq_obs_smoke.cjs` passed.
  This is **not** verified against real installed OBS.
- **TS checks**: a narrowed TS project for the new HQ components passed once;
  Electron TypeScript check passed. Subsequent expanded HQ edits passed the
  lightweight esbuild bundle, but latest narrow/full semantic TS check has
  not completed under heavy laptop load and remains a release gate.
- Original existing Staff API smoke with the full `build_app` passed
  `test_staff.py::test_staff_foundation_seeds_maya_and_avatar_catalog`,
  confirming original staff source still mounts.
