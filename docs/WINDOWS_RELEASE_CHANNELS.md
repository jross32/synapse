# Windows release channels

## Preview (frequent builds)
Use the GitHub Actions **Windows preview installer** workflow from a committed, reviewed release branch. The operator supplies a semantic version matching `package.json`. The workflow builds on a fresh Windows runner, typechecks, runs first-launch unit tests, bundles the Python daemon with PyInstaller, packages an unsigned NSIS installer, calculates SHA-256, and uploads a 30-day Actions artifact.

The `publish` switch is **off by default**. Turning it on creates a GitHub **prerelease** with the installer and checksum, explicitly labeled unsigned. Preview tags include the source commit to avoid replacing existing artifacts. A preview is not promoted automatically to stable, and the public stable download remains unchanged.

## Stable (public default)
Before publishing stable, require reproducible source/version provenance, signed installer where configured, fresh-install and existing-user upgrade/rollback tests, clean packaged onboarding walkthrough, daemon startup and shutdown verification, checksum, and working GitHub asset URL. Publish the installer with the exact filename `Synapse.Setup.<version>.exe` under GitHub tag `v<version>`. Then update `download-site/releases.json`, the HTML fallback, and verify `download-site/smoke-test.cjs` and the live download URL. Never overwrite a prior release asset.

## Concurrent AI development
Developers and AI workers use separate branches/worktrees. A release is built from an immutable commit, not a dirty shared workspace. Coordinate version ownership before cutting a release candidate. Never copy production account data, credentials, or daemon state into build artifacts.

## Current limitation
The new preview workflow is a candidate and must pass its first GitHub-hosted run before relying on it. The bundled app's visual first-launch acceptance and installed-upgrade tests are not included in this CI workflow yet. Unsigned previews are testing builds and may trigger Windows security warnings.
