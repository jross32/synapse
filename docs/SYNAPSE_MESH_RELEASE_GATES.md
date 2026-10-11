# Synapse Mesh 0.1.218 release contract (draft)

**Status:** integration candidate only. Do not publish as stable until every release gate below has passing evidence.

## Product guarantees
1. Every new Windows installation runs a readiness audit and offers default-checked, user-scoped installation of Git, Node.js LTS and Python. Missing winget/package-manager support is reported, never silently claimed successful. Administrator approvals are never bypassed.
2. Each signed-in device has a durable, revocable identity, a nickname, last heartbeat, and machine inventory. The same account sees its own devices only.
3. ChatGPT/Claude MCP commands run on an explicitly chosen computer. If multiple devices are enrolled and no target selected, fail closed. Never redirect destructive work on a heartbeat or timeout.
4. Every online account-owned computer can function as a command runner, app host, file source, or file destination, subject to its capabilities and per-device grants.
5. The account displays each device's local software, projects, storage, and running jobs; secrets and raw source files are never put in account profile sync metadata.
6. Project copying is preview-first, rejects symlinks and overwrites, excludes regenerated dependencies by default, verifies checksums, and is bounded.
7. Cross-device transfers are resumable, authenticated, account-isolated and checksum-verified. Network/direct relay fallback never drops files silently.
8. Project synchronization has explicit conflict handling; it does not blindly sync SQLite databases, Git internals, node_modules or build outputs.
9. Remote install policy is opt-in and scoped to approved tools. UAC/OS protection is not bypassed. Installation, command execution, transfers and device enrollment generate receipts.
10. Hardware-aware placement honors strict target selection, available CPU/RAM/storage/GPU, battery, installed runtimes, and per-project defaults. Offline source files cannot be accessed unless already replicated.
11. Personal project sources and credentials must not ship in the public installer or leak across accounts.

## Implemented in branch
- [x] Stable public v0.1.217 website link preserved.
- [x] Source and SQLite backup from existing laptop.
- [x] Account MCP per-device selection independently exercised on laptop and desktop.
- [x] Fail-closed routing for multiple enrolled devices without selection (cloud code not deployed).
- [x] Local developer tool/disk/RAM/battery inventory endpoint and Profile UI.
- [x] First-run hostname nickname API and Profile onboarding prompt.
- [x] Local registered-project preview/copy with checksum, size limits and no overwrite.
- [x] Installer first-run page for optional user-scoped developer tool installation.
- [x] API/TypeScript selected tests and renderer build.

## Blocking work before stable release
- [ ] Authenticated account-wide remote inventory and project catalog across multiple machines.
- [ ] True encrypted or authenticated resumable file transfer between two running devices, with real 2-PC proof and conflict/rollback tests.
- [ ] Explicit per-job target selection and durable receipts in all AI tool entrypoints (not only account-global default).
- [ ] Hardware-aware scheduling, job moves, per-project pinned machine settings and safe offline fallback.
- [ ] Remote app launch, preview streaming, management and UI on both devices.
- [ ] Cross-device project synchronization with Git strategy, verified transfers and database-safe snapshots.
- [ ] Desktop approval/identity flow for new devices and revocation tests against the Railway service.
- [ ] Full installer clean-install test on a VM or a new PC missing Git/Node/Python, optional tools checked/unchecked, repair, rollback, and uninstall.
- [ ] Windows installer signing/reputation strategy and supply-chain/source artifact audit.
- [ ] E2E browser UI tests on desktop, tablet and mobile plus machine offline/disconnect/rejoin tests.
- [ ] Full Python/TypeScript/Playwright CI and release packaging checks, no skipped blocking tests.
- [ ] New version tag and checksums; publish stable site and confirm actual installer works.

## Release safety
Do not overwrite the official v0.1.217 release with a distinct binary using the same version.
Candidate build version is 0.1.218-rc.1. No production cloud migration or update should be applied until it is reviewed and migration/rollback paths are verified.

## Packaged daemon smoke findings, 2026-10-10
- The isolated v0.1.218-rc.1 daemon started on a dynamically allocated loopback port, returned HTTP 200 from /api/v1/health and the authenticated machine inventory endpoint, and left the live port 7878 untouched.
- Authenticated inventory reported LAPTOP-GOMKH6MT, 9 development-tool entries, and 1 local disk. Fresh smoke SQLite integrity_check returned ok. The isolated test daemon was shut down.
- An intermittent heartbeat error (`sqlite3.OperationalError: cannot commit - no transaction is active`) appeared in the packaged daemon. Audit located a direct shared-connection commit in routes_local_ai.py. That call now uses storage.transaction(); 51 related Python tests passed. Commit fa85bde. This is a candidate fix, not verified elimination of every possible shared-connection race.
- Release candidates built before fa85bde are stale and must not be published; rebuild and repeat smoke tests on the fresh binary.- The PyInstaller onefile daemon creates child processes. Smoke-test cleanup discovered 9 orphaned test processes in the isolated release tree; all 9 were terminated after verifying exact executable and test data path. Live Synapse port 7878 remained healthy. Future smoke harness must stop every matching test child before rebuilding/releasing.