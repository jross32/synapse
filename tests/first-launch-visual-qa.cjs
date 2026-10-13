const { chromium } = require('playwright');
const fs = require('node:fs');
(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1 });
  const errors = [];
  page.on('pageerror', e => errors.push(e.message));
  await page.goto('http://127.0.0.1:5198/qa-first-launch.html', { waitUntil: 'domcontentloaded', timeout: 20000 });
  await page.locator('.fl-welcome-reference-image').waitFor({timeout: 20000});
  const imageLoaded = await page.locator('.fl-welcome-reference-image').evaluate(el => el.complete && el.naturalWidth === 1536);
  if (!imageLoaded) throw new Error('Exact reference image not loaded');
  fs.mkdirSync('artifacts', { recursive: true });
  await page.screenshot({ path: 'artifacts/first-launch-exact-welcome-desktop.png', fullPage: true });
  await page.getByRole('button', { name: /Get started/i }).first().click();
  await page.getByRole('heading', { name: 'Your Synapse account' }).waitFor();
  await page.screenshot({ path: 'artifacts/first-launch-account-desktop.png', fullPage: true });
  const guest = page.getByRole('button', { name: /Continue locally without an account/i });
  await guest.click();
  await page.getByRole('heading', { name: 'This computer' }).waitFor();
  await page.screenshot({ path: 'artifacts/first-launch-computer-desktop.png', fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({ path: 'artifacts/first-launch-computer-mobile.png', fullPage: true });
  await page.reload({waitUntil:'domcontentloaded'});
  await page.screenshot({ path: 'artifacts/first-launch-resume-mobile.png', fullPage: true });
  console.log(JSON.stringify({ imageLoaded, pageErrors: errors, screenshots: 5, currentHeading: await page.locator('h1').first().textContent() }));
  await browser.close();
  if (errors.length) process.exitCode = 1;
})().catch(e => { console.error(e); process.exitCode = 1; });

