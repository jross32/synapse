# Devices and saved work
Implemented 2026-10-12 in ProfileHub using DevicesSavedWork.tsx and scoped devices-saved-work.css.

The approved dark cyan/violet mockup is implemented as a responsive full-width section in the existing account hub. Native icons, CSS lighting, bordered panels, hover transitions and reduced motion avoid raster assets for controls.

The old portable-sync checkbox and Save button are removed. Opening the signed-in hub enables account preference sync via existing PATCH /profile if needed; errors remain visible and do not block independent host/MCP/service reads. Retry uses the same load path. Existing sign-up already enables preference sync.

Current-device Disconnect/Reconnect uses PATCH /profile/mcp-connections and pauses/restores AI tool access, not data deletion or account preference sync. Remote hosts show last-reported timestamps and previously-connected status; no live-online claim is inferred from profile inventory. Connect a computer explains installing and signing in on the other machine.

Files remain at their existing local/provider locations. No file replication, cloud storage integration, background pending-write recovery or two-device transfer implementation was added by this UI work. Those require separate backend verification. Do not call this a full shared-file synchronization release.

Verification: npm run typecheck (renderer and Electron), npm run build:renderer, scoped git diff --check passed. Isolated Chromium checked live Profile screen, connect help and 390px viewport horizontal overflow (false). Desktop/mobile screenshots in Windows TEMP. Two council reviewers reviewed semantics/accessibility; auto-enable failure isolation fixed. Disconnect was not executed against the real account during browser QA because it would interrupt the current MCP connection.

Changes are in the developer checkout, not a packaged/download-site release. ProfileHub already contained concurrent edits; do not commit the entire pre-existing diff without owner coordination.

## Full-surface follow-up
The account hub now has a full-height dark shell with a neural S brand, separate Devices, Account settings, and Connected apps views. Devices does not display legacy account panels. Other task deep links may open Apps initially; select Devices & saved work in the left navigation. Real desktop/mobile screenshots were inspected and responsive spacing refined. Independent device-result loading and a separate pending flag preserve retry after MCP load failures. Previous same-name registrations remain accessible in history.

Live Chromium verified navigation, help expansion, no horizontal overflow at 1440/1024/390 pixels, and intercepted MCP PATCH disconnect/reconnect UI roundtrip. The mock avoids disabling the live connector. No installer publication or full file-transfer backend is implied.
