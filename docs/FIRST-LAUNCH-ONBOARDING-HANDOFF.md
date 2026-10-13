# Premium first-launch onboarding â€” isolated frontend implementation

Date: 2026-10-13. Branch: `feat/premium-first-launch-ui-20261013`; worktree: `C:\Users\justi\Synapse-onboarding-ui-20261013`.

## Existing implementation audit
- `AGENTS.md`, `docs/MULTI-AI-WORKFLOW.md`, `PROGRESS.md`, `renderer/App.tsx`, `renderer/lib/api-client.ts`, `renderer/lib/profile-client.ts`, `renderer/components/ProfileHub.tsx`, `renderer/lib/electron-bridge.ts`, `renderer/lib/generated-types.ts` inspected.
- Existing ProfileHub provides real sign-in/signup and provider auth. Profile backend owns encrypted tokens; local daemon token is separate from account credentials.
- Main app boots local runtime auth, then renders dashboard; it did not have a mandatory desktop first-launch gate.
- Existing device-sync UI and device registry are not proof of cloud reachability, remote commands, file transfer, or authenticated MCP connectivity.
- Main worktree contains 282 dirty changes; no main worktree files, live daemon, Reflex or Chrome processes modified.
- Synapse AI context read via connector; `.synapse-ai-context.md` does not exist in the checked-out main repo filesystem.
- Design reference images: `C:\Users\justi\synapse\design-references\onboarding\`.

## Implemented in isolated branch
- Desktop-only first-launch gate in `renderer/App.tsx`, after local runtime auth, before dashboard.
- Six steps: Welcome, Account (signin/signup/social/guest), This computer (local health and truthful account status), AI & MCP (unverified diagnostics and registered device list), Companion (select/skip), Ready (truthful summary).
- Onboarding state saved to localStorage with explicit version, validation, and completion; no passwords or tokens saved in onboarding storage.
- Browser/non-Electron previews and mobile pairing flow are not gated.
- Event hook `window.dispatchEvent(new Event('synapse:restart-onboarding'))` reopens setup, but Settings button remains to be integrated.
- Account and device backend untouched. All cloud and MCP status wording deliberately conservative.

## Remaining backend/integration dependencies
1. Electron-preload first-install identity independent of old app localStorage and developer machine session. Need a per-installation marker stored in Electron userData with explicit migration policy. Current localStorage-only state is a frontend prototype, not a verified fresh-install boundary.
2. Backend session verification: distinguish stored profile identity from currently verified authenticated account session; support safe remembered-session reauth and explicit logout.
3. Device registration API with verified account linkage and cloud reachability status separate from registry membership.
4. Authenticated MCP diagnostics and supported-client connection action; never expose local token.
5. Device name and capabilities exposed by trusted bridge/API, not inferred from browser.
6. Companion preference in Settings and portable preference schema; current selection is local onboarding-only.
7. Settings button for restarting onboarding; do not overwrite concurrent Settings edits.
8. Installer first-launch handoff, upgrade migration, full clean VM testing and release gating.

## QA scope and safety
Run isolated typecheck and state tests; do not launch installer or active desktop UI. Visual verification requires an isolated browser with the UI served from this worktree (not the active desktop). Record evidence and failures before declaring production-ready. No backend connectivity claims without backend verification.

## Actual verification on 2026-10-13
- Frontend TypeScript typecheck in isolated worktree: PASS (exit 0).
- Node onboarding-state tests: 6 passed, 0 failed.
- Isolated Vite/Playwright screenshot attempt: FAILED (page navigation timed out after 15 seconds on port 5199); no visual screenshot evidence obtained, no visual verification claim.
- Clean-install, installer, auth/device backend, MCP client integration, and full regression tests: NOT RUN.
- No running desktop apps, Reflex, Chrome, or Synapse daemon restarted.


## Iteration 2
- Fixed account screen generic Next bypass: deliberate sign-in or guest choice required. Fixed async auth state transition to advance with mode atomically. Added explicit Continue with this account action for verified existing profile session.
- Added canAdvanceWithNext pure state gate and regression test: 7/7 passing.
- Existing design reference files located: design-references/onboarding/synapse-first-launch-welcome-v1.jpeg and synapse-onboarding-eight-screen-storyboard-v1.jpeg; visual parity not yet verified.



## Visual fidelity iteration 3 (2026-10-13)
- User explicitly required the EXACT previously approved welcome image, not a CSS-generated approximation.
- Original `synapse-first-launch-welcome-v1.jpeg` copied byte-for-byte to `renderer/public/onboarding/welcome-reference-v1.jpeg`; SHA256 matches source: 71298AF817E50BA14BA659F46C8FC3B034729A6E0DB514E4A981592CB2E7B921.
- Storyboard reference copied unchanged to `renderer/public/onboarding/storyboard-reference-v1.jpeg`.
- First screen now renders the original artwork directly, with a real accessible Get Started control and setup navigation. Original artwork is not modified.
- Isolated headless Playwright against Vite port 5198: PASS; reference loaded at natural width 1536; no page errors; 5 screenshots saved in `artifacts/` (welcome desktop, account desktop, computer desktop, computer mobile, resumed computer mobile). This is browser visual rendering evidence, not a subjective pixel-diff approval.
- Created Synapse squad `8fbcfe85b7ca` and review work item `9c36c99f38cf`; REST worker launch endpoint unavailable at guessed port 8765, so not claiming worker launched. Claude CLI review job 46a8df8c9a45 was started; result pending at checkpoint.
- No main worktree, installer, active Chrome, Reflex, or daemon changes.

## Iteration 4 — actual browser end-to-end checks
- Guest E2E Playwright test: PASS; account Next disabled until explicit decision, guest flow through computer, MCP, companion Ninja, ready, finish; saved state completed=true, mode=guest, companion=ninja, zero browser errors.
- Offline E2E Playwright test: PASS; aborted /health, displayed daemon unavailable, retry action and interrupted reload resume on computer step; zero browser errors.
- Fixed previously corrupted UTF-8 labels and companion previews. Sign-in now requires returned profile.signed_in=true before advancing.
- Isolated test scripts: tests/first-launch-guest-e2e.cjs and tests/first-launch-failure-e2e.cjs.
- Production readiness still blocked on real backend contracts, secure first-install marker, Settings reset and companion persistence, multi-device reachability verification, and installer E2E. Do not merge without integration review.
