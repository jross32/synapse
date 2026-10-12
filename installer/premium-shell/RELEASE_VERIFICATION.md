# Premium installer release candidate — 2026-10-11

## Built and tested
- Current working-tree frontend and Electron source: `npm run typecheck` PASS; `npm run build` PASS.
- Current working-tree Python daemon: `npm run build:daemon` PASS; generated 81,332,521-byte synapse-daemon.exe.
- Rebuilt actual NSIS package from current working tree: `release/Synapse Setup 0.1.209.exe`, 170,409,605 bytes, with signing disabled to work around Windows symlink privilege failure in winCodeSign cache.
- Rebundled this new NSIS payload into `release-premium-shell/Synapse Premium Setup 0.1.209.exe`, 241,947,797 bytes, with manifest SHA256 check.
- Eight-screen Playwright navigation PASS; native failed-install skip gate PASS; packaging gate PASS.
- Added repeatable `installer/premium-shell/build-current-release.ps1` build script (version lock, frontend, daemon, NSIS, payload hash, wrapper, packaging gate).

## Still blocked from production release
- Version metadata remains 0.1.209 while Git tags reach v0.1.217 and daemon context reports 0.1.212. This package includes the CURRENT DIRTY WORKTREE compiled today but is NOT a reconciled versioned Git release. Do not label 0.1.209 as latest.
- Current worktree has 136 changed files and other AI sessions may be editing. Must freeze/commit an approved release revision, assign the next valid version, update root package.json and package-lock.json consistently, then rebuild.
- Unsigned wrapper and NSIS; code-signing required for trusted distribution.
- No isolated clean Windows install, existing-install upgrade, custom install path, repair/uninstall, daemon launch, device registration or secure account E2E. No actual installation executed on user's working computer to avoid damaging active Synapse.
- The premium wrapper is a portable Electron bootstrapper containing NSIS, not a native NSIS visual wizard. Need verify silent /S behavior and all required optional bundles.
- Presence of Synapse.exe after NSIS is checked, but installed file version/content is not yet attested.

Do not publish this candidate as an official release. Preserve existing working installs.
