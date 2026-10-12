# Synapse public download website

Production: https://download.whatapc.com/

The static landing site in this folder is served independently from the private Synapse daemon. It supports desktop, tablet, and small mobile viewports. It currently provides the official Windows v0.1.217 release URL and marks macOS and Linux downloads unavailable until installers are published.

The site is publicly served through the existing Cloudflare route and Python static server. Cache-busting query parameters in index.html ensure the latest CSS and JS are used on public clients.

Local browser smoke test:

    node download-site/smoke-test.cjs

The smoke test checks 1440px desktop, 768px tablet, 390px iPhone-size, and 320px small-iPhone-size layouts, horizontal scrolling, release button link and mobile menu behavior. Native iOS Safari testing still requires an actual iOS/WebKit runner and is not certified by Chromium emulation. The hero currently uses an inline SVG; a generated bitmap artwork transfer to this Windows machine is not yet completed.

To publish a newer installer, update the release link in index.html only once GitHub release availability is verified. Cache-bust CSS/JS when changing those assets. Never imply unsupported macOS/Linux binaries are downloadable. Do not expose private Synapse MCP or daemon endpoints via the download domain.

Hero animation: The initial message and each of nine alternate messages stays visible for 30 seconds of foreground viewing, then erases at 7 ms/character and retypes at 16 ms/character. The 10-message rotation loops. It pauses when the tab is hidden and stays static for reduced-motion visitors. The original SEO-friendly HTML text remains visible without JavaScript.

    node download-site/hero-animation-test.cjs

## Premium preview and release hygiene (2026-10-11)

The optional premium preview is at https://github.com/jross32/synapse/releases/tag/premium-preview-0.1.209-20261011 and is linked from #premium-preview. It is an unsigned v0.1.209 testing build, NOT a replacement for stable v0.1.217. The preview binary was built from a dirty worktree and is not reproducible from its Git tag alone. Complete clean-install, upgrade/repair, login/device, signing and visual comparison gates before a stable release. Preserve historical releases and document the latest stable vs preview separately.

Site uptime depends on the localhost:8879 static server and Cloudflare tunnel. If the domain returns 502, verify the local server first; the current static server was restarted manually and is not yet guaranteed to restart on boot. The download-site source should gain an explicit managed startup/service definition. The fallback version in app.js is older than the stable release and should be reconciled. Release documentation should include installer SHA-256, provenance, tested OS versions, backup/rollback and known limitations.



## Premium v0.2.219 published preview (2026-10-12)

Public release: https://github.com/jross32/synapse/releases/tag/premium-preview-0.2.219-20261012

- The premium preview is now linked first under Downloads, clearly labeled UNSIGNED / PREVIEW.
- Its primary .exe link uses a permanent GitHub Releases asset (242,652,850 bytes).
- A checksum-matched local site mirror is available at /releases/Synapse-Premium-Setup-0.2.219-preview.exe when the local download server is online.
- The 0.1.217 stable release and its GitHub link remain unchanged; the dynamic stable fallback still filters out prereleases.
- releases.json retains version=0.1.217/channel=stable and documents v0.2.219 under previews with size, SHA-256, source snapshot and verification limitations.
- v0.2.219 source snapshot: https://github.com/jross32/synapse/tree/release/premium-preview-0.2.219-20261012.
- Neither 0.2.219 executable is Authenticode-signed; no clean-PC full install/upgrade/rollback or second-device E2E certification. Do not promote to stable automatically.
- The static server and tunnel are local processes, not durable cloud hosting for the mirror. GitHub is the primary binary host. Do not commit release .exe files into Git.
