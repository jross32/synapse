/**
 * capture-screenshots.js
 * Launches the installer shell in Playwright Chromium and captures
 * all 8 screens at 780×576 (the installer's exact window dimensions).
 *
 * Usage (from installer/premium-shell/):
 *   node scripts/capture-screenshots.js
 *
 * Requires: playwright installed (already in root node_modules or run npm i)
 * Output: screenshots/screen-{1..8}.png
 */

'use strict';

const path = require('path');
const fs   = require('fs');

// Resolve playwright from root node_modules first, then local
let playwright;
try {
  playwright = require(path.resolve(__dirname, '../../../node_modules/playwright'));
} catch {
  playwright = require('playwright');
}

// Start the built-in serve.cjs to host the HTML
const serverModule = require('../serve.cjs');

const BASE_URL   = 'http://127.0.0.1:3457';
const OUT_DIR    = path.join(__dirname, '..', 'screenshots');
const VIEWPORT   = { width: 780, height: 576 };
const SETTLE_MS  = 600; // ms after hash navigation before screenshot

const SCREENS = [
  { id: 1, name: 'welcome',           hash: '#screen-1', waitFor: '.welcome-h1' },
  { id: 2, name: 'install-type',      hash: '#screen-2', waitFor: '.type-grid' },
  { id: 3, name: 'system-check',      hash: '#screen-3', waitFor: '.checks-list',
    // Wait for all 6 checks to resolve — they run sequentially ~340ms apart
    extra: async (page) => {
      await page.waitForTimeout(3200); // 6 checks × ~340ms + buffer
      await page.waitForSelector('.checks-summary:not(.hidden)', { timeout: 4000 }).catch(() => {});
      await page.waitForTimeout(300);
    }
  },
  { id: 4, name: 'install-progress',  hash: '#screen-4', waitFor: '.prog-fill',
    extra: async (page) => { await page.waitForTimeout(800); } // let forceProgressDone render
  },
  { id: 5, name: 'account-signin',    hash: '#screen-5', waitFor: '.auth-form' },
  { id: 6, name: 'completion',        hash: '#screen-6', waitFor: '.success-circle' },
  { id: 7, name: 'whats-new',         hash: '#screen-7', waitFor: '.changelog' },
  { id: 8, name: 'launch',            hash: '#screen-8', waitFor: '.btn-launch' },
];

async function run() {
  // Ensure output directory exists
  fs.mkdirSync(OUT_DIR, { recursive: true });

  const { chromium } = playwright;
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: VIEWPORT });
  const page    = await context.newPage();

  console.log('[screenshots] Capturing 8 installer screens…\n');

  for (const screen of SCREENS) {
    const url = `${BASE_URL}/${screen.hash}`;
    const outFile = path.join(OUT_DIR, `screen-${screen.id}-${screen.name}.png`);

    await page.goto(url, { waitUntil: 'domcontentloaded' });

    // Wait for the anchor element to appear
    await page.waitForSelector(screen.waitFor, { timeout: 5000 }).catch(() => {});
    await page.waitForTimeout(SETTLE_MS);

    // Optional per-screen extra wait
    if (screen.extra) await screen.extra(page);

    await page.screenshot({ path: outFile, fullPage: false });
    console.log(`  ✓  screen-${screen.id} (${screen.name}) → ${path.basename(outFile)}`);
  }

  await browser.close();
  serverModule.close?.();

  console.log(`\n[screenshots] Done → ${OUT_DIR}`);
  process.exit(0);
}

run().catch((err) => {
  console.error('[screenshots] FAILED:', err.message);
  process.exit(1);
});
