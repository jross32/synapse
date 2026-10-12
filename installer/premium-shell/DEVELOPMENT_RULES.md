# Premium installer integration rules (Synapse)

Before changing installer code, inspect current Synapse repository, existing NSIS packaging, account service, device fleet, running workers, dirty Git files, and release outputs. Reuse existing implementations; do not rebuild them or overwrite concurrent work.

The official Synapse Windows installer remains the existing NSIS build until a new single-file premium setup has a bundled, version-matched Synapse payload; hash and signature verification; no file picker or second interactive wizard; real install failure handling and installed-app checks; secure account onboarding delegated to the existing Synapse account UI; device registration; clean-install, upgrade, uninstall, repair, rollback, and background-daemon verification.

Visual 8-screen shell currently exists but is not the official installer. Existing UI navigation and native failure-gate tests passed; production release-gate.cjs is BLOCKED. Codex attempt on 2026-10-11 failed on local executor, approval and token limits and made no verified functional changes. Do not retry Codex without a specific need. Claude authorization was expired.

Protect the root dirty worktree and existing releases. No production promotion without explicit test evidence.
