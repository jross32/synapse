# Cross-device sync: visual references and release gates

## Approved visual direction
- Midnight-navy surfaces, electric cyan/violet luminous accents, neural-brain/S mark, translucent glass panels, subtle glowing borders and restrained motion.
- Profile is the central account/device hub. Connected-device status must be truthful: distinguish currently verified online from previously registered. Account preferences auto-sync; project files remain local until authenticated file transfer is actually verified.
- Compact, viewport-fitted dashboard; larger interactive neural brain; independent panel scrolling; keyboard/reduced-motion alternatives. Do not replace the separately approved dashboard 3D-brain work.
- Onboarding shows account sync separately from project-file sync and AI remote execution permissions; never imply that enabling preferences copies project source.

## Visual evidence (captured 2026-10-12)
- `data/design-references/device-sync-qa-desktop-20261012.png`: 1280x800 Chromium screenshot of current onboarding UI with simulated laptop+desktop profile response.
- `data/design-references/device-sync-qa-mobile-20261012.png`: 390x844 Chromium screenshot with the same mock response.
- Both registered in `.synapse/image-assets.jsonl` with SHA-256 provenance. These are *implementation screenshots*, not original ChatGPT-generated approved mockups.
- `synapse_get_project_design_references` returned an empty reference list. The original image bytes must be recovered and registered before pixel-accurate mockup comparison can be claimed.

## Release gates (none may be skipped)
1. Two distinct trusted, authorized physical devices signed into the same account. Verify each host's daemon, app, installer, and protocol versions independently.
2. Enrollment with owner approval; key persistence and rotation; revocation; scoped project read/write permission; authenticated encrypted transport; replay and tamper protection.
3. Offline queue, reconnection, retries, interruption/restart, idempotent delivery, integrity checks, and conflict artifacts preserving both versions.
4. Two concurrent AI agents editing same/different files; isolate in Git worktrees; detect stale heartbeats; perform verified merge with real quality gates; promote only after successful tests.
5. Mixed-version clients negotiate capabilities; unsupported schemas degrade safely without silent data loss.
6. Real desktop/laptop round-trip and negative tests. Synthetic directories on one computer are *not* a substitute.
7. Capture real desktop/mobile screenshots, inspect and compare to approved mockups, adjust layout and contrast, test interactions and reduced motion.
8. Package signed release, validate installer/upgrade/rollback and account sync, then publish with explicit owner approval.

## Current verification limitations
- Current connected host: `LAPTOP-GOMKH6MT`. Registered `DESKTOP-NC8N8HC` last reported 2026-10-12T16:31:27Z; registration is not proof of current reachability.
- Focused tests: 26 passed, 1 skipped (Windows symlink creation restrictions). Renderer/Electron TypeScript typecheck passed.
- No live two-machine E2E, authenticated network transfer, key persistence/replay audit, or production deployment verified. No release claim.
