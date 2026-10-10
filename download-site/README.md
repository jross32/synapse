# Synapse public download website

Production: https://download.whatapc.com/

The static landing site in this folder is served independently from the private Synapse daemon. It supports desktop, tablet, and small mobile viewports. It currently provides the official Windows v0.1.214 release URL and marks macOS and Linux downloads unavailable until installers are published.

The site is publicly served through the existing Cloudflare route and Python static server. Cache-busting query parameters in index.html ensure the latest CSS and JS are used on public clients.

Local browser smoke test:

    node download-site/smoke-test.cjs

The smoke test checks 1440px desktop, 768px tablet, 390px iPhone-size, and 320px small-iPhone-size layouts, horizontal scrolling, release button link and mobile menu behavior. Native iOS Safari testing still requires an actual iOS/WebKit runner and is not certified by Chromium emulation. The hero currently uses an inline SVG; a generated bitmap artwork transfer to this Windows machine is not yet completed.

To publish a newer installer, update the release link in index.html only once GitHub release availability is verified. Cache-bust CSS/JS when changing those assets. Never imply unsupported macOS/Linux binaries are downloadable. Do not expose private Synapse MCP or daemon endpoints via the download domain.
