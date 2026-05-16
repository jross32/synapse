'use strict';
/*
 * inspect-electron.js -- attach to a running Electron app's renderer.
 *
 * Electron is Chromium under the hood; launched with --remote-debugging-port
 * it exposes a Chrome DevTools Protocol endpoint. This script connects over
 * CDP (no new browser is spawned -- we drive the *real* app window) so the
 * assistant / CI can screenshot it, read its console, inspect its DOM and
 * click around exactly like a web UI.
 *
 * It is intentionally GENERIC -- it works against any Electron app that was
 * started with a remote-debugging port, not just Synapse. Originally this
 * capability lived in the app-specific "nexus-mcp-server"; it is rebuilt here
 * as a self-contained, app-agnostic script.
 *
 * Synapse enables the CDP port when launched with --inspect-renderer
 * (or SYNAPSE_INSPECT=1). See electron/main.ts.
 *
 * Usage:
 *   node scripts/inspect-electron.js screenshot [outfile.png] [--full]
 *   node scripts/inspect-electron.js console [error|warning|info]
 *   node scripts/inspect-electron.js snapshot           # visible text dump
 *   node scripts/inspect-electron.js html [selector]
 *   node scripts/inspect-electron.js click "<selector-or-text>"
 *   node scripts/inspect-electron.js eval "<js-expression>"
 *   node scripts/inspect-electron.js title
 *
 * Env:
 *   SYNAPSE_INSPECT_PORT   CDP port to attach to (default 9222)
 *   INSPECT_CDP_URL        full CDP base URL (overrides the port)
 */

const path = require('node:path');

let chromium;
try {
  ({ chromium } = require('playwright'));
} catch (err) {
  console.error('inspect-electron: the "playwright" package is not installed.');
  console.error('Run "npm install" in the synapse repo first.');
  process.exit(3);
}

const PORT = process.env.SYNAPSE_INSPECT_PORT || '9222';
const CDP_URL = process.env.INSPECT_CDP_URL || `http://localhost:${PORT}`;

function fail(msg, code = 1) {
  console.error(`inspect-electron: ${msg}`);
  process.exit(code);
}

async function getRendererPage(browser) {
  // Electron exposes one BrowserContext; its first non-devtools page is the
  // app window. Skip about:blank / devtools:// pages defensively.
  const contexts = browser.contexts();
  if (!contexts.length) fail('no browser contexts -- is the Electron app running?');
  for (const ctx of contexts) {
    for (const pg of ctx.pages()) {
      const url = pg.url();
      if (url && !url.startsWith('devtools://')) return pg;
    }
  }
  fail('no renderer page found in the Electron app');
}

async function main() {
  const [, , action = 'screenshot', arg1, arg2] = process.argv;

  let browser;
  try {
    browser = await chromium.connectOverCDP(CDP_URL, { timeout: 10000 });
  } catch (err) {
    fail(
      `could not connect to CDP at ${CDP_URL}.\n` +
        '  Start the app with renderer inspection enabled, e.g.:\n' +
        '    npx electron . --inspect-renderer\n' +
        '  or set SYNAPSE_INSPECT=1 before launching synapse.cmd.',
      2
    );
  }

  try {
    const page = await getRendererPage(browser);

    switch (action) {
      case 'screenshot': {
        const out = arg1 || 'electron-shot.png';
        const fullPage = process.argv.includes('--full');
        await page.screenshot({ path: out, fullPage });
        console.log(`saved screenshot -> ${path.resolve(out)}`);
        break;
      }
      case 'console': {
        // CDP-attached pages only surface console events from the moment we
        // attach, so re-evaluate by reading the page's own buffer if present,
        // otherwise listen for a short window.
        const level = arg1 || 'info';
        const messages = [];
        page.on('console', (msg) => messages.push({ type: msg.type(), text: msg.text() }));
        await page.waitForTimeout(1500);
        const rank = { error: 3, warning: 2, info: 1, debug: 0 };
        const min = rank[level] ?? 1;
        const filtered = messages.filter((m) => (rank[m.type] ?? 1) >= min);
        console.log(JSON.stringify({ count: filtered.length, messages: filtered }, null, 2));
        break;
      }
      case 'snapshot': {
        const text = await page.evaluate(() => document.body.innerText);
        console.log(text);
        break;
      }
      case 'html': {
        const html = arg1
          ? await page.locator(arg1).first().innerHTML()
          : await page.content();
        console.log(html);
        break;
      }
      case 'click': {
        if (!arg1) fail('click requires a selector or visible text argument');
        try {
          await page.locator(arg1).first().click({ timeout: 5000 });
          console.log(`clicked selector: ${arg1}`);
        } catch (_) {
          await page.getByText(arg1, { exact: false }).first().click({ timeout: 5000 });
          console.log(`clicked text: ${arg1}`);
        }
        break;
      }
      case 'eval': {
        if (!arg1) fail('eval requires a JS expression argument');
        const result = await page.evaluate((expr) => {
          // eslint-disable-next-line no-eval
          return eval(expr);
        }, arg1);
        console.log(JSON.stringify(result, null, 2));
        break;
      }
      case 'title': {
        console.log(await page.title());
        console.log(page.url());
        break;
      }
      default:
        fail(`unknown action "${action}". See the header of this file for usage.`);
    }
  } finally {
    // connectOverCDP: closing only detaches our client -- the Electron app
    // keeps running. We never own its process.
    await browser.close().catch(() => {});
  }
}

main().catch((err) => fail(err && err.message ? err.message : String(err)));
