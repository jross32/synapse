# Synapse desktop updates (Windows)

The Electron UI now checks for a newer publisher-signed release on startup and every six hours. The notification can be dismissed for the current session. It never automatically interrupts live apps or workers. The Update button downloads the installer over HTTPS, validates the declared size and SHA-256 digest, then opens it interactively. The user controls when installation proceeds.

## Publisher configuration

The installed application's environment must supply `SYNAPSE_UPDATE_FEED_URL` (HTTPS JSON endpoint) and `SYNAPSE_UPDATE_PUBLIC_KEY` (Ed25519 SPKI PEM). Without both, updater checks are disabled rather than using an untrusted feed. Production release engineering should embed the **public** key and trusted feed URL in an immutable build configuration; private signing keys must remain outside source control.

Example release manifest structure:

```json
{
  "version": "0.1.220",
  "notes": "Release improvements",
  "windows": {
    "url": "https://example.com/releases/Synapse-Setup-0.1.220.exe",
    "sha256": "64 hexadecimal characters",
    "size": 12345678
  },
  "signature": "base64 Ed25519 signature"
}
```

The Ed25519 signature covers the UTF-8 JSON serialization of `{version,notes,windows}` in exactly that field order, with notes defaulting to an empty string. The publisher must sign the same bytes. The installer is staged under `userData/updates/<version>/` and runs only after integrity verification. Windows Authenticode signing of the installer is a separate release requirement before public distribution.

## Service continuity and limitations

**This is a first-stage update path, not a completed zero-downtime migration.** Opening the verified installer does not itself restart Electron or terminate workers. However the current packaged desktop can spawn/own the Python daemon, and the existing `will-quit` handler kills that owned daemon; NSIS installer behavior and cross-device workers have not yet been proven seamless. Do not advertise 'nothing in the background will stop' until daemon ownership is separated into a supervised Windows service, installer lifecycle and rollback are integrated and verified in real install/update tests. The normal `synapse:restart` action also intentionally stops services and must never be used as an updater shortcut.

The updater currently supports Windows installers only and requires a release publication process with key management. Failed signature/hash checks leave the running UI untouched. No automatic installer rollback is implemented; this requires a tested versioned installer/transactional service migration.

## Validation

Run `npm run build:electron`, `npm run build:renderer`, `npm run typecheck` and exercise signed-feed/current-version/corrupt-signature/hash mismatch/install-cancel flows in a packaged Windows test VM before releasing.

## Next packaging gate
Run npm run build:electron, npm run build:renderer, and node scripts/preflight-desktop-updater.cjs before packaging. The preflight is read-only.
Before deployment: embed a trusted HTTPS release feed and Ed25519 public key into the packaged build (current env-based settings are not embedded), Authenticode-sign the installer, publish its signed manifest, and verify install/cancel/tamper/rollback plus live daemon continuity in a disposable Windows VM.
Do not claim zero downtime until daemon ownership and NSIS installer handoff are independently tested. Coordinate a release freeze because the repository contains unrelated concurrent work.
