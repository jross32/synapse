# Premium installer handoff for next Synapse release

The eight-screen premium installer work is stored in `installer/premium-shell/`.
The main Synapse electron-builder package includes the premium shell assets as `resources/premium-installer-preview` for the next Windows update download. This inclusion preserves the work but **does not** replace the current NSIS installer, nor make the premium shell a functioning account-enabled installer.

The separately packaged preview is at `release-premium-shell/Synapse Premium Setup 0.1.0.exe` on the development PC. It is not a production installer. Do not publish it as the official Synapse setup.

## Release gate (must pass before promoting)
- Integrate the premium screens with the real NSIS installation lifecycle, including actual install status and failures.
- Embed the Synapse payload into one distributable; no second installer selection.
- Connect account sign-in to the actual Synapse auth service, with secure token storage and real error handling.
- Register/nickname devices through the real backend after authentication.
- Verify fresh install, repair, upgrade, uninstall, daemon start, background service continuity, account reconnect and error recovery on Windows.
- Re-run `node installer/premium-shell/release-gate.cjs`; it currently fails intentionally.
- Preserve existing NSIS installer until the unified premium installer passes all gates.

The source folder is included in the normal release package for continuity. The installer executable remains the existing stable NSIS target.
