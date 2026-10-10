// Browser-backed Connected Brain smoke test against the actual running daemon.
// Usage: node scripts/verify-connected-brain-ui.mjs
// Screenshots and JSON receipt are written under docs/proof/connected-brain.
import { chromium } from 'playwright';
import { mkdir, writeFile } from 'node:fs/promises';
import { join } from 'node:path';

const output = join(process.cwd(), 'docs', 'proof', 'connected-brain');
await mkdir(output, { recursive: true });
const result = { url: 'http://127.0.0.1:7878/', started_at: new Date().toISOString(), checks: [], console_errors: [] };
let browser;

function check(label, passed, detail = '') {
  result.checks.push({ label, passed, detail });
  if (!passed) throw new Error(`${label} failed: ${detail}`);
}

try {
  browser = await chromium.launch({ headless: true, channel: 'chrome' }).catch(() => chromium.launch({ headless: true }));
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1 });
  page.on('pageerror', error => result.console_errors.push(error.message));

  await page.goto(result.url, { waitUntil: 'domcontentloaded', timeout: 30000 });
  await page.getByRole('heading', { name: /Your Connected Brain/i }).waitFor({ timeout: 30000 });
  check('desktop hero renders', await page.getByRole('heading', { name: /Your Connected Brain/i }).isVisible());
  await page.screenshot({ path: join(output, 'home-desktop.png'), fullPage: false });

  await page.getByRole('button', { name: /Downloads & updates/i }).click();
  await page.getByRole('heading', { name: 'Downloads & Updates' }).waitFor({ timeout: 12000 });
  check('Updates navigation', true);
  await page.locator('.synapse-update-card').first().waitFor({ timeout: 15000 });
  check('Three OS release cards', await page.locator('.synapse-update-card').count() === 3);
  await page.screenshot({ path: join(output, 'updates-desktop.png'), fullPage: false });

  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(result.url, { waitUntil: 'domcontentloaded' });
  await page.getByRole('heading', { name: /Your Connected Brain/i }).waitFor({ timeout: 20000 });
  check('mobile hero renders', await page.getByRole('heading', { name: /Your Connected Brain/i }).isVisible());
  const heroOverflow = await page.locator('.synapse-brain-hero').evaluate(el => el.scrollWidth > el.clientWidth + 2);
  check('hero has no horizontal overflow at 390px', !heroOverflow);
  await page.screenshot({ path: join(output, 'home-mobile.png'), fullPage: false });

  check('no uncaught page errors', result.console_errors.length === 0, result.console_errors.join('; '));
  result.status = 'PASS';
} catch (error) {
  result.status = 'FAIL';
  result.error = String(error?.stack ?? error);
} finally {
  if (browser) await browser.close();
  result.finished_at = new Date().toISOString();
  await writeFile(join(output, 'result.json'), JSON.stringify(result, null, 2), 'utf8');
  console.log(JSON.stringify({ status: result.status, checks: result.checks, error: result.error, screenshots: output }));
  if (result.status !== 'PASS') process.exitCode = 1;
}
