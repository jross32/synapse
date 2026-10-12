# Unified premium installer verification — 0.2.219

The release snapshot now uses the approved premium eight-screen HTML with one native state machine. Setup never collects credentials; account creation and sign-in happen after launching Synapse.

Verified without installing over an existing application:
- `node test-host-release.cjs`: Windows/architecture, disk, hash, old installed version, missing daemon, NSIS failure and launch failure gates pass.
- `node test-release-provenance.cjs`: version drift, missing receipt, source edits and mismatched payload/daemon are rejected.
- `node test-native-gate.cjs`: real retry, installation navigation lock, failed checks, launch errors and preview-without-false-success pass in Chromium with a mocked native bridge.
- JS syntax checks pass.

Host verifies the installed app.asar package name and exact version plus packaged daemon presence. Launch success means Windows reported process spawn, not that account authentication or daemon startup has completed.

Build sequence: complete all source edits, run `build-provenance.cjs begin`, rebuild frontend/Electron/daemon and NSIS, run `build-provenance.cjs finish`, prepare the payload, build the premium wrapper and run `release-gate.cjs`. `build-current-release.ps1` performs this sequence and disallows stale-daemon reuse. Do not edit build inputs between begin and finish. Build provenance attests source-input digest and fresh daemon/NSIS hashes; it does not substitute for Windows E2E.

Still required before a production-complete claim: actual clean Windows install, existing installation upgrade, custom installation path, uninstall, installed daemon health/version, first-launch sign-up/sign-in, actual second-device account sync and live-download verification. Code signing is a separate distribution property and has not been verified here.

NSIS skips bootstrap-file rewriting when an established profile data directory exists, preserving upgrade choices. Electron applyBootstrapAiBundles and applyBootstrapOptionalTools consume the bootstrap JSON. Actual silent-install bundle defaults and upgrade preservation still require Windows lifecycle verification.

## Launch candidate checkpoint - 2026-10-12

### Verified on connected Windows development machine (without installing over active Synapse)
- Root package, lockfile, premium shell, and payload version all match **0.2.219**.
- npm run typecheck and npm run build (renderer + Electron) PASS.
- 66 targeted Python regression tests PASS (auth, profiles, premium account release, version consistency, release-pipeline authority, restart).
- Premium test-host-release.cjs, test-release-provenance.cjs, and test-native-gate.cjs PASS.
- installer/build-daemon.ps1 now bundles winpty/winpty-agent.exe and rejects a frozen daemon archive missing that file.
- The isolated frozen synapse-daemon.exe --version returns **0.2.219**, and a fresh temporary-data daemon boot returned healthy GET /api/v1/health.
- The same fresh packaged daemon successfully spawned a real WinPTY terminal session and its scrollback contained the expected test echo.
- build-current-release.ps1 has a Windows named mutex to reject concurrent premium release builds; a second-process attempt correctly failed before starting a build.
- Fresh native NSIS payload, daemon, wrapper, and source-build SHA-256 receipts pass release-gate.cjs (provenance only).
- The premium wrapper contains the version-matched NSIS payload, matching its SHA-256 manifest, and the unpacked app/daemon resources are present.
- Built artifacts: release/Synapse Setup 0.2.219.exe and release-premium-shell/Synapse Premium Setup 0.2.219.exe.

### Production publication blockers (must not be silently waived)
- **Neither executable contains an embedded Authenticode certificate table: both are UNSIGNED.** Real trusted code signing remains required for trustworthy public distribution.
- No isolated clean Windows VM/second-PC installer E2E, upgrade, custom path, repair, rollback, uninstall, active daemon and account/device sign-in across machines, or download-site live verification has yet been completed.
- Release source is still in a dirty multi-agent integration worktree rather than a committed/tagged/reviewed immutable release source.
- Source-build provenance is evidence of the specific compiled source snapshot, not a substitute for signing or physical installation testing.
- Do not replace the existing production download or current installed Synapse until these gates have been verified. No live deployment was done by this checkpoint.
